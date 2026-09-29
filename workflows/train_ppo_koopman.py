from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from isaaclab_app import AppLauncher

import cli_args
from koopman.phase5_2_profiles import (
    ADAPTER_PROFILE_IDS,
    CHANGED_AXIS_IDS,
    MPC_PROFILE_IDS,
    PHASE52_PROFILE_IDS,
    PHASE5_2_PROVENANCE_BY_EVIDENCE_LEVEL,
    PHASE5_2_TRAINING_EVIDENCE_LEVELS,
    adapter_profile_values,
    mpc_profile_values,
    resolve_phase52_profile,
)
from koopman.phase5_3_profiles import (
    PHASE53_PROFILE_IDS,
    PHASE5_3_CHANGED_AXIS_IDS,
    PHASE5_3_COMPARISON_BASELINE,
    PHASE5_3_HEALTH_FLOOR,
    PHASE5_3_PROVENANCE_BY_EVIDENCE_LEVEL,
    PHASE5_3_SENTINEL_EVIDENCE_LEVEL,
    PHASE5_3_TRAINING_EVIDENCE_LEVELS,
    PHASE5_3_TRAINING_LADDER_STAGES,
    resolve_phase53_profile,
)
from koopman.phase5_4_profiles import (
    PHASE54_PROFILE_IDS,
    PHASE5_4_CHANGED_AXIS_IDS,
    PHASE5_4_COMPARISON_BASELINE,
    PHASE5_4_EVIDENCE_LEVELS,
    PHASE5_4_HEALTH_FLOOR,
    PHASE5_4_PROVENANCE_BY_EVIDENCE_LEVEL,
    PHASE5_4_SENTINEL_EVIDENCE_LEVEL,
    PHASE5_4_TRAINING_EVIDENCE_LEVELS,
    PHASE5_4_TRAINING_LADDER_STAGES,
    effective_mpc_values,
    effective_reward_config,
    resolve_phase54_profile,
)


parser = argparse.ArgumentParser(description="Train an EasyUUV PPO/RSL-RL agent inside Koopman-MPC.")
parser.add_argument("--video", action="store_true", default=False, help="Record videos during training.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video in steps.")
parser.add_argument("--video_interval", type=int, default=2000, help="Interval between video recordings in steps.")
parser.add_argument(
    "--disable_fabric", action="store_true", default=False, help="Disable fabric and use USD I/O operations."
)
parser.add_argument("--num_envs", type=int, default=1, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default="EasyUUV-Direct-v1", help="Name of the task.")
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment.")
parser.add_argument("--max_iterations", type=int, default=1, help="RL policy training iterations.")
parser.add_argument("--save_interval", type=int, default=1, help="PPO checkpoint save interval.")
parser.add_argument("--controller_mode", choices=("koopman_mpc",), default="koopman_mpc")
parser.add_argument("--adapter_mode", choices=("heuristic_reference_delta_v0",), default="heuristic_reference_delta_v0")
parser.add_argument("--koopman_backend", choices=("direct_state",), default="direct_state")
parser.add_argument("--koopman_manifest_path", type=str, required=True, help="Selected direct-state Koopman manifest.")
parser.add_argument("--mpc_horizon", type=int, default=5, help="Koopman MPC horizon.")
parser.add_argument("--mpc_timeout_ms", type=float, default=12.0, help="Koopman MPC timeout in milliseconds.")
parser.add_argument("--mpc_delta_pwm_limit", type=float, default=0.35, help="Per-step PWM delta limit.")
parser.add_argument("--mpc_depth_weight", type=float, default=1.0, help="MPC depth tracking weight.")
parser.add_argument("--mpc_attitude_weight", type=float, default=1.0, help="MPC attitude tracking weight.")
parser.add_argument("--mpc_control_weight", type=float, default=0.01, help="MPC control energy weight.")
parser.add_argument("--mpc_smoothness_weight", type=float, default=0.05, help="MPC control smoothness weight.")
parser.add_argument("--adapter_policy_action_limit", type=float, default=1.0, help="Adapter action clip limit.")
parser.add_argument("--adapter_rpy_delta_scale", type=float, default=0.35, help="Adapter roll/pitch/yaw delta scale.")
parser.add_argument("--adapter_depth_delta_scale", type=float, default=0.5, help="Adapter depth delta scale.")
parser.add_argument("--adapter_depth_min", type=float, default=-3.0, help="Minimum adapted depth reference.")
parser.add_argument("--adapter_depth_max", type=float, default=3.0, help="Maximum adapted depth reference.")
parser.add_argument("--result_bucket", type=str, default="retrained_ppo_koopman_mpc")
parser.add_argument(
    "--ppo_evidence_level",
    choices=(
        "retrained_policy_smoke",
        "stability_sentinel",
        "stability_candidate",
        "phase5_2_health_sentinel",
        "phase5_2_health_candidate",
        "phase5_3_cross_sentinel",
        "phase5_3_cross_candidate",
        "phase5_3_cross_extended",
        "phase5_4_pareto_sentinel",
        "phase5_4_pareto_candidate",
        "phase5_4_pareto_refinement",
    ),
    default="retrained_policy_smoke",
)
parser.add_argument("--profile_id", choices=PHASE52_PROFILE_IDS + PHASE53_PROFILE_IDS + PHASE54_PROFILE_IDS, default="baseline_rerun")
parser.add_argument("--reward_profile", type=str, default=None)
parser.add_argument("--adapter_profile", choices=ADAPTER_PROFILE_IDS, default=None)
parser.add_argument("--mpc_profile", choices=MPC_PROFILE_IDS, default=None)
parser.add_argument("--changed_axis", choices=CHANGED_AXIS_IDS + PHASE5_3_CHANGED_AXIS_IDS + PHASE5_4_CHANGED_AXIS_IDS, default=None)
parser.add_argument("--training_ladder_stage", choices=PHASE5_3_TRAINING_LADDER_STAGES + PHASE5_4_TRAINING_LADDER_STAGES, default=None)
parser.add_argument(
    "--source_baseline_manifest",
    type=str,
    default="",
    help="Phase 5.1 or baseline rerun manifest used as the one-factor ablation source.",
)
parser.add_argument(
    "--source_phase5_2_summary_path",
    type=str,
    default="",
    help="Phase 5.2 aggregate summary used as Phase 5.3 comparison evidence.",
)
parser.add_argument(
    "--source_phase5_3_summary_path",
    type=str,
    default="",
    help="Phase 5.3 selection summary used as Phase 5.4 comparison evidence.",
)
parser.add_argument("--phase5_summary_path", type=str, default=None, help="Optional Phase 5 summary path.")
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

if args_cli.video:
    args_cli.enable_cameras = True

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app
print("[EASYUUV][TRAIN-PHASE5] Isaac app started; importing post-app modules", flush=True)

import gymnasium as gym
import torch
from rsl_rl.runners import OnPolicyRunner

from discover_ppo_checkpoints import discover_ppo_checkpoints
from easyuuv_task_registration import register_gym_tasks
from isaaclab_compat import RslRlOnPolicyRunnerCfg, RslRlVecEnvWrapper, get_checkpoint_path, parse_env_cfg
from koopman.policy_adapter import PolicyAdapterConfig
from koopman.ppo_training_adapter import (
    PHASE5_CHECKPOINT_PROVENANCE,
    PHASE5_1_PROVENANCE_BY_EVIDENCE_LEVEL,
    PHASE5_1_TRAINING_EVIDENCE_LEVELS,
    PHASE5_CONTROLLER_PATH,
    PHASE5_EVIDENCE_LEVEL,
    PHASE5_REWARD_PROFILE,
    PHASE5_RESULT_BUCKET,
    Phase5KoopmanReferenceWrapper,
)

try:
    from isaaclab.utils.dict import print_dict
    from isaaclab.utils.io import dump_pickle, dump_yaml
except ImportError:
    from omni.isaac.lab.utils.dict import print_dict
    from omni.isaac.lab.utils.io import dump_pickle, dump_yaml


torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
torch.backends.cudnn.deterministic = False
torch.backends.cudnn.benchmark = False


def _git_output(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def git_commit() -> str | None:
    return _git_output(["rev-parse", "HEAD"])


def git_dirty() -> bool | None:
    status = _git_output(["status", "--short"])
    if status is None:
        return None
    return bool(status.strip())


def parse_env_config(num_envs: int):
    return parse_env_cfg(
        args_cli.task,
        device=getattr(args_cli, "device", "cuda:0"),
        num_envs=num_envs,
        use_fabric=not args_cli.disable_fabric,
    )


def resolve_runtime_profile():
    profile = getattr(args_cli, "_phase_profile", None)
    if profile is None:
        if args_cli.profile_id in PHASE54_PROFILE_IDS:
            profile = resolve_phase54_profile(
                profile_id=args_cli.profile_id,
                reward_profile=args_cli.reward_profile,
                adapter_profile=args_cli.adapter_profile,
                mpc_profile=args_cli.mpc_profile,
                changed_axis=args_cli.changed_axis,
            )
        elif args_cli.profile_id in PHASE53_PROFILE_IDS:
            profile = resolve_phase53_profile(
                profile_id=args_cli.profile_id,
                reward_profile=args_cli.reward_profile,
                adapter_profile=args_cli.adapter_profile,
                mpc_profile=args_cli.mpc_profile,
                changed_axis=args_cli.changed_axis,
            )
        else:
            profile = resolve_phase52_profile(
                profile_id=args_cli.profile_id,
                reward_profile=args_cli.reward_profile,
                adapter_profile=args_cli.adapter_profile,
                mpc_profile=args_cli.mpc_profile,
                changed_axis=args_cli.changed_axis,
            )
        args_cli._phase_profile = profile
    return profile


def phase5_4_training_ladder_stage() -> str | None:
    if args_cli.ppo_evidence_level not in PHASE5_4_TRAINING_EVIDENCE_LEVELS:
        return args_cli.training_ladder_stage
    if args_cli.training_ladder_stage is None:
        raise ValueError("Phase 5.4 training requires --training_ladder_stage")
    expected_by_evidence = {
        "phase5_4_pareto_sentinel": "sentinel",
        "phase5_4_pareto_candidate": "candidate",
        "phase5_4_pareto_refinement": "refinement",
    }
    expected = expected_by_evidence[args_cli.ppo_evidence_level]
    if args_cli.training_ladder_stage != expected:
        raise ValueError(
            f"training_ladder_stage must be {expected!r} for {args_cli.ppo_evidence_level!r}, "
            f"got {args_cli.training_ladder_stage!r}"
        )
    return args_cli.training_ladder_stage


def phase5_3_training_ladder_stage() -> str | None:
    if args_cli.ppo_evidence_level not in PHASE5_3_TRAINING_EVIDENCE_LEVELS:
        return args_cli.training_ladder_stage
    if args_cli.training_ladder_stage is None:
        raise ValueError("Phase 5.3 training requires --training_ladder_stage")
    expected_by_evidence = {
        "phase5_3_cross_sentinel": "sentinel",
        "phase5_3_cross_candidate": "candidate",
        "phase5_3_cross_extended": "extended",
    }
    expected = expected_by_evidence[args_cli.ppo_evidence_level]
    if args_cli.training_ladder_stage != expected:
        raise ValueError(
            f"training_ladder_stage must be {expected!r} for {args_cli.ppo_evidence_level!r}, "
            f"got {args_cli.training_ladder_stage!r}"
        )
    return args_cli.training_ladder_stage


def training_ladder_stage() -> str | None:
    if args_cli.ppo_evidence_level in PHASE5_4_TRAINING_EVIDENCE_LEVELS:
        return phase5_4_training_ladder_stage()
    if args_cli.ppo_evidence_level in PHASE5_3_TRAINING_EVIDENCE_LEVELS:
        return phase5_3_training_ladder_stage()
    return args_cli.training_ladder_stage


def configure_phase5_env(env_cfg) -> None:
    if args_cli.num_envs != 1:
        raise ValueError("Phase 5 first smoke requires --num_envs 1 until vectorized adapter tests exist")
    if args_cli.result_bucket != PHASE5_RESULT_BUCKET:
        raise ValueError(f"result_bucket must be {PHASE5_RESULT_BUCKET!r}")
    allowed_evidence_levels = (
        (PHASE5_EVIDENCE_LEVEL,)
        + PHASE5_1_TRAINING_EVIDENCE_LEVELS
        + PHASE5_2_TRAINING_EVIDENCE_LEVELS
        + PHASE5_3_TRAINING_EVIDENCE_LEVELS
        + PHASE5_4_TRAINING_EVIDENCE_LEVELS
    )
    if args_cli.ppo_evidence_level not in allowed_evidence_levels:
        raise ValueError(f"ppo_evidence_level must be one of {list(allowed_evidence_levels)}")
    profile = resolve_runtime_profile()
    if args_cli.ppo_evidence_level in PHASE5_2_TRAINING_EVIDENCE_LEVELS and not args_cli.source_baseline_manifest.strip():
        raise ValueError("Phase 5.2 training requires --source_baseline_manifest")
    if args_cli.profile_id in PHASE52_PROFILE_IDS and args_cli.ppo_evidence_level not in PHASE5_2_TRAINING_EVIDENCE_LEVELS and profile.profile_id != "baseline_rerun":
        raise ValueError("Non-baseline Phase 5.2 profiles require a Phase 5.2 ppo_evidence_level")
    if args_cli.profile_id in PHASE53_PROFILE_IDS:
        if args_cli.ppo_evidence_level not in PHASE5_3_TRAINING_EVIDENCE_LEVELS:
            raise ValueError("Phase 5.3 cross profiles require a Phase 5.3 ppo_evidence_level")
        if not args_cli.source_phase5_2_summary_path.strip():
            raise ValueError("Phase 5.3 training requires --source_phase5_2_summary_path")
        phase5_3_training_ladder_stage()
    if args_cli.profile_id in PHASE54_PROFILE_IDS:
        if args_cli.ppo_evidence_level not in PHASE5_4_TRAINING_EVIDENCE_LEVELS:
            raise ValueError("Phase 5.4 Pareto profiles require a Phase 5.4 ppo_evidence_level")
        if not args_cli.source_phase5_2_summary_path.strip():
            raise ValueError("Phase 5.4 training requires --source_phase5_2_summary_path")
        if not args_cli.source_phase5_3_summary_path.strip():
            raise ValueError("Phase 5.4 training requires --source_phase5_3_summary_path")
        phase5_4_training_ladder_stage()

    env_cfg.controller_mode = "koopman_mpc"
    env_cfg.control_method = "Ssurface"
    env_cfg.reward_profile = profile.reward_profile
    env_cfg.koopman_manifest_path = args_cli.koopman_manifest_path
    if args_cli.profile_id in PHASE54_PROFILE_IDS:
        reward_config = effective_reward_config(profile)
        env_cfg.phase5_2_w_fallback = reward_config.w_fallback
        env_cfg.phase5_2_w_pwm_sat = reward_config.w_pwm_sat
        env_cfg.phase5_2_w_action = reward_config.w_action
        env_cfg.phase5_2_w_delta_action = reward_config.w_delta_action
        env_cfg.phase5_2_w_latency = reward_config.w_latency
        env_cfg.phase5_2_pwm_soft_limit = reward_config.pwm_soft_limit
        env_cfg.phase5_2_latency_ref_ms = reward_config.latency_ref_ms
        env_cfg.phase5_2_latency_clip = reward_config.latency_clip
        mpc_values = effective_mpc_values(profile)
        env_cfg.mpc_horizon = mpc_values.horizon
        env_cfg.mpc_timeout_ms = mpc_values.timeout_ms
    else:
        mpc_values = mpc_profile_values(profile.mpc_profile)
        env_cfg.mpc_horizon = args_cli.mpc_horizon
        env_cfg.mpc_timeout_ms = args_cli.mpc_timeout_ms
    env_cfg.mpc_delta_pwm_limit = mpc_values.delta_pwm_limit
    env_cfg.mpc_depth_weight = mpc_values.depth_weight
    env_cfg.mpc_attitude_weight = mpc_values.attitude_weight
    env_cfg.mpc_control_weight = mpc_values.control_weight
    env_cfg.mpc_smoothness_weight = mpc_values.smoothness_weight


def build_adapter_config() -> PolicyAdapterConfig:
    adapter_values = adapter_profile_values(resolve_runtime_profile().adapter_profile)
    return PolicyAdapterConfig(
        policy_action_limit=adapter_values.policy_action_limit,
        rpy_delta_scale=(
            adapter_values.rpy_delta_scale,
            adapter_values.rpy_delta_scale,
            adapter_values.rpy_delta_scale,
        ),
        depth_delta_scale=adapter_values.depth_delta_scale,
        depth_bounds=(adapter_values.depth_min, adapter_values.depth_max),
    )


def write_phase5_training_summary(
    log_dir: str,
    agent_cfg: RslRlOnPolicyRunnerCfg,
    phase5_env: Phase5KoopmanReferenceWrapper,
) -> None:
    discovery = discover_ppo_checkpoints([log_dir])
    selected_checkpoint = discovery.get("selected_checkpoint")
    source_checkpoint_mtime = None
    if selected_checkpoint:
        source_checkpoint_mtime = Path(selected_checkpoint).stat().st_mtime
    dirty_state = git_dirty()
    checkpoint_provenance = PHASE5_1_PROVENANCE_BY_EVIDENCE_LEVEL.get(
        args_cli.ppo_evidence_level,
        PHASE5_CHECKPOINT_PROVENANCE,
    )
    if args_cli.ppo_evidence_level in PHASE5_2_TRAINING_EVIDENCE_LEVELS:
        checkpoint_provenance = PHASE5_2_PROVENANCE_BY_EVIDENCE_LEVEL[args_cli.ppo_evidence_level]
    if args_cli.ppo_evidence_level in PHASE5_3_TRAINING_EVIDENCE_LEVELS:
        checkpoint_provenance = PHASE5_3_PROVENANCE_BY_EVIDENCE_LEVEL[args_cli.ppo_evidence_level]
    if args_cli.ppo_evidence_level in PHASE5_4_TRAINING_EVIDENCE_LEVELS:
        checkpoint_provenance = PHASE5_4_PROVENANCE_BY_EVIDENCE_LEVEL[args_cli.ppo_evidence_level]
    profile = resolve_runtime_profile()
    adapter_values = adapter_profile_values(profile.adapter_profile)
    if args_cli.profile_id in PHASE54_PROFILE_IDS:
        mpc_values = effective_mpc_values(profile)
        reward_config = effective_reward_config(profile)
    else:
        mpc_values = mpc_profile_values(profile.mpc_profile)
        reward_config = None
    if (
        args_cli.ppo_evidence_level == "stability_sentinel"
        or args_cli.ppo_evidence_level == "phase5_2_health_sentinel"
        or args_cli.ppo_evidence_level == PHASE5_3_SENTINEL_EVIDENCE_LEVEL
        or args_cli.ppo_evidence_level == PHASE5_4_SENTINEL_EVIDENCE_LEVEL
    ):
        selected_weight_status = "sentinel_only"
    elif args_cli.ppo_evidence_level in (
        PHASE5_1_TRAINING_EVIDENCE_LEVELS
        + PHASE5_2_TRAINING_EVIDENCE_LEVELS
        + PHASE5_3_TRAINING_EVIDENCE_LEVELS
        + PHASE5_4_TRAINING_EVIDENCE_LEVELS
    ):
        selected_weight_status = "candidate_only"
    else:
        selected_weight_status = "smoke_only"

    summary = {
        "checkpoint_found": bool(discovery.get("checkpoint_found")),
        "checkpoint_path": selected_checkpoint,
        "selected_checkpoint": selected_checkpoint,
        "selected_rule": discovery.get("selected_rule"),
        "checkpoint_provenance": checkpoint_provenance,
        "training_iterations": agent_cfg.max_iterations,
        "save_interval": agent_cfg.save_interval,
        "num_envs": args_cli.num_envs,
        "result_bucket": args_cli.result_bucket,
        "ppo_evidence_level": args_cli.ppo_evidence_level,
        "profile_id": profile.profile_id,
        "reward_profile": profile.reward_profile,
        "adapter_profile": profile.adapter_profile,
        "mpc_profile": profile.mpc_profile,
        "changed_axis": profile.changed_axis,
        "source_baseline_manifest": args_cli.source_baseline_manifest,
        "phase5_2_profile_contract_valid": True,
        "phase5_3_profile_contract_valid": args_cli.profile_id in PHASE53_PROFILE_IDS,
        "phase5_4_profile_contract_valid": args_cli.profile_id in PHASE54_PROFILE_IDS,
        "phase5_4_track": getattr(profile, "track", "not_applicable"),
        "sweep_round": getattr(profile, "sweep_round", "not_applicable"),
        "parent_profile_id": getattr(profile, "parent_profile_id", "not_applicable"),
        "parameter_distance_from_parent": getattr(profile, "parameter_distance_from_parent", 0.0),
        "changed_parameter_count": getattr(profile, "changed_parameter_count", 0),
        "parameter_step_count": getattr(profile, "parameter_step_count", {}),
        "protected_strengths": list(getattr(profile, "protected_strengths", ())),
        "nearest_smaller_candidate_id": getattr(profile, "nearest_smaller_candidate_id", None),
        "reward_overrides": getattr(profile, "reward_overrides", {}),
        "mpc_overrides": getattr(profile, "mpc_overrides", {}),
        "risk_level": getattr(profile, "risk_level", "not_applicable"),
        "sentinel_required": bool(getattr(profile, "sentinel_required", False)),
        "candidate_requires_review": bool(getattr(profile, "candidate_requires_review", False)),
        "training_ladder_stage": training_ladder_stage() or "not_applicable",
        "comparison_baseline": (
            PHASE5_4_COMPARISON_BASELINE
            if args_cli.profile_id in PHASE54_PROFILE_IDS
            else PHASE5_3_COMPARISON_BASELINE
            if args_cli.profile_id in PHASE53_PROFILE_IDS
            else "not_applicable"
        ),
        "health_floor": (
            PHASE5_4_HEALTH_FLOOR
            if args_cli.profile_id in PHASE54_PROFILE_IDS
            else PHASE5_3_HEALTH_FLOOR
            if args_cli.profile_id in PHASE53_PROFILE_IDS
            else "not_applicable"
        ),
        "source_phase5_2_summary_path": args_cli.source_phase5_2_summary_path,
        "source_phase5_3_summary_path": args_cli.source_phase5_3_summary_path,
        "adapter_profile_values": {
            "policy_action_limit": adapter_values.policy_action_limit,
            "rpy_delta_scale": adapter_values.rpy_delta_scale,
            "depth_delta_scale": adapter_values.depth_delta_scale,
            "depth_min": adapter_values.depth_min,
            "depth_max": adapter_values.depth_max,
        },
        "mpc_profile_values": {
            "horizon": getattr(mpc_values, "horizon", args_cli.mpc_horizon),
            "timeout_ms": getattr(mpc_values, "timeout_ms", args_cli.mpc_timeout_ms),
            "delta_pwm_limit": mpc_values.delta_pwm_limit,
            "depth_weight": mpc_values.depth_weight,
            "attitude_weight": mpc_values.attitude_weight,
            "control_weight": mpc_values.control_weight,
            "smoothness_weight": mpc_values.smoothness_weight,
        },
        "reward_profile_values": {
            "w_fallback": reward_config.w_fallback if reward_config else "default",
            "w_pwm_sat": reward_config.w_pwm_sat if reward_config else "default",
            "w_action": reward_config.w_action if reward_config else "default",
            "w_delta_action": reward_config.w_delta_action if reward_config else "default",
            "w_latency": reward_config.w_latency if reward_config else "default",
        },
        "controller_path": PHASE5_CONTROLLER_PATH,
        "adapter_mode": args_cli.adapter_mode,
        "koopman_backend": args_cli.koopman_backend,
        "koopman_manifest_path": args_cli.koopman_manifest_path,
        "observation_dim": 9,
        "action_dim": 4,
        "pwm_dim": 8,
        "log_dir": log_dir,
        "source_git_commit": git_commit() or "unknown",
        "source_git_dirty": True if dirty_state is None else dirty_state,
        "source_checkpoint_mtime": source_checkpoint_mtime,
        "training_loop_fallback_rate": "unavailable",
        "training_loop_latency_ms_mean": "unavailable",
        "training_loop_latency_ms_max": "unavailable",
        "training_loop_pwm_min": "unavailable",
        "training_loop_pwm_max": "unavailable",
        "nonfinite_observation_count": 0,
        "nonfinite_action_count": 0,
        "nonfinite_reward_count": 0,
        "episode_reward_mean_start": "unavailable",
        "episode_reward_mean_end": "unavailable",
        "episode_reward_nan_count": 0,
        "training_reference_source": "env_goal_quat_plus_zero_depth",
        "training_goal_distribution": "single_env_easyuuv_default_goal_distribution",
        "training_latency_warning_threshold_ms": 20.0,
        "control_loop_budget_ms": "unavailable",
        "latency_budget_violation_rate": "unavailable",
        "selected_weight_status": selected_weight_status,
        "completion_status": "completed",
        "allowed_claims": [
            "RSL-RL PPO can train inside the Koopman-MPC closed-loop path",
            "A retrained checkpoint can be generated and loaded for smoke evaluation",
        ],
        "disallowed_claims": [
            "PPO convergence is proven",
            "PPO+Koopman-MPC superiority is proven",
            "old PPO semantics are losslessly migrated",
        ],
    }
    summary.update(phase5_env.phase5_summary_fields())
    summary_path = args_cli.phase5_summary_path or os.path.join(log_dir, "phase5_training_summary.json")
    os.makedirs(os.path.dirname(os.path.abspath(summary_path)), exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)
    print(f"[INFO]: Wrote Phase 5 training summary to: {summary_path}")


def main() -> None:
    # controller_mode=koopman_mpc alone is not enough; Phase5KoopmanReferenceWrapper owns the adapter step gate.
    print("[EASYUUV][TRAIN-PHASE5] Entering main()", flush=True)
    register_gym_tasks()
    env_cfg = parse_env_config(args_cli.num_envs)
    configure_phase5_env(env_cfg)
    agent_cfg: RslRlOnPolicyRunnerCfg = cli_args.parse_rsl_rl_cfg(args_cli.task, args_cli)

    agent_cfg.experiment_name = args_cli.experiment_name or "easyuuv_koopman_mpc"
    agent_cfg.max_iterations = args_cli.max_iterations
    agent_cfg.save_interval = args_cli.save_interval

    log_root_path = os.path.abspath(os.path.join("logs", "rsl_rl", agent_cfg.experiment_name))
    print(f"[INFO] Logging experiment in directory: {log_root_path}")
    log_dir = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if agent_cfg.run_name:
        log_dir += f"_{agent_cfg.run_name}"
    log_dir = os.path.join(log_root_path, log_dir)

    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)
    if args_cli.video:
        video_kwargs = {
            "video_folder": os.path.join(log_dir, "videos"),
            "step_trigger": lambda step: step % args_cli.video_interval == 0,
            "video_length": args_cli.video_length,
            "disable_logger": True,
        }
        print("[INFO] Recording videos during training.")
        print_dict(video_kwargs, nesting=4)
        env = gym.wrappers.RecordVideo(env, **video_kwargs)

    phase5_env = Phase5KoopmanReferenceWrapper(
        env,
        adapter_config=build_adapter_config(),
        ppo_evidence_level=args_cli.ppo_evidence_level,
    )
    env = RslRlVecEnvWrapper(phase5_env)
    runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=log_dir, device=agent_cfg.device)
    runner.add_git_repo_to_log(__file__)

    if agent_cfg.resume:
        resume_path = get_checkpoint_path(log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint)
        print(f"[INFO]: Loading model checkpoint from: {resume_path}")
        runner.load(resume_path)

    env.seed(agent_cfg.seed)

    dump_yaml(os.path.join(log_dir, "params", "env.yaml"), env_cfg)
    dump_yaml(os.path.join(log_dir, "params", "agent.yaml"), agent_cfg)
    dump_pickle(os.path.join(log_dir, "params", "env.pkl"), env_cfg)
    dump_pickle(os.path.join(log_dir, "params", "agent.pkl"), agent_cfg)

    runner.learn(num_learning_iterations=agent_cfg.max_iterations, init_at_random_ep_len=True)
    write_phase5_training_summary(log_dir, agent_cfg, phase5_env)
    env.close()


if __name__ == "__main__":
    print("[EASYUUV][TRAIN-PHASE5] __main__ guard reached", flush=True)
    try:
        main()
    except BaseException:
        print("[EASYUUV][TRAIN-PHASE5] Unhandled exception follows", flush=True)
        traceback.print_exc()
        raise
    finally:
        simulation_app.close()
else:
    print(f"[EASYUUV][TRAIN-PHASE5] Loaded without __main__; __name__={__name__}", flush=True)

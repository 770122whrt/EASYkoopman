import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


def log_stage(message: str) -> None:
    print(f"[EASYUUV] {message}", flush=True)


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from isaaclab_app import AppLauncher

import cli_args
from discover_ppo_checkpoints import discover_ppo_checkpoints
from koopman.phase5_2_profiles import (
    ADAPTER_PROFILE_IDS,
    CHANGED_AXIS_IDS,
    MPC_PROFILE_IDS,
    PHASE52_PROFILE_IDS,
    PHASE5_2_MATCHED_EVIDENCE_LEVEL,
    adapter_profile_values,
    mpc_profile_values,
    resolve_phase52_profile,
)
from koopman.phase5_3_profiles import (
    PHASE53_PROFILE_IDS,
    PHASE5_3_CHANGED_AXIS_IDS,
    PHASE5_3_MATCHED_EVIDENCE_LEVEL,
    resolve_phase53_profile,
)
from koopman.phase5_4_profiles import (
    PHASE54_PROFILE_IDS,
    PHASE5_4_CHANGED_AXIS_IDS,
    PHASE5_4_MATCHED_EVIDENCE_LEVEL,
    effective_mpc_values,
    effective_reward_config,
    resolve_phase54_profile,
)
from validate_phase5_1_checkpoint_provenance import validate_phase5_1_checkpoint_provenance
from validate_phase5_2_checkpoint_provenance import validate_phase5_2_checkpoint_provenance
from validate_phase5_3_checkpoint_provenance import validate_phase5_3_checkpoint_provenance
from validate_phase5_4_checkpoint_provenance import validate_phase5_4_checkpoint_provenance
from validate_phase5_checkpoint_provenance import validate_phase5_checkpoint_provenance


parser = argparse.ArgumentParser(description="Run PPO/RL through a guarded Koopman MPC reference adapter.")
parser.add_argument(
    "--disable_fabric", action="store_true", default=False, help="Disable fabric and use USD I/O operations."
)
parser.add_argument("--num_envs", type=int, default=1, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default="EasyUUV-Direct-v1", help="Name of the task.")
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment.")
parser.add_argument("--eval_name", type=str, default="eval_ppo_koopman", help="Name of the eval run.")
parser.add_argument("--ppo_koopman_log_path", type=str, default=None, help="Path for PPO/Koopman JSONL logging.")
parser.add_argument("--steps_per_action", type=int, default=50, help="Steps to hold each target reference.")
parser.add_argument("--max_goals", type=int, default=None, help="Limit target goals for short smoke tests.")
parser.add_argument(
    "--trajectory_type",
    choices=("step", "sine", "irregular"),
    default="step",
    help="Reference trajectory family.",
)
parser.add_argument("--trajectory_cycles", type=int, default=1, help="Repeat the trajectory goal list this many times.")
parser.add_argument(
    "--policy_mode",
    choices=("stub", "checkpoint", "training_smoke"),
    default="stub",
    help="Policy source for the PPO/Koopman adapter smoke.",
)
parser.add_argument(
    "--allow_stub_fallback",
    action="store_true",
    default=False,
    help="Fall back to the deterministic stub policy when checkpoint mode has no checkpoint.",
)
parser.add_argument(
    "--controller_mode",
    choices=("koopman_mpc",),
    default="koopman_mpc",
    help="Controller mode to use inside EasyUUVEnv.",
)
parser.add_argument("--koopman_manifest_path", type=str, default="", help="Selected direct-state Koopman manifest path.")
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
parser.add_argument("--result_bucket", type=str, default=None, help="Evidence result bucket label.")
parser.add_argument("--profile_id", choices=PHASE52_PROFILE_IDS + PHASE53_PROFILE_IDS + PHASE54_PROFILE_IDS, default="baseline_rerun")
parser.add_argument("--reward_profile", type=str, default=None)
parser.add_argument("--adapter_profile", choices=ADAPTER_PROFILE_IDS, default=None)
parser.add_argument("--mpc_profile", choices=MPC_PROFILE_IDS, default=None)
parser.add_argument("--changed_axis", choices=CHANGED_AXIS_IDS + PHASE5_3_CHANGED_AXIS_IDS + PHASE5_4_CHANGED_AXIS_IDS, default=None)
parser.add_argument(
    "--ppo_evidence_level",
    choices=(
        "stub_only",
        "checkpoint_smoke",
        "training_entrypoint_only",
        "retrained_policy_smoke",
        "stability_sentinel",
        "stability_candidate",
        "matched_stability_eval",
        "phase5_2_health_sentinel",
        "phase5_2_health_candidate",
        "phase5_2_matched_eval",
        "phase5_3_cross_sentinel",
        "phase5_3_cross_candidate",
        "phase5_3_cross_extended",
        "phase5_3_cross_matched_eval",
        "phase5_4_pareto_sentinel",
        "phase5_4_pareto_candidate",
        "phase5_4_pareto_refinement",
        "phase5_4_pareto_matched_eval",
    ),
    default=None,
    help="Evidence label. retrained/matched evidence requires checkpoint provenance.",
)
parser.add_argument(
    "--source_training_summary_path",
    type=str,
    default=None,
    help="Phase 5 training summary JSON used to validate retrained checkpoint provenance.",
)

cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()


def preflight_policy_mode(args_cli):
    if args_cli.policy_mode == "stub":
        return None, {"checkpoint_found": False, "paths": []}
    if args_cli.policy_mode == "training_smoke":
        print(
            "training_smoke is a training-entrypoint verification path. Run workflows/train.py with a small "
            "--max_iterations value, then rerun this workflow with --policy_mode checkpoint.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if args_cli.play_checkpoint:
        checkpoint_path = args_cli.play_checkpoint
        return checkpoint_path, discover_ppo_checkpoints(explicit_checkpoint=checkpoint_path)

    discovery = discover_ppo_checkpoints()
    if discovery["selected_checkpoint"]:
        return discovery["selected_checkpoint"], discovery
    if args_cli.allow_stub_fallback:
        return None, discovery
    print(
        "No PPO checkpoint found before Isaac app startup. Use --policy_mode stub, pass --play_checkpoint, "
        "or add --allow_stub_fallback.",
        file=sys.stderr,
    )
    raise SystemExit(2)


PREFLIGHT_CHECKPOINT_PATH, PREFLIGHT_CHECKPOINT_INFO = preflight_policy_mode(args_cli)


def resolve_preflight_evidence_level(args_cli, checkpoint_path: str | None) -> str:
    if args_cli.ppo_evidence_level is not None:
        return args_cli.ppo_evidence_level
    if args_cli.result_bucket == "retrained_ppo_koopman_mpc":
        return "retrained_policy_smoke"
    if args_cli.policy_mode == "stub" or checkpoint_path is None:
        return "stub_only"
    return "checkpoint_smoke"


def preflight_phase5_provenance(args_cli, checkpoint_path: str | None) -> dict:
    evidence_level = resolve_preflight_evidence_level(args_cli, checkpoint_path)
    args_cli._resolved_ppo_evidence_level = evidence_level
    wants_retrained_bucket = args_cli.result_bucket == "retrained_ppo_koopman_mpc"
    wants_phase5_smoke_evidence = evidence_level == "retrained_policy_smoke"
    wants_phase5_1_matched_evidence = evidence_level == "matched_stability_eval"
    wants_phase5_2_matched_evidence = evidence_level == PHASE5_2_MATCHED_EVIDENCE_LEVEL
    wants_phase5_3_matched_evidence = evidence_level == PHASE5_3_MATCHED_EVIDENCE_LEVEL
    wants_phase5_4_matched_evidence = evidence_level == PHASE5_4_MATCHED_EVIDENCE_LEVEL
    wants_guarded_retrained_evidence = (
        wants_phase5_smoke_evidence
        or wants_phase5_1_matched_evidence
        or wants_phase5_2_matched_evidence
        or wants_phase5_3_matched_evidence
        or wants_phase5_4_matched_evidence
    )

    if wants_retrained_bucket and not wants_guarded_retrained_evidence:
        print(
            "result_bucket=retrained_ppo_koopman_mpc requires --ppo_evidence_level retrained_policy_smoke "
            "or matched_stability_eval or phase5_2_matched_eval or phase5_3_cross_matched_eval "
            "or phase5_4_pareto_matched_eval.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if wants_guarded_retrained_evidence and not wants_retrained_bucket:
        print(
            "retrained PPO evidence requires --result_bucket retrained_ppo_koopman_mpc.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if not wants_guarded_retrained_evidence:
        return {"checkpoint_provenance_valid": False}

    if args_cli.policy_mode != "checkpoint" or checkpoint_path is None:
        print("retrained PPO evidence requires --policy_mode checkpoint and a selected checkpoint.", file=sys.stderr)
        raise SystemExit(2)
    if not args_cli.source_training_summary_path:
        print("retrained PPO evidence requires --source_training_summary_path.", file=sys.stderr)
        raise SystemExit(2)
    try:
        if wants_phase5_1_matched_evidence:
            return validate_phase5_1_checkpoint_provenance(
                checkpoint_path,
                args_cli.source_training_summary_path,
                expected_evidence_level="matched_stability_eval",
            )
        if wants_phase5_2_matched_evidence:
            return validate_phase5_2_checkpoint_provenance(
                checkpoint_path,
                args_cli.source_training_summary_path,
                expected_evidence_level=PHASE5_2_MATCHED_EVIDENCE_LEVEL,
            )
        if wants_phase5_3_matched_evidence:
            return validate_phase5_3_checkpoint_provenance(
                checkpoint_path,
                args_cli.source_training_summary_path,
                expected_evidence_level=PHASE5_3_MATCHED_EVIDENCE_LEVEL,
            )
        if wants_phase5_4_matched_evidence:
            return validate_phase5_4_checkpoint_provenance(
                checkpoint_path,
                args_cli.source_training_summary_path,
                expected_evidence_level=PHASE5_4_MATCHED_EVIDENCE_LEVEL,
            )
        return validate_phase5_checkpoint_provenance(checkpoint_path, args_cli.source_training_summary_path)
    except ValueError as exc:
        print(f"Checkpoint provenance failed before Isaac startup: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


PREFLIGHT_PHASE5_PROVENANCE_INFO = preflight_phase5_provenance(args_cli, PREFLIGHT_CHECKPOINT_PATH)


def resolve_eval_profile():
    profile = getattr(args_cli, "_phase_profile", None)
    if profile is not None:
        return profile
    if PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_profile_id"):
        profile_id = PREFLIGHT_PHASE5_PROVENANCE_INFO["source_profile_id"]
        if profile_id in PHASE54_PROFILE_IDS:
            profile = resolve_phase54_profile(
                profile_id=profile_id,
                reward_profile=PREFLIGHT_PHASE5_PROVENANCE_INFO["source_reward_profile"],
                adapter_profile=PREFLIGHT_PHASE5_PROVENANCE_INFO["source_adapter_profile"],
                mpc_profile=PREFLIGHT_PHASE5_PROVENANCE_INFO["source_mpc_profile"],
                changed_axis=PREFLIGHT_PHASE5_PROVENANCE_INFO["source_changed_axis"],
            )
        elif profile_id in PHASE53_PROFILE_IDS:
            profile = resolve_phase53_profile(
                profile_id=profile_id,
                reward_profile=PREFLIGHT_PHASE5_PROVENANCE_INFO["source_reward_profile"],
                adapter_profile=PREFLIGHT_PHASE5_PROVENANCE_INFO["source_adapter_profile"],
                mpc_profile=PREFLIGHT_PHASE5_PROVENANCE_INFO["source_mpc_profile"],
                changed_axis=PREFLIGHT_PHASE5_PROVENANCE_INFO["source_changed_axis"],
            )
        else:
            profile = resolve_phase52_profile(
                profile_id=profile_id,
                reward_profile=PREFLIGHT_PHASE5_PROVENANCE_INFO["source_reward_profile"],
                adapter_profile=PREFLIGHT_PHASE5_PROVENANCE_INFO["source_adapter_profile"],
                mpc_profile=PREFLIGHT_PHASE5_PROVENANCE_INFO["source_mpc_profile"],
                changed_axis=PREFLIGHT_PHASE5_PROVENANCE_INFO["source_changed_axis"],
            )
    else:
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

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app
log_stage("Isaac app started; importing post-app modules")

import gymnasium as gym
import numpy as np
import torch

from easyuuv_env import EasyUUVEnvCfg
from easyuuv_task_registration import register_easyuuv_task
from isaaclab_compat import RslRlVecEnvWrapper, euler_xyz_from_quat, quat_from_euler_xyz
from koopman.policy_adapter import ADAPTER_MODE, PolicyAdapterConfig, adapt_policy_reference
from koopman_data import KoopmanDataLogger, build_koopman_sample
from koopman_logging import reference_vector, state_vector_from_env
from validate_ppo_koopman_log import validate_ppo_koopman_sample


EXPECTED_ADAPTER_MODE = "heuristic_reference_delta_v0"
SUPPORTED_EVIDENCE_LEVELS = (
    "stub_only",
    "checkpoint_smoke",
    "training_entrypoint_only",
    "retrained_policy_smoke",
    "stability_sentinel",
    "stability_candidate",
    "matched_stability_eval",
    "phase5_2_health_sentinel",
    "phase5_2_health_candidate",
    "phase5_2_matched_eval",
    "phase5_3_cross_sentinel",
    "phase5_3_cross_candidate",
    "phase5_3_cross_extended",
    "phase5_3_cross_matched_eval",
    "phase5_4_pareto_sentinel",
    "phase5_4_pareto_candidate",
    "phase5_4_pareto_refinement",
    "phase5_4_pareto_matched_eval",
)

log_stage("Registering EasyUUV task")
register_easyuuv_task()
log_stage("EasyUUV task registered")
strftime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


class StubPolicy:
    def __call__(self, obs):
        return torch.zeros((obs.shape[0], 4), dtype=obs.dtype, device=obs.device)


def generate_signal(
    duration=1.4,
    sample_rate=1000,
    amplitude=np.pi / 2,
    frequencies=(0.1, 0.2, 0.5, 1.0, 2.0, 3.5),
):
    t = np.linspace(0, duration, int(duration * sample_rate), endpoint=False)
    signal = np.zeros_like(t)
    for freq in frequencies:
        signal += np.sin(2 * np.pi * freq * t)
    max_abs = np.max(np.abs(signal))
    if max_abs != 0:
        signal = signal / max_abs
    signal *= amplitude
    return t, signal


_, signal1 = generate_signal(amplitude=1.1, frequencies=(-0.1, 0.2, 0.5, -1.0, 2.0, 3.5))
_, signal2 = generate_signal(amplitude=1.35, frequencies=(-0.1, 0.2, 0.4, 0.8, 1.6, -3.2))
_, signal3 = generate_signal(amplitude=0.95, frequencies=(0.15, 0.3, 0.5, -0.9, 1.8, -3))


def build_goal_list(trajectory_type: str, cycles: int) -> list[tuple[list[float], list[float]]]:
    if cycles <= 0:
        raise ValueError("trajectory_cycles must be positive")

    step_goals = [
        ([0, 0, 0], [0, 0, 0]),
        ([1.0472, 0, 0], [0, 0, 0]),
        ([-1.0472, 0, 0], [0, 0, 0]),
        ([0, 1.0472, 0], [0, 0, 0]),
        ([0, -1.0472, 0], [0, 0, 0]),
        ([0, 0, 1.0472], [0, 0, 0]),
        ([0, 0, -1.0472], [0, 0, 0]),
    ]
    if trajectory_type == "step":
        base_goals = step_goals
    elif trajectory_type == "sine":
        sample_indices = np.linspace(0, len(signal1) - 1, len(step_goals), dtype=int)
        base_goals = [
            ([float(signal1[index]), float(signal2[index]), float(signal3[index])], [0, 0, 0])
            for index in sample_indices
        ]
    elif trajectory_type == "irregular":
        base_goals = [
            ([0.20, -0.45, 0.75], [0, 0, 0.10]),
            ([-0.80, 0.15, -0.35], [0, 0, -0.15]),
            ([0.55, 0.85, -0.70], [0, 0, 0.05]),
            ([-0.35, -0.65, 0.25], [0, 0, -0.10]),
            ([0.95, -0.20, 0.55], [0, 0, 0.15]),
            ([-0.60, 0.50, -0.95], [0, 0, 0.00]),
            ([0.10, -0.90, 0.40], [0, 0, -0.05]),
        ]
    else:
        raise ValueError(f"Unsupported trajectory_type: {trajectory_type}")

    return base_goals * cycles


def policy_obs_from_observations(observations):
    if isinstance(observations, dict):
        return observations["policy"]
    return observations


def get_policy_obs(env):
    if hasattr(env, "get_observations"):
        result = env.get_observations()
    elif hasattr(env.unwrapped, "get_observations"):
        result = env.unwrapped.get_observations()
    else:
        result = env.reset()
    observations = result[0] if isinstance(result, tuple) else result
    return policy_obs_from_observations(observations)


def step_policy_obs(env, action):
    result = env.step(action)
    observations = result[0] if isinstance(result, tuple) else result
    return policy_obs_from_observations(observations)


def build_env_cfg():
    env_cfg = EasyUUVEnvCfg()
    env_cfg.scene.num_envs = args_cli.num_envs
    if hasattr(env_cfg.sim, "device"):
        env_cfg.sim.device = "cpu" if getattr(args_cli, "cpu", False) else getattr(args_cli, "device", "cuda:0")
    if hasattr(env_cfg.sim, "use_fabric"):
        env_cfg.sim.use_fabric = not args_cli.disable_fabric
    return env_cfg


def configure_env_cfg(env_cfg):
    controller_mode = args_cli.controller_mode
    profile = resolve_eval_profile()
    if profile.profile_id in PHASE54_PROFILE_IDS:
        mpc_values = effective_mpc_values(profile)
        reward_config = effective_reward_config(profile)
    else:
        mpc_values = mpc_profile_values(profile.mpc_profile)
        reward_config = None
    env_cfg.domain_randomization.use_custom_randomization = False
    env_cfg.volume = 0.0187613
    env_cfg.use_boundaries = False
    env_cfg.cap_episode_length = False
    env_cfg.episode_length_before_reset = 0
    env_cfg.goal_spawn_radius = 0
    env_cfg.eval_mode = True
    env_cfg.controller_mode = controller_mode
    env_cfg.control_method = "Ssurface"
    env_cfg.reward_profile = profile.reward_profile
    if reward_config is not None:
        env_cfg.phase5_2_w_fallback = reward_config.w_fallback
        env_cfg.phase5_2_w_pwm_sat = reward_config.w_pwm_sat
        env_cfg.phase5_2_w_action = reward_config.w_action
        env_cfg.phase5_2_w_delta_action = reward_config.w_delta_action
        env_cfg.phase5_2_w_latency = reward_config.w_latency
        env_cfg.phase5_2_pwm_soft_limit = reward_config.pwm_soft_limit
        env_cfg.phase5_2_latency_ref_ms = reward_config.latency_ref_ms
        env_cfg.phase5_2_latency_clip = reward_config.latency_clip
    env_cfg.s_ratio = 4
    env_cfg.self_adapt = True
    env_cfg.koopman_manifest_path = args_cli.koopman_manifest_path
    env_cfg.mpc_horizon = getattr(mpc_values, "horizon", args_cli.mpc_horizon)
    env_cfg.mpc_timeout_ms = getattr(mpc_values, "timeout_ms", args_cli.mpc_timeout_ms)
    env_cfg.mpc_delta_pwm_limit = mpc_values.delta_pwm_limit
    env_cfg.mpc_depth_weight = mpc_values.depth_weight
    env_cfg.mpc_attitude_weight = mpc_values.attitude_weight
    env_cfg.mpc_control_weight = mpc_values.control_weight
    env_cfg.mpc_smoothness_weight = mpc_values.smoothness_weight


def verify_koopman_manifest_contract(manifest_path: str) -> None:
    if not manifest_path:
        raise ValueError("koopman_manifest_path is required for Phase 4.5 PPO/Koopman runs")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("gate_status") != "pass":
        raise ValueError("Phase 4.5 requires a selected Koopman manifest with gate_status='pass'")
    if manifest.get("model_class") != "direct_state":
        raise ValueError("Phase 4.5 default PPO path requires model_class='direct_state'")


def set_koopman_reference(env, reference: list[float]) -> None:
    reference_tensor = torch.tensor(reference, dtype=torch.float32, device=env.device).reshape(1, 5)
    env._koopman_reference_5d = reference_tensor.repeat(env.num_envs, 1)


def first_solver_diagnostics(env) -> dict:
    diagnostics = getattr(env, "_last_koopman_mpc_diagnostics", None)
    if isinstance(diagnostics, list) and diagnostics:
        return dict(diagnostics[0])
    return {}


def resolve_checkpoint_path() -> tuple[str | None, dict]:
    return PREFLIGHT_CHECKPOINT_PATH, dict(PREFLIGHT_CHECKPOINT_INFO)


def resolve_result_bucket(policy_mode_used: str) -> str:
    if args_cli.result_bucket:
        return args_cli.result_bucket
    if policy_mode_used == "checkpoint":
        return "old_checkpoint_adapter_smoke"
    return "stub_policy_adapter_smoke"


def prepare_policy(env):
    resolved_evidence_level = getattr(args_cli, "_resolved_ppo_evidence_level", None)
    if args_cli.policy_mode == "stub":
        return env, StubPolicy(), "stub", resolved_evidence_level or "stub_only", {"checkpoint_found": False, "paths": []}
    if args_cli.policy_mode == "training_smoke":
        raise SystemExit(
            "training_smoke is a training-entrypoint verification path. Run workflows/train.py with a small "
            "--max_iterations value, then rerun this workflow with --policy_mode checkpoint."
        )

    checkpoint_path, discovery = resolve_checkpoint_path()
    if checkpoint_path is None:
        log_stage("Checkpoint mode fell back to deterministic stub policy")
        return env, StubPolicy(), "stub", "stub_only", discovery

    from rsl_rl.runners import OnPolicyRunner

    agent_cfg = cli_args.parse_rsl_rl_cfg(args_cli.task, args_cli)
    wrapped_env = RslRlVecEnvWrapper(env)
    runner = OnPolicyRunner(wrapped_env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    runner.load(checkpoint_path)
    policy = runner.get_inference_policy(device=wrapped_env.unwrapped.device)
    discovery["selected_checkpoint"] = checkpoint_path
    return wrapped_env, policy, "checkpoint", resolved_evidence_level or "checkpoint_smoke", discovery


def phase5_provenance_log_fields() -> dict:
    if not PREFLIGHT_PHASE5_PROVENANCE_INFO.get("checkpoint_provenance_valid"):
        return {}
    return {
        "checkpoint_provenance_valid": True,
        "checkpoint_provenance": PREFLIGHT_PHASE5_PROVENANCE_INFO["checkpoint_provenance"],
        "source_training_summary_path": PREFLIGHT_PHASE5_PROVENANCE_INFO["source_training_summary_path"],
        "source_result_bucket": PREFLIGHT_PHASE5_PROVENANCE_INFO["source_result_bucket"],
        "source_controller_path": PREFLIGHT_PHASE5_PROVENANCE_INFO["source_controller_path"],
        "source_adapter_mode": PREFLIGHT_PHASE5_PROVENANCE_INFO["source_adapter_mode"],
        "source_koopman_backend": PREFLIGHT_PHASE5_PROVENANCE_INFO["source_koopman_backend"],
        "source_reward_profile": PREFLIGHT_PHASE5_PROVENANCE_INFO["source_reward_profile"],
        "source_profile_id": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_profile_id"),
        "source_adapter_profile": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_adapter_profile"),
        "source_mpc_profile": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_mpc_profile"),
        "source_changed_axis": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_changed_axis"),
        "source_phase5_4_track": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_phase5_4_track"),
        "source_sweep_round": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_sweep_round"),
        "source_parent_profile_id": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_parent_profile_id"),
        "source_parameter_distance_from_parent": PREFLIGHT_PHASE5_PROVENANCE_INFO.get(
            "source_parameter_distance_from_parent"
        ),
        "source_changed_parameter_count": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_changed_parameter_count"),
        "source_parameter_step_count": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_parameter_step_count"),
        "source_protected_strengths": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_protected_strengths"),
        "source_baseline_manifest": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_baseline_manifest"),
        "source_phase5_2_summary_path": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_phase5_2_summary_path"),
        "source_phase5_3_summary_path": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_phase5_3_summary_path"),
        "source_risk_level": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_risk_level"),
        "source_training_ladder_stage": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_training_ladder_stage"),
        "source_log_dir": PREFLIGHT_PHASE5_PROVENANCE_INFO.get("source_log_dir"),
        "source_git_commit": PREFLIGHT_PHASE5_PROVENANCE_INFO["source_git_commit"],
        "source_git_dirty": PREFLIGHT_PHASE5_PROVENANCE_INFO["source_git_dirty"],
        "source_checkpoint_mtime": PREFLIGHT_PHASE5_PROVENANCE_INFO["source_checkpoint_mtime"],
    }


def build_adapter_config() -> PolicyAdapterConfig:
    adapter_values = adapter_profile_values(resolve_eval_profile().adapter_profile)
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


def main():
    log_stage("Building EasyUUVEnvCfg directly")
    verify_koopman_manifest_contract(args_cli.koopman_manifest_path)
    env_cfg = build_env_cfg()
    configure_env_cfg(env_cfg)

    log_stage("Creating Gym environment")
    env = gym.make(args_cli.task, cfg=env_cfg)
    env, policy, policy_mode_used, ppo_evidence_level, checkpoint_info = prepare_policy(env)
    log_stage(f"Using policy_mode={policy_mode_used} ppo_evidence_level={ppo_evidence_level}")

    save_path = os.path.join(PROJECT_ROOT, "source", "results", "ppo_koopman", args_cli.eval_name + "_" + strftime)
    os.makedirs(save_path, exist_ok=True)
    log_path = args_cli.ppo_koopman_log_path or os.path.join(save_path, "ppo_koopman_step.jsonl")
    logger = KoopmanDataLogger(log_path)
    print(f"[INFO]: Saving PPO/Koopman data into: {log_path}", flush=True)

    goal_list = build_goal_list(args_cli.trajectory_type, args_cli.trajectory_cycles)
    if args_cli.max_goals is not None:
        goal_list = goal_list[: args_cli.max_goals]

    adapter_config = build_adapter_config()
    profile = resolve_eval_profile()
    obs = get_policy_obs(env)
    action_iter = 0
    action_ix = 0
    counter = 0
    if ADAPTER_MODE != EXPECTED_ADAPTER_MODE:
        raise RuntimeError(f"Unexpected adapter mode: {ADAPTER_MODE}")
    log_stage(f"Starting PPO/Koopman rollout with adapter_mode={ADAPTER_MODE}")

    while action_ix < len(goal_list):
        counter += 1
        goal_orientation, goal_pos = goal_list[action_ix]

        with torch.inference_mode():
            des_ang_quat = quat_from_euler_xyz(
                torch.Tensor([goal_orientation[0]]),
                torch.Tensor([goal_orientation[1]]),
                torch.Tensor([goal_orientation[2]]),
            )
            env.unwrapped._goal[:] = des_ang_quat.to(env.unwrapped.device)
            obs[0, 0:4] = des_ang_quat[0].to(env.unwrapped.device)

            policy_action = policy(obs)
            previous_state = state_vector_from_env(env.unwrapped)
            base_reference = reference_vector(goal_pos[2], obs[0, 0:4])
            adapter_output = adapt_policy_reference(
                policy_action,
                base_reference,
                observation_goal_quat=obs[0, 0:4],
                config=adapter_config,
                ppo_evidence_level=ppo_evidence_level,
            )
            set_koopman_reference(env.unwrapped, adapter_output.adapted_reference_5d)
            obs = step_policy_obs(env, policy_action)
            next_state = state_vector_from_env(env.unwrapped)
            solver_diagnostics = first_solver_diagnostics(env.unwrapped)

            sample = build_koopman_sample(
                t=counter / 60,
                state=previous_state,
                reference=adapter_output.adapted_reference_5d,
                action_4d=policy_action,
                pwm_8d=env.unwrapped._last_pwm_8d[0],
                next_state=next_state,
                trajectory_type=args_cli.trajectory_type,
                controller_mode=f"{args_cli.controller_mode}/{env_cfg.control_method}",
            )
            sample.update(
                {
                    "policy_mode": policy_mode_used,
                    "result_bucket": resolve_result_bucket(policy_mode_used),
                    "checkpoint_found": bool(checkpoint_info.get("checkpoint_found")),
                    "checkpoint_path": checkpoint_info.get("selected_checkpoint"),
                    "selected_checkpoint": checkpoint_info.get("selected_checkpoint"),
                    "selected_rule": checkpoint_info.get("selected_rule"),
                    "policy_output": adapter_output.diagnostics.get("raw_policy_output", None)
                    or policy_action.detach().cpu().reshape(-1).tolist(),
                    "policy_output_clipped": adapter_output.policy_output_4d_clipped,
                    "base_reference": base_reference,
                    "adapted_reference": adapter_output.adapted_reference_5d,
                    "adapter_mode": adapter_output.adapter_mode,
                    "action_semantics": adapter_output.diagnostics["action_semantics"],
                    "ppo_evidence_level": ppo_evidence_level,
                    "controller_path": "koopman_mpc/direct_state",
                    "profile_id": profile.profile_id,
                    "phase5_4_track": getattr(profile, "track", "not_applicable"),
                    "reward_profile": profile.reward_profile,
                    "adapter_profile": profile.adapter_profile,
                    "mpc_profile": profile.mpc_profile,
                    "changed_axis": profile.changed_axis,
                    "sweep_round": getattr(profile, "sweep_round", "not_applicable"),
                    "parent_profile_id": getattr(profile, "parent_profile_id", "not_applicable"),
                    "parameter_distance_from_parent": getattr(profile, "parameter_distance_from_parent", 0.0),
                    "changed_parameter_count": getattr(profile, "changed_parameter_count", 0),
                    "parameter_step_count": getattr(profile, "parameter_step_count", {}),
                    "adapter_quat_convention": adapter_output.diagnostics["adapter_quat_convention"],
                    "base_reference_goal_match_max_error": adapter_output.diagnostics[
                        "base_reference_goal_match_max_error"
                    ],
                    "adapter_diagnostics": adapter_output.diagnostics,
                    "policy_action_clip_rate": adapter_output.diagnostics["policy_action_clip_rate"],
                    "backend_used": "direct_state",
                    "solver_diagnostics": solver_diagnostics,
                }
            )
            sample.update(phase5_provenance_log_fields())
            validate_ppo_koopman_sample(sample)
            logger.write(sample)

            if counter > 2:
                true_ang = obs[0, 5:9]
                true_ang_rpy = euler_xyz_from_quat(torch.unsqueeze(true_ang, 0))
                print(
                    "counter "
                    f"{counter} | {len(goal_list) * args_cli.steps_per_action} | "
                    f"roll {true_ang_rpy[0][0].cpu().item():.4f}",
                    end="\r",
                )

            action_iter += 1
            action_ix = action_iter // args_cli.steps_per_action

    logger.close()
    log_stage(f"Rollout finished; wrote PPO/Koopman JSONL to {log_path}")
    env.close()


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        log_stage("Unhandled exception follows")
        traceback.print_exc()
        raise
    finally:
        simulation_app.close()

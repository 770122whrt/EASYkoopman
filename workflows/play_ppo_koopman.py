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

cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app
log_stage("Isaac app started; importing post-app modules")

import gymnasium as gym
import numpy as np
import torch

from discover_ppo_checkpoints import discover_ppo_checkpoints
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
    env_cfg.domain_randomization.use_custom_randomization = False
    env_cfg.volume = 0.0187613
    env_cfg.use_boundaries = False
    env_cfg.cap_episode_length = False
    env_cfg.episode_length_before_reset = 0
    env_cfg.goal_spawn_radius = 0
    env_cfg.eval_mode = True
    env_cfg.controller_mode = controller_mode
    env_cfg.control_method = "Ssurface"
    env_cfg.s_ratio = 4
    env_cfg.self_adapt = True
    env_cfg.koopman_manifest_path = args_cli.koopman_manifest_path
    env_cfg.mpc_horizon = args_cli.mpc_horizon
    env_cfg.mpc_timeout_ms = args_cli.mpc_timeout_ms
    env_cfg.mpc_delta_pwm_limit = args_cli.mpc_delta_pwm_limit
    env_cfg.mpc_depth_weight = args_cli.mpc_depth_weight
    env_cfg.mpc_attitude_weight = args_cli.mpc_attitude_weight
    env_cfg.mpc_control_weight = args_cli.mpc_control_weight
    env_cfg.mpc_smoothness_weight = args_cli.mpc_smoothness_weight


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
    if args_cli.play_checkpoint:
        return args_cli.play_checkpoint, {"checkpoint_found": True, "paths": [args_cli.play_checkpoint]}
    discovery = discover_ppo_checkpoints()
    if discovery["paths"]:
        return discovery["paths"][0], discovery
    if args_cli.allow_stub_fallback:
        return None, discovery
    raise FileNotFoundError(
        "No PPO checkpoint found. Use --policy_mode stub, pass --play_checkpoint, or add --allow_stub_fallback."
    )


def prepare_policy(env):
    if args_cli.policy_mode == "stub":
        return env, StubPolicy(), "stub", "stub_only", {"checkpoint_found": False, "paths": []}
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
    return wrapped_env, policy, "checkpoint", "checkpoint_smoke", discovery


def build_adapter_config() -> PolicyAdapterConfig:
    return PolicyAdapterConfig(
        policy_action_limit=args_cli.adapter_policy_action_limit,
        rpy_delta_scale=(
            args_cli.adapter_rpy_delta_scale,
            args_cli.adapter_rpy_delta_scale,
            args_cli.adapter_rpy_delta_scale,
        ),
        depth_delta_scale=args_cli.adapter_depth_delta_scale,
        depth_bounds=(args_cli.adapter_depth_min, args_cli.adapter_depth_max),
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
                    "checkpoint_found": bool(checkpoint_info.get("checkpoint_found")),
                    "checkpoint_path": checkpoint_info.get("selected_checkpoint"),
                    "policy_output": adapter_output.diagnostics.get("raw_policy_output", None)
                    or policy_action.detach().cpu().reshape(-1).tolist(),
                    "policy_output_clipped": adapter_output.policy_output_4d_clipped,
                    "base_reference": base_reference,
                    "adapted_reference": adapter_output.adapted_reference_5d,
                    "adapter_mode": adapter_output.adapter_mode,
                    "action_semantics": adapter_output.diagnostics["action_semantics"],
                    "ppo_evidence_level": ppo_evidence_level,
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

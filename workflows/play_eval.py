from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from isaaclab_app import AppLauncher

import cli_args


parser = argparse.ArgumentParser(description="Evaluate a legacy EasyUUV PPO checkpoint.")
parser.add_argument(
    "--disable_fabric", action="store_true", default=False, help="Disable fabric and use USD I/O operations."
)
parser.add_argument("--num_envs", type=int, default=1, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default="EasyUUV-Direct-v1", help="Name of the task.")
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment.")
parser.add_argument("--eval_name", type=str, default="legacy_ppo_baseline", help="Name of the eval run.")
parser.add_argument("--custom_weights", type=str, default=None, help="Path to custom weights file.")
parser.add_argument("--koopman_log_path", type=str, default=None, help="Path for Koopman JSONL data logging.")
parser.add_argument("--phase46_summary_path", type=str, default=None, help="Path for Phase 4.6 sidecar summary.")
parser.add_argument("--export_policy", action="store_true", default=False, help="Export JIT/ONNX policy artifacts.")
parser.add_argument("--result_bucket", type=str, default="legacy_ppo_baseline", help="Phase 4.6 result bucket.")
parser.add_argument("--ppo_evidence_level", type=str, default="checkpoint_smoke", help="PPO evidence level.")
parser.add_argument("--reward_profile", type=str, default="legacy_easyuuv_v0", help="Reward profile label.")
parser.add_argument("--selected_rule", type=str, default="explicit_path", help="Checkpoint selection rule.")
parser.add_argument("--training_iterations", type=int, default=None, help="Iterations used to create the checkpoint.")
parser.add_argument("--steps_per_action", type=int, default=200, help="Steps to hold each reference.")
parser.add_argument("--max_goals", type=int, default=None, help="Limit goals for short smoke tests.")
parser.add_argument("--action_noise_std", type=float, default=0.0, help="Reserved for compatibility.")
parser.add_argument("--observation_noise_std", type=float, default=0.0, help="Reserved for compatibility.")
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import numpy as np
import torch
from rsl_rl.runners import OnPolicyRunner

from easyuuv_task_registration import register_easyuuv_task
from isaaclab_compat import (
    RslRlOnPolicyRunnerCfg,
    RslRlVecEnvWrapper,
    euler_xyz_from_quat,
    export_policy_as_jit,
    export_policy_as_onnx,
    get_checkpoint_path,
    parse_env_cfg,
    quat_from_euler_xyz,
)
from koopman_data import KoopmanDataLogger
from koopman_logging import record_koopman_step, reference_vector, state_vector_from_env


strftime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def quat_diff(quat1: np.ndarray, quat2: np.ndarray) -> np.ndarray:
    q1_conjugate = quat1.copy()
    q1_conjugate[:, 1:] *= -1
    diff = np.zeros_like(quat1)
    for i in range(len(quat1)):
        diff[i, 0] = (
            quat2[i, 0] * q1_conjugate[i, 0]
            - quat2[i, 1] * q1_conjugate[i, 1]
            - quat2[i, 2] * q1_conjugate[i, 2]
            - quat2[i, 3] * q1_conjugate[i, 3]
        )
        diff[i, 1] = (
            quat2[i, 0] * q1_conjugate[i, 1]
            + quat2[i, 1] * q1_conjugate[i, 0]
            + quat2[i, 2] * q1_conjugate[i, 3]
            - quat2[i, 3] * q1_conjugate[i, 2]
        )
        diff[i, 2] = (
            quat2[i, 0] * q1_conjugate[i, 2]
            - quat2[i, 1] * q1_conjugate[i, 3]
            + quat2[i, 2] * q1_conjugate[i, 0]
            + quat2[i, 3] * q1_conjugate[i, 1]
        )
        diff[i, 3] = (
            quat2[i, 0] * q1_conjugate[i, 3]
            + quat2[i, 1] * q1_conjugate[i, 2]
            - quat2[i, 2] * q1_conjugate[i, 1]
            + quat2[i, 3] * q1_conjugate[i, 0]
        )
    return diff


def ang_to_quat(roll: np.ndarray, pitch: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    q = np.zeros((len(roll), 4))
    q[:, 0] = np.cos(roll / 2) * np.cos(pitch / 2) * np.cos(yaw / 2) + np.sin(roll / 2) * np.sin(
        pitch / 2
    ) * np.sin(yaw / 2)
    q[:, 1] = np.sin(roll / 2) * np.cos(pitch / 2) * np.cos(yaw / 2) - np.cos(roll / 2) * np.sin(
        pitch / 2
    ) * np.sin(yaw / 2)
    q[:, 2] = np.cos(roll / 2) * np.sin(pitch / 2) * np.cos(yaw / 2) + np.sin(roll / 2) * np.cos(
        pitch / 2
    ) * np.sin(yaw / 2)
    q[:, 3] = np.cos(roll / 2) * np.cos(pitch / 2) * np.sin(yaw / 2) - np.sin(roll / 2) * np.sin(
        pitch / 2
    ) * np.cos(yaw / 2)
    return q


def configure_legacy_eval_env(env_cfg) -> None:
    env_cfg.domain_randomization.use_custom_randomization = False
    env_cfg.volume = 0.0187613
    env_cfg.use_boundaries = False
    env_cfg.cap_episode_length = False
    env_cfg.episode_length_before_reset = 0
    env_cfg.goal_spawn_radius = 0
    env_cfg.eval_mode = True
    env_cfg.controller_mode = "legacy"
    env_cfg.control_method = "Ssurface"
    env_cfg.s_ratio = 4
    env_cfg.self_adapt = True


def parse_env_config(num_envs: int):
    return parse_env_cfg(
        args_cli.task,
        device=getattr(args_cli, "device", "cuda:0"),
        num_envs=num_envs,
        use_fabric=not args_cli.disable_fabric,
    )


def get_policy_obs(env):
    if hasattr(env, "get_observations"):
        result = env.get_observations()
    elif hasattr(env.unwrapped, "get_observations"):
        result = env.unwrapped.get_observations()
    else:
        result = env.reset()
    observations = result[0] if isinstance(result, tuple) else result
    if isinstance(observations, dict):
        return observations["policy"]
    return observations


def step_policy_obs(env, action):
    result = env.step(action)
    observations = result[0] if isinstance(result, tuple) else result
    if isinstance(observations, dict):
        return observations["policy"]
    return observations


def build_goal_list() -> list[tuple[list[float], list[float]]]:
    goals = [
        ([0, 0, 0], [0, 0, 0]),
        ([1.0472, 0, 0], [0, 0, 0]),
        ([-1.0472, 0, 0], [0, 0, 0]),
        ([0, 1.0472, 0], [0, 0, 0]),
        ([0, -1.0472, 0], [0, 0, 0]),
        ([0, 0, 1.0472], [0, 0, 0]),
        ([0, 0, -1.0472], [0, 0, 0]),
    ]
    return goals[: args_cli.max_goals] if args_cli.max_goals is not None else goals


def write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_phase46_legacy_summary(
    *,
    summary_path: str,
    checkpoint_path: str,
    koopman_log_path: str,
    csv_path: str,
    row_count: int,
    action_clip_rate: float,
    pwm_min: float | None,
    pwm_max: float | None,
) -> None:
    summary = {
        "result_bucket": args_cli.result_bucket,
        "ppo_evidence_level": args_cli.ppo_evidence_level,
        "reward_profile": args_cli.reward_profile,
        "controller_path": "legacy/Ssurface",
        "checkpoint_found": True,
        "checkpoint_path": checkpoint_path,
        "selected_checkpoint": checkpoint_path,
        "selected_rule": args_cli.selected_rule,
        "training_iterations": args_cli.training_iterations,
        "action_dim": 4,
        "observation_dim": 9,
        "pwm_dim": 8,
        "sample_count": row_count,
        "koopman_log_path": koopman_log_path,
        "csv_path": csv_path,
        "action_clip_rate": action_clip_rate,
        "fallback_rate": None,
        "latency": None,
        "pwm_bounds": {"min": pwm_min, "max": pwm_max},
        "allowed_claims": ["legacy PPO checkpoint can be loaded through the original controller path"],
        "disallowed_claims": [
            "PPO+Koopman performance is proven",
            "old PPO semantics are losslessly migrated",
        ],
    }
    os.makedirs(os.path.dirname(os.path.abspath(summary_path)), exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)
    print(f"[INFO]: Wrote Phase 4.6 legacy PPO summary to: {summary_path}", flush=True)


def main() -> None:
    register_easyuuv_task()
    env_cfg = parse_env_config(args_cli.num_envs)
    configure_legacy_eval_env(env_cfg)
    agent_cfg: RslRlOnPolicyRunnerCfg = cli_args.parse_rsl_rl_cfg(args_cli.task, args_cli)

    env = gym.make(args_cli.task, cfg=env_cfg)
    env = RslRlVecEnvWrapper(env)

    log_root_path = os.path.abspath(os.path.join("logs", "rsl_rl", agent_cfg.experiment_name))
    print(f"[INFO] Loading experiment from directory: {log_root_path}")
    resume_path = args_cli.custom_weights or get_checkpoint_path(
        log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint
    )
    print(f"[INFO]: Loading model checkpoint from: {resume_path}")

    ppo_runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    ppo_runner.load(resume_path)
    policy = ppo_runner.get_inference_policy(device=env.unwrapped.device)

    if args_cli.export_policy:
        export_model_dir = os.path.join(os.path.dirname(resume_path), "exported")
        export_policy_as_jit(
            ppo_runner.alg.actor_critic,
            ppo_runner.obs_normalizer,
            path=export_model_dir,
            filename="policy.pt",
        )
        export_policy_as_onnx(ppo_runner.alg.actor_critic, path=export_model_dir, filename="policy.onnx")

    save_path = os.path.join(PROJECT_ROOT, "source", "results", "rsl_rl", agent_cfg.experiment_name, args_cli.eval_name + "_" + strftime)
    os.makedirs(save_path, exist_ok=True)
    csv_path = os.path.join(save_path, "logs.csv")
    koopman_log_path = args_cli.koopman_log_path or os.path.join(save_path, "legacy_ppo_baseline.jsonl")
    summary_path = args_cli.phase46_summary_path or str(Path(koopman_log_path).with_suffix(".summary.json"))
    koopman_logger = KoopmanDataLogger(koopman_log_path)
    print(f"[INFO]: Saving Koopman data into: {koopman_log_path}")

    rows: list[dict] = []
    policy_clip_events = 0
    policy_value_count = 0
    pwm_min: float | None = None
    pwm_max: float | None = None
    obs = get_policy_obs(env)
    action_iter = 0
    action_ix = 0
    counter = 0
    goal_list = build_goal_list()

    while action_ix < len(goal_list):
        counter += 1
        goal_orientation, goal_pos = goal_list[action_ix]
        t = counter / 60
        goal_orientation = [0.4 * np.sin(t * 1.4), 0.55 * np.cos(t * 1.2), np.sin(t)]

        with torch.inference_mode():
            des_ang_quat = quat_from_euler_xyz(
                torch.Tensor([goal_orientation[0]]),
                torch.Tensor([goal_orientation[1]]),
                torch.Tensor([goal_orientation[2]]),
            )
            env.unwrapped._goal[:] = des_ang_quat.to(env.unwrapped.device)
            actions = policy(obs)
            policy_clip_events += int((actions.detach().abs() >= 0.999).sum().item())
            policy_value_count += int(actions.numel())
            previous_state = state_vector_from_env(env.unwrapped)
            reference = reference_vector(goal_pos[2], des_ang_quat[0])
            obs = step_policy_obs(env, actions)
            next_state = state_vector_from_env(env.unwrapped)
            record_koopman_step(
                koopman_logger,
                t=counter / 60,
                env=env.unwrapped,
                previous_state=previous_state,
                reference=reference,
                action_4d=actions,
                next_state=next_state,
                trajectory_type="sine",
                controller_mode="legacy/Ssurface",
            )

            pwm = env.unwrapped._last_pwm_8d.detach().cpu().reshape(-1).tolist()
            pwm_min = min(pwm) if pwm_min is None else min(pwm_min, min(pwm))
            pwm_max = max(pwm) if pwm_max is None else max(pwm_max, max(pwm))
            true_pos = env.unwrapped._robot.data.root_pos_w[0].cpu().numpy()
            true_ang = obs[0, 5:9]
            true_ang_rpy = euler_xyz_from_quat(torch.unsqueeze(true_ang, 0))
            true_ang_rpy = np.array(
                [true_ang_rpy[0][0].cpu().item(), true_ang_rpy[1][0].cpu().item(), true_ang_rpy[2][0].cpu().item()]
            )
            true_ang_rpy = np.where(true_ang_rpy >= math.pi, true_ang_rpy - (2 * math.pi), true_ang_rpy)
            true_linvel = env.unwrapped._robot.data.root_lin_vel_b[0].cpu().numpy()
            true_angvel = env.unwrapped._robot.data.root_ang_vel_b[0].cpu().numpy()
            des_ang_rpy = euler_xyz_from_quat(torch.unsqueeze(des_ang_quat[0], 0))
            des_ang_rpy = np.array(
                [des_ang_rpy[0][0].cpu().item(), des_ang_rpy[1][0].cpu().item(), des_ang_rpy[2][0].cpu().item()]
            )
            des_ang_rpy = np.where(des_ang_rpy >= math.pi, des_ang_rpy - (2 * math.pi), des_ang_rpy)
            rows.append(
                {
                    "des_depth": goal_pos[2],
                    "des_roll": des_ang_rpy[0],
                    "des_pitch": des_ang_rpy[1],
                    "des_yaw": des_ang_rpy[2],
                    "true_x": true_pos[0],
                    "true_y": true_pos[1],
                    "true_z": true_pos[2],
                    "true_x_vel": true_linvel[0],
                    "true_y_vel": true_linvel[1],
                    "true_z_vel": true_linvel[2],
                    "true_roll": true_ang_rpy[0],
                    "true_pitch": true_ang_rpy[1],
                    "true_yaw": true_ang_rpy[2],
                    "true_roll_vel": true_angvel[0],
                    "true_pitch_vel": true_angvel[1],
                    "true_yaw_vel": true_angvel[2],
                }
            )

            if counter > 2:
                ang_diff = quat_diff(
                    ang_to_quat(
                        np.array([row["true_roll"] for row in rows]),
                        np.array([row["true_pitch"] for row in rows]),
                        np.array([row["true_yaw"] for row in rows]),
                    ),
                    ang_to_quat(
                        np.array([row["des_roll"] for row in rows]),
                        np.array([row["des_pitch"] for row in rows]),
                        np.array([row["des_yaw"] for row in rows]),
                    ),
                )
                mse = np.mean((np.arccos(ang_diff[:, 0]) * 2) ** 2)
                print(f"counter {counter} | {len(goal_list) * args_cli.steps_per_action} | MSE : {mse:.4f} rad^2", end="\r")

            action_iter += 1
            action_ix = action_iter // args_cli.steps_per_action

    write_csv(csv_path, rows)
    koopman_logger.close()
    action_clip_rate = policy_clip_events / policy_value_count if policy_value_count else 0.0
    write_phase46_legacy_summary(
        summary_path=summary_path,
        checkpoint_path=resume_path,
        koopman_log_path=koopman_log_path,
        csv_path=csv_path,
        row_count=len(rows),
        action_clip_rate=action_clip_rate,
        pwm_min=pwm_min,
        pwm_max=pwm_max,
    )
    env.close()


if __name__ == "__main__":
    try:
        main()
    finally:
        simulation_app.close()

import argparse
import math
import os
import sys
from datetime import datetime


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from isaaclab_app import AppLauncher


parser = argparse.ArgumentParser(description="Run the EasyUUV direct legacy controller.")
parser.add_argument("--cpu", action="store_true", default=False, help="Use CPU pipeline.")
parser.add_argument(
    "--disable_fabric", action="store_true", default=False, help="Disable fabric and use USD I/O operations."
)
parser.add_argument("--num_envs", type=int, default=1, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default="EasyUUV-Direct-v1", help="Name of the task.")
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment.")
parser.add_argument("--eval_name", type=str, default="eval_controller", help="Name of the eval run.")
parser.add_argument("--koopman_log_path", type=str, default=None, help="Path for Koopman JSONL data logging.")
parser.add_argument("--action_noise_std", type=float, default=0.0, help="Reserved for future controller tests.")
parser.add_argument("--observation_noise_std", type=float, default=0.0, help="Reserved for future controller tests.")

AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import numpy as np
import pandas as pd
import torch

try:
    import wandb
except ImportError:
    wandb = None

from easyuuv_task_registration import register_easyuuv_task
from isaaclab_compat import (
    euler_xyz_from_quat,
    parse_env_cfg,
    quat_apply,
    quat_conjugate,
    quat_from_euler_xyz,
    quat_mul,
)
from koopman_data import KoopmanDataLogger
from koopman_logging import record_koopman_step, reference_vector, state_vector_from_env


register_easyuuv_task()
strftime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def angle_remap(angle):
    return (angle + torch.pi) % (2 * torch.pi) - torch.pi


def ang_to_quat(roll: np.ndarray, pitch: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    q = np.zeros((len(roll), 4))
    q[:, 0] = (
        np.cos(roll / 2) * np.cos(pitch / 2) * np.cos(yaw / 2)
        + np.sin(roll / 2) * np.sin(pitch / 2) * np.sin(yaw / 2)
    )
    q[:, 1] = (
        np.sin(roll / 2) * np.cos(pitch / 2) * np.cos(yaw / 2)
        - np.cos(roll / 2) * np.sin(pitch / 2) * np.sin(yaw / 2)
    )
    q[:, 2] = (
        np.cos(roll / 2) * np.sin(pitch / 2) * np.cos(yaw / 2)
        + np.sin(roll / 2) * np.cos(pitch / 2) * np.sin(yaw / 2)
    )
    q[:, 3] = (
        np.cos(roll / 2) * np.cos(pitch / 2) * np.sin(yaw / 2)
        - np.sin(roll / 2) * np.sin(pitch / 2) * np.cos(yaw / 2)
    )
    return q


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


def policy_obs_from_observations(observations):
    if isinstance(observations, dict):
        return observations["policy"]
    return observations


def get_policy_obs(env):
    target_env = env if hasattr(env, "get_observations") else env.unwrapped
    result = target_env.get_observations()
    observations = result[0] if isinstance(result, tuple) else result
    return policy_obs_from_observations(observations)


def step_policy_obs(env, action):
    result = env.step(action)
    observations = result[0] if isinstance(result, tuple) else result
    return policy_obs_from_observations(observations)


def init_wandb_run(eval_name: str, env_cfg):
    if wandb is None:
        print("[WARN]: wandb is not installed; CSV and JSONL logging will still run.")
        return None

    try:
        return wandb.init(
            project=os.environ.get("EASYUUV_WANDB_PROJECT", "easyuuv"),
            name=eval_name,
            config=env_cfg,
            mode=os.environ.get("WANDB_MODE", "disabled"),
        )
    except Exception as exc:
        print(f"[WARN]: wandb init failed ({exc}); CSV and JSONL logging will still run.")
        return None


_, signal1 = generate_signal(amplitude=1.1, frequencies=(-0.1, 0.2, 0.5, -1.0, 2.0, 3.5))
_, signal2 = generate_signal(amplitude=1.35, frequencies=(-0.1, 0.2, 0.4, 0.8, 1.6, -3.2))
_, signal3 = generate_signal(amplitude=0.95, frequencies=(0.15, 0.3, 0.5, -0.9, 1.8, -3))


def main():
    env_cfg = parse_env_cfg(
        args_cli.task,
        use_gpu=not args_cli.cpu,
        num_envs=args_cli.num_envs,
        use_fabric=not args_cli.disable_fabric,
    )

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

    env = gym.make(args_cli.task, cfg=env_cfg)
    wandb_run = init_wandb_run(args_cli.eval_name + "_" + strftime, env_cfg)

    save_path = os.path.join(PROJECT_ROOT, "source", "results", "direct_controller", args_cli.eval_name + "_" + strftime)
    os.makedirs(save_path, exist_ok=True)

    print(f"[INFO]: Saving results into: {save_path}")

    eval_csv_path = os.path.join(save_path, "logs.csv")
    koopman_log_path = args_cli.koopman_log_path or os.path.join(save_path, "koopman_step.jsonl")
    koopman_logger = KoopmanDataLogger(koopman_log_path)
    print(f"[INFO]: Saving Koopman data into: {koopman_log_path}")

    log_df = pd.DataFrame(
        columns=[
            "des_depth",
            "des_roll",
            "des_pitch",
            "des_yaw",
            "true_x",
            "true_y",
            "true_z",
            "true_x_vel",
            "true_y_vel",
            "true_z_vel",
            "true_roll",
            "true_pitch",
            "true_yaw",
            "true_roll_vel",
            "true_pitch_vel",
            "true_yaw_vel",
            "mse",
            "reward",
        ]
    )

    goal_list = [
        ([0, 0, 0], [0, 0, 0]),
        ([1.0472, 0, 0], [0, 0, 0]),
        ([-1.0472, 0, 0], [0, 0, 0]),
        ([0, 1.0472, 0], [0, 0, 0]),
        ([0, -1.0472, 0], [0, 0, 0]),
        ([0, 0, 1.0472], [0, 0, 0]),
        ([0, 0, -1.0472], [0, 0, 0]),
    ]

    obs = get_policy_obs(env)
    action_iter = 0
    steps_per_action = 200
    action_ix = 0
    counter = 0

    while action_ix < len(goal_list):
        counter += 1
        goal_orientation, goal_pos = goal_list[action_ix]

        with torch.inference_mode():
            des_ang_rpy = goal_orientation
            des_ang_quat = quat_from_euler_xyz(
                torch.Tensor([des_ang_rpy[0]]),
                torch.Tensor([des_ang_rpy[1]]),
                torch.Tensor([des_ang_rpy[2]]),
            )
            env.unwrapped._goal[:] = des_ang_quat.to(env_cfg.sim.device)
            obs[0, 0:4] = des_ang_quat[0].to(env_cfg.sim.device)
            now_quat = obs[0, 5:9]
            goal_quat = quat_mul(now_quat, quat_conjugate(des_ang_quat[0].to(env_cfg.sim.device)))

            goal_quat_roll, goal_quat_pitch, goal_quat_yaw = euler_xyz_from_quat(goal_quat.unsqueeze(0))
            goal_quat_roll = angle_remap(goal_quat_roll)
            goal_quat_pitch = angle_remap(goal_quat_pitch)
            goal_quat_yaw = angle_remap(goal_quat_yaw)
            action_symb = torch.Tensor([0.5, -0.5, 0.5, -0.5]).reshape(1, 4).to(env_cfg.sim.device)
            action_terms = torch.stack(
                (
                    goal_quat_roll.reshape(()),
                    goal_quat_pitch.reshape(()),
                    goal_quat_yaw.reshape(()),
                    obs[0, 4].reshape(()),
                )
            )
            action = action_terms.reshape(1, 4).to(env_cfg.sim.device) * action_symb

            action_lim = torch.tensor([1, 1, 1, 1]).reshape(1, 4).to(env_cfg.sim.device)
            action = torch.clip(action, -action_lim, action_lim).to(env_cfg.sim.device)
            previous_state = state_vector_from_env(env.unwrapped)
            reference = reference_vector(goal_pos[2], des_ang_quat[0])
            obs = step_policy_obs(env, action)
            next_state = state_vector_from_env(env.unwrapped)
            record_koopman_step(
                koopman_logger,
                t=counter / 60,
                env=env.unwrapped,
                previous_state=previous_state,
                reference=reference,
                action_4d=action,
                next_state=next_state,
                trajectory_type="step",
                controller_mode=f"legacy/{env_cfg.control_method}",
            )

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

            record1 = action.detach().cpu().numpy()[0]
            record2 = np.zeros(4)

            log_row = {
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
                "action_1": record1[0],
                "action_2": record1[1],
                "action_3": record1[2],
                "action_4": record1[3],
                "action_real_1": record2[0],
                "action_real_2": record2[1],
                "action_real_3": record2[2],
                "action_real_4": record2[3],
            }

            action_iter += 1

            if (action_iter % steps_per_action) != 0 and wandb_run is not None:
                wandb_run.log(log_row)

            log_df = log_df._append(log_row, ignore_index=True)

            if counter > 2:
                ang_diff = quat_diff(
                    ang_to_quat(np.array(log_df["true_roll"]), np.array(log_df["true_pitch"]), np.array(log_df["true_yaw"])),
                    ang_to_quat(np.array(log_df["des_roll"]), np.array(log_df["des_pitch"]), np.array(log_df["des_yaw"])),
                )

                ang_diff = np.arccos(ang_diff[:, 0]) * 2
                mse = np.mean(ang_diff**2)

                print(f"counter {counter} | {len(goal_list) * steps_per_action} | MSE : {mse:.4f} rad^2      ", end="\r")

            action_ix = action_iter // steps_per_action

    log_df.to_csv(eval_csv_path)
    koopman_logger.close()
    if wandb_run is not None:
        wandb_run.finish()
    env.close()


if __name__ == "__main__":
    try:
        main()
    finally:
        simulation_app.close()

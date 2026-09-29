from __future__ import annotations

import argparse
import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from isaaclab_app import AppLauncher

import cli_args


parser = argparse.ArgumentParser(description="Export an EasyUUV PPO checkpoint policy.")
parser.add_argument(
    "--disable_fabric", action="store_true", default=False, help="Disable fabric and use USD I/O operations."
)
parser.add_argument("--num_envs", type=int, default=1, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default="EasyUUV-Direct-v1", help="Name of the task.")
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment.")
parser.add_argument("--eval_name", type=str, default="export_policy", help="Name of the export run.")
parser.add_argument("--custom_weights", type=str, default=None, help="Path to custom weights file.")
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
from rsl_rl.runners import OnPolicyRunner

from easyuuv_task_registration import register_gym_tasks
from isaaclab_compat import (
    RslRlOnPolicyRunnerCfg,
    RslRlVecEnvWrapper,
    export_policy_as_jit,
    export_policy_as_onnx,
    get_checkpoint_path,
    parse_env_cfg,
)


def parse_env_config(num_envs: int):
    return parse_env_cfg(
        args_cli.task,
        device=getattr(args_cli, "device", "cuda:0"),
        num_envs=num_envs,
        use_fabric=not args_cli.disable_fabric,
    )


def main() -> None:
    register_gym_tasks()
    env_cfg = parse_env_config(args_cli.num_envs)
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

    export_model_dir = os.path.join(os.path.dirname(resume_path), "exported")
    export_policy_as_jit(
        ppo_runner.alg.actor_critic,
        ppo_runner.obs_normalizer,
        path=export_model_dir,
        filename="policy.pt",
    )
    export_policy_as_onnx(ppo_runner.alg.actor_critic, path=export_model_dir, filename="policy.onnx")
    print("Policy export OK!")
    env.close()


if __name__ == "__main__":
    try:
        main()
    finally:
        simulation_app.close()

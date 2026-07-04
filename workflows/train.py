from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from isaaclab_app import AppLauncher

import cli_args


parser = argparse.ArgumentParser(description="Train an EasyUUV PPO/RSL-RL agent.")
parser.add_argument("--video", action="store_true", default=False, help="Record videos during training.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video in steps.")
parser.add_argument("--video_interval", type=int, default=2000, help="Interval between video recordings in steps.")
parser.add_argument(
    "--disable_fabric", action="store_true", default=False, help="Disable fabric and use USD I/O operations."
)
parser.add_argument("--num_envs", type=int, default=2048, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default="EasyUUV-Direct-v1", help="Name of the task.")
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment.")
parser.add_argument("--max_iterations", type=int, default=None, help="RL policy training iterations.")
parser.add_argument("--save_interval", type=int, default=None, help="Override PPO checkpoint save interval.")
parser.add_argument(
    "--result_bucket",
    type=str,
    default="legacy_ppo_baseline",
    help="Phase 4.6 result bucket for the training smoke.",
)
parser.add_argument(
    "--ppo_evidence_level",
    type=str,
    default="training_entrypoint_only",
    choices=("training_entrypoint_only", "checkpoint_smoke", "retrained_policy_smoke"),
    help="Evidence level attached to the training smoke summary.",
)
parser.add_argument("--reward_profile", type=str, default="legacy_easyuuv_v0", help="Reward profile label.")
parser.add_argument("--phase46_summary_path", type=str, default=None, help="Optional Phase 4.6 summary path.")
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

if args_cli.video:
    args_cli.enable_cameras = True

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app
print("[EASYUUV][TRAIN] Isaac app started; importing post-app modules", flush=True)

import gymnasium as gym
import torch
import traceback
from rsl_rl.runners import OnPolicyRunner

from discover_ppo_checkpoints import discover_ppo_checkpoints
from easyuuv_task_registration import register_easyuuv_task
from isaaclab_compat import RslRlOnPolicyRunnerCfg, RslRlVecEnvWrapper, get_checkpoint_path, parse_env_cfg

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


def configure_phase46_legacy_env(env_cfg) -> None:
    if hasattr(env_cfg, "controller_mode"):
        env_cfg.controller_mode = "legacy"
    if hasattr(env_cfg, "control_method"):
        env_cfg.control_method = "Ssurface"
    if hasattr(env_cfg, "reward_profile"):
        env_cfg.reward_profile = args_cli.reward_profile


def parse_env_config(num_envs: int):
    return parse_env_cfg(
        args_cli.task,
        device=getattr(args_cli, "device", "cuda:0"),
        num_envs=num_envs,
        use_fabric=not args_cli.disable_fabric,
    )


def write_phase46_training_summary(log_dir: str, agent_cfg: RslRlOnPolicyRunnerCfg) -> None:
    discovery = discover_ppo_checkpoints([log_dir])
    selected_checkpoint = discovery.get("selected_checkpoint")
    summary = {
        "result_bucket": args_cli.result_bucket,
        "ppo_evidence_level": args_cli.ppo_evidence_level,
        "reward_profile": args_cli.reward_profile,
        "controller_path": "legacy/Ssurface",
        "checkpoint_found": bool(discovery.get("checkpoint_found")),
        "checkpoint_path": selected_checkpoint,
        "selected_checkpoint": selected_checkpoint,
        "selected_rule": discovery.get("selected_rule"),
        "training_iterations": agent_cfg.max_iterations,
        "save_interval": agent_cfg.save_interval,
        "action_dim": 4,
        "observation_dim": 9,
        "pwm_dim": 8,
        "log_dir": log_dir,
        "allowed_claims": [
            "PPO/RSL-RL training entrypoint can run under the selected controller path",
            "Checkpoint evidence is present only when checkpoint_found is true",
        ],
        "disallowed_claims": [
            "PPO convergence is proven",
            "PPO+Koopman performance is proven",
            "old PPO semantics are losslessly migrated",
        ],
    }
    summary_path = args_cli.phase46_summary_path or os.path.join(log_dir, "phase46_training_summary.json")
    os.makedirs(os.path.dirname(os.path.abspath(summary_path)), exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)
    print(f"[INFO]: Wrote Phase 4.6 training summary to: {summary_path}")


def main() -> None:
    print("[EASYUUV][TRAIN] Entering main()", flush=True)
    register_easyuuv_task()
    env_cfg = parse_env_config(args_cli.num_envs)
    configure_phase46_legacy_env(env_cfg)
    agent_cfg: RslRlOnPolicyRunnerCfg = cli_args.parse_rsl_rl_cfg(args_cli.task, args_cli)

    if args_cli.max_iterations is not None:
        agent_cfg.max_iterations = args_cli.max_iterations
    if args_cli.save_interval is not None:
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

    env = RslRlVecEnvWrapper(env)
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
    write_phase46_training_summary(log_dir, agent_cfg)
    env.close()


if __name__ == "__main__":
    print("[EASYUUV][TRAIN] __main__ guard reached", flush=True)
    try:
        main()
    except BaseException:
        print("[EASYUUV][TRAIN] Unhandled exception follows", flush=True)
        traceback.print_exc()
        raise
    finally:
        simulation_app.close()
else:
    print(f"[EASYUUV][TRAIN] Loaded without __main__; __name__={__name__}", flush=True)

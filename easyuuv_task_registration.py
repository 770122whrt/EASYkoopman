"""Gym registration for EasyUUV from a normal repository checkout."""

from __future__ import annotations

import gymnasium as gym

try:
    from . import agents
    from .easyuuv_env import EasyUUVEnv, EasyUUVEnvCfg
except ImportError:
    import agents
    from easyuuv_env import EasyUUVEnv, EasyUUVEnvCfg


TASK_ID = "EasyUUV-Direct-v1"


def register_easyuuv_task() -> None:
    if TASK_ID in gym.registry:
        return

    gym.register(
        id="EasyUUV-Direct-v1",
        entry_point=EasyUUVEnv,
        disable_env_checker=True,
        kwargs={
            "env_cfg_entry_point": EasyUUVEnvCfg,
            "rsl_rl_cfg_entry_point": agents.rsl_rl_ppo_cfg.EasyUUVPPORunnerCfg,
        },
    )

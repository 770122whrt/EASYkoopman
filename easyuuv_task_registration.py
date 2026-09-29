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


def register_gym_tasks() -> None:
    expected_kwargs = {
        "env_cfg_entry_point": EasyUUVEnvCfg,
        "rsl_rl_cfg_entry_point": agents.rsl_rl_ppo_cfg.EasyUUVPPORunnerCfg,
    }
    if TASK_ID in gym.registry:
        specification = gym.spec(TASK_ID)
        if not (
            specification.entry_point is EasyUUVEnv
            and specification.disable_env_checker is True
            and specification.kwargs == expected_kwargs
        ):
            raise RuntimeError(f"task_registration_conflict:{TASK_ID}")
        return

    gym.register(
        id="EasyUUV-Direct-v1",
        entry_point=EasyUUVEnv,
        disable_env_checker=True,
        kwargs=expected_kwargs,
    )


def register_easyuuv_task() -> None:
    """Backward-compatible alias for older callers."""
    register_gym_tasks()

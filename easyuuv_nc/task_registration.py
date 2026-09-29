"""Explicit, fail-closed Gym task registration for EasyUUV-NC.

Importing this module is safe before Isaac's :class:`AppLauncher` starts.  The
Gym and environment imports are intentionally delayed until
:func:`register_gym_tasks` is called by an app-started consumer.
"""

from __future__ import annotations

from typing import Any


_ENTRY = "easyuuv_nc.env:EasyUUVEnv"
GYM_TASK_IDS = (
    "EasyUUV-Direct-v1",
    "EasyUUV-Direct-Parametric-v1",
    "EasyUUV-Direct-Parametric-SatObs-v1",
    "EasyUUV-Direct-Parametric-Wide256-v1",
)


def _expected_registrations() -> tuple[dict[str, Any], ...]:
    import gymnasium as gym  # noqa: F401 - import is deliberately post-AppLauncher

    from .env import (
        EasyUUVEnvCfg,
        EasyUUVParametricEnvCfg,
        EasyUUVParametricSatObsEnvCfg,
        agents,
    )

    return (
        dict(
            id="EasyUUV-Direct-v1",
            env_cfg=EasyUUVEnvCfg,
            runner_cfg=agents.rsl_rl_ppo_cfg.EasyUUVPPORunnerCfg,
        ),
        dict(
            id="EasyUUV-Direct-Parametric-v1",
            env_cfg=EasyUUVParametricEnvCfg,
            runner_cfg=agents.rsl_rl_ppo_cfg.EasyUUVParametricPPORunnerCfg,
        ),
        dict(
            id="EasyUUV-Direct-Parametric-SatObs-v1",
            env_cfg=EasyUUVParametricSatObsEnvCfg,
            runner_cfg=agents.rsl_rl_ppo_cfg.EasyUUVParametricPPORunnerCfg,
        ),
        dict(
            id="EasyUUV-Direct-Parametric-Wide256-v1",
            env_cfg=EasyUUVParametricEnvCfg,
            runner_cfg=agents.rsl_rl_ppo_cfg.EasyUUVParametricWide256PPORunnerCfg,
        ),
    )


def _registration_matches(spec: Any, expected_kwargs: dict[str, Any]) -> bool:
    return (
        getattr(spec, "entry_point", None) == _ENTRY
        and getattr(spec, "disable_env_checker", None) is True
        and getattr(spec, "kwargs", None) == expected_kwargs
    )


def register_gym_tasks() -> tuple[str, ...]:
    """Register all four public tasks after AppLauncher, or reject conflicts.

    Repeated calls are safe only when every existing Gym specification is
    exactly the one this package owns.  A process cannot silently retain a task
    registered by a different EasyUUV checkout or environment implementation.
    """
    import gymnasium as gym

    registrations = _expected_registrations()
    expected_by_id = {
        registration["id"]: {
            "env_cfg_entry_point": registration["env_cfg"],
            "rsl_rl_cfg_entry_point": registration["runner_cfg"],
        }
        for registration in registrations
    }

    for task_id, expected_kwargs in expected_by_id.items():
        if task_id in gym.registry and not _registration_matches(
            gym.spec(task_id), expected_kwargs
        ):
            raise RuntimeError(f"task_registration_conflict:{task_id}")

    for task_id, expected_kwargs in expected_by_id.items():
        if task_id not in gym.registry:
            gym.register(
                id=task_id,
                entry_point=_ENTRY,
                disable_env_checker=True,
                kwargs=expected_kwargs,
            )

    return GYM_TASK_IDS

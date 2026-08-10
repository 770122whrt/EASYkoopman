"""EasyUUV-NC package facade with explicit post-AppLauncher registration.

The package may be imported by Isaac-free catalog and validation code.  Runtime
environment imports therefore happen only through :func:`register_gym_tasks`
or a legacy attribute lookup after Isaac has started.
"""

from __future__ import annotations

from .task_registration import GYM_TASK_IDS, register_gym_tasks


_LAZY_ENV_EXPORTS = {
    "EasyUUVEnv",
    "EasyUUVEnvCfg",
    "EasyUUVParametricEnvCfg",
    "EasyUUVParametricSatObsEnvCfg",
    "agents",
}


def __getattr__(name: str):
    """Preserve legacy environment attributes without preloading Isaac."""
    if name not in _LAZY_ENV_EXPORTS:
        raise AttributeError(name)
    from . import env

    return getattr(env, name)


__all__ = ["GYM_TASK_IDS", "register_gym_tasks", *_LAZY_ENV_EXPORTS]

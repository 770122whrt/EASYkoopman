# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""EasyUUV-NC: 去伪存真重构后的干净子仓库。

设计要点（相对 legacy easyuuv_stdw）：
- **干净包名**：不再物理伪装成 ``omni.isaac.lab_tasks.direct.easyuuv_stdw``，因此
  gym entry_point 用普通模块路径 ``easyuuv_nc.env:EasyUUVEnv``，
  **彻底删除** legacy ``_bootstrap_local_lab_tasks_package()`` importlib 注入 hack。
- **剔除死分支**：不注册 DCE 变体（B5 ii-b 已证伪）。
- 环境本体零依赖 ``omni.isaac.lab_tasks``；只用核心 ``omni.isaac.lab`` + ``rsl_rl``。

运行须知：本机 ``run_with_isaac_env.sh`` 的 ``exec python "$@"`` 会误解析相对脚本路径，
统一用：``export PYTHONPATH=$(pwd):$PYTHONPATH && conda run -n isaaclab python <script>``。
"""

try:
    import gymnasium as gym

    from .env import (
        EasyUUVEnv,
        EasyUUVEnvCfg,
        EasyUUVParametricEnvCfg,
        EasyUUVParametricSatObsEnvCfg,
        agents,
    )
except ModuleNotFoundError as exc:
    # 让 easyuuv_nc 在缺少 Isaac Sim / omni.kit 的机器上仍可 import（仅注册需要 Isaac）。
    missing_name = getattr(exc, "name", "")
    if missing_name not in {"gymnasium"} and not str(missing_name).startswith("omni"):
        raise
    gym = None
    agents = None
    EasyUUVEnv = EasyUUVEnvCfg = EasyUUVParametricEnvCfg = EasyUUVParametricSatObsEnvCfg = None


if gym is not None:
    _ENTRY = "easyuuv_nc.env:EasyUUVEnv"

    gym.register(
        id="EasyUUV-Direct-v1",
        entry_point=_ENTRY,
        disable_env_checker=True,
        kwargs={
            "env_cfg_entry_point": EasyUUVEnvCfg,
            "rsl_rl_cfg_entry_point": agents.rsl_rl_ppo_cfg.EasyUUVPPORunnerCfg,
        },
    )

    gym.register(
        id="EasyUUV-Direct-Parametric-v1",
        entry_point=_ENTRY,
        disable_env_checker=True,
        kwargs={
            "env_cfg_entry_point": EasyUUVParametricEnvCfg,
            "rsl_rl_cfg_entry_point": agents.rsl_rl_ppo_cfg.EasyUUVParametricPPORunnerCfg,
        },
    )

    gym.register(
        id="EasyUUV-Direct-Parametric-SatObs-v1",
        entry_point=_ENTRY,
        disable_env_checker=True,
        kwargs={
            "env_cfg_entry_point": EasyUUVParametricSatObsEnvCfg,
            "rsl_rl_cfg_entry_point": agents.rsl_rl_ppo_cfg.EasyUUVParametricPPORunnerCfg,
        },
    )

    # wide256 变体：Phase-8 免训练在线自适应主用 checkpoint 的 runner cfg（[256,256]）。
    gym.register(
        id="EasyUUV-Direct-Parametric-Wide256-v1",
        entry_point=_ENTRY,
        disable_env_checker=True,
        kwargs={
            "env_cfg_entry_point": EasyUUVParametricEnvCfg,
            "rsl_rl_cfg_entry_point": agents.rsl_rl_ppo_cfg.EasyUUVParametricWide256PPORunnerCfg,
        },
    )

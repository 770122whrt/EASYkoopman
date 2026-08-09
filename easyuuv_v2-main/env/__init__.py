# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""EasyUUV-NC environment subpackage.

干净包名重构：本子包不再伪装成 ``omni.isaac.lab_tasks.direct.easyuuv_stdw``，
因此不需要 legacy ``_bootstrap_local_lab_tasks_package()`` hack。环境本体只依赖
核心 ``omni.isaac.lab`` 与 ``rsl_rl``（见 agents/rsl_rl_ppo_cfg.py），gym 注册在
包根 ``easyuuv_nc/__init__.py`` 完成。
"""

from .easyuuv_env import (  # noqa: F401
    EasyUUVEnv,
    EasyUUVEnvCfg,
    EasyUUVParametricEnvCfg,
    EasyUUVParametricSatObsEnvCfg,
)
from . import agents  # noqa: F401

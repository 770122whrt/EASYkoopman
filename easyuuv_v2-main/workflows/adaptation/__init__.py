# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""``easyuuv_nc.workflows.adaptation`` — STDW 在线自适应的 helper 包。

由臃肿的 ``workflows/adapt.py``（~7070 行）拆分而来。``adapt.py`` 现退化为
"薄入口"：仅保留 ``main()`` + argparse/AppLauncher 编排，全部独立 helper 迁到
本包。函数体在迁移中逐字节保真（byte-identical），并通过 flip360 冒烟 CSV
byte-level 回归核对（见 docs/REFACTOR_GUIDE.md §3）。

模块职责边界：
- :mod:`.cli_parsers`   —— CLI 参数解析小工具（bool/axes/p_diag/grad_mask...）。
- :mod:`.policy`        —— policy forward / L2 / RNG 状态 / 向量相关。
- :mod:`.pose`          —— 位姿读取 / 四元数 / 跟踪误差方向 / direction-gate。
- :mod:`.zeta`          —— 4-D zeta4 乘子 / 深度地板 / surrogate & runtime 写入。
- :mod:`.action_bridge` —— action_bridge residual / 部署侧 reduced-action-anchor。
- :mod:`.failsafe`      —— 解析式 s-surface / Task A 深度 failsafe（正交 fast-loop）。
- :mod:`.pseudo_action` —— 低层修正 / 逆动力学对角 / pseudo-action 目标构造。
- :mod:`.phase56`       —— Phase56 FM 桥接 runtime 监控 / 曲率诊断 / live contract。
- :mod:`.env_io`        —— drift router / 初始扰动 / reset / 快照 / checkpoint 保存。
"""

from __future__ import annotations

from .cli_parsers import (
    _bool_arg,
    _format_axes,
    _parse_axes,
    _parse_channel_indices,
    _parse_p_diag,
    _parse_zeta_grad_mask,
)
from .policy import (
    _capture_torch_rng_state,
    _policy_forward_eval,
    _policy_forward_train,
    _policy_param_l2,
    _restore_torch_rng_state,
    _safe_vector_corr,
    _tensor_1d_list,
)
from .pose import (
    _direction_gate_correction_direction,
    _get_desired_pose,
    _get_true_pose,
    _quat_conjugate,
    _quat_mul,
    _tracking_error_direction,
)
from .zeta import (
    _apply_runtime_zeta4_update,
    _apply_zeta4_surrogate,
    _bounded_multiplier_to_delta,
    _effective_zeta4_multipliers,
    _enforce_zeta_depth_floor_,
    _zeta4_multipliers,
)
from .action_bridge import (
    _apply_action_bridge_residual_write,
    _apply_deployed_action_bridge_residual,
    _apply_deployed_reduced_action_anchor,
)
from .failsafe import (
    _analytic_s_surface_action,
    _apply_analytic_action_shim,
    _apply_task_a_depth_failsafe_shim,
)
from .pseudo_action import (
    _build_pseudo_action_target,
    _read_jacobian_inv_diag,
    _read_low_level_correction,
)
from .phase56 import (
    PHASE56_RUNTIME_FEATURE_SETS,
    PHASE56_RUNTIME_HARD_THRESHOLDS,
    PHASE56_RUNTIME_SOFT_THRESHOLDS,
    _phase56_curvature_relative_defaults,
    _phase56_curvature_relative_row,
    _phase56_curvature_relative_summary,
    _phase56_flow_cfg,
    _phase56_prepare_live_bundle,
    _phase56_runtime_execution_directives,
    _phase56_runtime_feature_vector,
    _phase56_runtime_live_contract,
    _phase56_runtime_monitor_defaults,
    _phase56_runtime_state_step,
    _phase56_standardize,
    _phase8_fm_midpoint_state_anchor,
)
from .env_io import (
    _phase4a_anchor_contract,
    _phase4a_empty_anchor_contract,
    _read_initial_cob_xy,
    _reset_wrapper_env,
    _resolve_drift_router,
    _runtime_control_snapshot,
    _runtime_reference_context,
    _save_stdw_checkpoint,
    _set_initial_disturbance,
)

__all__ = [
    # cli_parsers
    "_bool_arg", "_parse_axes", "_parse_p_diag", "_parse_zeta_grad_mask",
    "_parse_channel_indices", "_format_axes",
    # policy
    "_policy_forward_eval", "_policy_forward_train", "_policy_param_l2",
    "_capture_torch_rng_state", "_restore_torch_rng_state", "_safe_vector_corr",
    "_tensor_1d_list",
    # pose
    "_quat_conjugate", "_quat_mul", "_get_true_pose", "_get_desired_pose",
    "_tracking_error_direction", "_direction_gate_correction_direction",
    # zeta
    "_zeta4_multipliers", "_effective_zeta4_multipliers", "_bounded_multiplier_to_delta",
    "_enforce_zeta_depth_floor_", "_apply_zeta4_surrogate", "_apply_runtime_zeta4_update",
    # action_bridge
    "_apply_action_bridge_residual_write", "_apply_deployed_action_bridge_residual",
    "_apply_deployed_reduced_action_anchor",
    # failsafe
    "_analytic_s_surface_action", "_apply_analytic_action_shim",
    "_apply_task_a_depth_failsafe_shim",
    # pseudo_action
    "_read_low_level_correction", "_read_jacobian_inv_diag", "_build_pseudo_action_target",
    # phase56
    "PHASE56_RUNTIME_FEATURE_SETS", "PHASE56_RUNTIME_SOFT_THRESHOLDS",
    "PHASE56_RUNTIME_HARD_THRESHOLDS",
    "_phase56_runtime_monitor_defaults", "_phase56_curvature_relative_defaults",
    "_phase56_curvature_relative_row", "_phase56_curvature_relative_summary",
    "_phase56_flow_cfg", "_phase56_standardize", "_phase56_prepare_live_bundle",
    "_phase56_runtime_feature_vector", "_phase56_runtime_state_step",
    "_phase56_runtime_execution_directives", "_phase56_runtime_live_contract",
    "_phase8_fm_midpoint_state_anchor",
    "_phase4a_empty_anchor_contract", "_phase4a_anchor_contract",
    # env_io
    "_read_initial_cob_xy", "_resolve_drift_router", "_set_initial_disturbance",
    "_reset_wrapper_env", "_runtime_control_snapshot", "_runtime_reference_context",
    "_save_stdw_checkpoint",
]

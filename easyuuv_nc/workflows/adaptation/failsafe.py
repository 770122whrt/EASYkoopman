# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""解析式 s-surface 动作 / analytic shim / Task A 深度 failsafe (正交 fast-loop)。

（由 adapt.py 拆分而来，函数体逐字节保真。）
"""

from __future__ import annotations

import numpy as np
import torch

from easyuuv_nc.stdw_integration import convert_depth_to_v1
from .pose import _get_true_pose, _quat_conjugate, _quat_mul
from .env_io import _runtime_control_snapshot


def _analytic_s_surface_action(
    raw_obs: torch.Tensor,
    *,
    action_dim: int,
    depth_target: float,
    roll_pitch_action_lim: float,
    yaw_action_lim: float,
    depth_action_lim: float,
) -> torch.Tensor:
    """Build normalized S-surface action from raw EasyUUV observation.

    Observation layout is env-local: goal quaternion (4), true z (1), root
    quaternion (4), optional body angular velocity (3).  The first three action
    channels are body-frame SO(3) error `2*sgn(w)*vec(q_curr^-1*q_goal)`,
    normalized by the same action limits the env will multiply back in
    `_pid_control`.  The depth channel is `(target_depth - z) / depth_lim`.
    """
    if raw_obs.ndim == 1:
        raw_obs = raw_obs.unsqueeze(0)
    device = raw_obs.device
    dtype = raw_obs.dtype
    q_goal = raw_obs[:, 0:4]
    true_z = raw_obs[:, 4:5]
    q_curr = raw_obs[:, 5:9]
    q_err = _quat_mul(_quat_conjugate(q_curr), q_goal)
    sign = torch.where(q_err[:, 0:1] >= 0.0, torch.ones_like(q_err[:, 0:1]), -torch.ones_like(q_err[:, 0:1]))
    e_r = 2.0 * sign * q_err[:, 1:4]
    limits = torch.tensor(
        [roll_pitch_action_lim, roll_pitch_action_lim, yaw_action_lim],
        device=device,
        dtype=dtype,
    ).reshape(1, 3).clamp_min(1.0e-6)
    depth_lim = max(float(depth_action_lim), 1.0e-6)
    ctrl = torch.zeros(raw_obs.shape[0], max(action_dim, 4), device=device, dtype=dtype)
    ctrl[:, 0:3] = e_r / limits
    ctrl[:, 3:4] = (float(depth_target) - true_z) / depth_lim
    return torch.clamp(ctrl[:, :action_dim], -1.0, 1.0)


def _apply_analytic_action_shim(
    raw_obs: torch.Tensor,
    policy_action: torch.Tensor,
    ref_action: torch.Tensor | None,
    args,
) -> torch.Tensor:
    if args.analytic_action_mode == "off":
        return policy_action
    analytic = _analytic_s_surface_action(
        raw_obs,
        action_dim=policy_action.shape[-1],
        depth_target=float(args.analytic_depth_target),
        roll_pitch_action_lim=float(args.analytic_roll_pitch_action_lim),
        yaw_action_lim=float(args.analytic_yaw_action_lim),
        depth_action_lim=float(args.analytic_depth_action_lim),
    )
    out = policy_action.clone()
    if args.analytic_action_mode == "analytic":
        out[:, 0:4] = analytic[:, 0:4]
    elif args.analytic_action_mode == "residual_from_start":
        if ref_action is None:
            raise RuntimeError("analytic residual mode requires a frozen reference action")
        out[:, 0:4] = analytic[:, 0:4] + float(args.analytic_residual_scale) * (
            policy_action[:, 0:4] - ref_action[:, 0:4].detach()
        )
    else:
        raise RuntimeError(f"unknown analytic_action_mode {args.analytic_action_mode!r}")
    if out.shape[-1] > 4:
        if args.analytic_gain_mode == "zero":
            out[:, 4:] = 0.0
        elif args.analytic_gain_mode == "residual_from_start":
            if ref_action is None:
                raise RuntimeError("analytic gain residual mode requires a frozen reference action")
            out[:, 4:] = float(args.analytic_residual_scale) * (
                policy_action[:, 4:] - ref_action[:, 4:].detach()
            )
        elif args.analytic_gain_mode == "policy":
            out[:, 4:] = policy_action[:, 4:]
        else:
            raise RuntimeError(f"unknown analytic_gain_mode {args.analytic_gain_mode!r}")
    return torch.clamp(out, -1.0, 1.0)


def _apply_task_a_depth_failsafe_shim(
    *,
    raw_obs: torch.Tensor,
    action: torch.Tensor,
    env,
    args,
    depth_reference_frame: str,
    depth_surface_z: float,
    sswp_ema: torch.Tensor | None,
    latched: bool,
) -> tuple[torch.Tensor, int, float, float, torch.Tensor | None, bool]:
    """Optional Task-A fast-loop depth failsafe. Default-off and deployable only."""

    mode = str(getattr(args, "task_a_depth_failsafe_mode", "off"))
    if mode == "off" or int(action.shape[-1]) < 4:
        return action, 0, 0.0, float("nan"), sswp_ema, False

    _, _, true_z, _, _, _ = _get_true_pose(env)
    true_depth_v1 = float(
        convert_depth_to_v1(
            true_z,
            reference_frame=depth_reference_frame,
            surface_z=depth_surface_z,
        )
    )
    enter_trigger = float(args.task_a_depth_failsafe_lower_trigger)
    release_trigger = float(args.task_a_depth_failsafe_release_trigger)
    if latched:
        if true_depth_v1 >= release_trigger:
            latched = False
    elif true_depth_v1 <= enter_trigger:
        latched = True
    if not latched:
        return action, 0, 0.0, true_depth_v1, sswp_ema, False

    out = action.clone()
    before = out[:, 3].clone()
    blend = min(max(float(args.task_a_depth_failsafe_blend), 0.0), 1.0)

    if mode == "analytic_depth_channel":
        depth_target_raw = (
            depth_surface_z + float(args.task_a_depth_failsafe_target_v1)
            if str(depth_reference_frame) == "surface_relative_depth"
            else float(args.task_a_depth_failsafe_target_v1)
        )
        analytic = _analytic_s_surface_action(
            raw_obs,
            action_dim=action.shape[-1],
            depth_target=depth_target_raw,
            roll_pitch_action_lim=float(args.analytic_roll_pitch_action_lim),
            yaw_action_lim=float(args.analytic_yaw_action_lim),
            depth_action_lim=float(args.analytic_depth_action_lim),
        )
        out[:, 3] = (1.0 - blend) * out[:, 3] + blend * analytic[:, 3]
    elif mode == "sswp_depth_channel":
        runtime_control = _runtime_control_snapshot(env, True)
        runtime_pid = runtime_control.get("runtime_pid_value", [])
        if not isinstance(runtime_pid, list) or not runtime_pid:
            return action, 0, 0.0, true_depth_v1, sswp_ema, latched
        runtime_pid_arr = np.asarray(runtime_pid, dtype=float)
        low_level_delta_arr = np.zeros(int(action.shape[-1]), dtype=float)
        count = min(low_level_delta_arr.size, runtime_pid_arr.size)
        low_level_delta_arr[:count] = runtime_pid_arr[:count]
        low_level_delta = torch.as_tensor(
            low_level_delta_arr, device=action.device, dtype=action.dtype
        )
        beta = min(max(float(args.phase4a_sswp_beta), 0.0), 0.999999)
        if sswp_ema is None or sswp_ema.shape != low_level_delta.shape:
            sswp_ema = torch.zeros_like(low_level_delta)
        sswp_ema = beta * sswp_ema + (1.0 - beta) * low_level_delta
        out[:, 3] = torch.clamp(
            out[:, 3] - float(args.task_a_depth_failsafe_sswp_scale) * sswp_ema[3],
            -1.0,
            1.0,
        )
    else:
        raise RuntimeError(f"unknown task_a_depth_failsafe_mode {mode!r}")

    out = torch.clamp(out, -1.0, 1.0)
    delta_norm = float(torch.linalg.norm(out[:, 3] - before).item())
    return out, 1, delta_norm, true_depth_v1, sswp_ema, latched


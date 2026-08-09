# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""位姿读取 / 四元数运算 / 跟踪误差方向 / direction-gate 方向。

（由 adapt.py 拆分而来，函数体逐字节保真。）
"""

from __future__ import annotations

import math

import torch

from easyuuv_nc.stdw_integration import angle_remap, convert_depth_to_v1


def _quat_conjugate(q: torch.Tensor) -> torch.Tensor:
    return torch.cat([q[..., 0:1], -q[..., 1:4]], dim=-1)


def _quat_mul(q1: torch.Tensor, q2: torch.Tensor) -> torch.Tensor:
    w1, x1, y1, z1 = q1.unbind(dim=-1)
    w2, x2, y2, z2 = q2.unbind(dim=-1)
    return torch.stack(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ],
        dim=-1,
    )


def _get_true_pose(env):
    from omni.isaac.lab.utils.math import euler_xyz_from_quat  # lazy: omni 需 AppLauncher 先启动

    root_pos = env.unwrapped._robot.data.root_pos_w[0]
    root_quat = env.unwrapped._robot.data.root_quat_w[0]
    true_roll, true_pitch, true_yaw = euler_xyz_from_quat(root_quat.unsqueeze(0))
    return (
        float(root_pos[0].item()),
        float(root_pos[1].item()),
        float(root_pos[2].item()),
        float(angle_remap(true_roll)[0].item()),
        float(angle_remap(true_pitch)[0].item()),
        float(angle_remap(true_yaw)[0].item()),
    )


def _get_desired_pose(env):
    from omni.isaac.lab.utils.math import euler_xyz_from_quat  # lazy: omni 需 AppLauncher 先启动

    desired_quat = env.unwrapped._goal[0]
    des_roll, des_pitch, des_yaw = euler_xyz_from_quat(desired_quat.unsqueeze(0))
    des_depth = float(env.unwrapped.cfg.starting_depth)
    return (
        float(angle_remap(des_roll)[0].item()),
        float(angle_remap(des_pitch)[0].item()),
        float(angle_remap(des_yaw)[0].item()),
        des_depth,
    )


def _tracking_error_direction(
    env,
    *,
    batch_shape: torch.Size,
    device: torch.device,
    dtype: torch.dtype,
    depth_reference_frame: str,
    depth_surface_z: float,
) -> torch.Tensor:
    """Build a deployable 4-D correction direction from live tracking error."""

    des_roll, des_pitch, des_yaw, des_depth = _get_desired_pose(env)
    _, _, true_z, true_roll, true_pitch, true_yaw = _get_true_pose(env)
    des_depth_v1 = float(
        convert_depth_to_v1(
            des_depth,
            reference_frame=depth_reference_frame,
            surface_z=depth_surface_z,
        )
    )
    true_depth_v1 = float(
        convert_depth_to_v1(
            true_z,
            reference_frame=depth_reference_frame,
            surface_z=depth_surface_z,
        )
    )
    error_vec = torch.tensor(
        [
            des_roll - true_roll,
            des_pitch - true_pitch,
            math.atan2(math.sin(des_yaw - true_yaw), math.cos(des_yaw - true_yaw)),
            des_depth_v1 - true_depth_v1,
        ],
        device=device,
        dtype=dtype,
    )
    view_shape = (1,) * (len(batch_shape) - 1) + (4,)
    return error_vec.reshape(view_shape).expand(batch_shape)


def _direction_gate_correction_direction(
    *,
    source: str,
    action_before: torch.Tensor,
    pseudo_anchor: torch.Tensor,
    target_anchor: torch.Tensor | None,
    env,
    depth_reference_frame: str,
    depth_surface_z: float,
) -> torch.Tensor:
    """Return the action-space correction direction used by direction_gate."""

    if source == "tracking_error":
        return _tracking_error_direction(
            env,
            batch_shape=action_before.shape,
            device=action_before.device,
            dtype=action_before.dtype,
            depth_reference_frame=depth_reference_frame,
            depth_surface_z=depth_surface_z,
        )
    if source == "target_anchor":
        if target_anchor is None:
            raise RuntimeError(
                "stdw_direction_gate_source=target_anchor requires an action-space target anchor."
            )
        anchor = target_anchor.to(action_before.device, action_before.dtype)
    else:
        anchor = pseudo_anchor.to(action_before.device, action_before.dtype)
    return anchor - action_before


# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""4-D zeta4 乘子 / 深度地板 / surrogate & runtime 写入。

（由 adapt.py 拆分而来，函数体逐字节保真。）
"""

from __future__ import annotations

import math

import numpy as np
import torch


def _zeta4_multipliers(zeta_delta: torch.Tensor, bound: float) -> torch.Tensor:
    """Return positive 4-D zeta multipliers around one.

    The bounded parameterization keeps Phase-8 online adaptation low-dimensional
    and prevents unbounded gain excursions while still allowing gradients to
    flow into zeta_delta.
    """

    return 1.0 + float(bound) * torch.tanh(zeta_delta.reshape(4))


def _effective_zeta4_multipliers(
    zeta_delta: torch.Tensor,
    bound: float,
    write_scale: float = 1.0,
) -> torch.Tensor:
    """Return deployment-side effective zeta multipliers."""

    mult = _zeta4_multipliers(zeta_delta, bound)
    return 1.0 + float(write_scale) * (mult - 1.0)


def _bounded_multiplier_to_delta(multiplier: float, bound: float) -> float:
    """Invert the bounded zeta parameterization for a target multiplier."""

    if not math.isfinite(float(multiplier)):
        raise ValueError("target multiplier must be finite")
    if float(bound) <= 0.0:
        raise ValueError("bound must be positive")
    normalized = (float(multiplier) - 1.0) / float(bound)
    normalized = max(min(normalized, 1.0 - 1.0e-6), -1.0 + 1.0e-6)
    return float(np.arctanh(normalized))


def _enforce_zeta_depth_floor_(
    zeta_delta: torch.Tensor | None,
    *,
    bound: float,
    min_multiplier: float,
) -> None:
    """Clamp the depth zeta channel to a minimum allowed multiplier in-place."""

    if zeta_delta is None or zeta_delta.numel() < 4:
        return
    if float(min_multiplier) <= 0.0:
        return
    if float(bound) <= 0.0:
        raise SystemExit("--stdw_zeta_depth_min_multiplier requires --stdw_zeta_bound > 0.")
    feasible_min = max(float(min_multiplier), 1.0 - float(bound) + 1.0e-6)
    feasible_min = min(feasible_min, 1.0 + float(bound) - 1.0e-6)
    current = float(_zeta4_multipliers(zeta_delta, bound)[3].detach().item())
    if current >= feasible_min:
        return
    floor_delta = _bounded_multiplier_to_delta(feasible_min, bound)
    with torch.no_grad():
        zeta_delta.data[3] = torch.as_tensor(
            floor_delta, device=zeta_delta.device, dtype=zeta_delta.dtype
        )


def _apply_zeta4_surrogate(
    action: torch.Tensor,
    zeta_delta: torch.Tensor,
    bound: float,
    write_scale: float = 1.0,
) -> torch.Tensor:
    """Differentiable surrogate for 4-D controller-gain modulation."""

    base = action.detach()
    n = min(4, int(base.shape[-1]))
    mult = _effective_zeta4_multipliers(zeta_delta, bound, write_scale).to(base.device, base.dtype)
    if n <= 0:
        return base.clone()
    if n < int(base.shape[-1]):
        tail = torch.ones(int(base.shape[-1]) - n, device=base.device, dtype=base.dtype)
        scale = torch.cat((mult[:n], tail), dim=0)
    else:
        scale = mult[:n]
    view_shape = (1,) * (base.ndim - 1) + (int(base.shape[-1]),)
    return base * scale.reshape(view_shape)


def _apply_runtime_zeta4_update(
    raw_env,
    rel_multiplier: torch.Tensor,
    *,
    attitude_zeta_path: str = "legacy_pid",
) -> None:
    """Persist accepted zeta updates into the underlying EasyUUV env."""

    underlying = raw_env.unwrapped
    rel = rel_multiplier.detach().to(dtype=torch.float32).cpu().tolist()
    if attitude_zeta_path == "geo_so3":
        if not hasattr(underlying, "apply_runtime_geo_zeta1_multipliers"):
            raise RuntimeError("geo_so3 runtime zeta path requested but env lacks apply_runtime_geo_zeta1_multipliers().")
        underlying.apply_runtime_geo_zeta1_multipliers(rel[:3])
        depth_only = [1.0, 1.0, 1.0, float(rel[3])]
        if hasattr(underlying, "apply_runtime_zeta1_multipliers"):
            underlying.apply_runtime_zeta1_multipliers(depth_only)
            return
        underlying.apply_pid_multipliers({"depth_zeta1": float(rel[3])})
        return
    if hasattr(underlying, "apply_runtime_zeta1_multipliers"):
        underlying.apply_runtime_zeta1_multipliers(rel)
        return
    # Fallback for older env objects; this is less robust under meta-control
    # restore, but keeps the branch usable in partial checkouts.
    axes = ("roll", "pitch", "yaw", "depth")
    underlying.apply_pid_multipliers({f"{axis}_zeta1": float(value) for axis, value in zip(axes, rel)})


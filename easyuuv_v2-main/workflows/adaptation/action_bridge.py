# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""action_bridge residual 写入 / 部署侧 reduced-action-anchor。

（由 adapt.py 拆分而来，函数体逐字节保真。）
"""

from __future__ import annotations

from typing import Optional

import torch

from .zeta import _effective_zeta4_multipliers


def _apply_action_bridge_residual_write(
    *,
    base_action: torch.Tensor,
    action: torch.Tensor,
    anchor_action: torch.Tensor,
    zeta_delta: torch.Tensor,
    bound: float,
    residual_scale: float,
    residual_clip: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Optional direct residual write toward the action_bridge anchor."""

    out = action.clone()
    residual_term = torch.zeros_like(out)
    if abs(float(residual_scale)) <= 0.0:
        return out, residual_term
    n = min(4, int(out.shape[-1]), int(base_action.shape[-1]), int(anchor_action.shape[-1]))
    if n <= 0:
        return out, residual_term
    residual = anchor_action[..., :n] - base_action[..., :n]
    if float(residual_clip) > 0.0:
        residual = residual.clamp(-float(residual_clip), float(residual_clip))
    mult_delta = _effective_zeta4_multipliers(zeta_delta, bound, 1.0).to(out.device, out.dtype)[:n] - 1.0
    view_shape = (1,) * (out.ndim - 1) + (n,)
    residual_term[..., :n] = (
        float(residual_scale) * mult_delta.reshape(view_shape) * residual
    )
    out[..., :n] = out[..., :n] + residual_term[..., :n]
    return out, residual_term


def _apply_deployed_action_bridge_residual(
    *,
    action: torch.Tensor,
    residual_basis: Optional[torch.Tensor],
    deployed_multiplier: Optional[torch.Tensor],
    residual_scale: float,
    residual_clip: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Apply the latest accepted action-bridge residual in the fast loop."""

    out = action.clone()
    residual_term = torch.zeros_like(out)
    if residual_basis is None or deployed_multiplier is None or abs(float(residual_scale)) <= 0.0:
        return out, residual_term
    n = min(4, int(out.shape[-1]), int(residual_basis.numel()), int(deployed_multiplier.numel()))
    if n <= 0:
        return out, residual_term
    residual = residual_basis[:n].to(out.device, out.dtype)
    if float(residual_clip) > 0.0:
        residual = residual.clamp(-float(residual_clip), float(residual_clip))
    mult_delta = deployed_multiplier[:n].to(out.device, out.dtype) - 1.0
    view_shape = (1,) * (out.ndim - 1) + (n,)
    residual_term[..., :n] = (
        float(residual_scale)
        * mult_delta.reshape(view_shape)
        * residual.reshape(view_shape)
    )
    out[..., :n] = out[..., :n] + residual_term[..., :n]
    return out, residual_term


def _apply_deployed_reduced_action_anchor(
    *,
    action: torch.Tensor,
    residual_basis: Optional[torch.Tensor],
    anchor_scale: float,
    anchor_clip: float,
    channels: str,
    sswp_sign_ema: Optional[torch.Tensor] = None,
    tracking_error_dir: Optional[torch.Tensor] = None,
    use_sswp_sign: bool = False,
    dual_source_gate: bool = False,
    consensus_gate: bool = False,
    consensus_preferred_sign: bool = False,
) -> tuple[torch.Tensor, torch.Tensor, dict[str, float]]:
    """Apply the latest accepted direct action-anchor residual in the fast loop."""

    out = action.clone()
    residual_term = torch.zeros_like(out)
    stats = {
        "consensus_changed_frac": float("nan"),
        "raw_sswp_match_frac": float("nan"),
        "raw_track_match_frac": float("nan"),
        "sswp_track_agree_frac": float("nan"),
    }
    if residual_basis is None or abs(float(anchor_scale)) <= 0.0:
        return out, residual_term, stats
    if str(channels) == "attitude":
        n = min(3, int(out.shape[-1]), int(residual_basis.numel()))
    else:
        n = min(4, int(out.shape[-1]), int(residual_basis.numel()))
    if n <= 0:
        return out, residual_term, stats
    residual = residual_basis[:n].to(out.device, out.dtype)
    if float(anchor_clip) > 0.0:
        residual = residual.clamp(-float(anchor_clip), float(anchor_clip))
    raw_residual = residual.clone()
    raw_sign = torch.sign(residual)
    track_sign = None
    sswp_sign = None
    if tracking_error_dir is not None and (
        bool(consensus_gate) or bool(consensus_preferred_sign)
    ):
        track_vec = tracking_error_dir.reshape(-1).to(out.device, out.dtype)
        if track_vec.numel() >= n:
            track_sign = torch.sign(track_vec[:n])
    if sswp_sign_ema is not None and (bool(use_sswp_sign) or bool(dual_source_gate)):
        oracle = sswp_sign_ema[:n].to(out.device, out.dtype)
        oracle_sign = -torch.sign(oracle)
        oracle_sign = torch.where(oracle_sign == 0, raw_sign, oracle_sign)
        sswp_sign = oracle_sign.clone()
        if bool(use_sswp_sign):
            residual = residual.abs() * oracle_sign
        if bool(dual_source_gate):
            keep = (raw_sign == 0) | (oracle_sign == 0) | (raw_sign == oracle_sign)
            residual = torch.where(keep, residual, torch.zeros_like(residual))
    if sswp_sign_ema is not None and track_sign is not None and (
        bool(consensus_gate) or bool(consensus_preferred_sign)
    ):
        sswp_sign = -torch.sign(sswp_sign_ema[:n].to(out.device, out.dtype))
        sswp_sign = torch.where(sswp_sign == 0, track_sign, sswp_sign)
        track_sign = torch.where(track_sign == 0, sswp_sign, track_sign)
        agree = sswp_sign == track_sign
        if bool(consensus_gate):
            consensus_sign = torch.where(agree, track_sign, torch.zeros_like(track_sign))
            residual = torch.where(
                consensus_sign == 0,
                torch.zeros_like(residual),
                residual.abs() * consensus_sign,
            )
        elif bool(consensus_preferred_sign):
            preferred_sign = torch.where(agree, track_sign, raw_sign)
            preferred_sign = torch.where(preferred_sign == 0, raw_sign, preferred_sign)
            residual = residual.abs() * preferred_sign
        stats["raw_sswp_match_frac"] = float((raw_sign == sswp_sign).to(torch.float32).mean().item())
        stats["raw_track_match_frac"] = float((raw_sign == track_sign).to(torch.float32).mean().item())
        stats["sswp_track_agree_frac"] = float((sswp_sign == track_sign).to(torch.float32).mean().item())
    stats["consensus_changed_frac"] = float(
        (torch.sign(residual) != torch.sign(raw_residual)).to(torch.float32).mean().item()
    ) if raw_residual.numel() > 0 else float("nan")
    view_shape = (1,) * (out.ndim - 1) + (n,)
    residual_term[..., :n] = float(anchor_scale) * residual.reshape(view_shape)
    out[..., :n] = out[..., :n] + residual_term[..., :n]
    return out, residual_term, stats


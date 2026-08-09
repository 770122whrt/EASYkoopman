# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""低层修正读取 / 逆动力学对角 / pseudo-action 目标构造。

（由 adapt.py 拆分而来，函数体逐字节保真。）
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

import torch

from .cli_parsers import _parse_channel_indices, _parse_p_diag
from .failsafe import _analytic_s_surface_action


def _read_low_level_correction(stdw_wrapper: EasyUUVStdwWrapper, env, action_template: torch.Tensor) -> torch.Tensor:
    """Read the pseudo-label signal from env.unwrapped.

    Fix A v2 (DIAG_stdw_pseudo_label_mechanism_20260707 §10) decoupled the
    STDW pseudo-label from the in-loop correction. Prefer ``_pseudo_label_buf``
    which is the sanctioned read-only signal; fall back to ``_pid_value_add_buf``
    for backward compatibility when the env has not been rebuilt.

    Falls back to zeros when both fields are missing (e.g. self_adapt=False).
    """
    delta_u = stdw_wrapper.last_low_level.get("delta_u") if stdw_wrapper.last_low_level else None
    if delta_u is None:
        delta_u = getattr(env.unwrapped, "_pseudo_label_buf", None)
    if delta_u is None:
        delta_u = getattr(env.unwrapped, "_pid_value_add_buf", None)
    if delta_u is None or not isinstance(delta_u, torch.Tensor):
        return torch.zeros_like(action_template)
    delta_u = delta_u.to(device=action_template.device, dtype=action_template.dtype)
    if delta_u.shape != action_template.shape:
        try:
            delta_u = delta_u.reshape(action_template.shape)
        except Exception:
            return torch.zeros_like(action_template)
    return delta_u


def _read_jacobian_inv_diag(action_template: torch.Tensor) -> torch.Tensor:
    """4-channel allocation matrix is fixed; J_inv on this 4D space is identity diag."""
    return torch.ones_like(action_template)


def _build_pseudo_action_target(
    raw_obs: torch.Tensor,
    policy_action: torch.Tensor,
    stdw_wrapper: EasyUUVStdwWrapper,
    env,
    drift_frac: float,
    args,
) -> torch.Tensor:
    """Build the slow-loop pseudo target without touching the fast-loop control path.

    Default ``legacy_delta`` preserves the historical ``action + correction`` rule.
    Opt-in ``analytic_blend`` / ``analytic_residual`` / ``analytic_residual_error_gate`` keep the same action
    dimensionality but reshape the first four control channels toward an analytic
    S-surface action computed from the current observation, which gives OPR a
    directly interpretable target while leaving the fast loop untouched.
    """
    if not args.enable_pseudo_action:
        return policy_action.clone()

    mode = str(getattr(args, "pseudo_action_target_mode", "legacy_delta"))
    if mode in {"analytic_blend", "analytic_residual", "analytic_residual_error_gate"}:
        depth_target = float(getattr(env.unwrapped.cfg, "starting_depth", float(args.analytic_depth_target)))
        analytic_target = _analytic_s_surface_action(
            raw_obs,
            action_dim=policy_action.shape[-1],
            depth_target=depth_target,
            roll_pitch_action_lim=float(args.analytic_roll_pitch_action_lim),
            yaw_action_lim=float(args.analytic_yaw_action_lim),
            depth_action_lim=float(args.analytic_depth_action_lim),
        )
        target = policy_action.clone()
        if mode == "analytic_blend":
            mix = min(max(float(getattr(args, "pseudo_action_analytic_mix", 0.5)), 0.0), 1.0)
            target[:, 0:4] = (1.0 - mix) * policy_action[:, 0:4] + mix * analytic_target[:, 0:4]
        else:
            scale = float(getattr(args, "pseudo_action_residual_scale", 0.5))
            residual = analytic_target[:, 0:4] - policy_action[:, 0:4]
            clip_abs = float(getattr(args, "pseudo_action_residual_clip", 0.15))
            if clip_abs > 0.0:
                residual = torch.clamp(residual, -clip_abs, clip_abs)
            target[:, 0:4] = policy_action[:, 0:4]
            channel_ids = _parse_channel_indices(
                getattr(args, "pseudo_action_residual_channels", "0,1,2,3"),
                limit=min(4, policy_action.shape[-1]),
            )
            if not channel_ids:
                channel_ids = list(range(min(4, policy_action.shape[-1])))
            if mode == "analytic_residual_error_gate":
                injected = stdw_wrapper.last_extras or {}
                metric_name = str(getattr(args, "pseudo_action_error_gate_metric", "filtered_error"))
                if metric_name == "raw_error":
                    runtime_error = float(injected.get("stdw_raw_error", float("nan")))
                else:
                    runtime_error = float(injected.get("stdw_filt_error", float("nan")))
                if not math.isfinite(runtime_error) or runtime_error < float(
                    getattr(args, "pseudo_action_error_gate_threshold", 0.35)
                ):
                    return policy_action.clone()
            lyap_gate = str(getattr(args, "pseudo_action_lyapunov_gate", "off"))
            if lyap_gate != "off":
                injected = stdw_wrapper.last_extras or {}
                lyap_pass = float(injected.get("stdw_lyap_pass", float("nan")))
                if not math.isfinite(lyap_pass):
                    return policy_action.clone()
                certificate_passed = lyap_pass >= 0.5
                if lyap_gate == "require_pass" and not certificate_passed:
                    return policy_action.clone()
                if lyap_gate == "require_fail" and certificate_passed:
                    return policy_action.clone()
            descent_align = str(getattr(args, "pseudo_action_descent_align", "off"))
            if descent_align != "off":
                # Line 2: align the residual with the certified descent direction.
                # The S-surface analytic action is the error-reducing action, so it
                # is the action-space image of -grad(V); P weights high-Lyapunov
                # channels. align = sum_c P[c] * residual[c] * analytic[c].
                p_full = torch.tensor(
                    _parse_p_diag(getattr(args, "lyapunov_p_diag", "1.0,1.0,1.0,1.0")),
                    device=policy_action.device,
                    dtype=policy_action.dtype,
                )
                d = analytic_target[:, channel_ids]
                p_sub = p_full[channel_ids]
                r = residual[:, channel_ids]
                if not torch.isfinite(d).all() or not torch.isfinite(r).all():
                    return policy_action.clone()
                margin = float(getattr(args, "pseudo_action_descent_margin", 0.0))
                align_dot = (p_sub * r * d).sum(dim=-1, keepdim=True)
                aligned = align_dot > margin
                if descent_align == "gate":
                    r = torch.where(aligned, r, torch.zeros_like(r))
                else:  # project
                    denom = (p_sub * d * d).sum(dim=-1, keepdim=True).clamp_min(1.0e-12)
                    coeff = (align_dot / denom).clamp_min(0.0)
                    proj = coeff * d
                    r = torch.where(aligned, proj, torch.zeros_like(proj))
                residual = residual.clone()
                residual[:, channel_ids] = r
            injected_target = policy_action[:, channel_ids] + scale * residual[:, channel_ids]
            if bool(getattr(args, "pseudo_action_residual_sign_aware", False)):
                sign_mask = (analytic_target[:, channel_ids] * policy_action[:, channel_ids]) >= 0.0
                injected_target = torch.where(sign_mask, injected_target, policy_action[:, channel_ids])
            target[:, channel_ids] = injected_target
        return torch.clamp(target, -1.0, 1.0)

    delta_u = _read_low_level_correction(stdw_wrapper, env, policy_action)
    j_inv_diag = _read_jacobian_inv_diag(policy_action)
    decay = max(0.0, 1.0 - args.pseudo_decay * float(drift_frac))
    scaled_gain = args.pseudo_gain * decay
    raw_correction = scaled_gain * j_inv_diag * delta_u
    gate = float(args.pseudo_gate_limit)
    if gate > 0.0:
        correction = torch.clamp(raw_correction, -gate, gate)
    else:
        correction = raw_correction
    if not torch.isfinite(correction).all():
        return policy_action.clone()
    return torch.clamp(policy_action + correction, -1.0, 1.0)


# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Phase56 FM 桥接 runtime 监控 / 曲率诊断 / live contract / FM midpoint anchor。

（由 adapt.py 拆分而来，函数体逐字节保真。）
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from easyuuv_nc.stdw_integration.flow_matching import (
    FlowMatchingConfig,
    compute_path_curvature,
    integrate_flow_euler,
)
from easyuuv_nc.stdw_integration.phase56 import prepare_phase56_runtime_bundle
from easyuuv_nc.esuot.light import LightOTConfig


PHASE56_RUNTIME_FEATURE_SETS = {
    "core6": (
        "true_roll",
        "true_pitch",
        "true_yaw",
        "true_depth_v1",
        "runtime_motor_saturation_ratio",
        "runtime_motor_abs_max_raw",
    ),
    "core6_sswp": (
        "true_roll",
        "true_pitch",
        "true_yaw",
        "true_depth_v1",
        "runtime_motor_saturation_ratio",
        "runtime_motor_abs_max_raw",
        "phase4a_sswp_delta_norm",
        "phase4a_sswp_delta_abs_mean",
    ),
    "core6_sswp_fault": (
        "true_roll",
        "true_pitch",
        "true_yaw",
        "true_depth_v1",
        "runtime_motor_saturation_ratio",
        "runtime_motor_abs_max_raw",
        "phase4a_sswp_delta_norm",
        "phase4a_sswp_delta_abs_mean",
        "fault_efficiency_min",
        "depth_barrier_penalty",
    ),
}

PHASE56_RUNTIME_SOFT_THRESHOLDS = {
    "fm_path_curvature_runtime_warn": 0.05,
    "lyapunov_pass_rate_window_min": 0.8,
    "runtime_motor_saturation_ratio_warn": 0.9,
    "state_only_marginal_error_runtime_warn": 1.0e-4,
}

PHASE56_RUNTIME_HARD_THRESHOLDS = {
    "depth_violation_max": 0.0,
    "fm_path_curvature_runtime_max": 0.3,
    "lyapunov_pass_min": 0.5,
    "runtime_motor_saturation_ratio_max": 1.0,
    "state_only_marginal_error_runtime_max": 1.0e-2,
}



def _phase56_runtime_monitor_defaults(
    *,
    enabled: bool,
    ready: bool,
    target_alpha: float,
    current_state: str,
    transition: str = "",
) -> dict[str, object]:
    return {
        "phase56_runtime_binding": bool(enabled),
        "phase56_runtime_binding_ready": bool(ready),
        "phase56_runtime_target_alpha": float(target_alpha) if enabled else float("nan"),
        "fm_path_curvature_runtime": float("nan"),
        "state_only_marginal_error_runtime": float("nan"),
        "phase56_runtime_state": str(current_state),
        "phase56_runtime_state_transition": str(transition),
        "phase56_runtime_execution_hooks": False,
        "phase56_runtime_allows_update": False,
        "phase56_runtime_freeze_applied": False,
        "phase56_runtime_clear_freeze_applied": False,
        "phase56_runtime_zero_drift_applied": False,
        "phase56_runtime_requests_reset": False,
        "phase56_runtime_state_age": 0,
        "phase56_runtime_cycle_id": 0,
        "phase56_runtime_cycle_step": 0,
        "phase56_runtime_active_age": 0,
        "phase56_runtime_frozen_age": 0,
        "phase56_runtime_fallback_age": 0,
        "phase56_runtime_reset_age": 0,
        "phase56_runtime_reset_to_rearm_latency": float("nan"),
    }


def _phase56_curvature_relative_defaults(
    *,
    enabled: bool,
    baseline_source: str,
    baseline_window_label: str,
    baseline_p95: float,
    baseline_p99: float,
    window_size: int,
    scope_caveat: str,
    nonbinding_state: str = "disabled",
) -> dict[str, object]:
    return {
        "phase56_curvature_relative_enabled": bool(enabled),
        "phase56_curvature_baseline_source": str(baseline_source),
        "phase56_curvature_baseline_window_label": str(baseline_window_label),
        "phase56_curvature_baseline_p95": float(baseline_p95) if enabled else float("nan"),
        "phase56_curvature_baseline_p99": float(baseline_p99) if enabled else float("nan"),
        "phase56_curvature_minus_p95": float("nan"),
        "phase56_curvature_over_p95": float("nan"),
        "phase56_curvature_watch": False,
        "phase56_curvature_stress": False,
        "phase56_curvature_watch_window_count": 0,
        "phase56_curvature_stress_window_count": 0,
        "phase56_curvature_window_size": int(window_size),
        "phase56_curvature_nonbinding_state": str(nonbinding_state),
        "phase56_curvature_scope_caveat": str(scope_caveat),
    }


def _phase56_curvature_relative_row(
    *,
    enabled: bool,
    curvature_value: float,
    baseline_source: str,
    baseline_window_label: str,
    baseline_p95: float,
    baseline_p99: float,
    window_size: int,
    scope_caveat: str,
    watch_history: deque,
    stress_history: deque,
) -> dict[str, object]:
    row = _phase56_curvature_relative_defaults(
        enabled=enabled,
        baseline_source=baseline_source,
        baseline_window_label=baseline_window_label,
        baseline_p95=baseline_p95,
        baseline_p99=baseline_p99,
        window_size=window_size,
        scope_caveat=scope_caveat,
    )
    if not enabled:
        return row
    if not np.isfinite(float(curvature_value)) or baseline_p95 <= 0.0 or baseline_p99 <= 0.0:
        row["phase56_curvature_nonbinding_state"] = "not_ready"
        watch_history.append(False)
        stress_history.append(False)
        return row
    minus_p95 = float(curvature_value) - float(baseline_p95)
    over_p95 = float(curvature_value) / max(float(baseline_p95), 1.0e-12)
    watch = bool(float(curvature_value) > float(baseline_p95))
    stress = bool(float(curvature_value) > float(baseline_p99))
    watch_history.append(watch)
    stress_history.append(stress)
    nonbinding_state = "stress" if stress else ("watch" if watch else "nominal")
    row.update(
        {
            "phase56_curvature_minus_p95": float(minus_p95),
            "phase56_curvature_over_p95": float(over_p95),
            "phase56_curvature_watch": bool(watch),
            "phase56_curvature_stress": bool(stress),
            "phase56_curvature_watch_window_count": int(sum(bool(x) for x in watch_history)),
            "phase56_curvature_stress_window_count": int(sum(bool(x) for x in stress_history)),
            "phase56_curvature_nonbinding_state": str(nonbinding_state),
        }
    )
    return row


def _phase56_curvature_relative_summary(
    csv_df: pd.DataFrame,
    *,
    enabled: bool,
    baseline_source: str,
    baseline_window_label: str,
    baseline_p95: float,
    baseline_p99: float,
    scope_caveat: str,
    nonbinding_state_counts: dict[str, int],
) -> dict[str, object]:
    summary = {
        "phase56_curvature_relative_enabled": bool(enabled),
        "phase56_curvature_baseline_source": str(baseline_source),
        "phase56_curvature_baseline_window_label": str(baseline_window_label),
        "phase56_curvature_baseline_p95": float(baseline_p95) if enabled else None,
        "phase56_curvature_baseline_p99": float(baseline_p99) if enabled else None,
        "phase56_curvature_minus_p95_mean": None,
        "phase56_curvature_minus_p95_p95": None,
        "phase56_curvature_over_p95_mean": None,
        "phase56_curvature_over_p95_p95": None,
        "phase56_curvature_watch_fraction": None,
        "phase56_curvature_stress_fraction": None,
        "phase56_curvature_watch_window_peak": None,
        "phase56_curvature_stress_window_peak": None,
        "phase56_curvature_nonbinding_state_counts": dict(nonbinding_state_counts),
        "phase56_curvature_scope_caveat": str(scope_caveat),
    }
    if not enabled:
        return summary
    if "phase56_curvature_minus_p95" in csv_df.columns:
        vals = pd.to_numeric(csv_df.get("phase56_curvature_minus_p95"), errors="coerce")
        if vals.notna().any():
            summary["phase56_curvature_minus_p95_mean"] = float(vals.mean())
            summary["phase56_curvature_minus_p95_p95"] = float(vals.quantile(0.95))
    if "phase56_curvature_over_p95" in csv_df.columns:
        vals = pd.to_numeric(csv_df.get("phase56_curvature_over_p95"), errors="coerce")
        if vals.notna().any():
            summary["phase56_curvature_over_p95_mean"] = float(vals.mean())
            summary["phase56_curvature_over_p95_p95"] = float(vals.quantile(0.95))
    if "phase56_curvature_watch" in csv_df.columns:
        vals = csv_df.get("phase56_curvature_watch")
        summary["phase56_curvature_watch_fraction"] = float(vals.astype(bool).mean())
    if "phase56_curvature_stress" in csv_df.columns:
        vals = csv_df.get("phase56_curvature_stress")
        summary["phase56_curvature_stress_fraction"] = float(vals.astype(bool).mean())
    if "phase56_curvature_watch_window_count" in csv_df.columns:
        vals = pd.to_numeric(csv_df.get("phase56_curvature_watch_window_count"), errors="coerce")
        if vals.notna().any():
            summary["phase56_curvature_watch_window_peak"] = int(vals.max())
    if "phase56_curvature_stress_window_count" in csv_df.columns:
        vals = pd.to_numeric(csv_df.get("phase56_curvature_stress_window_count"), errors="coerce")
        if vals.notna().any():
            summary["phase56_curvature_stress_window_peak"] = int(vals.max())
    return summary


def _phase56_flow_cfg(profile: str, *, device: str) -> FlowMatchingConfig:
    if profile == "m160_i16_s128":
        return FlowMatchingConfig(hidden_dim=64, depth=2, batch_size=128, num_steps=160, integration_steps=16, device=device, seed=0)
    if profile == "m120_i12_s128":
        return FlowMatchingConfig(hidden_dim=64, depth=2, batch_size=128, num_steps=120, integration_steps=12, device=device, seed=0)
    if profile == "m220_i24_s160":
        return FlowMatchingConfig(hidden_dim=64, depth=2, batch_size=160, num_steps=220, integration_steps=24, device=device, seed=0)
    raise ValueError(f"Unsupported Phase 5/6 FM profile: {profile!r}")


def _phase56_standardize(
    source: np.ndarray,
    target: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    both = np.concatenate([source, target], axis=0).astype(np.float32)
    mean = both.mean(axis=0)
    std = both.std(axis=0)
    std = np.where(std < 1.0e-6, 1.0, std)
    return (
        ((source - mean) / std).astype(np.float32),
        ((target - mean) / std).astype(np.float32),
        {
            "mean": mean.astype(np.float32),
            "std": std.astype(np.float32),
        },
    )


def _phase56_prepare_live_bundle(
    reference_csv: str | Path,
    *,
    feature_set: str,
    context_gate: str,
    fm_profile: str,
    max_samples: int,
    target_alpha: float,
    device: str,
) -> dict[str, object]:
    if feature_set not in PHASE56_RUNTIME_FEATURE_SETS:
        raise ValueError(f"Unsupported Phase 5/6 feature set: {feature_set!r}")
    feature_columns = PHASE56_RUNTIME_FEATURE_SETS[feature_set]
    fm_cfg = _phase56_flow_cfg(fm_profile, device=device)
    bundle = prepare_phase56_runtime_bundle(
        reference_csv,
        feature_columns=feature_columns,
        context_gate=context_gate,
        fm_cfg=fm_cfg,
        max_samples=max_samples,
        target_alpha=target_alpha,
        light_cfg=LightOTConfig(eps=0.1, num_iters=120, device=device),
    )
    bundle["feature_set"] = str(feature_set)
    bundle["fm_profile"] = str(fm_profile)
    bundle["device"] = str(device)
    return bundle


def _phase56_runtime_feature_vector(
    *,
    feature_columns: list[str],
    true_roll: float,
    true_pitch: float,
    true_yaw: float,
    true_depth_v1: float,
    runtime_motor_saturation_ratio: float,
    runtime_motor_abs_max_raw: float,
    phase4a_sswp_delta_norm: float,
    phase4a_sswp_delta_abs_mean: float,
    fault_efficiency_min: float,
    depth_barrier_penalty: float,
) -> np.ndarray | None:
    value_map = {
        "true_roll": float(true_roll),
        "true_pitch": float(true_pitch),
        "true_yaw": float(true_yaw),
        "true_depth_v1": float(true_depth_v1),
        "runtime_motor_saturation_ratio": float(runtime_motor_saturation_ratio),
        "runtime_motor_abs_max_raw": float(runtime_motor_abs_max_raw),
        "phase4a_sswp_delta_norm": float(phase4a_sswp_delta_norm),
        "phase4a_sswp_delta_abs_mean": float(phase4a_sswp_delta_abs_mean),
        "fault_efficiency_min": float(fault_efficiency_min),
        "depth_barrier_penalty": float(depth_barrier_penalty),
    }
    vector = np.asarray([value_map.get(column, float("nan")) for column in feature_columns], dtype=np.float32)
    if vector.ndim != 1 or not np.all(np.isfinite(vector)):
        return None
    return vector


def _phase56_runtime_state_step(
    current_state: str,
    *,
    state_age: int,
    recovery_streak: int,
    lyapunov_pass: float,
    lyapunov_pass_rate_window: float,
    depth_violation: float,
    runtime_motor_saturation_ratio: float,
    fm_path_curvature_runtime: float,
    state_only_marginal_error_runtime: float,
    fault_active: bool,
    include_marginal_trip: bool = True,
    frozen_min_dwell_steps: int = 2,
    frozen_recover_steps: int = 3,
    fallback_dwell_steps: int = 2,
) -> tuple[str, str, int, int]:
    prev_state = str(current_state)
    state = prev_state if prev_state else "NOMINAL_LOCKED"
    prev_age = max(int(state_age), 0)
    soft = PHASE56_RUNTIME_SOFT_THRESHOLDS
    hard = PHASE56_RUNTIME_HARD_THRESHOLDS
    marginal_hard_trip = include_marginal_trip and (
        state_only_marginal_error_runtime >= hard["state_only_marginal_error_runtime_max"]
    )
    hard_trip = (
        depth_violation > hard["depth_violation_max"]
        or lyapunov_pass < hard["lyapunov_pass_min"]
        or runtime_motor_saturation_ratio >= hard["runtime_motor_saturation_ratio_max"]
        or fm_path_curvature_runtime >= hard["fm_path_curvature_runtime_max"]
        or marginal_hard_trip
    )
    marginal_soft_trip = include_marginal_trip and (
        state_only_marginal_error_runtime >= soft["state_only_marginal_error_runtime_warn"]
    )
    soft_trip = (
        lyapunov_pass_rate_window < soft["lyapunov_pass_rate_window_min"]
        or runtime_motor_saturation_ratio >= soft["runtime_motor_saturation_ratio_warn"]
        or fm_path_curvature_runtime >= soft["fm_path_curvature_runtime_warn"]
        or marginal_soft_trip
    )
    arm_ok = (
        bool(fault_active)
        and depth_violation <= hard["depth_violation_max"]
        and runtime_motor_saturation_ratio < soft["runtime_motor_saturation_ratio_warn"]
    )
    if state == "NOMINAL_LOCKED":
        recovery_streak = 0
        if arm_ok and not soft_trip and not hard_trip:
            state = "ADAPT_ARMED"
    elif state == "ADAPT_ARMED":
        recovery_streak = 0
        if hard_trip:
            state = "FALLBACK_ZERO_DRIFT"
        elif soft_trip:
            state = "FROZEN"
        else:
            state = "ADAPT_ACTIVE"
    elif state == "ADAPT_ACTIVE":
        recovery_streak = 0
        if hard_trip:
            state = "FALLBACK_ZERO_DRIFT"
        elif soft_trip:
            state = "FROZEN"
    elif state == "FROZEN":
        if hard_trip:
            state = "FALLBACK_ZERO_DRIFT"
            recovery_streak = 0
        elif not soft_trip:
            recovery_streak += 1
            if prev_age >= max(int(frozen_min_dwell_steps), 1) and recovery_streak >= max(int(frozen_recover_steps), 1):
                state = "ADAPT_ACTIVE"
                recovery_streak = 0
        else:
            recovery_streak = 0
    elif state == "FALLBACK_ZERO_DRIFT":
        recovery_streak = 0
        if prev_age >= max(int(fallback_dwell_steps), 1):
            state = "RESET_REQUIRED"
    elif state == "RESET_REQUIRED":
        recovery_streak = 0
        if not bool(fault_active):
            state = "NOMINAL_LOCKED"
    else:
        state = "NOMINAL_LOCKED"
        recovery_streak = 0
    transition = f"{prev_state}->{state}" if state != prev_state else ""
    next_age = (prev_age + 1) if state == prev_state else 1
    return state, transition, recovery_streak, next_age


def _phase56_runtime_execution_directives(
    *,
    prev_state: str,
    current_state: str,
    current_state_age: int,
    reset_dwell_steps: int,
) -> dict[str, bool]:
    frozen_states = {"FROZEN", "FALLBACK_ZERO_DRIFT", "RESET_REQUIRED"}
    healthy_states = {"NOMINAL_LOCKED", "ADAPT_ARMED", "ADAPT_ACTIVE"}
    return {
        "allows_update": current_state == "ADAPT_ACTIVE",
        "freeze_applied": current_state in frozen_states and prev_state not in frozen_states,
        "clear_freeze_applied": prev_state in frozen_states and current_state in healthy_states,
        "zero_drift_applied": current_state == "FALLBACK_ZERO_DRIFT" and prev_state != "FALLBACK_ZERO_DRIFT",
        "requests_reset": current_state == "RESET_REQUIRED" and int(current_state_age) >= max(int(reset_dwell_steps), 1),
    }


def _phase56_runtime_live_contract(
    bundle: dict[str, object],
    feature_vector: np.ndarray,
    *,
    current_state: str,
    state_age: int,
    recovery_streak: int,
    lyapunov_pass: float,
    lyapunov_pass_rate_window: float,
    depth_violation: float,
    runtime_motor_saturation_ratio: float,
    fault_active: bool,
    include_marginal_trip: bool = True,
    frozen_min_dwell_steps: int = 2,
    frozen_recover_steps: int = 3,
    fallback_dwell_steps: int = 2,
) -> tuple[dict[str, object], str, int, int]:
    norm = bundle["norm"]
    if not isinstance(norm, dict) or "mean" not in norm or "std" not in norm:
        raise RuntimeError("Malformed Phase 5/6 runtime bundle normalization payload.")
    mean = np.asarray(norm["mean"], dtype=np.float32)
    std = np.asarray(norm["std"], dtype=np.float32)
    feature_z = ((feature_vector.astype(np.float32) - mean) / std).reshape(1, -1)
    device_t = torch.device(str(bundle["device"]))
    feature_t = torch.as_tensor(feature_z, dtype=torch.float32, device=device_t)
    fm_model = bundle["fm_model"]
    transport = bundle["transport"]
    target_t = bundle["target_t"]
    fm_cfg = bundle["fm_cfg"]
    if not isinstance(target_t, torch.Tensor):
        raise RuntimeError("Malformed Phase 5/6 runtime bundle target tensor.")
    if not isinstance(fm_cfg, FlowMatchingConfig):
        raise RuntimeError("Malformed Phase 5/6 runtime bundle FM config.")
    moved_t, traj_t = integrate_flow_euler(
        fm_model,
        feature_t,
        integration_steps=int(fm_cfg.integration_steps),
    )
    _ = moved_t
    curvature = float(compute_path_curvature(traj_t))
    moved_light = transport.transport(feature_t).detach().cpu().numpy()
    target_np = target_t.detach().cpu().numpy()
    marginal_error = float(
        np.sqrt(((moved_light[:, None, :] - target_np[None, :, :]) ** 2).sum(axis=-1).min(axis=1))[0]
    )
    next_state, transition, next_recovery, next_state_age = _phase56_runtime_state_step(
        current_state,
        state_age=int(state_age),
        recovery_streak=recovery_streak,
        lyapunov_pass=float(lyapunov_pass),
        lyapunov_pass_rate_window=float(lyapunov_pass_rate_window),
        depth_violation=float(depth_violation),
        runtime_motor_saturation_ratio=float(runtime_motor_saturation_ratio),
        fm_path_curvature_runtime=float(curvature),
        state_only_marginal_error_runtime=float(marginal_error),
        fault_active=bool(fault_active),
        include_marginal_trip=bool(include_marginal_trip),
        frozen_min_dwell_steps=int(frozen_min_dwell_steps),
        frozen_recover_steps=int(frozen_recover_steps),
        fallback_dwell_steps=int(fallback_dwell_steps),
    )
    row = _phase56_runtime_monitor_defaults(
        enabled=True,
        ready=True,
        target_alpha=float(bundle["target_alpha"]),
        current_state=next_state,
        transition=transition,
    )
    row["fm_path_curvature_runtime"] = float(curvature)
    row["state_only_marginal_error_runtime"] = float(marginal_error)
    row["phase56_runtime_state_age"] = int(next_state_age)
    return row, next_state, next_recovery, next_state_age


def _phase8_fm_midpoint_state_anchor(
    bundle: dict[str, object],
    states: torch.Tensor,
    *,
    alpha: float,
) -> tuple[torch.Tensor, dict[str, float]]:
    """Generate a detached FM midpoint anchor in the raw state space.

    This is intentionally a target-generator only: the FM model is frozen, the
    returned z_bridge is detached, and gradients can only flow through the
    downstream state-match proxy into the selected STDW update target.
    """

    norm = bundle.get("norm")
    if not isinstance(norm, dict) or "mean" not in norm or "std" not in norm:
        raise RuntimeError("Malformed Phase56 FM bundle normalization payload.")
    fm_model = bundle.get("fm_model")
    fm_cfg = bundle.get("fm_cfg")
    if not isinstance(fm_model, torch.nn.Module):
        raise RuntimeError("Malformed Phase56 FM bundle model payload.")
    if not isinstance(fm_cfg, FlowMatchingConfig):
        raise RuntimeError("Malformed Phase56 FM bundle config payload.")

    original_device = states.device
    original_dtype = states.dtype
    device_t = torch.device(str(getattr(fm_cfg, "device", "cpu")))
    mean = torch.as_tensor(norm["mean"], dtype=torch.float32, device=device_t).reshape(1, -1)
    std = torch.as_tensor(norm["std"], dtype=torch.float32, device=device_t).reshape(1, -1)
    if int(states.shape[-1]) != int(mean.shape[-1]):
        raise RuntimeError(
            f"FM midpoint z_bridge dim mismatch: states dim={int(states.shape[-1])}, "
            f"bundle dim={int(mean.shape[-1])}. Use an obs/state-space Phase56 bundle "
            "matching the state_match_proxy state_dim."
        )

    alpha_f = float(np.clip(alpha, 0.0, 1.0))
    with torch.no_grad():
        states_t = states.detach().to(device_t, dtype=torch.float32)
        states_z = (states_t - mean) / std.clamp_min(1.0e-6)
        _, traj_t = integrate_flow_euler(
            fm_model,
            states_z,
            integration_steps=int(fm_cfg.integration_steps),
        )
        target_idx = max(
            min(int(round(alpha_f * (int(traj_t.shape[0]) - 1))), int(traj_t.shape[0]) - 1),
            0,
        )
        z_mid = traj_t[target_idx].to(device_t, dtype=torch.float32)
        z_raw = z_mid * std + mean
        shift_norm = torch.norm(z_raw - states_t, dim=-1)
        info = {
            "alpha": alpha_f,
            "target_index": float(target_idx),
            "curvature": float(compute_path_curvature(traj_t)),
            "shift_norm_mean": float(shift_norm.mean().detach().cpu().item()),
            "shift_norm_p95": float(torch.quantile(shift_norm, 0.95).detach().cpu().item()),
        }
    return z_raw.to(original_device, dtype=original_dtype).detach(), info


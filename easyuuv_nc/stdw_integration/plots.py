"""STDW diagnostic plotting helpers.

This module is the canonical home for the seven STDW diagnostic figures.  The
old workflow (``workflows/play_stdw_adapt.py``) and the new STDW online
adaptation workflow (``workflows_new_stdw/play_stdw_adapt.py``) both import the
same primitives from here.  Plot helpers gracefully degrade when columns such
as ``distill_loss``/``target_loss``/``teacher_action``/``student_action`` are
absent in the new workflow's CSV output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .metrics import (
    DEFAULT_DEPTH_LOWER_LIMIT,
    DEFAULT_DEPTH_REFERENCE_FRAME,
    DEFAULT_DEPTH_SURFACE_Z,
    DEFAULT_DEPTH_TRANSITION_WIDTH,
    DEFAULT_DEPTH_UPPER_LIMIT,
    calculate_actuator_saturation_stats,
    calculate_depth_barrier_penalty,
    convert_depth_to_v1,
    resolve_depth_barrier_limits,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _angle_error_np(true_values, desired_values) -> np.ndarray:
    return (np.asarray(true_values, dtype=float) - np.asarray(desired_values, dtype=float) + np.pi) % (2.0 * np.pi) - np.pi


def _stack_vector_column(csv_df, column_name: str) -> np.ndarray:
    if column_name not in csv_df or len(csv_df) == 0:
        return np.empty((0, 0), dtype=float)
    values = []
    for value in csv_df[column_name]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                continue
        values.append(value)
    if not values:
        return np.empty((0, 0), dtype=float)
    return np.asarray(values, dtype=float)


def _infer_dt_seconds(csv_df, default: float = 1.0) -> float:
    if "time_s" not in csv_df.columns or len(csv_df) < 2:
        return float(default)
    times = np.asarray(csv_df["time_s"], dtype=float)
    diffs = np.diff(times[np.isfinite(times)])
    diffs = diffs[diffs > 0.0]
    return float(np.median(diffs)) if diffs.size else float(default)


def _first_float(csv_df, column_name: str, default: float) -> float:
    if column_name not in csv_df.columns or len(csv_df) == 0:
        return float(default)
    try:
        values = np.asarray(csv_df[column_name], dtype=float)
        values = values[np.isfinite(values)]
        return float(values[0]) if values.size else float(default)
    except Exception:
        return float(default)


def _first_str(csv_df, column_name: str, default: str) -> str:
    if column_name not in csv_df.columns or len(csv_df) == 0:
        return str(default)
    value = csv_df[column_name].iloc[0]
    return str(value) if str(value) else str(default)


def _depth_contract_from_csv(csv_df) -> dict[str, float | str]:
    frame = _first_str(csv_df, "depth_reference_frame", DEFAULT_DEPTH_REFERENCE_FRAME)
    surface_z = _first_float(csv_df, "depth_surface_z", DEFAULT_DEPTH_SURFACE_Z)
    upper_limit = _first_float(csv_df, "depth_upper_limit", DEFAULT_DEPTH_UPPER_LIMIT)
    lower_limit = _first_float(csv_df, "depth_lower_limit", DEFAULT_DEPTH_LOWER_LIMIT)
    transition_width = _first_float(csv_df, "depth_transition_width", DEFAULT_DEPTH_TRANSITION_WIDTH)
    limits = resolve_depth_barrier_limits(
        upper_limit=upper_limit,
        lower_limit=lower_limit,
        transition_width=transition_width,
    )
    return {
        "depth_reference_frame": frame,
        "depth_surface_z": surface_z,
        **limits,
    }


def _depth_series_v1(csv_df, source_col: str, target_col: str) -> np.ndarray:
    if target_col in csv_df.columns:
        return np.asarray(csv_df[target_col], dtype=float)
    if source_col not in csv_df.columns:
        return np.asarray([], dtype=float)
    contract = _depth_contract_from_csv(csv_df)
    return np.asarray(
        convert_depth_to_v1(
            csv_df[source_col],
            reference_frame=str(contract["depth_reference_frame"]),
            surface_z=float(contract["depth_surface_z"]),
        ),
        dtype=float,
    )


def _depth_barrier_from_csv(csv_df) -> dict:
    contract = _depth_contract_from_csv(csv_df)
    true_depth_v1 = _depth_series_v1(csv_df, "true_z", "true_depth_v1")
    barrier = calculate_depth_barrier_penalty(
        true_depth_v1,
        dt=_infer_dt_seconds(csv_df),
        upper_limit=float(contract["depth_upper_limit"]),
        upper_safe=float(contract["depth_upper_safe"]),
        lower_safe=float(contract["depth_lower_safe"]),
        lower_limit=float(contract["depth_lower_limit"]),
    )
    barrier.update(contract)
    return barrier


def _compute_tracking_mse(csv_df) -> dict:
    roll_error = _angle_error_np(csv_df["true_roll"], csv_df["des_roll"])
    pitch_error = _angle_error_np(csv_df["true_pitch"], csv_df["des_pitch"])
    yaw_error = _angle_error_np(csv_df["true_yaw"], csv_df["des_yaw"])
    true_depth_v1 = _depth_series_v1(csv_df, "true_z", "true_depth_v1")
    des_depth_v1 = _depth_series_v1(csv_df, "des_depth", "des_depth_v1")
    depth_error = true_depth_v1 - des_depth_v1
    roll_mse = roll_error ** 2
    pitch_mse = pitch_error ** 2
    yaw_mse = yaw_error ** 2
    depth_mse = depth_error ** 2
    attitude_mse = roll_mse + pitch_mse + yaw_mse
    total_mse = roll_mse + pitch_mse + yaw_mse + depth_mse
    legacy_depth_error = np.asarray(csv_df["true_z"], dtype=float) - np.asarray(csv_df["des_depth"], dtype=float)
    legacy_total_mse = roll_mse + pitch_mse + yaw_mse + legacy_depth_error ** 2
    barrier = _depth_barrier_from_csv(csv_df)
    return {
        "roll_error": roll_error,
        "pitch_error": pitch_error,
        "yaw_error": yaw_error,
        "depth_error": depth_error,
        "roll_mse": roll_mse,
        "pitch_mse": pitch_mse,
        "yaw_mse": yaw_mse,
        "depth_mse": depth_mse,
        "attitude_mse": attitude_mse,
        "total_mse": total_mse,
        "legacy_total_mse": legacy_total_mse,
        "depth_barrier_penalty": np.asarray(barrier["depth_barrier_penalty"], dtype=float),
        "depth_violation": np.asarray(barrier["depth_violation"], dtype=float),
        "depth_upper_transition_penalty": np.asarray(barrier["depth_upper_transition_penalty"], dtype=float),
        "depth_lower_transition_penalty": np.asarray(barrier["depth_lower_transition_penalty"], dtype=float),
        "mean_roll_mse": float(np.mean(roll_mse)) if roll_mse.size else 0.0,
        "mean_pitch_mse": float(np.mean(pitch_mse)) if pitch_mse.size else 0.0,
        "mean_yaw_mse": float(np.mean(yaw_mse)) if yaw_mse.size else 0.0,
        "mean_depth_mse": float(np.mean(depth_mse)) if depth_mse.size else 0.0,
        "mean_attitude_mse": float(np.mean(attitude_mse)) if attitude_mse.size else 0.0,
        "mean_total_mse": float(np.mean(total_mse)) if total_mse.size else 0.0,
        "mean_legacy_total_mse": float(np.mean(legacy_total_mse)) if legacy_total_mse.size else 0.0,
        "max_total_mse": float(np.max(total_mse)) if total_mse.size else 0.0,
        "depth_reference_frame": str(barrier.get("depth_reference_frame", DEFAULT_DEPTH_REFERENCE_FRAME)),
        "depth_surface_z": float(barrier.get("depth_surface_z", DEFAULT_DEPTH_SURFACE_Z)),
        "depth_tube_width": float(barrier.get("depth_tube_width", DEFAULT_DEPTH_UPPER_LIMIT - DEFAULT_DEPTH_LOWER_LIMIT)),
        "depth_transition_width": float(barrier.get("depth_transition_width", DEFAULT_DEPTH_TRANSITION_WIDTH)),
        "depth_violation_integral": float(barrier["depth_violation_integral"]),
        "depth_violation_time_fraction": float(barrier["depth_violation_time_fraction"]),
        "depth_upper_transition_integral": float(barrier["depth_upper_transition_integral"]),
        "depth_lower_transition_integral": float(barrier["depth_lower_transition_integral"]),
        "depth_barrier_penalty_mean": float(barrier["depth_barrier_penalty_mean"]),
        "depth_barrier_penalty_max": float(barrier["depth_barrier_penalty_max"]),
        "depth_barrier_penalty_integral": float(barrier["depth_barrier_penalty_integral"]),
    }


def _shade_bool_spans(ax, steps, mask_bool, color: str, alpha: float, label: str | None = None) -> None:
    """Shade contiguous ``mask_bool==True`` spans on ``ax`` (label only first span)."""
    steps = np.asarray(steps, dtype=float)
    mask_bool = np.asarray(mask_bool, dtype=bool)
    if steps.size == 0 or mask_bool.size == 0:
        return
    in_span = False
    span_start = None
    labelled = False
    for i, active in enumerate(mask_bool):
        if active and not in_span:
            in_span, span_start = True, steps[i]
        elif not active and in_span:
            ax.axvspan(span_start, steps[i], color=color, alpha=alpha, label=None if labelled else label)
            labelled = True
            in_span = False
    if in_span:
        ax.axvspan(span_start, steps[-1], color=color, alpha=alpha, label=None if labelled else label)


def _add_event_markers(ax, volume_jump_step: int, flow_jump_step: int, best_save_step: int | None = None) -> None:
    if volume_jump_step is not None:
        ax.axvline(volume_jump_step, color="#444444", linestyle=":", linewidth=1.0, alpha=0.8, label="Volume jump")
    if flow_jump_step is not None:
        ax.axvline(flow_jump_step, color="#2ca02c", linestyle=":", linewidth=1.0, alpha=0.8, label="Flow injection")
    if best_save_step is not None:
        ax.axvline(best_save_step, color="#9467bd", linestyle="-.", linewidth=1.0, alpha=0.9, label="Best policy save")


# ---------------------------------------------------------------------------
# Plot primitives
# ---------------------------------------------------------------------------


def _plot_results(csv_df, output_plot: Path, volume_jump_step: int, flow_jump_step: int, best_save_step: int | None) -> None:
    fig, ax_error = plt.subplots(figsize=(11, 6))
    ax_rho = ax_error.twinx()

    ax_error.plot(csv_df["step"], csv_df["compound_error"], color="#1f77b4", linewidth=1.6, label="Compound Error")
    ax_rho.plot(csv_df["step"], csv_df["rho"], color="#d62728", linestyle="--", linewidth=1.4, label="Rho")

    if volume_jump_step is not None:
        ax_error.axvline(volume_jump_step, color="#444444", linestyle=":", linewidth=1.2, label="Volume jump")
    if flow_jump_step is not None:
        ax_error.axvline(flow_jump_step, color="#2ca02c", linestyle=":", linewidth=1.2, label="Flow injection")
    if best_save_step is not None:
        ax_error.axvline(best_save_step, color="#9467bd", linestyle="-.", linewidth=1.2, label="Best policy save")

    ax_error.set_xlabel("Simulation Step")
    ax_error.set_ylabel("Compound Error")
    ax_rho.set_ylabel("Rho")
    ax_error.grid(True, alpha=0.3)

    handles_error, labels_error = ax_error.get_legend_handles_labels()
    handles_rho, labels_rho = ax_rho.get_legend_handles_labels()
    ax_error.legend(handles_error + handles_rho, labels_error + labels_rho, loc="upper right")
    fig.tight_layout()
    fig.savefig(output_plot, dpi=180)
    plt.close(fig)


def _plot_tracking_rpy(csv_df, output_plot: Path, volume_jump_step: int, flow_jump_step: int, best_save_step: int | None) -> None:
    steps = csv_df["step"]
    axes_cfg = [
        ("roll", "Roll (rad)", "des_roll", "true_roll"),
        ("pitch", "Pitch (rad)", "des_pitch", "true_pitch"),
        ("yaw", "Yaw (rad)", "des_yaw", "true_yaw"),
    ]
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    for ax, (_, ylabel, desired_col, true_col) in zip(axes, axes_cfg):
        ax.plot(steps, csv_df[desired_col], color="#444444", linestyle="--", linewidth=1.2, label="Desired")
        ax.plot(steps, csv_df[true_col], color="#1f77b4", linewidth=1.2, label="Actual")
        _add_event_markers(ax, volume_jump_step, flow_jump_step, best_save_step)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)
    axes[-1].set_xlabel("Simulation Step")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right")
    fig.suptitle("STDW RPY Tracking")
    fig.tight_layout(rect=(0, 0, 0.98, 0.97))
    fig.savefig(output_plot, dpi=180)
    plt.close(fig)


def _plot_tracking_depth(csv_df, output_plot: Path, volume_jump_step: int, flow_jump_step: int, best_save_step: int | None) -> None:
    if "step" not in csv_df.columns:
        return
    true_depth_v1 = _depth_series_v1(csv_df, "true_z", "true_depth_v1")
    des_depth_v1 = _depth_series_v1(csv_df, "des_depth", "des_depth_v1")
    fig, ax = plt.subplots(figsize=(12, 5))
    if des_depth_v1.size:
        ax.plot(csv_df["step"], des_depth_v1, color="#444444", linestyle="--", linewidth=1.3, label="Desired V1 depth")
    if true_depth_v1.size:
        ax.plot(csv_df["step"], true_depth_v1, color="#1f77b4", linewidth=1.3, label="Actual V1 depth")
    _add_event_markers(ax, volume_jump_step, flow_jump_step, best_save_step)
    ax.set_xlabel("Simulation Step")
    ax.set_ylabel("V1 depth (m, negative underwater)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    contract = _depth_contract_from_csv(csv_df)
    ax.set_title(
        "STDW V1 Depth Reference "
        f"(frame={contract['depth_reference_frame']}, surface_z={float(contract['depth_surface_z']):.2f})"
    )
    fig.tight_layout()
    fig.savefig(output_plot, dpi=180)
    plt.close(fig)


def _plot_depth_barrier_profile(
    csv_df,
    output_plot: Path,
    volume_jump_step: int,
    flow_jump_step: int,
    best_save_step: int | None,
) -> bool:
    """V1 depth-as-barrier diagnostic profile.

    This figure is intentionally separate from the legacy depth tracking plot:
    the new benchmark treats depth as a safety tube, not as a strong MSE target.
    """
    if "true_z" not in csv_df.columns or "step" not in csv_df.columns:
        return False
    steps = np.asarray(csv_df["step"], dtype=float)
    true_depth_v1 = _depth_series_v1(csv_df, "true_z", "true_depth_v1")
    des_depth_v1 = _depth_series_v1(csv_df, "des_depth", "des_depth_v1")
    barrier = _depth_barrier_from_csv(csv_df)
    penalty = np.asarray(barrier["depth_barrier_penalty"], dtype=float)
    violation = np.asarray(barrier["depth_violation"], dtype=float)

    upper_limit = float(barrier["depth_upper_limit"])
    upper_safe = float(barrier["depth_upper_safe"])
    lower_safe = float(barrier["depth_lower_safe"])
    lower_limit = float(barrier["depth_lower_limit"])

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax_depth, ax_penalty = axes

    ax_depth.axhspan(lower_safe, upper_safe, color="#2ca02c", alpha=0.10, label="Safe core")
    ax_depth.axhspan(upper_safe, upper_limit, color="#ffbf00", alpha=0.16, label="Upper transition")
    ax_depth.axhspan(lower_limit, lower_safe, color="#ffbf00", alpha=0.16, label="Lower transition")
    for y, name, color in [
        (upper_limit, "Upper hard bound", "#d62728"),
        (upper_safe, "Upper safe core", "#2ca02c"),
        (lower_safe, "Lower safe core", "#2ca02c"),
        (lower_limit, "Lower hard bound", "#d62728"),
    ]:
        ax_depth.axhline(y, color=color, linestyle=":" if "safe" in name.lower() else "--", linewidth=1.0, alpha=0.8)
    if des_depth_v1.size:
        ax_depth.plot(steps, des_depth_v1, color="#666666", linestyle="--", linewidth=1.1, label="Desired V1 depth")
    ax_depth.plot(steps, true_depth_v1, color="#1f77b4", linewidth=1.3, label="Actual V1 depth")
    _add_event_markers(ax_depth, volume_jump_step, flow_jump_step, best_save_step)
    ax_depth.set_ylabel("V1 depth (m, negative underwater)")
    ax_depth.grid(True, alpha=0.3)
    ax_depth.legend(loc="best", fontsize=8)

    ax_penalty.plot(steps, penalty, color="#d62728", linewidth=1.2, label="Barrier penalty")
    ax_penalty.plot(steps, violation, color="#9467bd", linestyle="--", linewidth=1.1, label="Hard-bound violation")
    _add_event_markers(ax_penalty, volume_jump_step, flow_jump_step, best_save_step)
    ax_penalty.set_ylabel("Penalty / violation")
    ax_penalty.set_xlabel("Simulation Step")
    ax_penalty.grid(True, alpha=0.3)
    ax_penalty.legend(loc="best", fontsize=8)

    fig.suptitle(
        "V1 Depth Barrier Profile "
        f"(violation_integral={float(barrier['depth_violation_integral']):.3e}, "
        f"time_frac={float(barrier['depth_violation_time_fraction']):.3f}, "
        f"frame={barrier.get('depth_reference_frame')}, "
        f"surface_z={float(barrier.get('depth_surface_z', DEFAULT_DEPTH_SURFACE_Z)):.2f})"
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_plot, dpi=180)
    plt.close(fig)
    return True


def _plot_saturation_authority_profile(
    csv_df,
    output_plot: Path,
    volume_jump_step: int,
    flow_jump_step: int,
    best_save_step: int | None,
) -> bool:
    """V1 allocator saturation and remaining-authority proxy."""
    if "runtime_motor_saturation_ratio" not in csv_df.columns or "step" not in csv_df.columns:
        return False
    steps = np.asarray(csv_df["step"], dtype=float)
    sat = np.asarray(csv_df["runtime_motor_saturation_ratio"], dtype=float)
    if not np.any(np.isfinite(sat)):
        return False
    stats = calculate_actuator_saturation_stats(sat)
    authority = 1.0 - np.clip(sat, 0.0, 1.0)

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    axes[0].plot(steps, sat, color="#d62728", linewidth=1.2, label="Motor saturation ratio")
    axes[0].plot(steps, authority, color="#2ca02c", linewidth=1.2, label="Authority proxy (1 - saturation)")
    axes[0].set_ylim(-0.05, 1.05)
    axes[0].set_ylabel("Ratio")

    drew_second = False
    if "runtime_motor_abs_max_raw" in csv_df.columns:
        axes[1].plot(steps, csv_df["runtime_motor_abs_max_raw"], color="#ff7f0e", linewidth=1.1, label="max |raw PWM|")
        drew_second = True
    if "runtime_motor_abs_max_clipped" in csv_df.columns:
        axes[1].plot(steps, csv_df["runtime_motor_abs_max_clipped"], color="#1f77b4", linewidth=1.1, label="max |clipped PWM|")
        drew_second = True
    if not drew_second:
        axes[1].plot(steps, sat, color="#d62728", linewidth=1.1, label="Motor saturation ratio")
    axes[1].axhline(1.0, color="#444444", linestyle=":", linewidth=0.9, alpha=0.7, label="PWM rail")
    axes[1].set_ylabel("PWM magnitude")

    for ax in axes:
        _add_event_markers(ax, volume_jump_step, flow_jump_step, best_save_step)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=8)
    axes[-1].set_xlabel("Simulation Step")

    fig.suptitle(
        "V1 Saturation / Control Authority "
        f"(sat_time_frac={stats['actuator_saturation_time_fraction']:.3f}, "
        f"authority_proxy={stats['attitude_control_authority_ratio']:.3f})"
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_plot, dpi=180)
    plt.close(fig)
    return True


def _plot_mse(csv_df, output_plot: Path, mse_data: dict, volume_jump_step: int, flow_jump_step: int, best_save_step: int | None) -> None:
    steps = csv_df["step"]
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    axes[0].plot(steps, mse_data["roll_mse"], label="Roll MSE", linewidth=1.1)
    axes[0].plot(steps, mse_data["pitch_mse"], label="Pitch MSE", linewidth=1.1)
    axes[0].plot(steps, mse_data["yaw_mse"], label="Yaw MSE", linewidth=1.1)
    axes[0].plot(steps, mse_data["depth_mse"], label="Depth MSE", linewidth=1.1)
    axes[1].plot(steps, mse_data["total_mse"], color="#d62728", label="Total tracking MSE", linewidth=1.3)
    if "compound_error" in csv_df:
        axes[1].plot(steps, csv_df["compound_error"], color="#1f77b4", linestyle="--", label="Compound error", linewidth=1.1)
    for ax in axes:
        _add_event_markers(ax, volume_jump_step, flow_jump_step, best_save_step)
        ax.set_ylabel("Squared Error")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
    axes[-1].set_xlabel("Simulation Step")
    fig.suptitle("STDW Tracking MSE")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_plot, dpi=180)
    plt.close(fig)


def _plot_losses(csv_df, output_plot: Path, volume_jump_step: int, flow_jump_step: int, best_save_step: int | None) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    if "loss" in csv_df.columns:
        axes[0].plot(csv_df["step"], csv_df["loss"], label="Total loss", linewidth=1.2)
    if "distill_loss" in csv_df.columns:
        axes[0].plot(csv_df["step"], csv_df["distill_loss"], label="Distill loss", linewidth=1.0)
    if "target_loss" in csv_df.columns:
        axes[0].plot(csv_df["step"], csv_df["target_loss"], label="Target loss", linewidth=1.0)
    if "loss_source" in csv_df.columns:
        axes[0].plot(csv_df["step"], csv_df["loss_source"], label="Source loss", linewidth=1.0)
    if "loss_target" in csv_df.columns:
        axes[0].plot(csv_df["step"], csv_df["loss_target"], label="Target loss (STDW)", linewidth=1.0)
    if "loss_reg" in csv_df.columns:
        axes[0].plot(csv_df["step"], csv_df["loss_reg"], label="L2 reg", linewidth=1.0)
    if "rho" in csv_df.columns:
        axes[1].plot(csv_df["step"], csv_df["rho"], label="Rho", color="#d62728", linewidth=1.2)
    if "mask" in csv_df.columns:
        axes[1].plot(csv_df["step"], csv_df["mask"], label="Mask", color="#2ca02c", linewidth=1.0)
    if "stdw_mask" in csv_df.columns:
        axes[1].plot(csv_df["step"], csv_df["stdw_mask"], label="STDW mask", color="#17becf", linewidth=1.0)
    if "domain_bias" in csv_df.columns:
        axes[1].plot(csv_df["step"], csv_df["domain_bias"], label="Domain bias", color="#9467bd", linewidth=1.0)
    if "drift_fraction" in csv_df.columns:
        axes[1].plot(csv_df["step"], csv_df["drift_fraction"], label="Drift frac", color="#bcbd22", linewidth=1.0)
    # Grey shading: TAG adaptation-silenced spans (filt_err < trigger_threshold).
    if "trigger_gate_silenced" in csv_df.columns and "step" in csv_df.columns:
        step_vals = np.asarray(csv_df["step"], dtype=float)
        silenced = np.asarray(csv_df["trigger_gate_silenced"], dtype=float) > 0.5
        in_span = False
        span_start = None
        for i, s in enumerate(silenced):
            if s and not in_span:
                in_span, span_start = True, step_vals[i]
            elif not s and in_span:
                for ax in axes:
                    ax.axvspan(span_start, step_vals[i], color="grey", alpha=0.15)
                in_span = False
        if in_span and len(step_vals):
            for ax in axes:
                ax.axvspan(span_start, step_vals[-1], color="grey", alpha=0.15)
    for ax in axes:
        _add_event_markers(ax, volume_jump_step, flow_jump_step, best_save_step)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
    axes[0].set_ylabel("Loss")
    axes[1].set_ylabel("Schedule / Bias")
    axes[-1].set_xlabel("Simulation Step")
    fig.suptitle("STDW Loss and Schedule")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_plot, dpi=180)
    plt.close(fig)


def _plot_actions(csv_df, output_plot: Path, volume_jump_step: int, flow_jump_step: int, best_save_step: int | None) -> None:
    steps = np.asarray(csv_df["step"], dtype=float)
    executed_actions = _stack_vector_column(csv_df, "executed_action")
    teacher_actions = _stack_vector_column(csv_df, "teacher_action") if "teacher_action" in csv_df.columns else np.empty((0, 0))
    student_actions = _stack_vector_column(csv_df, "student_action") if "student_action" in csv_df.columns else np.empty((0, 0))
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    if executed_actions.size:
        for idx in range(executed_actions.shape[1]):
            axes[0].plot(steps, executed_actions[:, idx], linewidth=1.0, label=f"Executed a{idx}")
    if teacher_actions.size and student_actions.size and teacher_actions.shape == student_actions.shape:
        action_divergence = np.max(np.abs(student_actions - teacher_actions), axis=1)
        axes[1].plot(steps, action_divergence, color="#d62728", linewidth=1.2, label="max |student-teacher|")
    if "control_effort" in csv_df.columns:
        axes[1].plot(steps, csv_df["control_effort"], color="#1f77b4", linewidth=1.1, label="Control effort")
    for ax in axes:
        _add_event_markers(ax, volume_jump_step, flow_jump_step, best_save_step)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", ncol=2)
    axes[0].set_ylabel("Action")
    axes[1].set_ylabel("Effort / Divergence")
    axes[-1].set_xlabel("Simulation Step")
    fig.suptitle("STDW Actions and Control Effort")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_plot, dpi=180)
    plt.close(fig)


def _plot_domain(csv_df, output_plot: Path, volume_jump_step: int, flow_jump_step: int, best_save_step: int | None) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    if "fluid_vx" in csv_df.columns:
        axes[0].plot(csv_df["step"], csv_df["fluid_vx"], label="fluid_vx", linewidth=1.1)
    if "fluid_vy" in csv_df.columns:
        axes[0].plot(csv_df["step"], csv_df["fluid_vy"], label="fluid_vy", linewidth=1.1)
    if "fluid_vz" in csv_df.columns:
        axes[0].plot(csv_df["step"], csv_df["fluid_vz"], label="fluid_vz", linewidth=1.1)
    if "volume_mean" in csv_df.columns:
        axes[1].plot(csv_df["step"], csv_df["volume_mean"], color="#1f77b4", label="volume_mean", linewidth=1.2)
    if "domain_bias" in csv_df.columns:
        axes[1].plot(csv_df["step"], csv_df["domain_bias"], color="#d62728", label="domain_bias", linewidth=1.1)
    if "drift_fraction" in csv_df.columns:
        axes[1].plot(csv_df["step"], csv_df["drift_fraction"], color="#9467bd", label="drift_fraction", linewidth=1.1)
    for ax in axes:
        _add_event_markers(ax, volume_jump_step, flow_jump_step, best_save_step)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
    axes[0].set_ylabel("Fluid Velocity")
    axes[1].set_ylabel("Volume / Bias")
    axes[-1].set_xlabel("Simulation Step")
    fig.suptitle("STDW Domain Shift Signals")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_plot, dpi=180)
    plt.close(fig)


def _plot_tracking_overlay(csv_df, output_plot: Path, mse_data: dict, volume_jump_step: int, flow_jump_step: int, best_save_step: int | None) -> None:
    """Raw target-vs-actual overlay for roll/pitch/yaw/depth with per-channel MSE in titles."""
    steps = csv_df["step"]
    depth_des_col = "des_depth_v1" if "des_depth_v1" in csv_df.columns else "des_depth"
    depth_true_col = "true_depth_v1" if "true_depth_v1" in csv_df.columns else "true_z"
    depth_ylabel = "V1 depth (m)" if "true_depth_v1" in csv_df.columns else "Depth / z"
    channels = [
        ("Roll (rad)", "des_roll", "true_roll", mse_data.get("mean_roll_mse", 0.0)),
        ("Pitch (rad)", "des_pitch", "true_pitch", mse_data.get("mean_pitch_mse", 0.0)),
        ("Yaw (rad)", "des_yaw", "true_yaw", mse_data.get("mean_yaw_mse", 0.0)),
        (depth_ylabel, depth_des_col, depth_true_col, mse_data.get("mean_depth_mse", 0.0)),
    ]
    fig, axes = plt.subplots(4, 1, figsize=(12, 11), sharex=True)
    for ax, (ylabel, des_col, true_col, mse_val) in zip(axes, channels):
        if des_col in csv_df.columns:
            ax.plot(steps, csv_df[des_col], color="#444444", linestyle="--", linewidth=1.2, label="Target")
        if true_col in csv_df.columns:
            ax.plot(steps, csv_df[true_col], color="#1f77b4", linewidth=1.2, label="Actual")
        _add_event_markers(ax, volume_jump_step, flow_jump_step, best_save_step)
        ax.set_ylabel(ylabel)
        ax.set_title(f"{ylabel.split(' ')[0]}  MSE={mse_val:.4e}", fontsize=9)
        ax.grid(True, alpha=0.3)
    axes[-1].set_xlabel("Simulation Step")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right")
    fig.suptitle("STDW Raw Tracking Overlay (Target vs Actual)")
    fig.tight_layout(rect=(0, 0, 0.98, 0.97))
    fig.savefig(output_plot, dpi=180)
    plt.close(fig)


def _plot_lyapunov_guard(csv_df, output_plot: Path, volume_jump_step: int, flow_jump_step: int, best_save_step: int | None) -> bool:
    """Lyapunov sieve + STDW direction-guard diagnostics.

    Three stacked panels (each drawn only when its columns exist):

    * V_t / dV timeline with Lyapunov-fail spans shaded.
    * Lyapunov windowed pass-rate + safety-block spans.
    * STDW direction-guard pass-rate / signed alignment with update-reject spans.

    Returns ``False`` (and writes nothing) when none of the source columns are
    present so callers can drop the path from the returned dict.
    """
    has_V = "lyapunov_V" in csv_df.columns
    has_pass_rate = "lyapunov_pass_rate_window" in csv_df.columns
    has_guard = "stdw_dir_guard_pass_rate" in csv_df.columns or "stdw_dir_guard_align" in csv_df.columns
    if not (has_V or has_pass_rate or has_guard):
        return False

    steps = np.asarray(csv_df["step"], dtype=float)
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    # Panel 0: V_t and dV, shade Lyapunov-fail steps.
    ax_v = axes[0]
    if has_V:
        ax_v.plot(steps, np.asarray(csv_df["lyapunov_V"], dtype=float), color="#1f77b4", linewidth=1.3, label="V_t")
    if "lyapunov_dV" in csv_df.columns:
        ax_dv = ax_v.twinx()
        ax_dv.plot(steps, np.asarray(csv_df["lyapunov_dV"], dtype=float), color="#ff7f0e", linewidth=1.0, alpha=0.8, label="dV")
        ax_dv.axhline(0.0, color="#ff7f0e", linestyle=":", linewidth=0.8, alpha=0.6)
        ax_dv.set_ylabel("dV", color="#ff7f0e")
    if "lyapunov_pass" in csv_df.columns:
        fail = np.asarray(csv_df["lyapunov_pass"], dtype=float) < 0.5
        _shade_bool_spans(ax_v, steps, fail, color="#d62728", alpha=0.12, label="Lyapunov fail")
    _add_event_markers(ax_v, volume_jump_step, flow_jump_step, best_save_step)
    ax_v.set_ylabel("V_t", color="#1f77b4")
    ax_v.grid(True, alpha=0.3)
    ax_v.legend(loc="upper left", fontsize=8)

    # Panel 1: windowed pass-rate and safety-block spans.
    ax_pr = axes[1]
    if has_pass_rate:
        ax_pr.plot(steps, np.asarray(csv_df["lyapunov_pass_rate_window"], dtype=float), color="#2ca02c", linewidth=1.2, label="Pass-rate (window)")
        ax_pr.set_ylim(-0.05, 1.05)
    if "lyapunov_safety_block" in csv_df.columns:
        blocked = np.asarray(csv_df["lyapunov_safety_block"], dtype=float) > 0.5
        _shade_bool_spans(ax_pr, steps, blocked, color="#8c564b", alpha=0.18, label="Safety block")
    _add_event_markers(ax_pr, volume_jump_step, flow_jump_step, best_save_step)
    ax_pr.set_ylabel("Lyapunov pass-rate")
    ax_pr.grid(True, alpha=0.3)
    ax_pr.legend(loc="best", fontsize=8)

    # Panel 2: direction-guard pass-rate / signed alignment, shade rejected updates.
    ax_g = axes[2]
    if "stdw_dir_guard_pass_rate" in csv_df.columns:
        ax_g.plot(steps, np.asarray(csv_df["stdw_dir_guard_pass_rate"], dtype=float), color="#9467bd", linewidth=1.2, label="Dir-guard pass-rate")
    if "stdw_dir_guard_align" in csv_df.columns:
        ax_g.plot(steps, np.asarray(csv_df["stdw_dir_guard_align"], dtype=float), color="#17becf", linewidth=1.2, label="Dir-guard align (signed)")
    ax_g.axhline(0.0, color="#444444", linestyle=":", linewidth=0.8, alpha=0.6)
    if "stdw_update_rejected" in csv_df.columns:
        rejected = np.asarray(csv_df["stdw_update_rejected"], dtype=float) > 0.5
        _shade_bool_spans(ax_g, steps, rejected, color="#d62728", alpha=0.15, label="Update rejected")
    _add_event_markers(ax_g, volume_jump_step, flow_jump_step, best_save_step)
    ax_g.set_ylabel("Direction guard")
    ax_g.set_xlabel("Simulation Step")
    ax_g.grid(True, alpha=0.3)
    ax_g.legend(loc="best", fontsize=8)

    fig.suptitle("STDW Lyapunov Sieve & Direction Guard")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_plot, dpi=180)
    plt.close(fig)
    return True


def _plot_boundary_wrench(csv_df, output_plot: Path, volume_jump_step: int, flow_jump_step: int, best_save_step: int | None) -> bool:
    """M4 near-boundary diagnostics: submersion ratio, boundary forces, ventilation.

    Panels (each drawn only when its columns exist):

    * Free-surface submersion ratio s(t) ∈ [0, 1].
    * Additive boundary force magnitudes (residual buoyancy ΔB, ground-effect |F|).
    * Per-step minimum thruster ventilation factor ∈ [0, 1].

    Returns ``False`` (writes nothing) when none of the columns are present so
    callers can drop the path from the returned dict (graceful degrade when M4
    is off / columns absent).
    """
    has_sub = "boundary_submersion_ratio" in csv_df.columns
    has_force = "boundary_residual_dB" in csv_df.columns or "boundary_ground_mag" in csv_df.columns
    has_vent = "boundary_vent_min" in csv_df.columns
    if not (has_sub or has_force or has_vent):
        return False

    steps = np.asarray(csv_df["step"], dtype=float)

    def _finite(col: str) -> np.ndarray | None:
        arr = np.asarray(csv_df[col], dtype=float)
        return arr if np.any(np.isfinite(arr)) else None

    panels: list[str] = []
    if has_sub:
        panels.append("sub")
    if has_force:
        panels.append("force")
    if has_vent:
        panels.append("vent")
    fig, axes = plt.subplots(len(panels), 1, figsize=(12, 3.2 * len(panels)), sharex=True, squeeze=False)
    axes = axes[:, 0]

    drew_any = False
    for ax, kind in zip(axes, panels):
        if kind == "sub":
            arr = _finite("boundary_submersion_ratio")
            if arr is not None:
                ax.plot(steps, arr, color="#1f77b4", linewidth=1.3, label="Submersion ratio s(t)")
                ax.set_ylim(-0.05, 1.05)
                drew_any = True
            ax.set_ylabel("s(t)")
        elif kind == "force":
            r = _finite("boundary_residual_dB") if "boundary_residual_dB" in csv_df.columns else None
            g = _finite("boundary_ground_mag") if "boundary_ground_mag" in csv_df.columns else None
            if r is not None:
                ax.plot(steps, r, color="#2ca02c", linewidth=1.2, label="Residual buoyancy ΔB")
                drew_any = True
            if g is not None:
                ax.plot(steps, g, color="#d62728", linewidth=1.2, label="Ground-effect |F|")
                drew_any = True
            ax.set_ylabel("Boundary force (N)")
        elif kind == "vent":
            arr = _finite("boundary_vent_min")
            if arr is not None:
                ax.plot(steps, arr, color="#9467bd", linewidth=1.3, label="Min ventilation factor")
                ax.set_ylim(-0.05, 1.05)
                drew_any = True
            ax.set_ylabel("Ventilation")
        _add_event_markers(ax, volume_jump_step, flow_jump_step, best_save_step)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=8)
    axes[-1].set_xlabel("Simulation Step")

    if not drew_any:
        plt.close(fig)
        return False

    fig.suptitle("STDW M4 Near-Boundary Effects")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_plot, dpi=180)
    plt.close(fig)
    return True


def _plot_stdw_diagnostics(csv_df, output_dir: Path, volume_jump_step: int, flow_jump_step: int, best_save_step: int | None):
    output_dir = Path(output_dir)
    mse_data = _compute_tracking_mse(csv_df)
    plot_paths = {
        "tracking_rpy": output_dir / "stdw_tracking_rpy.png",
        "tracking_depth": output_dir / "stdw_tracking_depth.png",
        "tracking_mse": output_dir / "stdw_tracking_mse.png",
        "tracking_overlay": output_dir / "stdw_tracking_overlay.png",
        "depth_barrier_profile": output_dir / "stdw_depth_barrier_profile.png",
        "saturation_authority_profile": output_dir / "stdw_saturation_authority.png",
        "losses": output_dir / "stdw_losses.png",
        "actions": output_dir / "stdw_actions.png",
        "domain_shift": output_dir / "stdw_domain_shift.png",
    }
    _plot_tracking_rpy(csv_df, plot_paths["tracking_rpy"], volume_jump_step, flow_jump_step, best_save_step)
    _plot_tracking_depth(csv_df, plot_paths["tracking_depth"], volume_jump_step, flow_jump_step, best_save_step)
    _plot_mse(csv_df, plot_paths["tracking_mse"], mse_data, volume_jump_step, flow_jump_step, best_save_step)
    _plot_tracking_overlay(csv_df, plot_paths["tracking_overlay"], mse_data, volume_jump_step, flow_jump_step, best_save_step)
    if not _plot_depth_barrier_profile(csv_df, plot_paths["depth_barrier_profile"], volume_jump_step, flow_jump_step, best_save_step):
        plot_paths.pop("depth_barrier_profile", None)
    if not _plot_saturation_authority_profile(csv_df, plot_paths["saturation_authority_profile"], volume_jump_step, flow_jump_step, best_save_step):
        plot_paths.pop("saturation_authority_profile", None)
    _plot_losses(csv_df, plot_paths["losses"], volume_jump_step, flow_jump_step, best_save_step)
    _plot_actions(csv_df, plot_paths["actions"], volume_jump_step, flow_jump_step, best_save_step)
    _plot_domain(csv_df, plot_paths["domain_shift"], volume_jump_step, flow_jump_step, best_save_step)
    lyapunov_guard_path = output_dir / "stdw_lyapunov_V.png"
    if _plot_lyapunov_guard(csv_df, lyapunov_guard_path, volume_jump_step, flow_jump_step, best_save_step):
        plot_paths["lyapunov_guard"] = lyapunov_guard_path
    boundary_path = output_dir / "stdw_boundary_wrench.png"
    if _plot_boundary_wrench(csv_df, boundary_path, volume_jump_step, flow_jump_step, best_save_step):
        plot_paths["boundary_wrench"] = boundary_path
    mse_summary = {key: value for key, value in mse_data.items() if isinstance(value, float)}
    return plot_paths, mse_summary


# Public (no-leading-underscore) aliases used by the package __init__ re-export.
plot_results = _plot_results
plot_tracking_rpy = _plot_tracking_rpy
plot_tracking_depth = _plot_tracking_depth
plot_mse = _plot_mse
plot_tracking_overlay = _plot_tracking_overlay
plot_losses = _plot_losses
plot_actions = _plot_actions
plot_domain = _plot_domain
plot_lyapunov_guard = _plot_lyapunov_guard
plot_boundary_wrench = _plot_boundary_wrench
plot_depth_barrier_profile = _plot_depth_barrier_profile
plot_saturation_authority_profile = _plot_saturation_authority_profile
plot_stdw_diagnostics = _plot_stdw_diagnostics

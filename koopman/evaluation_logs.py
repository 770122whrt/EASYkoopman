from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from koopman_data import load_koopman_samples


def _as_array(samples: list[dict[str, Any]], field: str) -> np.ndarray:
    return np.asarray([sample[field] for sample in samples], dtype=float)


def _rmse(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(values))))


def _attitude_angle_errors(states: np.ndarray, references: np.ndarray) -> np.ndarray:
    state_quat = states[:, 1:5]
    reference_quat = references[:, 1:5]
    state_norm = np.linalg.norm(state_quat, axis=1)
    reference_norm = np.linalg.norm(reference_quat, axis=1)
    valid = (state_norm > 0.0) & (reference_norm > 0.0)
    errors = np.zeros(states.shape[0], dtype=float)
    if not np.any(valid):
        return errors

    dots = np.sum(state_quat[valid] * reference_quat[valid], axis=1) / (state_norm[valid] * reference_norm[valid])
    dots = np.clip(np.abs(dots), 0.0, 1.0)
    errors[valid] = 2.0 * np.arccos(dots)
    return errors


def _solver_diagnostics(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagnostics = []
    for sample in samples:
        value = sample.get("solver_diagnostics")
        if isinstance(value, dict):
            diagnostics.append(value)
    return diagnostics


def _backend_used(samples: list[dict[str, Any]], diagnostics: list[dict[str, Any]]) -> str:
    for diagnostic in diagnostics:
        backend = diagnostic.get("backend_used")
        if backend:
            return str(backend)
    controller_mode = str(samples[0]["controller_mode"])
    if controller_mode.startswith("legacy"):
        return "legacy"
    return "unknown"


def summarize_samples(samples: list[dict[str, Any]], *, log_path: str | Path | None = None) -> dict[str, Any]:
    if not samples:
        raise ValueError("Cannot summarize an empty Koopman log")

    states = _as_array(samples, "state")
    references = _as_array(samples, "reference")
    pwm = _as_array(samples, "pwm_8d")
    diagnostics = _solver_diagnostics(samples)

    depth_error = states[:, 0] - references[:, 0]
    attitude_error = _attitude_angle_errors(states, references)
    delta_pwm = np.diff(pwm, axis=0) if len(samples) > 1 else np.zeros((0, pwm.shape[1]))
    latency_values = np.asarray(
        [float(diagnostic.get("latency_ms", 0.0) or 0.0) for diagnostic in diagnostics],
        dtype=float,
    )
    fallback_count = sum(1 for diagnostic in diagnostics if bool(diagnostic.get("fallback_used", False)))
    status_counts = Counter(str(diagnostic.get("status")) for diagnostic in diagnostics if diagnostic.get("status"))
    latency_budget_violations = sum(
        1 for diagnostic in diagnostics if diagnostic.get("latency_budget_met") is False
    )

    finite_fields = np.concatenate(
        [
            states.reshape(-1),
            references.reshape(-1),
            _as_array(samples, "action_4d").reshape(-1),
            pwm.reshape(-1),
            _as_array(samples, "next_state").reshape(-1),
        ]
    )
    nonfinite_count = int(np.size(finite_fields) - np.count_nonzero(np.isfinite(finite_fields)))

    summary = {
        "log_path": str(log_path) if log_path is not None else "",
        "sample_count": len(samples),
        "trajectory_type": str(samples[0]["trajectory_type"]),
        "controller_mode": str(samples[0]["controller_mode"]),
        "backend_used": _backend_used(samples, diagnostics),
        "depth_rmse": _rmse(depth_error),
        "attitude_angle_rmse": _rmse(attitude_error),
        "mean_pwm_l2": float(np.mean(np.linalg.norm(pwm, axis=1))),
        "mean_pwm_abs": float(np.mean(np.abs(pwm))),
        "pwm_saturation_rate": float(np.mean(np.abs(pwm) >= 0.999)),
        "mean_delta_pwm_l2": float(np.mean(np.linalg.norm(delta_pwm, axis=1))) if delta_pwm.size else 0.0,
        "max_delta_pwm_l2": float(np.max(np.linalg.norm(delta_pwm, axis=1))) if delta_pwm.size else 0.0,
        "fallback_rate": float(fallback_count / len(diagnostics)) if diagnostics else 0.0,
        "status_counts": dict(sorted(status_counts.items())),
        "mean_latency_ms": float(np.mean(latency_values)) if latency_values.size else 0.0,
        "max_latency_ms": float(np.max(latency_values)) if latency_values.size else 0.0,
        "latency_budget_violation_rate": (
            float(latency_budget_violations / len(diagnostics)) if diagnostics else 0.0
        ),
        "pwm_min": float(np.min(pwm)),
        "pwm_max": float(np.max(pwm)),
        "pwm_bounded": bool(np.min(pwm) >= -1.0 and np.max(pwm) <= 1.0),
        "nonfinite_count": nonfinite_count,
    }
    return summary


def summarize_log_path(path: str | Path) -> dict[str, Any]:
    samples = load_koopman_samples(path)
    return summarize_samples(samples, log_path=path)


def build_phase4_report(log_paths: list[str | Path]) -> dict[str, Any]:
    runs = [summarize_log_path(path) for path in log_paths]
    return {
        "run_count": len(runs),
        "runs": runs,
        "eligible_for_phase45_baseline": bool(
            runs and all(run["pwm_bounded"] and run["nonfinite_count"] == 0 for run in runs)
        ),
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 4 Controller Evaluation Metrics",
        "",
        f"Run count: {report.get('run_count', 0)}",
        "",
        "| Trajectory | Controller | Backend | Samples | Depth RMSE | Attitude RMSE | Fallback | Max Latency ms | PWM Bounded |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for run in report.get("runs", []):
        lines.append(
            "| {trajectory} | {controller} | {backend} | {samples} | {depth:.6g} | {attitude:.6g} | {fallback:.3f} | {latency:.6g} | {bounded} |".format(
                trajectory=run["trajectory_type"],
                controller=run["controller_mode"],
                backend=run["backend_used"],
                samples=run["sample_count"],
                depth=run["depth_rmse"],
                attitude=run["attitude_angle_rmse"],
                fallback=run["fallback_rate"],
                latency=run["max_latency_ms"],
                bounded="yes" if run["pwm_bounded"] else "no",
            )
        )
    lines.extend(
        [
            "",
            "## Phase 4.5 Baseline",
            "",
            "Eligible for Phase 4.5 baseline: "
            + ("yes" if report.get("eligible_for_phase45_baseline") else "no"),
            "",
        ]
    )
    return "\n".join(lines)

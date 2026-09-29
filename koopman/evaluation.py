from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .dataset import KoopmanDataset


def rmse(prediction: np.ndarray, target: np.ndarray) -> float:
    pred = np.asarray(prediction, dtype=float)
    truth = np.asarray(target, dtype=float)
    if pred.shape != truth.shape:
        raise ValueError("prediction and target must have the same shape")
    if not np.all(np.isfinite(pred)) or not np.all(np.isfinite(truth)):
        return float("inf")
    return float(np.sqrt(np.mean((pred - truth) ** 2)))


def rollout_predictions(model: Any, dataset: KoopmanDataset, horizon: int) -> np.ndarray:
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    steps = min(horizon, dataset.sample_count)
    state = dataset.X[0].copy()
    predictions = []
    for index in range(steps):
        state = model.predict_next(state, dataset.U[index], dataset.R[index])
        predictions.append(state)
    return np.asarray(predictions, dtype=float)


def _unique_horizons(horizon: int, horizons: Iterable[int] | None) -> tuple[int, ...]:
    values = tuple(horizons) if horizons is not None else (horizon,)
    cleaned = tuple(dict.fromkeys(int(value) for value in values if int(value) > 0))
    if not cleaned:
        raise ValueError("at least one positive horizon is required")
    return cleaned


def _divergence_rate(prediction: np.ndarray, *, depth_abs_max: float, attitude_abs_max: float, velocity_abs_max: float) -> float:
    if prediction.size == 0:
        return 0.0
    finite_rows = np.all(np.isfinite(prediction), axis=1)
    depth_bad = np.abs(prediction[:, 0]) > depth_abs_max
    attitude_bad = np.any(np.abs(prediction[:, 2:5]) > attitude_abs_max, axis=1)
    velocity_bad = np.any(np.abs(prediction[:, 5:11]) > velocity_abs_max, axis=1)
    bad = (~finite_rows) | depth_bad | attitude_bad | velocity_bad
    return float(np.mean(bad))


def has_diverged(metrics: dict[str, Any]) -> bool:
    if bool(metrics.get("diverged", False)):
        return True
    if int(metrics.get("nonfinite_count", 0)) > 0:
        return True
    if float(metrics.get("divergence_rate@20", 0.0)) > 0.0:
        return True
    one_step = float(metrics.get("one_step_rmse", 0.0))
    horizon_60 = int(metrics.get("multi_step_horizon@60", 0))
    multi_60 = float(metrics.get("multi_step_rmse@60", 0.0))
    if horizon_60 >= 60 and one_step > 1e-12 and multi_60 > 3.0 * one_step:
        return True
    return False


def evaluate_model(
    model: Any,
    dataset: KoopmanDataset,
    *,
    horizon: int = 20,
    horizons: Iterable[int] | None = None,
    depth_abs_max: float = 50.0,
    attitude_abs_max: float = 12.566370614359172,
    velocity_abs_max: float = 20.0,
) -> dict[str, float | int | bool]:
    one_step = model.predict_next(dataset.X, dataset.U, dataset.R)
    velocity_slice = slice(5, 11)
    attitude_slice = slice(2, 5)
    horizon_values = _unique_horizons(horizon, horizons)

    metrics: dict[str, float | int | bool] = {
        "sample_count": dataset.sample_count,
        "one_step_rmse": rmse(one_step, dataset.Y),
        "depth_rmse": rmse(one_step[:, 0], dataset.Y[:, 0]),
        "velocity_rmse": rmse(one_step[:, velocity_slice], dataset.Y[:, velocity_slice]),
        "attitude_angle_rmse": rmse(one_step[:, attitude_slice], dataset.Y[:, attitude_slice]),
    }
    nonfinite_count = int(np.size(one_step) - np.count_nonzero(np.isfinite(one_step)))
    max_error = 0.0
    for current_horizon in horizon_values:
        rollout = rollout_predictions(model, dataset, current_horizon)
        rollout_target = dataset.Y[: rollout.shape[0]]
        horizon_rmse = rmse(rollout, rollout_target)
        errors = np.abs(rollout - rollout_target)
        if errors.size and np.all(np.isfinite(errors)):
            max_error = max(max_error, float(np.max(errors)))
        else:
            max_error = float("inf")
        nonfinite_count += int(np.size(rollout) - np.count_nonzero(np.isfinite(rollout)))
        metrics[f"multi_step_horizon@{current_horizon}"] = int(rollout.shape[0])
        metrics[f"multi_step_rmse@{current_horizon}"] = horizon_rmse
        metrics[f"divergence_rate@{current_horizon}"] = _divergence_rate(
            rollout,
            depth_abs_max=depth_abs_max,
            attitude_abs_max=attitude_abs_max,
            velocity_abs_max=velocity_abs_max,
        )

    legacy_horizon = horizon_values[-1]
    metrics["multi_step_horizon"] = metrics[f"multi_step_horizon@{legacy_horizon}"]
    metrics["multi_step_rmse"] = metrics[f"multi_step_rmse@{legacy_horizon}"]
    metrics["max_error"] = max_error
    metrics["nonfinite_count"] = nonfinite_count
    metrics["diverged"] = has_diverged(metrics)
    return metrics


def write_metrics(metrics: dict, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")

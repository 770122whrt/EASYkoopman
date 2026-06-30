from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .dataset import KoopmanDataset
from .model import KoopmanModel


def rmse(prediction: np.ndarray, target: np.ndarray) -> float:
    pred = np.asarray(prediction, dtype=float)
    truth = np.asarray(target, dtype=float)
    if pred.shape != truth.shape:
        raise ValueError("prediction and target must have the same shape")
    return float(np.sqrt(np.mean((pred - truth) ** 2)))


def rollout_predictions(model: KoopmanModel, dataset: KoopmanDataset, horizon: int) -> np.ndarray:
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    steps = min(horizon, dataset.sample_count)
    state = dataset.X[0].copy()
    predictions = []
    for index in range(steps):
        state = model.predict_next(state, dataset.U[index], dataset.R[index])
        predictions.append(state)
    return np.asarray(predictions, dtype=float)


def evaluate_model(model: KoopmanModel, dataset: KoopmanDataset, *, horizon: int = 20) -> dict[str, float | int]:
    one_step = model.predict_next(dataset.X, dataset.U, dataset.R)
    rollout = rollout_predictions(model, dataset, horizon)
    rollout_target = dataset.Y[: rollout.shape[0]]
    velocity_slice = slice(5, 11)

    return {
        "sample_count": dataset.sample_count,
        "one_step_rmse": rmse(one_step, dataset.Y),
        "depth_rmse": rmse(one_step[:, 0], dataset.Y[:, 0]),
        "velocity_rmse": rmse(one_step[:, velocity_slice], dataset.Y[:, velocity_slice]),
        "multi_step_horizon": int(rollout.shape[0]),
        "multi_step_rmse": rmse(rollout, rollout_target),
    }


def write_metrics(metrics: dict, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")


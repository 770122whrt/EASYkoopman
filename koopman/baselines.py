from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from koopman_data import PWM_DIM, REFERENCE_DIM, STATE_DIM

from .dataset import KoopmanDataset


@dataclass
class PersistenceBaseline:
    state_dim: int = STATE_DIM
    control_dim: int = PWM_DIM
    reference_dim: int = REFERENCE_DIM
    metadata: dict[str, Any] = field(default_factory=dict)
    model_class: str = "persistence"

    def predict_next(self, state: np.ndarray, control: np.ndarray, reference: np.ndarray) -> np.ndarray:
        state_array = np.asarray(state, dtype=float)
        return state_array.copy()


@dataclass
class SimpleLinearBaseline:
    coefficient_matrix: np.ndarray
    ridge: float
    state_dim: int = STATE_DIM
    control_dim: int = PWM_DIM
    reference_dim: int = REFERENCE_DIM
    metadata: dict[str, Any] = field(default_factory=dict)
    model_class: str = "simple_linear"

    def __post_init__(self) -> None:
        self.coefficient_matrix = np.asarray(self.coefficient_matrix, dtype=float)
        expected_width = 1 + self.state_dim + self.control_dim + self.reference_dim
        if self.coefficient_matrix.shape != (self.state_dim, expected_width):
            raise ValueError(f"coefficient_matrix must have shape ({self.state_dim}, {expected_width})")

    def predict_next(self, state: np.ndarray, control: np.ndarray, reference: np.ndarray) -> np.ndarray:
        state_array = np.asarray(state, dtype=float)
        single = state_array.ndim == 1
        if single:
            state_array = state_array.reshape(1, -1)
        control_array = np.asarray(control, dtype=float)
        if control_array.ndim == 1:
            control_array = control_array.reshape(1, -1)
        reference_array = np.asarray(reference, dtype=float)
        if reference_array.ndim == 1:
            reference_array = reference_array.reshape(1, -1)
        if not (state_array.shape[0] == control_array.shape[0] == reference_array.shape[0]):
            raise ValueError("state, control and reference must contain the same number of samples")
        bias = np.ones((state_array.shape[0], 1), dtype=float)
        design = np.concatenate([bias, state_array, control_array, reference_array], axis=1)
        prediction = design @ self.coefficient_matrix.T
        return prediction[0] if single else prediction


def fit_simple_linear_baseline(dataset: KoopmanDataset, *, ridge: float = 1e-6) -> SimpleLinearBaseline:
    if ridge < 0:
        raise ValueError("ridge must be non-negative")
    bias = np.ones((dataset.sample_count, 1), dtype=float)
    design = np.concatenate([bias, dataset.X, dataset.U, dataset.R], axis=1)
    gram = design.T @ design
    if ridge > 0:
        gram = gram + ridge * np.eye(gram.shape[0])
    rhs = design.T @ dataset.Y
    try:
        coefficients = np.linalg.solve(gram, rhs).T
    except np.linalg.LinAlgError:
        coefficients = (np.linalg.pinv(gram) @ rhs).T
    return SimpleLinearBaseline(
        coefficient_matrix=coefficients,
        ridge=ridge,
        state_dim=dataset.X.shape[1],
        control_dim=dataset.U.shape[1],
        reference_dim=dataset.R.shape[1],
        metadata={
            "sample_count": dataset.sample_count,
            "source_paths": list(dataset.source_paths),
            "dt": dataset.dt,
        },
    )

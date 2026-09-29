"""Selection-ineligible state11/control4 baselines for Phase 8."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np


STATE_DIM_V2 = 11
CONTROL_DIM_V2 = 4
BASELINE_VERSION_V2 = "phase8-koopman-baselines-v1"


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _model_arrays(states: Any, controls: Any) -> tuple[np.ndarray, np.ndarray, bool]:
    state_array = np.asarray(states, dtype=np.float64)
    control_array = np.asarray(controls, dtype=np.float64)
    single = state_array.ndim == 1
    if single:
        state_array = state_array.reshape(1, -1)
    if control_array.ndim == 1:
        control_array = control_array.reshape(1, -1)
    if (
        state_array.ndim != 2
        or state_array.shape[1] != STATE_DIM_V2
        or control_array.ndim != 2
        or control_array.shape[1] != CONTROL_DIM_V2
        or state_array.shape[0] != control_array.shape[0]
        or state_array.shape[0] == 0
    ):
        _fail("baseline_shape_invalid")
    if not np.isfinite(state_array).all() or not np.isfinite(control_array).all():
        _fail("baseline_nonfinite")
    return state_array, control_array, single


@dataclass(frozen=True)
class PersistenceBaselineV2:
    state_dim: int = STATE_DIM_V2
    control_dim: int = CONTROL_DIM_V2
    version: str = BASELINE_VERSION_V2
    role: str = "persistence"
    selection_eligible: bool = False

    def __post_init__(self) -> None:
        if (
            self.state_dim != STATE_DIM_V2
            or self.control_dim != CONTROL_DIM_V2
            or self.version != BASELINE_VERSION_V2
            or self.role != "persistence"
            or self.selection_eligible is not False
        ):
            _fail("baseline_contract_invalid")

    def predict_next(self, state: Any, control: Any) -> np.ndarray:
        states, _, single = _model_arrays(state, control)
        prediction = np.array(states, copy=True)
        return prediction[0] if single else prediction


@dataclass(frozen=True)
class SimpleLinearBaselineV2:
    coefficient_matrix: np.ndarray
    ridge: float
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    state_dim: int = STATE_DIM_V2
    control_dim: int = CONTROL_DIM_V2
    version: str = BASELINE_VERSION_V2
    role: str = "simple_linear_v2"
    selection_eligible: bool = False

    def __post_init__(self) -> None:
        coefficients = np.array(self.coefficient_matrix, dtype=np.float64, copy=True)
        if coefficients.shape != (STATE_DIM_V2, 1 + STATE_DIM_V2 + CONTROL_DIM_V2):
            _fail("baseline_shape_invalid", "coefficient_matrix")
        if not np.isfinite(coefficients).all():
            _fail("baseline_nonfinite", "coefficient_matrix")
        if not np.isfinite(self.ridge) or self.ridge < 0.0:
            _fail("baseline_ridge_invalid")
        coefficients.setflags(write=False)
        object.__setattr__(self, "coefficient_matrix", coefficients)
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))
        if (
            self.state_dim != STATE_DIM_V2
            or self.control_dim != CONTROL_DIM_V2
            or self.version != BASELINE_VERSION_V2
            or self.role != "simple_linear_v2"
            or self.selection_eligible is not False
        ):
            _fail("baseline_contract_invalid")

    def predict_next(self, state: Any, control: Any) -> np.ndarray:
        states, controls, single = _model_arrays(state, control)
        design = np.concatenate(
            [np.ones((states.shape[0], 1), dtype=np.float64), states, controls],
            axis=1,
        )
        prediction = design @ self.coefficient_matrix.T
        return prediction[0] if single else prediction


def fit_simple_linear_baseline_v2(
    states: Any,
    controls: Any,
    targets: Any,
    *,
    ridge: float = 1.0e-6,
) -> SimpleLinearBaselineV2:
    state_array, control_array, _ = _model_arrays(states, controls)
    target_array = np.asarray(targets, dtype=np.float64)
    if target_array.shape != (state_array.shape[0], STATE_DIM_V2):
        _fail("baseline_shape_invalid", "targets")
    if not np.isfinite(target_array).all():
        _fail("baseline_nonfinite", "targets")
    if not np.isfinite(ridge) or ridge < 0.0:
        _fail("baseline_ridge_invalid")
    design = np.concatenate(
        [np.ones((state_array.shape[0], 1), dtype=np.float64), state_array, control_array],
        axis=1,
    )
    rank = int(np.linalg.matrix_rank(design))
    gram = design.T @ design
    rhs = design.T @ target_array
    if ridge > 0.0:
        gram = gram + ridge * np.eye(gram.shape[0], dtype=np.float64)
    method = "solve" if ridge > 0.0 or rank == design.shape[1] else "pinv"
    if method == "solve":
        try:
            coefficients = np.linalg.solve(gram, rhs).T
        except np.linalg.LinAlgError:
            method = "pinv"
    if method == "pinv":
        coefficients = (np.linalg.pinv(gram) @ rhs).T
    return SimpleLinearBaselineV2(
        coefficient_matrix=coefficients,
        ridge=float(ridge),
        diagnostics={
            "design_rank": rank,
            "design_width": int(design.shape[1]),
            "sample_count": int(design.shape[0]),
            "solve_method": method,
        },
    )

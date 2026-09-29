"""SO(3)-increment EDMD and structured conditional design for Phase 8.1."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Any, ClassVar, Mapping, Sequence

import numpy as np

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.contracts_v21 import (
    CONDITIONING_STRUCTURED_PCA2_V21,
    CONDITIONAL_NOT_APPLICABLE_SCOPE_V21 as CONDITIONAL_POPULATION_NOT_APPLICABLE_V21,
    FINAL_REFIT_ALL8_SCOPE_V21 as CONDITIONAL_POPULATION_FINAL_REFIT_ALL8_V21,
    LOCO_SOURCE7_SCOPE_V21 as CONDITIONAL_POPULATION_LOCO_SOURCE7_V21,
)
from koopman.evidence_v2 import canonical_sha256
from koopman.so3_v21 import (
    INCREMENT_TARGET_DIM_V21,
    STATE_DIM_V21,
    build_increment_target_v21,
    quaternion_to_r6_v21,
)


MODEL_VERSION_V21 = "koopman-so3-edmd-v2.1"
PRIMARY_INPUT_DIM_V21 = 19
ACTUATOR_MEMORY_DIM_V21 = 4
CONTROL_DIM_V21 = 4
PCA_SCORE_DIM_V21 = 2
REGULARIZED_CONDITION_LIMIT_V21 = 1.0e8
ESTIMATOR_EQUIVALENCE_CLASS_V21 = "so3_linear_increment_ridge_v1"
CONDITIONING_NONE_V21 = "none"

LINEAR_NONBIAS_FEATURE_NAMES_V21 = (
    "depth_m",
    "R00",
    "R10",
    "R20",
    "R01",
    "R11",
    "R21",
    "linear_velocity_body_x",
    "linear_velocity_body_y",
    "linear_velocity_body_z",
    "angular_velocity_body_x",
    "angular_velocity_body_y",
    "angular_velocity_body_z",
    "actuator_memory_roll",
    "actuator_memory_pitch",
    "actuator_memory_yaw",
    "actuator_memory_depth",
    "virtual_control_roll",
    "virtual_control_pitch",
    "virtual_control_yaw",
    "virtual_control_depth",
)

_R6_NAMES = LINEAR_NONBIAS_FEATURE_NAMES_V21[1:7]
_LINEAR_VELOCITY_NAMES = LINEAR_NONBIAS_FEATURE_NAMES_V21[7:10]
_ANGULAR_VELOCITY_NAMES = LINEAR_NONBIAS_FEATURE_NAMES_V21[10:13]
KINEMATIC_LIFT_FEATURE_NAMES_V21 = (
    "depth_m_squared",
    *(f"{name}_squared" for name in _LINEAR_VELOCITY_NAMES),
    *(f"{name}_squared" for name in _ANGULAR_VELOCITY_NAMES),
    *(
        f"{rotation_name}_x_{angular_name}"
        for rotation_name in _R6_NAMES
        for angular_name in _ANGULAR_VELOCITY_NAMES
    ),
    *(
        f"{linear_name}_x_{angular_name}"
        for linear_name in _LINEAR_VELOCITY_NAMES
        for angular_name in _ANGULAR_VELOCITY_NAMES
    ),
)

_OBSERVABLE_NAMES = MappingProxyType(
    {
        "so3_identity_v1": ("bias",) + LINEAR_NONBIAS_FEATURE_NAMES_V21,
        "so3_kinematic_v1": (
            ("bias",)
            + LINEAR_NONBIAS_FEATURE_NAMES_V21
            + KINEMATIC_LIFT_FEATURE_NAMES_V21
        ),
    }
)
_CONDITIONING_MODES = frozenset(
    {CONDITIONING_NONE_V21, CONDITIONING_STRUCTURED_PCA2_V21}
)
_NORMALIZATION_MODES = frozenset({"none", "standard_v1"})


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def observable_feature_names_v21(name: str) -> tuple[str, ...]:
    try:
        return _OBSERVABLE_NAMES[name]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"observable_schema_unknown:{name}") from exc


def _rows(value: Any, width: int, name: str) -> tuple[np.ndarray, bool]:
    array = np.asarray(value, dtype=np.float64)
    single = array.ndim == 1
    if single:
        array = array.reshape(1, -1)
    if array.ndim != 2 or array.shape[1] != width:
        _fail("model_shape_invalid", name)
    if not np.isfinite(array).all():
        _fail("model_nonfinite", name)
    return np.array(array, dtype=np.float64, copy=True), single


def _primary_rows(
    states: Any, actuator_memory: Any, controls: Any
) -> tuple[np.ndarray, np.ndarray, np.ndarray, bool]:
    state_array, state_single = _rows(states, STATE_DIM_V21, "states")
    memory_array, memory_single = _rows(
        actuator_memory, ACTUATOR_MEMORY_DIM_V21, "actuator_memory"
    )
    control_array, control_single = _rows(controls, CONTROL_DIM_V21, "controls")
    if not (
        state_array.shape[0] == memory_array.shape[0] == control_array.shape[0]
    ):
        _fail("model_shape_invalid", "row_count")
    if state_single != memory_single or state_single != control_single:
        _fail("model_shape_invalid", "batch_mode")
    return state_array, memory_array, control_array, state_single


def _linear_nonbias_rows(
    states: np.ndarray, memories: np.ndarray, controls: np.ndarray
) -> np.ndarray:
    result = np.empty((states.shape[0], len(LINEAR_NONBIAS_FEATURE_NAMES_V21)))
    for index, state in enumerate(states):
        result[index] = np.concatenate(
            (
                [state[0]],
                quaternion_to_r6_v21(state[1:5]),
                state[5:8],
                state[8:11],
                memories[index],
                controls[index],
            )
        )
    return result


def build_observable_features_v21(
    states: Any,
    actuator_memory: Any,
    controls: Any,
    observable_schema: str,
) -> np.ndarray:
    """Build the frozen 22D/56D handcrafted feature library."""

    names = observable_feature_names_v21(observable_schema)
    state_array, memory_array, control_array, single = _primary_rows(
        states, actuator_memory, controls
    )
    linear = _linear_nonbias_rows(state_array, memory_array, control_array)
    identity = np.column_stack((np.ones(state_array.shape[0]), linear))
    if observable_schema == "so3_identity_v1":
        result = identity
    else:
        depth = state_array[:, [0]]
        velocity = state_array[:, 5:8]
        angular = state_array[:, 8:11]
        r6 = linear[:, 1:7]
        lift_parts = [depth**2, velocity**2, angular**2]
        lift_parts.extend(
            r6[:, [rotation_index]] * angular[:, [angular_index]]
            for rotation_index in range(6)
            for angular_index in range(3)
        )
        lift_parts.extend(
            velocity[:, [linear_index]] * angular[:, [angular_index]]
            for linear_index in range(3)
            for angular_index in range(3)
        )
        result = np.column_stack((identity, *lift_parts))
    if result.shape[1] != len(names):
        _fail("observable_width_invalid")
    return result[0] if single else result


def build_conditional_design_v21(
    observable_features: Any, platform_scores: Any
) -> np.ndarray:
    phi = np.asarray(observable_features, dtype=np.float64)
    scores = np.asarray(platform_scores, dtype=np.float64)
    single = phi.ndim == 1
    if single:
        phi = phi.reshape(1, -1)
        scores = scores.reshape(1, -1)
    if (
        phi.ndim != 2
        or phi.shape[1] not in (22, 56)
        or scores.shape != (phi.shape[0], PCA_SCORE_DIM_V21)
        or not np.isfinite(phi).all()
        or not np.isfinite(scores).all()
    ):
        _fail("conditional_design_shape_invalid")
    linear_nonbias = phi[:, 1:22]
    result = np.column_stack(
        (
            phi,
            scores,
            scores[:, [0]] * linear_nonbias,
            scores[:, [1]] * linear_nonbias,
        )
    )
    expected = 66 if phi.shape[1] == 22 else 100
    if result.shape[1] != expected:
        _fail("conditional_design_width_invalid")
    return result[0] if single else result


def build_increment_targets_v21(states: Any, next_states: Any) -> np.ndarray:
    current, current_single = _rows(states, STATE_DIM_V21, "states")
    following, next_single = _rows(next_states, STATE_DIM_V21, "next_states")
    if current.shape != following.shape or current_single != next_single:
        _fail("model_shape_invalid", "next_states")
    result = np.asarray(
        [
            build_increment_target_v21(first, second)
            for first, second in zip(current, following, strict=True)
        ],
        dtype=np.float64,
    )
    return result[0] if current_single else result


@dataclass(frozen=True)
class DesignNormalizerV21:
    mean: np.ndarray
    scale: np.ndarray

    def __post_init__(self) -> None:
        mean = np.array(self.mean, dtype=np.float64, copy=True)
        scale = np.array(self.scale, dtype=np.float64, copy=True)
        if (
            mean.ndim != 1
            or scale.shape != mean.shape
            or not np.isfinite(mean).all()
            or not np.isfinite(scale).all()
            or np.any(scale <= 0.0)
            or mean[0] != 0.0
            or scale[0] != 1.0
        ):
            _fail("design_normalizer_invalid")
        mean.setflags(write=False)
        scale.setflags(write=False)
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "scale", scale)

    @classmethod
    def fit(cls, design: Any) -> "DesignNormalizerV21":
        values = np.asarray(design, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] < 1 or not np.isfinite(values).all():
            _fail("design_invalid")
        mean = np.mean(values, axis=0, dtype=np.float64)
        scale = np.std(values, axis=0, ddof=0, dtype=np.float64)
        mean[0] = 0.0
        scale[0] = 1.0
        scale[scale == 0.0] = 1.0
        return cls(mean, scale)

    def transform(self, design: Any) -> np.ndarray:
        values = np.asarray(design, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != self.mean.size:
            _fail("design_invalid")
        result = (values - self.mean) / self.scale
        result[:, 0] = values[:, 0]
        if not np.isfinite(result).all():
            _fail("model_nonfinite")
        return result

    def to_dict(self) -> dict[str, Any]:
        return {"mean": self.mean.tolist(), "scale": self.scale.tolist()}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "DesignNormalizerV21 | None":
        if value is None:
            return None
        if not isinstance(value, Mapping) or set(value) != {"mean", "scale"}:
            _fail("design_normalizer_invalid")
        return cls(np.asarray(value["mean"]), np.asarray(value["scale"]))


@dataclass(frozen=True)
class TargetNormalizerV21:
    mean: np.ndarray
    scale: np.ndarray

    def __post_init__(self) -> None:
        mean = np.array(self.mean, dtype=np.float64, copy=True)
        scale = np.array(self.scale, dtype=np.float64, copy=True)
        if (
            mean.shape != (INCREMENT_TARGET_DIM_V21,)
            or scale.shape != mean.shape
            or not np.isfinite(mean).all()
            or not np.isfinite(scale).all()
            or np.any(scale <= 0.0)
        ):
            _fail("target_normalizer_invalid")
        mean.setflags(write=False)
        scale.setflags(write=False)
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "scale", scale)

    @classmethod
    def fit(cls, targets: np.ndarray) -> "TargetNormalizerV21":
        mean = np.mean(targets, axis=0, dtype=np.float64)
        scale = np.std(targets, axis=0, ddof=0, dtype=np.float64)
        scale[scale == 0.0] = 1.0
        return cls(mean, scale)

    def transform(self, targets: np.ndarray) -> np.ndarray:
        return (targets - self.mean) / self.scale

    def inverse_transform(self, targets: np.ndarray) -> np.ndarray:
        return targets * self.scale + self.mean

    def to_dict(self) -> dict[str, Any]:
        return {"mean": self.mean.tolist(), "scale": self.scale.tolist()}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "TargetNormalizerV21 | None":
        if value is None:
            return None
        if not isinstance(value, Mapping) or set(value) != {"mean", "scale"}:
            _fail("target_normalizer_invalid")
        return cls(np.asarray(value["mean"]), np.asarray(value["scale"]))


@dataclass(frozen=True)
class SolveDesignDiagnosticsV21:
    design_rank: int
    effective_rank: float
    design_width: int
    regularized_condition: float
    rank_tolerance: float
    admitted: bool
    rejection_reason: str | None

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "admitted",
            "design_rank",
            "design_width",
            "effective_rank",
            "rank_tolerance",
            "regularized_condition",
            "rejection_reason",
        }
    )

    def __post_init__(self) -> None:
        if (
            isinstance(self.design_rank, bool)
            or not isinstance(self.design_rank, int)
            or self.design_rank < 0
            or isinstance(self.design_width, bool)
            or not isinstance(self.design_width, int)
            or self.design_width <= 0
            or self.design_rank > self.design_width
            or type(self.admitted) is not bool
        ):
            _fail("solve_design_diagnostics_invalid")
        for name in ("effective_rank", "rank_tolerance", "regularized_condition"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                _fail("solve_design_diagnostics_invalid", name)
            numeric = float(value)
            if numeric < 0.0 or (
                name != "regularized_condition" and not math.isfinite(numeric)
            ):
                _fail("solve_design_diagnostics_invalid", name)
            object.__setattr__(self, name, numeric)
        if self.admitted:
            if (
                self.rejection_reason is not None
                or self.design_rank != self.design_width
                or not math.isfinite(self.regularized_condition)
                or self.regularized_condition > REGULARIZED_CONDITION_LIMIT_V21
            ):
                _fail("solve_design_diagnostics_invalid", "admitted")
        elif not isinstance(self.rejection_reason, str) or not self.rejection_reason:
            _fail("solve_design_diagnostics_invalid", "rejection_reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "design_rank": self.design_rank,
            "design_width": self.design_width,
            "effective_rank": self.effective_rank,
            "rank_tolerance": self.rank_tolerance,
            "regularized_condition": self.regularized_condition,
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "SolveDesignDiagnosticsV21":
        if not isinstance(value, Mapping) or set(value) != cls._FIELDS:
            _fail("solve_design_diagnostics_invalid", "field_set")
        return cls(
            design_rank=value["design_rank"],
            effective_rank=value["effective_rank"],
            design_width=value["design_width"],
            regularized_condition=value["regularized_condition"],
            rank_tolerance=value["rank_tolerance"],
            admitted=value["admitted"],
            rejection_reason=value["rejection_reason"],
        )


def diagnose_solve_design_v21(
    design: Any, *, ridge: float
) -> SolveDesignDiagnosticsV21:
    values = np.asarray(design, dtype=np.float64)
    if (
        values.ndim != 2
        or values.shape[1] < 1
        or not np.isfinite(values).all()
        or isinstance(ridge, bool)
        or not isinstance(ridge, (int, float))
        or not math.isfinite(float(ridge))
        or ridge < 0.0
    ):
        _fail("design_invalid")
    width = int(values.shape[1])
    singular = np.linalg.svd(values, compute_uv=False)
    padded = np.zeros(width, dtype=np.float64)
    padded[: singular.size] = singular
    largest = float(padded[0]) if padded.size else 0.0
    tolerance = np.finfo(np.float64).eps * max(values.shape) * largest
    rank = int(np.count_nonzero(padded > tolerance))
    positive = padded[padded > 0.0]
    if positive.size:
        probabilities = positive / np.sum(positive)
        effective_rank = float(
            math.exp(-float(np.sum(probabilities * np.log(probabilities))))
        )
    else:
        effective_rank = 0.0
    smallest = float(padded[-1]) if padded.size else 0.0
    denominator = smallest * smallest + float(ridge)
    regularized_condition = (
        math.inf
        if denominator == 0.0
        else (largest * largest + float(ridge)) / denominator
    )
    rejection = None
    if rank != width:
        rejection = "design_rank_below_width"
    elif not math.isfinite(regularized_condition) or regularized_condition > REGULARIZED_CONDITION_LIMIT_V21:
        rejection = "regularized_condition_above_limit"
    return SolveDesignDiagnosticsV21(
        design_rank=rank,
        effective_rank=effective_rank,
        design_width=width,
        regularized_condition=regularized_condition,
        rank_tolerance=tolerance,
        admitted=rejection is None,
        rejection_reason=rejection,
    )


class CandidateAdmissionErrorV21(ValueError):
    def __init__(self, diagnostics: Mapping[str, Any]) -> None:
        self.diagnostics = MappingProxyType(dict(diagnostics))
        super().__init__(str(self.diagnostics.get("rejection_reason", "candidate_rejected")))


def ridge_solve_v21(design: Any, targets: Any, *, ridge: float) -> np.ndarray:
    values = np.asarray(design, dtype=np.float64)
    target_values = np.asarray(targets, dtype=np.float64)
    if (
        values.ndim != 2
        or target_values.ndim != 2
        or target_values.shape[0] != values.shape[0]
        or not np.isfinite(values).all()
        or not np.isfinite(target_values).all()
        or not math.isfinite(float(ridge))
        or ridge < 0.0
    ):
        _fail("ridge_solve_invalid")
    gram = values.T @ values + float(ridge) * np.eye(values.shape[1])
    rhs = values.T @ target_values
    try:
        solution = np.linalg.solve(gram, rhs)
    except np.linalg.LinAlgError as exc:
        raise ValueError("ridge_solve_failed") from exc
    return solution.T


@dataclass(frozen=True)
class ControlledEDMDV21:
    coefficient_matrix: np.ndarray
    observable_schema: str
    conditioning: str
    ridge: float
    normalization: str
    diagnostics: Mapping[str, Any]
    design_normalizer: DesignNormalizerV21 | None = None
    target_normalizer: TargetNormalizerV21 | None = None
    source_configurations: tuple[str, ...] = ()
    population_scope: str = CONDITIONAL_POPULATION_NOT_APPLICABLE_V21
    version: str = MODEL_VERSION_V21
    model_sha256: str = field(init=False)

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "coefficient_matrix",
            "conditioning",
            "design_normalizer",
            "diagnostics",
            "model_sha256",
            "normalization",
            "observable_schema",
            "population_scope",
            "ridge",
            "source_configurations",
            "target_normalizer",
            "version",
        }
    )

    def __post_init__(self) -> None:
        names = observable_feature_names_v21(self.observable_schema)
        if (
            self.conditioning not in _CONDITIONING_MODES
            or self.normalization not in _NORMALIZATION_MODES
            or self.version != MODEL_VERSION_V21
        ):
            _fail("model_contract_invalid")
        if (
            isinstance(self.ridge, bool)
            or not isinstance(self.ridge, (int, float))
            or not math.isfinite(float(self.ridge))
            or float(self.ridge) < 0.0
        ):
            _fail("ridge_invalid")
        object.__setattr__(self, "ridge", float(self.ridge))
        width = (
            len(names)
            if self.conditioning == CONDITIONING_NONE_V21
            else (66 if len(names) == 22 else 100)
        )
        coefficients = np.array(self.coefficient_matrix, dtype=np.float64, copy=True)
        if coefficients.shape != (INCREMENT_TARGET_DIM_V21, width) or not np.isfinite(coefficients).all():
            _fail("model_shape_invalid", "coefficient_matrix")
        try:
            solve_diagnostics = SolveDesignDiagnosticsV21.from_mapping(
                self.diagnostics
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError("model_diagnostics_invalid") from exc
        if (
            not solve_diagnostics.admitted
            or solve_diagnostics.rejection_reason is not None
            or solve_diagnostics.design_rank != solve_diagnostics.design_width
            or solve_diagnostics.design_width != width
            or not math.isfinite(solve_diagnostics.regularized_condition)
            or solve_diagnostics.regularized_condition
            > REGULARIZED_CONDITION_LIMIT_V21
        ):
            _fail("model_diagnostics_invalid")
        if self.normalization == "none" and (
            self.design_normalizer is not None or self.target_normalizer is not None
        ):
            _fail("model_normalizer_forbidden")
        if self.normalization == "standard_v1" and (
            self.design_normalizer is None or self.target_normalizer is None
        ):
            _fail("model_normalizer_required")
        sources = tuple(self.source_configurations)
        if self.conditioning == CONDITIONING_STRUCTURED_PCA2_V21:
            expected_count = {
                CONDITIONAL_POPULATION_LOCO_SOURCE7_V21: 7,
                CONDITIONAL_POPULATION_FINAL_REFIT_ALL8_V21: 8,
            }.get(self.population_scope)
            if (
                expected_count is None
                or len(sources) != expected_count
                or len(set(sources)) != expected_count
                or (
                    self.population_scope
                    == CONDITIONAL_POPULATION_FINAL_REFIT_ALL8_V21
                    and sources != tuple(SUPPORTED_EMBODIMENTS)
                )
            ):
                _fail("conditional_population_scope_invalid")
        elif (
            self.population_scope != CONDITIONAL_POPULATION_NOT_APPLICABLE_V21
            or sources
        ):
            _fail("conditional_population_scope_invalid")
        coefficients.setflags(write=False)
        object.__setattr__(self, "coefficient_matrix", coefficients)
        object.__setattr__(self, "source_configurations", sources)
        object.__setattr__(
            self,
            "diagnostics",
            MappingProxyType(solve_diagnostics.to_dict()),
        )
        object.__setattr__(self, "model_sha256", canonical_sha256(self.payload_without_hash()))

    @property
    def design_width(self) -> int:
        return int(self.coefficient_matrix.shape[1])

    @property
    def simple_linear_equivalent(self) -> bool:
        return (
            self.observable_schema == "so3_identity_v1"
            and self.conditioning == CONDITIONING_NONE_V21
        )

    @property
    def estimator_equivalence_class(self) -> str:
        if self.simple_linear_equivalent:
            return ESTIMATOR_EQUIVALENCE_CLASS_V21
        if self.conditioning == CONDITIONING_STRUCTURED_PCA2_V21:
            return "structured_conditional_pca2_v1"
        return "handcrafted_koopman_style_nonlinear_v1"

    @classmethod
    def fit(
        cls,
        states: Any,
        actuator_memory: Any,
        controls: Any,
        targets: Any,
        *,
        observable_schema: str,
        conditioning: str,
        ridge: float,
        normalization: str,
        platform_scores: Any | None = None,
        row_configurations: Sequence[str] | None = None,
        source_configurations: Sequence[str] = (),
        population_scope: str | None = None,
    ) -> "ControlledEDMDV21":
        state_array, memory_array, control_array, single = _primary_rows(
            states, actuator_memory, controls
        )
        if single:
            _fail("model_shape_invalid", "fit_requires_batch")
        target_array, target_single = _rows(
            targets, INCREMENT_TARGET_DIM_V21, "targets"
        )
        if target_single or target_array.shape[0] != state_array.shape[0]:
            _fail("model_shape_invalid", "targets")
        if conditioning not in _CONDITIONING_MODES:
            _fail("conditioning_unknown")
        if normalization not in _NORMALIZATION_MODES:
            _fail("normalization_unknown")
        phi = build_observable_features_v21(
            state_array, memory_array, control_array, observable_schema
        )
        sources = tuple(source_configurations)
        if conditioning == CONDITIONING_NONE_V21:
            if platform_scores is not None or row_configurations is not None:
                _fail("platform_features_forbidden")
            if population_scope not in (
                None,
                CONDITIONAL_POPULATION_NOT_APPLICABLE_V21,
            ) or sources:
                _fail("conditional_population_scope_invalid")
            resolved_population_scope = CONDITIONAL_POPULATION_NOT_APPLICABLE_V21
            design = phi
        else:
            resolved_population_scope = (
                CONDITIONAL_POPULATION_LOCO_SOURCE7_V21
                if population_scope is None
                else population_scope
            )
            expected_count = {
                CONDITIONAL_POPULATION_LOCO_SOURCE7_V21: 7,
                CONDITIONAL_POPULATION_FINAL_REFIT_ALL8_V21: 8,
            }.get(resolved_population_scope)
            if (
                expected_count is None
                or len(sources) != expected_count
                or len(set(sources)) != expected_count
            ):
                _fail("conditional_population_scope_invalid")
            labels = tuple(row_configurations or ())
            if len(labels) != state_array.shape[0] or set(labels) != set(sources):
                _fail("source_configuration_set_mismatch")
            if any(label not in sources for label in labels):
                _fail("heldout_design_leakage")
            design = build_conditional_design_v21(phi, platform_scores)
        design_normalizer = (
            DesignNormalizerV21.fit(design)
            if normalization == "standard_v1"
            else None
        )
        target_normalizer = (
            TargetNormalizerV21.fit(target_array)
            if normalization == "standard_v1"
            else None
        )
        solve_design = (
            design_normalizer.transform(design)
            if design_normalizer is not None
            else design
        )
        solve_target = (
            target_normalizer.transform(target_array)
            if target_normalizer is not None
            else target_array
        )
        diagnostics = diagnose_solve_design_v21(solve_design, ridge=ridge)
        if not diagnostics.admitted:
            raise CandidateAdmissionErrorV21(diagnostics.to_dict())
        coefficients = ridge_solve_v21(solve_design, solve_target, ridge=ridge)
        return cls(
            coefficient_matrix=coefficients,
            observable_schema=observable_schema,
            conditioning=conditioning,
            ridge=float(ridge),
            normalization=normalization,
            diagnostics=diagnostics.to_dict(),
            design_normalizer=design_normalizer,
            target_normalizer=target_normalizer,
            source_configurations=sources,
            population_scope=resolved_population_scope,
        )

    def _design(
        self,
        states: Any,
        actuator_memory: Any,
        controls: Any,
        platform_score: Any | None,
    ) -> tuple[np.ndarray, bool]:
        state_array, memory_array, control_array, single = _primary_rows(
            states, actuator_memory, controls
        )
        phi = build_observable_features_v21(
            state_array, memory_array, control_array, self.observable_schema
        )
        if self.conditioning == CONDITIONING_NONE_V21:
            if platform_score is not None:
                _fail("platform_features_forbidden")
            return phi, single
        if platform_score is None:
            _fail("platform_score_required")
        scores = np.asarray(platform_score, dtype=np.float64)
        if single:
            scores = scores.reshape(1, -1)
        design = build_conditional_design_v21(phi, scores)
        return design, single

    def predict_increment(
        self,
        state: Any,
        actuator_memory: Any,
        control: Any,
        *,
        platform_score: Any | None = None,
    ) -> np.ndarray:
        design, single = self._design(
            state, actuator_memory, control, platform_score
        )
        solve_design = (
            self.design_normalizer.transform(design)
            if self.design_normalizer is not None
            else design
        )
        prediction = solve_design @ self.coefficient_matrix.T
        if self.target_normalizer is not None:
            prediction = self.target_normalizer.inverse_transform(prediction)
        if not np.isfinite(prediction).all():
            _fail("model_nonfinite", "prediction")
        return prediction[0] if single else prediction

    def payload_without_hash(self) -> dict[str, Any]:
        return {
            "coefficient_matrix": self.coefficient_matrix.tolist(),
            "conditioning": self.conditioning,
            "design_normalizer": None if self.design_normalizer is None else self.design_normalizer.to_dict(),
            "diagnostics": dict(self.diagnostics),
            "normalization": self.normalization,
            "observable_schema": self.observable_schema,
            "population_scope": self.population_scope,
            "ridge": self.ridge,
            "source_configurations": list(self.source_configurations),
            "target_normalizer": None if self.target_normalizer is None else self.target_normalizer.to_dict(),
            "version": self.version,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload_without_hash(), "model_sha256": self.model_sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ControlledEDMDV21":
        if not isinstance(value, Mapping) or set(value) != cls._FIELDS:
            _fail("model_field_set_mismatch")
        result = cls(
            coefficient_matrix=np.asarray(value["coefficient_matrix"]),
            observable_schema=str(value["observable_schema"]),
            conditioning=str(value["conditioning"]),
            ridge=value["ridge"],
            normalization=str(value["normalization"]),
            diagnostics=dict(value["diagnostics"]),
            design_normalizer=DesignNormalizerV21.from_dict(value["design_normalizer"]),
            target_normalizer=TargetNormalizerV21.from_dict(value["target_normalizer"]),
            source_configurations=tuple(value["source_configurations"]),
            population_scope=str(value["population_scope"]),
            version=str(value["version"]),
        )
        if value.get("model_sha256") != result.model_sha256:
            _fail("model_hash_mismatch")
        return result

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(self.to_dict(), handle, indent=2, sort_keys=True, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    @classmethod
    def load(cls, path: str | Path) -> "ControlledEDMDV21":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

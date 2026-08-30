"""One additive controlled-EDMD backend for all Phase 8 Koopman regimes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Any, ClassVar

import numpy as np

from koopman.evidence_v2 import canonical_sha256
from koopman.platform_features_v2 import (
    PlatformFeatureDescriptorV2,
    PlatformFeatureNormalizerV2,
    select_platform_feature_schema_v2,
)
from koopman.preprocessing_v2 import QUATERNION_PREPROCESSOR_VERSION_V2
from koopman.splits_v2 import LOCOFoldManifestV2


STATE_DIM_V2 = 11
CONTROL_DIM_V2 = 4
MODEL_VERSION_V2 = "phase8-controlled-edmd-v2"
OBSERVABLE_SCHEMA_VERSION_V2 = "phase8-observable-schema-v1"
ARRAY_NORMALIZER_VERSION_V2 = "phase8-array-normalizer-v1"
_NORMALIZATION_MODES = frozenset({"none", "standard_v1"})
_CONDITIONING_MODES = frozenset({"none", "platform_affine"})
_STATE_FEATURES = (
    "depth_z",
    "quat_w",
    "quat_x",
    "quat_y",
    "quat_z",
    "lin_vel_b_x",
    "lin_vel_b_y",
    "lin_vel_b_z",
    "ang_vel_b_x",
    "ang_vel_b_y",
    "ang_vel_b_z",
)
_IDENTITY_FEATURES = ("bias", *_STATE_FEATURES)
_AUV_KINEMATIC_FEATURES = _IDENTITY_FEATURES + (
    "depth_z_sq",
    "lin_vel_b_x_sq",
    "lin_vel_b_y_sq",
    "lin_vel_b_z_sq",
    "ang_vel_b_x_sq",
    "ang_vel_b_y_sq",
    "ang_vel_b_z_sq",
    *(f"{quat}_x_{angular}" for quat in _STATE_FEATURES[1:5] for angular in _STATE_FEATURES[8:11]),
    *(f"{linear}_x_{angular}" for linear in _STATE_FEATURES[5:8] for angular in _STATE_FEATURES[8:11]),
)
_OBSERVABLES = MappingProxyType(
    {
        "identity_v1": _IDENTITY_FEATURES,
        "auv_kinematic_v1": _AUV_KINEMATIC_FEATURES,
    }
)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _readonly_matrix(value: Any, *, width: int, name: str) -> np.ndarray:
    array = np.array(value, dtype=np.float64, copy=True)
    if array.ndim != 2 or array.shape[1] != width or array.shape[0] == 0:
        _fail("model_shape_invalid", name)
    if not np.isfinite(array).all():
        _fail("model_nonfinite", name)
    array.setflags(write=False)
    return array


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
        _fail("model_shape_invalid")
    if not np.isfinite(state_array).all() or not np.isfinite(control_array).all():
        _fail("model_nonfinite")
    return state_array, control_array, single


def observable_feature_names_v2(schema_name: str) -> tuple[str, ...]:
    try:
        return _OBSERVABLES[schema_name]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"observable_schema_unknown:{schema_name}") from exc


def _observable_schema_sha256(schema_name: str) -> str:
    return canonical_sha256(
        {
            "feature_names": list(observable_feature_names_v2(schema_name)),
            "schema_name": schema_name,
            "schema_version": OBSERVABLE_SCHEMA_VERSION_V2,
        }
    )


def _lift_state_v2(states: np.ndarray, schema_name: str) -> np.ndarray:
    bias = np.ones((states.shape[0], 1), dtype=np.float64)
    identity = np.concatenate([bias, states], axis=1)
    if schema_name == "identity_v1":
        return identity
    if schema_name != "auv_kinematic_v1":
        _fail("observable_schema_unknown", str(schema_name))
    depth_square = np.square(states[:, [0]])
    linear = states[:, 5:8]
    angular = states[:, 8:11]
    quaternion = states[:, 1:5]
    quaternion_angular = np.einsum("ni,nj->nij", quaternion, angular).reshape(
        states.shape[0], -1
    )
    linear_angular = np.einsum("ni,nj->nij", linear, angular).reshape(
        states.shape[0], -1
    )
    return np.concatenate(
        [
            identity,
            depth_square,
            np.square(linear),
            np.square(angular),
            quaternion_angular,
            linear_angular,
        ],
        axis=1,
    )


def build_controlled_design_v2(
    states: Any,
    controls: Any,
    *,
    observable_schema: str,
    conditioning: str,
    normalized_platform_features: Any | None = None,
) -> np.ndarray:
    state_array, control_array, _ = _model_arrays(states, controls)
    if conditioning not in _CONDITIONING_MODES:
        _fail("conditioning_unknown", str(conditioning))
    base = np.concatenate(
        [_lift_state_v2(state_array, observable_schema), control_array], axis=1
    )
    if conditioning == "none":
        if normalized_platform_features is not None:
            _fail("platform_features_forbidden")
        return base
    if normalized_platform_features is None:
        _fail("platform_features_required")
    physical = np.asarray(normalized_platform_features, dtype=np.float64)
    if (
        physical.ndim != 2
        or physical.shape[0] != base.shape[0]
        or physical.shape[1] == 0
    ):
        _fail("model_shape_invalid", "platform_features")
    if not np.isfinite(physical).all():
        _fail("model_nonfinite", "platform_features")
    interactions = np.einsum("ni,nj->nij", physical, base).reshape(base.shape[0], -1)
    return np.concatenate([base, physical, interactions], axis=1)


@dataclass(frozen=True)
class ArrayNormalizerV2:
    mean: np.ndarray
    scale: np.ndarray
    version: str = ARRAY_NORMALIZER_VERSION_V2
    normalizer_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        mean = np.array(self.mean, dtype=np.float64, copy=True)
        scale = np.array(self.scale, dtype=np.float64, copy=True)
        if (
            mean.ndim != 1
            or scale.shape != mean.shape
            or mean.size == 0
            or not np.isfinite(mean).all()
            or not np.isfinite(scale).all()
            or np.any(scale <= 0.0)
            or self.version != ARRAY_NORMALIZER_VERSION_V2
        ):
            _fail("array_normalizer_invalid")
        mean.setflags(write=False)
        scale.setflags(write=False)
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "scale", scale)
        object.__setattr__(self, "normalizer_sha256", canonical_sha256(self.payload()))

    @classmethod
    def fit(cls, values: np.ndarray) -> "ArrayNormalizerV2":
        mean = np.mean(values, axis=0)
        raw_scale = np.std(values, axis=0)
        return cls(mean=mean, scale=np.where(raw_scale == 0.0, 1.0, raw_scale))

    def transform(self, values: np.ndarray) -> np.ndarray:
        result = (values - self.mean) / self.scale
        if not np.isfinite(result).all():
            _fail("model_nonfinite", "normalized_values")
        return result

    def inverse_transform(self, values: np.ndarray) -> np.ndarray:
        result = values * self.scale + self.mean
        if not np.isfinite(result).all():
            _fail("model_nonfinite", "inverse_normalized_values")
        return result

    def payload(self) -> dict[str, Any]:
        return {
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "version": self.version,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload(), "normalizer_sha256": self.normalizer_sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ArrayNormalizerV2 | None":
        if value is None:
            return None
        result = cls(
            mean=np.asarray(value["mean"], dtype=np.float64),
            scale=np.asarray(value["scale"], dtype=np.float64),
            version=str(value["version"]),
        )
        if value.get("normalizer_sha256") != result.normalizer_sha256:
            _fail("array_normalizer_hash_mismatch")
        return result


def _platform_normalizer_from_dict(
    value: Mapping[str, Any] | None,
) -> PlatformFeatureNormalizerV2 | None:
    if value is None:
        return None
    result = PlatformFeatureNormalizerV2(
        fold_id=str(value["fold_id"]),
        holdout_configuration=str(value["holdout_configuration"]),
        source_configurations=tuple(value["source_configurations"]),
        source_episode_sha256s=tuple(value["source_episode_sha256s"]),
        feature_schema_name=str(value["feature_schema_name"]),
        feature_schema_sha256=str(value["feature_schema_sha256"]),
        mean=np.asarray(value["mean"], dtype=np.float64),
        scale=np.asarray(value["scale"], dtype=np.float64),
        zero_scale_rule=str(value["zero_scale_rule"]),
        normalizer_version=str(value["normalizer_version"]),
    )
    if value.get("normalizer_sha256") != result.normalizer_sha256:
        _fail("platform_normalizer_hash_mismatch")
    return result


def _descriptor_sequence(
    value: PlatformFeatureDescriptorV2 | Sequence[PlatformFeatureDescriptorV2],
    *,
    count: int,
) -> tuple[PlatformFeatureDescriptorV2, ...]:
    if isinstance(value, PlatformFeatureDescriptorV2):
        return (value,) * count
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("platform_descriptor_required")
    descriptors = tuple(value)
    if len(descriptors) != count or not all(
        isinstance(item, PlatformFeatureDescriptorV2) for item in descriptors
    ):
        _fail("model_shape_invalid", "platform_descriptors")
    return descriptors


@dataclass(frozen=True)
class ControlledEDMDV2:
    coefficient_matrix: np.ndarray
    observable_schema: str
    observable_schema_sha256: str
    conditioning: str
    ridge: float
    normalization: str
    preprocessing_sha256: str
    diagnostics: Mapping[str, Any]
    input_normalizer: ArrayNormalizerV2 | None = None
    target_normalizer: ArrayNormalizerV2 | None = None
    platform_normalizer: PlatformFeatureNormalizerV2 | None = None
    fold_id: str | None = None
    holdout_configuration: str | None = None
    source_configurations: tuple[str, ...] = ()
    state_dim: int = STATE_DIM_V2
    control_dim: int = CONTROL_DIM_V2
    version: str = MODEL_VERSION_V2
    backend: str = "controlled_edmd_v2"
    model_sha256: str = field(init=False)

    _SERIALIZED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "backend",
            "coefficient_matrix",
            "conditioning",
            "control_dim",
            "diagnostics",
            "fold_id",
            "holdout_configuration",
            "input_normalizer",
            "model_sha256",
            "normalization",
            "observable_schema",
            "observable_schema_sha256",
            "platform_normalizer",
            "preprocessing_sha256",
            "ridge",
            "source_configurations",
            "state_dim",
            "target_normalizer",
            "version",
        }
    )

    def __post_init__(self) -> None:
        if self.version != MODEL_VERSION_V2 or self.backend != "controlled_edmd_v2":
            _fail("model_version_unsupported")
        if self.state_dim != STATE_DIM_V2 or self.control_dim != CONTROL_DIM_V2:
            _fail("model_dimension_invalid")
        names = observable_feature_names_v2(self.observable_schema)
        expected_schema_sha = _observable_schema_sha256(self.observable_schema)
        if self.observable_schema_sha256 != expected_schema_sha:
            _fail("observable_schema_hash_mismatch")
        if self.conditioning not in _CONDITIONING_MODES:
            _fail("conditioning_unknown")
        if self.normalization not in _NORMALIZATION_MODES:
            _fail("normalization_unknown")
        if not np.isfinite(self.ridge) or self.ridge < 0.0:
            _fail("ridge_invalid")
        if not _is_sha256(self.preprocessing_sha256):
            _fail("preprocessing_hash_invalid")
        if self.conditioning == "platform_affine" and self.platform_normalizer is None:
            _fail("platform_normalizer_required")
        if self.conditioning == "none" and self.platform_normalizer is not None:
            _fail("platform_normalizer_forbidden")
        if self.normalization == "none" and (
            self.input_normalizer is not None or self.target_normalizer is not None
        ):
            _fail("array_normalizer_forbidden")
        if self.normalization == "standard_v1" and (
            self.input_normalizer is None or self.target_normalizer is None
        ):
            _fail("array_normalizer_required")
        coefficients = np.array(self.coefficient_matrix, dtype=np.float64, copy=True)
        platform_dimension = self.platform_feature_dimension
        base_width = len(names) + CONTROL_DIM_V2
        expected_width = (
            base_width
            if self.conditioning == "none"
            else base_width + platform_dimension + platform_dimension * base_width
        )
        if coefficients.shape != (STATE_DIM_V2, expected_width):
            _fail("model_shape_invalid", "coefficient_matrix")
        if not np.isfinite(coefficients).all():
            _fail("model_nonfinite", "coefficient_matrix")
        coefficients.setflags(write=False)
        object.__setattr__(self, "coefficient_matrix", coefficients)
        object.__setattr__(self, "source_configurations", tuple(self.source_configurations))
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))
        object.__setattr__(self, "model_sha256", canonical_sha256(self.payload_without_hash()))

    @property
    def observable_dim(self) -> int:
        return len(observable_feature_names_v2(self.observable_schema))

    @property
    def platform_feature_dimension(self) -> int:
        return 0 if self.platform_normalizer is None else int(self.platform_normalizer.mean.size)

    @property
    def design_width(self) -> int:
        return int(self.coefficient_matrix.shape[1])

    @property
    def platform_normalizer_sha256(self) -> str | None:
        return (
            None
            if self.platform_normalizer is None
            else self.platform_normalizer.normalizer_sha256
        )

    @property
    def input_normalizer_sha256(self) -> str | None:
        return None if self.input_normalizer is None else self.input_normalizer.normalizer_sha256

    @property
    def target_normalizer_sha256(self) -> str | None:
        return None if self.target_normalizer is None else self.target_normalizer.normalizer_sha256

    @classmethod
    def fit(
        cls,
        states: Any,
        controls: Any,
        targets: Any,
        *,
        preprocessing_sha256: str,
        observable_schema: str,
        conditioning: str,
        ridge: float,
        normalization: str,
        platform_descriptors: Sequence[PlatformFeatureDescriptorV2] | None = None,
        platform_normalizer: PlatformFeatureNormalizerV2 | None = None,
        fold: LOCOFoldManifestV2 | None = None,
    ) -> "ControlledEDMDV2":
        state_array, control_array, _ = _model_arrays(states, controls)
        target_array = np.asarray(targets, dtype=np.float64)
        if target_array.shape != (state_array.shape[0], STATE_DIM_V2):
            _fail("model_shape_invalid", "targets")
        if not np.isfinite(target_array).all():
            _fail("model_nonfinite", "targets")
        if not _is_sha256(preprocessing_sha256):
            _fail("preprocessing_hash_invalid")
        if conditioning not in _CONDITIONING_MODES:
            _fail("conditioning_unknown")
        if normalization not in _NORMALIZATION_MODES:
            _fail("normalization_unknown")
        if not np.isfinite(ridge) or ridge < 0.0:
            _fail("ridge_invalid")

        normalized_physical: np.ndarray | None = None
        source_configurations: tuple[str, ...] = ()
        fold_id: str | None = None
        holdout: str | None = None
        if conditioning == "platform_affine":
            if platform_normalizer is None or fold is None or platform_descriptors is None:
                _fail("platform_normalizer_required")
            platform_normalizer.require_fold(fold)
            descriptors = _descriptor_sequence(
                platform_descriptors, count=state_array.shape[0]
            )
            for descriptor in descriptors:
                if descriptor.configuration == fold.holdout_configuration:
                    _fail("heldout_design_leakage", descriptor.configuration)
                if descriptor.configuration not in fold.source_configurations:
                    _fail("normalizer_source_set_mismatch", descriptor.configuration)
            normalized_physical = np.asarray(
                [platform_normalizer.transform(item) for item in descriptors],
                dtype=np.float64,
            )
            source_configurations = fold.source_configurations
            fold_id = fold.fold_id
            holdout = fold.holdout_configuration
        else:
            if platform_descriptors is not None or platform_normalizer is not None:
                _fail("platform_features_forbidden")
            if fold is not None:
                source_configurations = fold.source_configurations
                fold_id = fold.fold_id
                holdout = fold.holdout_configuration

        design = build_controlled_design_v2(
            state_array,
            control_array,
            observable_schema=observable_schema,
            conditioning=conditioning,
            normalized_platform_features=normalized_physical,
        )
        input_normalizer = (
            ArrayNormalizerV2.fit(design) if normalization == "standard_v1" else None
        )
        target_normalizer = (
            ArrayNormalizerV2.fit(target_array)
            if normalization == "standard_v1"
            else None
        )
        fit_design = (
            input_normalizer.transform(design) if input_normalizer is not None else design
        )
        fit_target = (
            target_normalizer.transform(target_array)
            if target_normalizer is not None
            else target_array
        )
        gram = fit_design.T @ fit_design
        rhs = fit_design.T @ fit_target
        eigenvalues = np.linalg.eigvalsh(gram)
        largest_eigenvalue = max(0.0, float(eigenvalues[-1]))
        largest_singular = math.sqrt(largest_eigenvalue)
        tolerance = (
            largest_singular
            * max(fit_design.shape)
            * np.finfo(fit_design.dtype).eps
        )
        positive = eigenvalues[eigenvalues > tolerance * tolerance]
        rank = int(positive.size)
        condition_number = (
            math.sqrt(largest_eigenvalue / float(positive[0]))
            if rank == fit_design.shape[1] and positive.size
            else math.inf
        )
        condition_finite = math.isfinite(condition_number)
        if ridge > 0.0:
            gram = gram + float(ridge) * np.eye(gram.shape[0], dtype=np.float64)
        method = "solve" if ridge > 0.0 or rank == fit_design.shape[1] else "pinv"
        if method == "solve":
            try:
                coefficients = np.linalg.solve(gram, rhs).T
            except np.linalg.LinAlgError:
                method = "pinv"
        if method == "pinv":
            coefficients = (np.linalg.pinv(gram) @ rhs).T
        return cls(
            coefficient_matrix=coefficients,
            observable_schema=observable_schema,
            observable_schema_sha256=_observable_schema_sha256(observable_schema),
            conditioning=conditioning,
            ridge=float(ridge),
            normalization=normalization,
            preprocessing_sha256=preprocessing_sha256,
            diagnostics={
                "condition_finite": condition_finite,
                "condition_number": condition_number if condition_finite else None,
                "design_rank": rank,
                "design_width": int(fit_design.shape[1]),
                "preprocessor_version": QUATERNION_PREPROCESSOR_VERSION_V2,
                "sample_count": int(fit_design.shape[0]),
                "solve_method": method,
            },
            input_normalizer=input_normalizer,
            target_normalizer=target_normalizer,
            platform_normalizer=platform_normalizer,
            fold_id=fold_id,
            holdout_configuration=holdout,
            source_configurations=source_configurations,
        )

    def _physical_for_prediction(
        self,
        value: PlatformFeatureDescriptorV2 | Sequence[PlatformFeatureDescriptorV2] | None,
        *,
        count: int,
    ) -> np.ndarray | None:
        if self.conditioning == "none":
            if value is not None:
                _fail("platform_features_forbidden")
            return None
        if value is None or self.platform_normalizer is None:
            _fail("platform_descriptor_required")
        descriptors = _descriptor_sequence(value, count=count)
        return np.asarray(
            [self.platform_normalizer.transform(item) for item in descriptors],
            dtype=np.float64,
        )

    def predict_next(
        self,
        state: Any,
        control: Any,
        *,
        platform_descriptor: PlatformFeatureDescriptorV2
        | Sequence[PlatformFeatureDescriptorV2]
        | None = None,
    ) -> np.ndarray:
        states, controls, single = _model_arrays(state, control)
        normalized_physical = self._physical_for_prediction(
            platform_descriptor, count=states.shape[0]
        )
        design = build_controlled_design_v2(
            states,
            controls,
            observable_schema=self.observable_schema,
            conditioning=self.conditioning,
            normalized_platform_features=normalized_physical,
        )
        fit_design = (
            self.input_normalizer.transform(design)
            if self.input_normalizer is not None
            else design
        )
        prediction = fit_design @ self.coefficient_matrix.T
        if self.target_normalizer is not None:
            prediction = self.target_normalizer.inverse_transform(prediction)
        if not np.isfinite(prediction).all():
            _fail("model_nonfinite", "prediction")
        return prediction[0] if single else prediction

    def payload_without_hash(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "coefficient_matrix": self.coefficient_matrix.tolist(),
            "conditioning": self.conditioning,
            "control_dim": self.control_dim,
            "diagnostics": dict(self.diagnostics),
            "fold_id": self.fold_id,
            "holdout_configuration": self.holdout_configuration,
            "input_normalizer": (
                None if self.input_normalizer is None else self.input_normalizer.to_dict()
            ),
            "normalization": self.normalization,
            "observable_schema": self.observable_schema,
            "observable_schema_sha256": self.observable_schema_sha256,
            "platform_normalizer": (
                None
                if self.platform_normalizer is None
                else self.platform_normalizer.to_dict()
            ),
            "preprocessing_sha256": self.preprocessing_sha256,
            "ridge": self.ridge,
            "source_configurations": list(self.source_configurations),
            "state_dim": self.state_dim,
            "target_normalizer": (
                None if self.target_normalizer is None else self.target_normalizer.to_dict()
            ),
            "version": self.version,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload_without_hash(), "model_sha256": self.model_sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ControlledEDMDV2":
        if not isinstance(value, Mapping) or set(value) != cls._SERIALIZED_FIELDS:
            _fail("model_field_set_mismatch")
        if value.get("version") != MODEL_VERSION_V2:
            _fail("model_version_unsupported")
        schema_name = str(value["observable_schema"])
        if value.get("observable_schema_sha256") != _observable_schema_sha256(schema_name):
            _fail("observable_schema_hash_mismatch")
        result = cls(
            coefficient_matrix=np.asarray(value["coefficient_matrix"], dtype=np.float64),
            observable_schema=schema_name,
            observable_schema_sha256=str(value["observable_schema_sha256"]),
            conditioning=str(value["conditioning"]),
            ridge=float(value["ridge"]),
            normalization=str(value["normalization"]),
            preprocessing_sha256=str(value["preprocessing_sha256"]),
            diagnostics=dict(value["diagnostics"]),
            input_normalizer=ArrayNormalizerV2.from_dict(value["input_normalizer"]),
            target_normalizer=ArrayNormalizerV2.from_dict(value["target_normalizer"]),
            platform_normalizer=_platform_normalizer_from_dict(value["platform_normalizer"]),
            fold_id=value["fold_id"],
            holdout_configuration=value["holdout_configuration"],
            source_configurations=tuple(value["source_configurations"]),
            state_dim=int(value["state_dim"]),
            control_dim=int(value["control_dim"]),
            version=str(value["version"]),
            backend=str(value["backend"]),
        )
        if value.get("model_sha256") != result.model_sha256:
            _fail("model_hash_mismatch")
        return result

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(self.to_dict(), handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)
            os.replace(temporary_path, target)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    @classmethod
    def load(cls, path: str | Path) -> "ControlledEDMDV2":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

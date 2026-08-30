"""Physical-only platform descriptors and source-fold normalizers for Phase 8."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any

import numpy as np

from easyuuv_nc.embodiments import (
    EMBODIMENT_CONFIGS,
    SUPPORTED_EMBODIMENTS,
    qualification_record,
)
from koopman.evidence_v2 import canonical_sha256
from koopman.splits_v2 import LOCOFoldManifestV2


PLATFORM_FEATURE_SCHEMA_VERSION_V2 = "phase8-platform-feature-schema-v1"
PLATFORM_FEATURE_NORMALIZER_VERSION_V2 = "phase8-platform-feature-normalizer-v1"
_FORBIDDEN_IDENTITY_TOKENS = (
    "configuration",
    "identity",
    "one_hot",
    "onehot",
    "name",
    "hash",
)
_PLATFORM_CONTEXT_FIELDS = frozenset(
    {
        "allocation_mode",
        "com_to_cob_offset_m",
        "configuration",
        "control_channels",
        "control_mask",
        "declared_control_rank",
        "drag_multiplier",
        "inertia_diagonal_kg_m2",
        "mass_kg",
        "thruster_count",
        "thruster_dynamics_time_constant_s",
        "volume_m3",
    }
)
_CORE_FEATURES = (
    "log_mass_kg",
    "log_volume_m3",
    "log_inertia_x_kg_m2",
    "log_inertia_y_kg_m2",
    "log_inertia_z_kg_m2",
    "com_to_cob_x_m",
    "com_to_cob_y_m",
    "com_to_cob_z_m",
    "log_drag_multiplier",
    "log_thruster_time_constant_s",
    "thruster_count_fraction",
    "declared_control_rank_fraction",
    "control_mask_roll",
    "control_mask_pitch",
    "control_mask_yaw",
    "control_mask_depth",
    "allocation_mode_legacy",
    "allocation_mode_pinv",
    "allocation_mode_wls",
)
_COMPACT_FEATURES = (
    "log_mass_kg",
    "log_volume_m3",
    "thruster_count_fraction",
    "declared_control_rank_fraction",
    "control_mask_roll",
    "control_mask_pitch",
    "control_mask_yaw",
    "control_mask_depth",
    "allocation_mode_legacy",
    "allocation_mode_pinv",
    "allocation_mode_wls",
)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _readonly_vector(value: Any, *, width: int, name: str) -> np.ndarray:
    array = np.array(value, dtype=np.float64, copy=True)
    if array.shape != (width,) or not np.isfinite(array).all():
        _fail("physical_value_invalid", name)
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class PlatformFeatureSchemaV2:
    schema_name: str
    feature_names: tuple[str, ...]
    schema_version: str = PLATFORM_FEATURE_SCHEMA_VERSION_V2
    schema_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schema_name, str)
            or not self.schema_name
            or self.schema_version != PLATFORM_FEATURE_SCHEMA_VERSION_V2
        ):
            _fail("feature_schema_invalid")
        names = tuple(self.feature_names)
        if not names or len(set(names)) != len(names):
            _fail("feature_schema_invalid", "feature_names")
        if any(
            token in name.lower()
            for name in (self.schema_name, *names)
            for token in _FORBIDDEN_IDENTITY_TOKENS
        ):
            _fail("configuration_identity_forbidden")
        unknown = set(names) - set(_CORE_FEATURES)
        if unknown:
            _fail("feature_schema_invalid", ",".join(sorted(unknown)))
        object.__setattr__(self, "feature_names", names)
        object.__setattr__(
            self,
            "schema_sha256",
            canonical_sha256(
                {
                    "feature_names": list(names),
                    "schema_name": self.schema_name,
                    "schema_version": self.schema_version,
                }
            ),
        )

    @property
    def dimension(self) -> int:
        return len(self.feature_names)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "schema_name": self.schema_name,
            "schema_sha256": self.schema_sha256,
            "schema_version": self.schema_version,
        }


_SCHEMAS = MappingProxyType(
    {
        "platform_physical_core_v1": PlatformFeatureSchemaV2(
            schema_name="platform_physical_core_v1", feature_names=_CORE_FEATURES
        ),
        "platform_physical_compact_v1": PlatformFeatureSchemaV2(
            schema_name="platform_physical_compact_v1",
            feature_names=_COMPACT_FEATURES,
        ),
    }
)


def select_platform_feature_schema_v2(name: str) -> PlatformFeatureSchemaV2:
    try:
        return _SCHEMAS[name]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"feature_schema_unknown:{name}") from exc


def declared_platform_context_v2(configuration: str) -> dict[str, Any]:
    """Return catalog/runtime-declared physical facts without importing Isaac."""
    if configuration not in SUPPORTED_EMBODIMENTS:
        _fail("configuration_unknown", str(configuration))
    config = EMBODIMENT_CONFIGS[configuration]
    topology = qualification_record(configuration)
    return {
        "allocation_mode": topology["allocation_mode"],
        "com_to_cob_offset_m": list(config["com_to_cob_offset"]),
        "configuration": configuration,
        "control_channels": list(topology["control_channels"]),
        "control_mask": list(topology["control_mask"]),
        "declared_control_rank": topology["declared_control_rank"],
        "drag_multiplier": float(config["drag_multiplier"]),
        "inertia_diagonal_kg_m2": list(config["inertia_tensors"]),
        "mass_kg": float(config["mass"]),
        "thruster_count": topology["thruster_count"],
        "thruster_dynamics_time_constant_s": float(config["dyn_time_constant"]),
        "volume_m3": float(config.get("volume", 0.022747843530591776)),
    }


def _finite_number(value: Any, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("physical_value_invalid", path)
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0.0):
        _fail("physical_value_invalid", path)
    return number


def _vector(
    value: Any, width: int, path: str, *, positive: bool = False
) -> tuple[float, ...]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or len(value) != width
    ):
        _fail("physical_value_invalid", path)
    return tuple(
        _finite_number(item, f"{path}[{index}]", positive=positive)
        for index, item in enumerate(value)
    )


def _validate_context(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("physical_field_set_mismatch")
    extra = set(value) - _PLATFORM_CONTEXT_FIELDS
    if any(
        token in str(field).lower()
        for field in extra
        for token in _FORBIDDEN_IDENTITY_TOKENS
    ):
        _fail("configuration_identity_forbidden")
    if set(value) != _PLATFORM_CONTEXT_FIELDS:
        _fail("physical_field_set_mismatch")
    configuration = value["configuration"]
    if configuration not in SUPPORTED_EMBODIMENTS:
        _fail("configuration_unknown", str(configuration))
    topology = qualification_record(configuration)
    for field_name in (
        "thruster_count",
        "control_channels",
        "control_mask",
        "allocation_mode",
        "declared_control_rank",
    ):
        expected = topology[field_name]
        actual = value[field_name]
        if isinstance(expected, tuple):
            actual = tuple(actual) if isinstance(actual, Sequence) else actual
        if actual != expected:
            if field_name == "allocation_mode":
                _fail("allocation_mode_unknown", str(actual))
            _fail("physical_value_invalid", field_name)
    if value["allocation_mode"] not in {"legacy", "pinv", "wls"}:
        _fail("allocation_mode_unknown", str(value["allocation_mode"]))
    for field_name in (
        "mass_kg",
        "volume_m3",
        "drag_multiplier",
        "thruster_dynamics_time_constant_s",
    ):
        _finite_number(value[field_name], field_name, positive=True)
    _vector(value["inertia_diagonal_kg_m2"], 3, "inertia", positive=True)
    _vector(value["com_to_cob_offset_m"], 3, "com_to_cob")
    return value


def _json_value(value: Any) -> Any:
    """Restore dataset-frozen containers to their canonical JSON value."""

    if isinstance(value, Mapping):
        return {str(key): _json_value(nested) for key, nested in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_json_value(item) for item in value]
    return value


def _physical_feature_values(context: Mapping[str, Any]) -> dict[str, float]:
    inertia = _vector(
        context["inertia_diagonal_kg_m2"], 3, "inertia", positive=True
    )
    offset = _vector(context["com_to_cob_offset_m"], 3, "com_to_cob")
    mask = tuple(int(item) for item in context["control_mask"])
    mode = context["allocation_mode"]
    return {
        "log_mass_kg": math.log(_finite_number(context["mass_kg"], "mass", positive=True)),
        "log_volume_m3": math.log(_finite_number(context["volume_m3"], "volume", positive=True)),
        "log_inertia_x_kg_m2": math.log(inertia[0]),
        "log_inertia_y_kg_m2": math.log(inertia[1]),
        "log_inertia_z_kg_m2": math.log(inertia[2]),
        "com_to_cob_x_m": offset[0],
        "com_to_cob_y_m": offset[1],
        "com_to_cob_z_m": offset[2],
        "log_drag_multiplier": math.log(
            _finite_number(context["drag_multiplier"], "drag", positive=True)
        ),
        "log_thruster_time_constant_s": math.log(
            _finite_number(
                context["thruster_dynamics_time_constant_s"],
                "thruster_time_constant",
                positive=True,
            )
        ),
        "thruster_count_fraction": int(context["thruster_count"]) / 8.0,
        "declared_control_rank_fraction": int(context["declared_control_rank"]) / 4.0,
        "control_mask_roll": float(mask[0]),
        "control_mask_pitch": float(mask[1]),
        "control_mask_yaw": float(mask[2]),
        "control_mask_depth": float(mask[3]),
        "allocation_mode_legacy": float(mode == "legacy"),
        "allocation_mode_pinv": float(mode == "pinv"),
        "allocation_mode_wls": float(mode == "wls"),
    }


@dataclass(frozen=True)
class PlatformFeatureDescriptorV2:
    configuration: str
    values: np.ndarray
    schema_name: str
    schema_sha256: str
    physical_facts_sha256: str

    def __post_init__(self) -> None:
        schema = select_platform_feature_schema_v2(self.schema_name)
        if self.schema_sha256 != schema.schema_sha256:
            _fail("feature_schema_hash_mismatch")
        object.__setattr__(
            self,
            "values",
            _readonly_vector(self.values, width=schema.dimension, name="descriptor"),
        )


def build_platform_descriptor_v2(
    platform_contexts: Sequence[Mapping[str, Any]],
    *,
    schema: PlatformFeatureSchemaV2,
) -> PlatformFeatureDescriptorV2:
    """Extract one constant per-episode physical descriptor without row identity."""
    if not isinstance(schema, PlatformFeatureSchemaV2):
        _fail("feature_schema_invalid")
    if (
        isinstance(platform_contexts, (str, bytes))
        or not isinstance(platform_contexts, Sequence)
        or not platform_contexts
    ):
        _fail("physical_field_set_mismatch")
    contexts = tuple(_validate_context(value) for value in platform_contexts)
    canonical_contexts = tuple(_json_value(context) for context in contexts)
    first_hash = canonical_sha256(canonical_contexts[0])
    if any(canonical_sha256(context) != first_hash for context in canonical_contexts[1:]):
        _fail("platform_context_drift")
    feature_map = _physical_feature_values(contexts[0])
    values = [feature_map[name] for name in schema.feature_names]
    return PlatformFeatureDescriptorV2(
        configuration=str(contexts[0]["configuration"]),
        values=np.asarray(values, dtype=np.float64),
        schema_name=schema.schema_name,
        schema_sha256=schema.schema_sha256,
        physical_facts_sha256=first_hash,
    )


@dataclass(frozen=True)
class PlatformFeatureNormalizerV2:
    fold_id: str
    holdout_configuration: str
    source_configurations: tuple[str, ...]
    source_episode_sha256s: tuple[str, ...]
    feature_schema_name: str
    feature_schema_sha256: str
    mean: np.ndarray
    scale: np.ndarray
    zero_scale_rule: str = "unit_scale"
    normalizer_version: str = PLATFORM_FEATURE_NORMALIZER_VERSION_V2
    normalizer_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        schema = select_platform_feature_schema_v2(self.feature_schema_name)
        if self.feature_schema_sha256 != schema.schema_sha256:
            _fail("feature_schema_hash_mismatch")
        if self.zero_scale_rule != "unit_scale":
            _fail("normalizer_zero_scale_rule_invalid")
        sources = tuple(self.source_configurations)
        hashes = tuple(self.source_episode_sha256s)
        if len(sources) != 7 or len(set(sources)) != 7:
            _fail("normalizer_source_set_mismatch")
        if self.holdout_configuration in sources:
            _fail("heldout_normalization_leakage")
        mean = _readonly_vector(self.mean, width=schema.dimension, name="mean")
        scale = _readonly_vector(self.scale, width=schema.dimension, name="scale")
        if np.any(scale <= 0.0):
            _fail("normalizer_scale_invalid")
        object.__setattr__(self, "source_configurations", sources)
        object.__setattr__(self, "source_episode_sha256s", hashes)
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "scale", scale)
        object.__setattr__(
            self, "normalizer_sha256", canonical_sha256(self.payload_without_hash())
        )

    def payload_without_hash(self) -> dict[str, Any]:
        return {
            "feature_schema_name": self.feature_schema_name,
            "feature_schema_sha256": self.feature_schema_sha256,
            "fold_id": self.fold_id,
            "holdout_configuration": self.holdout_configuration,
            "mean": self.mean.tolist(),
            "normalizer_version": self.normalizer_version,
            "scale": self.scale.tolist(),
            "source_configurations": list(self.source_configurations),
            "source_episode_sha256s": list(self.source_episode_sha256s),
            "zero_scale_rule": self.zero_scale_rule,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload_without_hash(), "normalizer_sha256": self.normalizer_sha256}

    def require_fold(self, fold: LOCOFoldManifestV2) -> None:
        if (
            self.fold_id != fold.fold_id
            or self.holdout_configuration != fold.holdout_configuration
            or self.source_configurations != fold.source_configurations
            or self.source_episode_sha256s != fold.source_episode_sha256s
        ):
            _fail("normalizer_fold_mismatch")

    def transform(self, descriptor: PlatformFeatureDescriptorV2) -> np.ndarray:
        if not isinstance(descriptor, PlatformFeatureDescriptorV2):
            _fail("descriptor_required")
        if descriptor.schema_sha256 != self.feature_schema_sha256:
            _fail("feature_schema_hash_mismatch")
        result = (descriptor.values - self.mean) / self.scale
        if not np.isfinite(result).all():
            _fail("physical_value_invalid", "normalized_descriptor")
        result.setflags(write=False)
        return result


def fit_platform_feature_normalizer_v2(
    descriptors: Mapping[str, PlatformFeatureDescriptorV2],
    *,
    fold: LOCOFoldManifestV2,
    schema: PlatformFeatureSchemaV2,
) -> PlatformFeatureNormalizerV2:
    """Fit equal-configuration statistics on the exact seven source platforms."""
    if fold.holdout_configuration in descriptors:
        _fail("heldout_normalization_leakage", fold.holdout_configuration)
    if set(descriptors) != set(fold.source_configurations):
        _fail("normalizer_source_set_mismatch")
    ordered: list[np.ndarray] = []
    for configuration in fold.source_configurations:
        descriptor = descriptors[configuration]
        if descriptor.configuration != configuration:
            _fail("normalizer_source_set_mismatch", configuration)
        if descriptor.schema_sha256 != schema.schema_sha256:
            _fail("feature_schema_hash_mismatch")
        ordered.append(descriptor.values)
    values = np.asarray(ordered, dtype=np.float64)
    mean = np.mean(values, axis=0)
    raw_scale = np.std(values, axis=0)
    scale = np.where(raw_scale == 0.0, 1.0, raw_scale)
    return PlatformFeatureNormalizerV2(
        fold_id=fold.fold_id,
        holdout_configuration=fold.holdout_configuration,
        source_configurations=fold.source_configurations,
        source_episode_sha256s=fold.source_episode_sha256s,
        feature_schema_name=schema.schema_name,
        feature_schema_sha256=schema.schema_sha256,
        mean=mean,
        scale=scale,
    )

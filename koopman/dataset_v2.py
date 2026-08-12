"""Immutable model-facing views for validated Koopman schema-v2 episodes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np

from koopman.schema_v2 import (
    load_episode_jsonl_v2,
    validate_episode_artifact_v2,
    validate_episode_v2,
)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if not detail else f"{reason}:{detail}")


def _readonly_array(value: Any, *, dtype: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
    array = np.array(value, dtype=dtype, copy=True)
    if array.shape != shape:
        _fail("dataset_shape_invalid", f"{name}:expected={shape};actual={array.shape}")
    if np.issubdtype(array.dtype, np.number) and not np.isfinite(array).all():
        _fail("dataset_nonfinite", name)
    array.setflags(write=False)
    return array


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(nested) for key, nested in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class ActuatorDiagnostics:
    motor_pwm_padded_8: np.ndarray
    thruster_mask_8: np.ndarray
    applied_wrench_6: np.ndarray
    saturation_ratio: np.ndarray
    energy_proxy: np.ndarray

    def __post_init__(self) -> None:
        motor = np.array(self.motor_pwm_padded_8, dtype=np.float64, copy=True)
        if motor.ndim != 2:
            _fail("dataset_shape_invalid", "diagnostics.motor_pwm_padded_8")
        count = int(motor.shape[0])
        arrays = {
            "motor_pwm_padded_8": _readonly_array(
                motor, dtype=np.float64, shape=(count, 8), name="diagnostics.motor_pwm_padded_8"
            ),
            "thruster_mask_8": _readonly_array(
                self.thruster_mask_8,
                dtype=np.int8,
                shape=(count, 8),
                name="diagnostics.thruster_mask_8",
            ),
            "applied_wrench_6": _readonly_array(
                self.applied_wrench_6,
                dtype=np.float64,
                shape=(count, 6),
                name="diagnostics.applied_wrench_6",
            ),
            "saturation_ratio": _readonly_array(
                self.saturation_ratio,
                dtype=np.float64,
                shape=(count,),
                name="diagnostics.saturation_ratio",
            ),
            "energy_proxy": _readonly_array(
                self.energy_proxy,
                dtype=np.float64,
                shape=(count,),
                name="diagnostics.energy_proxy",
            ),
        }
        for name, array in arrays.items():
            object.__setattr__(self, name, array)


@dataclass(frozen=True)
class KoopmanDatasetV2:
    X: np.ndarray
    virtual_control_4: np.ndarray
    R: np.ndarray
    Y: np.ndarray
    diagnostics: ActuatorDiagnostics
    configurations: tuple[str, ...]
    episode_ids: tuple[str, ...]
    step_indices: np.ndarray
    platform_contexts: tuple[Mapping[str, Any], ...]
    environment_contexts_oracle: tuple[Mapping[str, Any], ...]
    environment_contexts_estimated: tuple[Mapping[str, Any], ...]
    episode_provenance: tuple[Mapping[str, Any], ...]
    source_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        control = np.array(self.virtual_control_4, dtype=np.float64, copy=True)
        if control.ndim != 2:
            _fail("dataset_shape_invalid", "virtual_control_4")
        count = int(control.shape[0])
        if count == 0:
            _fail("dataset_empty")
        arrays = {
            "X": _readonly_array(self.X, dtype=np.float64, shape=(count, 11), name="X"),
            "virtual_control_4": _readonly_array(
                control, dtype=np.float64, shape=(count, 4), name="virtual_control_4"
            ),
            "R": _readonly_array(self.R, dtype=np.float64, shape=(count, 5), name="R"),
            "Y": _readonly_array(self.Y, dtype=np.float64, shape=(count, 11), name="Y"),
            "step_indices": _readonly_array(
                self.step_indices, dtype=np.int64, shape=(count,), name="step_indices"
            ),
        }
        for name, array in arrays.items():
            object.__setattr__(self, name, array)
        if not isinstance(self.diagnostics, ActuatorDiagnostics):
            _fail("dataset_diagnostics_invalid")
        if self.diagnostics.motor_pwm_padded_8.shape[0] != count:
            _fail("dataset_row_count_mismatch", "diagnostics")
        metadata = {
            "configurations": tuple(self.configurations),
            "episode_ids": tuple(self.episode_ids),
            "platform_contexts": tuple(_freeze(value) for value in self.platform_contexts),
            "environment_contexts_oracle": tuple(
                _freeze(value) for value in self.environment_contexts_oracle
            ),
            "environment_contexts_estimated": tuple(
                _freeze(value) for value in self.environment_contexts_estimated
            ),
            "episode_provenance": tuple(_freeze(value) for value in self.episode_provenance),
        }
        for name, values in metadata.items():
            if len(values) != count:
                _fail("dataset_row_count_mismatch", name)
            object.__setattr__(self, name, values)
        object.__setattr__(self, "source_paths", tuple(str(path) for path in self.source_paths))

    @property
    def U(self) -> np.ndarray:
        """Return only the topology-independent post-mask 4D control."""
        return self.virtual_control_4

    @property
    def sample_count(self) -> int:
        return int(self.X.shape[0])


def dataset_from_records_v2(
    records: Iterable[Mapping[str, Any]], *, source_paths: Iterable[str | Path] = ()
) -> KoopmanDatasetV2:
    rows = list(records)
    if not rows:
        _fail("dataset_empty")
    validate_episode_v2(rows)

    motor = np.asarray([row["motor_pwm_padded_8"] for row in rows], dtype=np.float64)
    diagnostics = ActuatorDiagnostics(
        motor_pwm_padded_8=motor,
        thruster_mask_8=np.asarray([row["thruster_mask_8"] for row in rows], dtype=np.int8),
        applied_wrench_6=np.asarray([row["applied_wrench_6"] for row in rows], dtype=np.float64),
        saturation_ratio=np.mean(np.abs(motor) >= 1.0 - 1.0e-6, axis=1),
        energy_proxy=np.sum(np.square(motor), axis=1),
    )
    provenance = [row["episode_provenance"] for row in rows]
    return KoopmanDatasetV2(
        X=np.asarray([row["state_11"] for row in rows], dtype=np.float64),
        virtual_control_4=np.asarray([row["virtual_control_4"] for row in rows], dtype=np.float64),
        R=np.asarray([row["reference_5"] for row in rows], dtype=np.float64),
        Y=np.asarray([row["next_state_11"] for row in rows], dtype=np.float64),
        diagnostics=diagnostics,
        configurations=tuple(str(value["configuration"]) for value in provenance),
        episode_ids=tuple(str(value["episode_id"]) for value in provenance),
        step_indices=np.asarray([value["step_index"] for value in provenance], dtype=np.int64),
        platform_contexts=tuple(row["platform_context"] for row in rows),
        environment_contexts_oracle=tuple(row["environment_context_oracle"] for row in rows),
        environment_contexts_estimated=tuple(row["environment_context_estimated"] for row in rows),
        episode_provenance=tuple(provenance),
        source_paths=tuple(str(path) for path in source_paths),
    )


def load_koopman_episode_v2(
    jsonl_path: str | Path, manifest_path: str | Path
) -> KoopmanDatasetV2:
    """Load one strict schema-v2 episode/manifest pair as a model-facing view."""
    validate_episode_artifact_v2(jsonl_path, manifest_path)
    records = load_episode_jsonl_v2(jsonl_path)
    return dataset_from_records_v2(
        records, source_paths=(str(jsonl_path), str(manifest_path))
    )

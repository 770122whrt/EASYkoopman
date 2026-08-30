"""Immutable 19D model-facing views for validated schema-v2.1 episodes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np

from koopman.schema_v21 import (
    load_episode_jsonl_v21,
    validate_episode_artifact_v21,
    validate_episode_v21,
)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _readonly(value: Any, *, dtype: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
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
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class ActuatorDiagnosticsV21:
    """Simulator-only diagnostics that are never part of the primary input."""

    motor_pwm_padded_8: np.ndarray
    thruster_mask_8: np.ndarray
    applied_wrench_6: np.ndarray
    environment_contexts_oracle: tuple[Mapping[str, Any], ...]
    environment_contexts_estimated: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        motor = np.asarray(self.motor_pwm_padded_8)
        if motor.ndim != 2:
            _fail("dataset_shape_invalid", "diagnostics.motor_pwm_padded_8")
        count = int(motor.shape[0])
        arrays = {
            "motor_pwm_padded_8": _readonly(
                self.motor_pwm_padded_8,
                dtype=np.float64,
                shape=(count, 8),
                name="diagnostics.motor_pwm_padded_8",
            ),
            "thruster_mask_8": _readonly(
                self.thruster_mask_8,
                dtype=np.int8,
                shape=(count, 8),
                name="diagnostics.thruster_mask_8",
            ),
            "applied_wrench_6": _readonly(
                self.applied_wrench_6,
                dtype=np.float64,
                shape=(count, 6),
                name="diagnostics.applied_wrench_6",
            ),
        }
        for name, array in arrays.items():
            object.__setattr__(self, name, array)
        for name in ("environment_contexts_oracle", "environment_contexts_estimated"):
            values = tuple(_freeze(item) for item in getattr(self, name))
            if len(values) != count:
                _fail("dataset_row_count_mismatch", f"diagnostics.{name}")
            object.__setattr__(self, name, values)


@dataclass(frozen=True)
class KoopmanDatasetV21:
    """A strict primary view: ``[state_11, memory_4, virtual_control_4]``."""

    X: np.ndarray
    state_11: np.ndarray
    actuator_memory_4: np.ndarray
    virtual_control_4: np.ndarray
    R: np.ndarray
    Y: np.ndarray
    diagnostics: ActuatorDiagnosticsV21
    configurations: tuple[str, ...]
    episode_ids: tuple[str, ...]
    step_indices: np.ndarray
    platform_contexts: tuple[Mapping[str, Any], ...]
    episode_provenance: tuple[Mapping[str, Any], ...]
    source_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        control = np.asarray(self.virtual_control_4)
        if control.ndim != 2:
            _fail("dataset_shape_invalid", "virtual_control_4")
        count = int(control.shape[0])
        if count == 0:
            _fail("dataset_empty")
        arrays = {
            "X": _readonly(self.X, dtype=np.float64, shape=(count, 19), name="X"),
            "state_11": _readonly(
                self.state_11, dtype=np.float64, shape=(count, 11), name="state_11"
            ),
            "actuator_memory_4": _readonly(
                self.actuator_memory_4,
                dtype=np.float64,
                shape=(count, 4),
                name="actuator_memory_4",
            ),
            "virtual_control_4": _readonly(
                control,
                dtype=np.float64,
                shape=(count, 4),
                name="virtual_control_4",
            ),
            "R": _readonly(self.R, dtype=np.float64, shape=(count, 5), name="R"),
            "Y": _readonly(self.Y, dtype=np.float64, shape=(count, 11), name="Y"),
            "step_indices": _readonly(
                self.step_indices, dtype=np.int64, shape=(count,), name="step_indices"
            ),
        }
        for name, array in arrays.items():
            object.__setattr__(self, name, array)
        expected_primary = np.concatenate(
            [arrays["state_11"], arrays["actuator_memory_4"], arrays["virtual_control_4"]],
            axis=1,
        )
        if not np.array_equal(arrays["X"], expected_primary):
            _fail("dataset_primary_contract_mismatch")
        if not isinstance(self.diagnostics, ActuatorDiagnosticsV21):
            _fail("dataset_diagnostics_invalid")
        if self.diagnostics.motor_pwm_padded_8.shape[0] != count:
            _fail("dataset_row_count_mismatch", "diagnostics")

        for name in (
            "configurations",
            "episode_ids",
            "platform_contexts",
            "episode_provenance",
        ):
            raw = tuple(getattr(self, name))
            if len(raw) != count:
                _fail("dataset_row_count_mismatch", name)
            values = raw if name in {"configurations", "episode_ids"} else tuple(
                _freeze(value) for value in raw
            )
            object.__setattr__(self, name, values)
        object.__setattr__(self, "source_paths", tuple(str(path) for path in self.source_paths))

    @property
    def primary_X(self) -> np.ndarray:
        return self.X

    @property
    def U(self) -> np.ndarray:
        return self.virtual_control_4

    @property
    def sample_count(self) -> int:
        return int(self.X.shape[0])


def dataset_from_records_v21(
    records: Iterable[Mapping[str, Any]],
    *,
    source_paths: Iterable[str | Path] = (),
) -> KoopmanDatasetV21:
    rows = list(records)
    if not rows:
        _fail("dataset_empty")
    validate_episode_v21(rows)

    state = np.asarray([row["state_11"] for row in rows], dtype=np.float64)
    memory = np.asarray([row["actuator_memory_4"] for row in rows], dtype=np.float64)
    control = np.asarray([row["virtual_control_4"] for row in rows], dtype=np.float64)
    provenance = [row["episode_provenance"] for row in rows]
    diagnostics = ActuatorDiagnosticsV21(
        motor_pwm_padded_8=np.asarray(
            [row["motor_pwm_padded_8"] for row in rows], dtype=np.float64
        ),
        thruster_mask_8=np.asarray(
            [row["thruster_mask_8"] for row in rows], dtype=np.int8
        ),
        applied_wrench_6=np.asarray(
            [row["applied_wrench_6"] for row in rows], dtype=np.float64
        ),
        environment_contexts_oracle=tuple(
            row["environment_context_oracle"] for row in rows
        ),
        environment_contexts_estimated=tuple(
            row["environment_context_estimated"] for row in rows
        ),
    )
    return KoopmanDatasetV21(
        X=np.concatenate([state, memory, control], axis=1),
        state_11=state,
        actuator_memory_4=memory,
        virtual_control_4=control,
        R=np.asarray([row["reference_5"] for row in rows], dtype=np.float64),
        Y=np.asarray([row["next_state_11"] for row in rows], dtype=np.float64),
        diagnostics=diagnostics,
        configurations=tuple(str(item["configuration"]) for item in provenance),
        episode_ids=tuple(str(item["episode_id"]) for item in provenance),
        step_indices=np.asarray([item["step_index"] for item in provenance], dtype=np.int64),
        platform_contexts=tuple(row["platform_context"] for row in rows),
        episode_provenance=tuple(provenance),
        source_paths=tuple(str(path) for path in source_paths),
    )


def load_koopman_episode_v21(
    jsonl_path: str | Path, manifest_path: str | Path
) -> KoopmanDatasetV21:
    validate_episode_artifact_v21(jsonl_path, manifest_path)
    rows = load_episode_jsonl_v21(jsonl_path)
    return dataset_from_records_v21(
        rows, source_paths=(str(jsonl_path), str(manifest_path))
    )

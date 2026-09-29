"""Strict additive Phase 8.1 transition, episode and artifact contracts.

Schema v2.1 adds only the causal ``actuator_memory_4`` field and explicit
physics/control timing provenance.  It never upgrades or mutates schema-v2
records.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any

import numpy as np

from koopman.actuator_memory_v21 import ActuatorMemoryProxyV21
from koopman.schema_v2 import (
    KOOPMAN_TRANSITION_SCHEMA_V2,
    LOCAL_EVIDENCE_LEVEL,
    SERVER_EVIDENCE_LEVEL,
    validate_episode_v2,
    validate_transition_v2,
)


KOOPMAN_TRANSITION_SCHEMA_V21 = "easyuuv-koopman-transition-v2.1"
KOOPMAN_EPISODE_MANIFEST_V21 = "easyuuv-koopman-episode-manifest-v2.1"
ACTUATOR_MEMORY_DIM = 4
RECURRENCE_ATOL = 1e-12
RECURRENCE_RTOL = 1e-12
MAX_JSONL_BYTES = 64 * 1024 * 1024
MAX_JSONL_LINE_BYTES = 1024 * 1024
MAX_JSONL_LINES = 10_000_000

_V2_TRANSITION_FIELDS = frozenset(
    {
        "schema_version",
        "state_11",
        "reference_5",
        "raw_action_4",
        "virtual_control_4",
        "motor_pwm_padded_8",
        "thruster_mask_8",
        "applied_wrench_6",
        "platform_context",
        "environment_context_oracle",
        "environment_context_estimated",
        "next_state_11",
        "episode_provenance",
    }
)
TRANSITION_FIELDS_V21 = _V2_TRANSITION_FIELDS | {"actuator_memory_4"}
_V2_PROVENANCE_FIELDS = frozenset(
    {
        "configuration",
        "scenario",
        "episode_id",
        "step_index",
        "seed",
        "simulation_time_s",
        "control_dt_s",
        "task_id",
        "controller_mode",
        "source_commit",
        "evidence_level",
    }
)
EPISODE_PROVENANCE_FIELDS_V21 = _V2_PROVENANCE_FIELDS | {
    "physics_dt_s",
    "decimation",
}
EPISODE_INVARIANT_FIELDS_V21 = frozenset(
    {
        "configuration",
        "scenario",
        "episode_id",
        "seed",
        "physics_dt_s",
        "decimation",
        "control_dt_s",
        "task_id",
        "controller_mode",
        "source_commit",
        "evidence_level",
    }
)
MANIFEST_FIELDS_V21 = frozenset(
    {
        "manifest_version",
        "transition_schema_version",
        "transition_file",
        "transition_sha256",
        "record_count",
        "first_step_index",
        "last_step_index",
        "first_simulation_time_s",
        "last_simulation_time_s",
        "episode_invariants",
        "platform_context_sha256",
        "timing_provenance",
        "runtime_provenance",
        "evidence_level",
    }
)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _exact_mapping(value: Any, fields: frozenset[str], *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("type_invalid", path)
    actual = set(value)
    if actual != fields:
        missing = ",".join(sorted(fields - actual)) or "none"
        extra = ",".join(sorted(actual - fields)) or "none"
        _fail("field_set_mismatch", f"{path}:missing={missing};extra={extra}")
    return value


def _finite_float(value: Any, *, reason: str, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(reason, path)
    result = float(value)
    if not math.isfinite(result):
        _fail(reason, path)
    return result


def _vector4(value: Any, *, path: str) -> np.ndarray:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 4:
        _fail("shape_invalid", path)
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"type_invalid:{path}") from exc
    if result.shape != (4,):
        _fail("shape_invalid", path)
    if not np.isfinite(result).all():
        _fail("nonfinite_value", path)
    return result


def _legacy_transition(payload: Mapping[str, Any]) -> dict[str, Any]:
    legacy = deepcopy(dict(payload))
    legacy["schema_version"] = KOOPMAN_TRANSITION_SCHEMA_V2
    legacy.pop("actuator_memory_4")
    legacy_provenance = legacy["episode_provenance"]
    legacy_provenance.pop("physics_dt_s")
    legacy_provenance.pop("decimation")
    return legacy


def validate_timing_provenance_v21(provenance: Any) -> dict[str, float | int]:
    payload = _exact_mapping(
        provenance, EPISODE_PROVENANCE_FIELDS_V21, path="episode_provenance"
    )
    physics_dt_s = _finite_float(
        payload["physics_dt_s"],
        reason="timing_provenance_invalid",
        path="episode_provenance.physics_dt_s",
    )
    control_dt_s = _finite_float(
        payload["control_dt_s"],
        reason="timing_provenance_invalid",
        path="episode_provenance.control_dt_s",
    )
    decimation = payload["decimation"]
    if physics_dt_s <= 0.0 or control_dt_s <= 0.0:
        _fail("timing_provenance_invalid")
    if isinstance(decimation, bool) or not isinstance(decimation, int) or decimation <= 0:
        _fail("timing_provenance_invalid", "episode_provenance.decimation")
    if control_dt_s != physics_dt_s * decimation:
        _fail("timing_relation_mismatch")
    return {
        "physics_dt_s": physics_dt_s,
        "decimation": decimation,
        "control_dt_s": control_dt_s,
    }


def validate_transition_v21(transition: Any) -> None:
    """Validate one exact schema-v2.1 row without mutating caller data."""
    payload = _exact_mapping(transition, TRANSITION_FIELDS_V21, path="transition")
    if payload["schema_version"] != KOOPMAN_TRANSITION_SCHEMA_V21:
        _fail("schema_version_mismatch")
    provenance = _exact_mapping(
        payload["episode_provenance"],
        EPISODE_PROVENANCE_FIELDS_V21,
        path="episode_provenance",
    )
    timing = validate_timing_provenance_v21(provenance)
    validate_transition_v2(_legacy_transition(payload))

    memory = _vector4(payload["actuator_memory_4"], path="actuator_memory_4")
    mask = np.asarray(payload["platform_context"]["control_mask"], dtype=np.int8)
    disabled = mask == 0
    if np.any(memory[disabled] != 0.0):
        if str(provenance["configuration"]).startswith("uuv4") and memory[2] != 0.0:
            _fail("underactuated_yaw_memory_nonzero")
        _fail("actuator_memory_disabled_channel_nonzero")
    if str(provenance["configuration"]).startswith("uuv4") and memory[2] != 0.0:
        _fail("underactuated_yaw_memory_nonzero")
    # Keep the returned local variable exercised so timing validation cannot be
    # accidentally removed while leaving only the exact-field check.
    assert timing["control_dt_s"] > 0.0


def build_local_transition_v21(**fields: Any) -> dict[str, Any]:
    transition = deepcopy(fields)
    validate_transition_v21(transition)
    if transition["episode_provenance"]["evidence_level"] != LOCAL_EVIDENCE_LEVEL:
        _fail("local_evidence_required")
    return transition


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        text = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"serialization_invalid:{exc}") from exc
    return (text + "\n").encode("utf-8")


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def validate_episode_v21(
    transitions: Sequence[Mapping[str, Any]],
    *,
    numeric_tolerance: float = RECURRENCE_ATOL,
) -> dict[str, Any]:
    """Validate a contiguous reset-local v2.1 episode and replay its proxy."""
    if isinstance(transitions, (str, bytes)) or not isinstance(transitions, Sequence):
        _fail("type_invalid", "transitions")
    if len(transitions) < 2:
        _fail("episode_too_short", str(len(transitions)))
    tolerance = _finite_float(
        numeric_tolerance, reason="numeric_tolerance_invalid", path="numeric_tolerance"
    )
    if tolerance < 0.0:
        _fail("numeric_tolerance_invalid")

    for row in transitions:
        validate_transition_v21(row)
    legacy_rows = [_legacy_transition(row) for row in transitions]
    legacy_summary = validate_episode_v2(legacy_rows, numeric_tolerance=tolerance)

    first = transitions[0]
    first_provenance = first["episode_provenance"]
    if first_provenance["step_index"] != 0 or first_provenance["simulation_time_s"] != 0.0:
        _fail("episode_reset_timing_invalid")
    first_memory = np.asarray(first["actuator_memory_4"], dtype=np.float64)
    if first_memory.tobytes() != np.zeros(4, dtype=np.float64).tobytes():
        _fail("actuator_memory_initial_state_nonzero")

    timing = validate_timing_provenance_v21(first_provenance)
    invariant_values = {
        field: deepcopy(first_provenance[field])
        for field in sorted(EPISODE_INVARIANT_FIELDS_V21)
    }
    for index, row in enumerate(transitions[1:], start=1):
        provenance = row["episode_provenance"]
        for field in EPISODE_INVARIANT_FIELDS_V21:
            if provenance[field] != first_provenance[field]:
                _fail("episode_invariant_drift", f"row={index};field={field}")

    proxy = ActuatorMemoryProxyV21(
        float(first["platform_context"]["thruster_dynamics_time_constant_s"]),
        timing["control_dt_s"],
        first["platform_context"]["control_mask"],
    )
    for index, row in enumerate(transitions):
        expected = proxy.current()
        actual = np.asarray(row["actuator_memory_4"], dtype=np.float64)
        if not np.allclose(actual, expected, atol=RECURRENCE_ATOL, rtol=RECURRENCE_RTOL):
            _fail("actuator_memory_recurrence_mismatch", f"row={index}")
        proxy.advance(row["virtual_control_4"])

    return {
        **legacy_summary,
        "episode_invariants": invariant_values,
        "platform_context_sha256": _digest(first["platform_context"]),
        "timing_provenance": timing,
    }


def _reject_constant(token: str) -> None:
    _fail("nonfinite_json_constant", token)


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key", key)
        result[key] = value
    return result


def _parse_object(text: str, *, path: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json:{path}:{exc.msg}") from exc
    if not isinstance(payload, dict):
        _fail("root_not_object", path)
    return payload


def load_episode_jsonl_v21(
    path: str | Path,
    *,
    max_bytes: int = MAX_JSONL_BYTES,
    max_line_bytes: int = MAX_JSONL_LINE_BYTES,
    max_lines: int = MAX_JSONL_LINES,
) -> list[dict[str, Any]]:
    artifact = Path(path)
    if artifact.name.endswith(".part"):
        _fail("partial_artifact_refused", str(artifact))
    if not artifact.is_file():
        _fail("artifact_not_found", str(artifact))
    if artifact.stat().st_size > max_bytes:
        _fail("artifact_too_large")
    try:
        lines = artifact.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("artifact_not_utf8") from exc
    if len(lines) > max_lines:
        _fail("line_count_exceeded")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line or len(line.encode("utf-8")) > max_line_bytes:
            _fail("line_invalid", str(line_number))
        row = _parse_object(line, path=f"line={line_number}")
        validate_transition_v21(row)
        rows.append(row)
    validate_episode_v21(rows)
    return rows


def _validate_manifest(
    manifest: Any,
    *,
    transition_path: Path,
    transition_bytes: bytes,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = _exact_mapping(manifest, MANIFEST_FIELDS_V21, path="manifest")
    if payload["manifest_version"] != KOOPMAN_EPISODE_MANIFEST_V21:
        _fail("manifest_version_mismatch")
    if payload["transition_schema_version"] != KOOPMAN_TRANSITION_SCHEMA_V21:
        _fail("schema_version_mismatch")
    if payload["transition_file"] != transition_path.name:
        _fail("manifest_transition_file_mismatch")
    actual_hash = hashlib.sha256(transition_bytes).hexdigest()
    if payload["transition_sha256"] != actual_hash:
        _fail("manifest_hash_mismatch")
    summary = validate_episode_v21(records)
    for field in (
        "record_count",
        "first_step_index",
        "last_step_index",
        "first_simulation_time_s",
        "last_simulation_time_s",
        "episode_invariants",
        "platform_context_sha256",
        "timing_provenance",
    ):
        if payload[field] != summary[field]:
            _fail("manifest_episode_mismatch", field)
    if not isinstance(payload["runtime_provenance"], Mapping):
        _fail("type_invalid", "manifest.runtime_provenance")
    evidence_level = summary["episode_invariants"]["evidence_level"]
    if payload["evidence_level"] != evidence_level:
        _fail("manifest_episode_mismatch", "evidence_level")
    return summary


def validate_episode_artifact_v21(
    jsonl_path: str | Path, manifest_path: str | Path
) -> dict[str, Any]:
    transition_path = Path(jsonl_path)
    records = load_episode_jsonl_v21(transition_path)
    manifest = _parse_object(Path(manifest_path).read_text(encoding="utf-8"), path="manifest")
    summary = _validate_manifest(
        manifest,
        transition_path=transition_path,
        transition_bytes=transition_path.read_bytes(),
        records=records,
    )
    return {
        "validation_gate": "schema_v21_episode_valid",
        "evidence_level": manifest["evidence_level"],
        "record_count": summary["record_count"],
        "configuration": summary["episode_invariants"]["configuration"],
        "episode_id": summary["episode_invariants"]["episode_id"],
        "transition_sha256": manifest["transition_sha256"],
        "warnings": [],
    }


class KoopmanEpisodeLoggerV21:
    """Write one schema-v2.1 episode at its explicitly validated evidence level."""

    def __init__(
        self,
        jsonl_path: str | Path,
        *,
        manifest_path: str | Path | None = None,
        runtime_provenance: Mapping[str, Any] | None = None,
    ) -> None:
        self.path = Path(jsonl_path)
        if self.path.name.endswith(".part"):
            _fail("partial_target_invalid")
        self.manifest_path = (
            Path(manifest_path)
            if manifest_path is not None
            else self.path.with_name(f"{self.path.name}.manifest.json")
        )
        self.part_path = self.path.with_name(f"{self.path.name}.part")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        for candidate in (self.path, self.manifest_path, self.part_path):
            if candidate.exists():
                _fail("artifact_exists", str(candidate))
        self._stream = self.part_path.open("xb")
        self._records: list[dict[str, Any]] = []
        self._finalized = False
        if runtime_provenance is None:
            runtime_provenance = {
                "artifact_origin": LOCAL_EVIDENCE_LEVEL,
                "generator": "KoopmanEpisodeLoggerV21",
            }
        if not isinstance(runtime_provenance, Mapping):
            _fail("type_invalid", "runtime_provenance")
        self._runtime_provenance = deepcopy(dict(runtime_provenance))

    def write(self, transition: Mapping[str, Any]) -> None:
        if self._stream.closed or self._finalized:
            _fail("logger_closed")
        validate_transition_v21(transition)
        row = deepcopy(dict(transition))
        self._stream.write(_canonical_json_bytes(row))
        self._stream.flush()
        self._records.append(row)

    def finalize(self) -> dict[str, Any]:
        if self._stream.closed or self._finalized:
            _fail("logger_closed")
        summary = validate_episode_v21(self._records)
        evidence_level = summary["episode_invariants"]["evidence_level"]
        if self._runtime_provenance.get("artifact_origin") != evidence_level:
            _fail("runtime_provenance_evidence_mismatch")
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._stream.close()
        transition_bytes = self.part_path.read_bytes()
        manifest: dict[str, Any] = {
            "manifest_version": KOOPMAN_EPISODE_MANIFEST_V21,
            "transition_schema_version": KOOPMAN_TRANSITION_SCHEMA_V21,
            "transition_file": self.path.name,
            "transition_sha256": hashlib.sha256(transition_bytes).hexdigest(),
            "record_count": summary["record_count"],
            "first_step_index": summary["first_step_index"],
            "last_step_index": summary["last_step_index"],
            "first_simulation_time_s": summary["first_simulation_time_s"],
            "last_simulation_time_s": summary["last_simulation_time_s"],
            "episode_invariants": summary["episode_invariants"],
            "platform_context_sha256": summary["platform_context_sha256"],
            "timing_provenance": summary["timing_provenance"],
            "runtime_provenance": deepcopy(self._runtime_provenance),
            "evidence_level": evidence_level,
        }
        _validate_manifest(
            manifest,
            transition_path=self.path,
            transition_bytes=transition_bytes,
            records=self._records,
        )

        manifest_temp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.manifest_path.parent,
                prefix=f".{self.manifest_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                manifest_temp = Path(stream.name)
                stream.write(_canonical_json_bytes(manifest))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(self.part_path, self.path)
            os.replace(manifest_temp, self.manifest_path)
        finally:
            if manifest_temp is not None and manifest_temp.exists():
                manifest_temp.unlink()
        self._finalized = True
        return deepcopy(manifest)

    def close(self) -> None:
        if not self._stream.closed:
            self._stream.flush()
            self._stream.close()

    def __enter__(self) -> "KoopmanEpisodeLoggerV21":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

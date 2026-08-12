"""Strict, pure-Python transition and episode contracts for Koopman schema v2.

The module deliberately imports the EasyUUV catalog lazily.  File validation and
cold imports therefore do not require Torch, Gymnasium, Isaac Sim, or Isaac Lab.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any


KOOPMAN_TRANSITION_SCHEMA_V2 = "easyuuv-koopman-transition-v2"
KOOPMAN_EPISODE_MANIFEST_V1 = "easyuuv-koopman-episode-manifest-v1"
LOCAL_EVIDENCE_LEVEL = "local_contract"
SERVER_EVIDENCE_LEVEL = "server_isaac_smoke"

STATE_DIM = 11
REFERENCE_DIM = 5
ACTION_DIM = 4
PWM_PADDED_DIM = 8
WRENCH_DIM = 6
CONTROL_BOUND = 1.0
BOUND_TOLERANCE = 1e-6
DEFAULT_NUMERIC_TOLERANCE = 1e-9
MAX_JSONL_BYTES = 64 * 1024 * 1024
MAX_JSONL_LINE_BYTES = 1024 * 1024
MAX_JSONL_LINES = 10_000_000
MAX_MANIFEST_BYTES = 1024 * 1024

TRANSITION_FIELDS = frozenset(
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
PLATFORM_CONTEXT_FIELDS = frozenset(
    {
        "configuration",
        "thruster_count",
        "control_channels",
        "control_mask",
        "allocation_mode",
        "declared_control_rank",
        "mass_kg",
        "inertia_diagonal_kg_m2",
        "com_to_cob_offset_m",
        "volume_m3",
        "drag_multiplier",
        "thruster_dynamics_time_constant_s",
    }
)
ENVIRONMENT_CONTEXT_FIELDS = frozenset(
    {
        "available",
        "method",
        "method_version",
        "source_kind",
        "source_signals",
        "values",
        "units",
        "frames",
        "value_provenance",
    }
)
EPISODE_PROVENANCE_FIELDS = frozenset(
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
ORACLE_VALUE_FIELDS = frozenset(
    {
        "fluid_velocity_world_3",
        "water_density_kg_m3",
        "dynamic_viscosity_pa_s",
        "drag_multiplier",
        "thruster_efficiency_n",
    }
)
EPISODE_INVARIANT_FIELDS = frozenset(
    {
        "configuration",
        "scenario",
        "episode_id",
        "seed",
        "control_dt_s",
        "task_id",
        "controller_mode",
        "source_commit",
        "evidence_level",
    }
)
MANIFEST_FIELDS = frozenset(
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
        "runtime_provenance",
        "evidence_level",
    }
)

_SOURCE_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if not detail else f"{reason}:{detail}")


def _require_exact_mapping(
    value: Any, expected_fields: frozenset[str], *, path: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("type_invalid", path)
    actual = set(value)
    if actual != expected_fields:
        missing = ",".join(sorted(expected_fields - actual)) or "none"
        extra = ",".join(sorted(actual - expected_fields)) or "none"
        _fail("field_set_mismatch", f"{path}:missing={missing};extra={extra}")
    return value


def _require_nonempty_string(value: Any, *, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("type_invalid", path)
    return value


def _require_int(value: Any, *, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("type_invalid", path)
    return value


def _require_number(value: Any, *, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("type_invalid", path)
    numeric = float(value)
    if not math.isfinite(numeric):
        _fail("nonfinite_value", path)
    return numeric


def _require_vector(
    value: Any,
    width: int,
    *,
    path: str,
    bounds: tuple[float, float] | None = None,
    bounds_reason: str = "control_out_of_bounds",
) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("type_invalid", path)
    if len(value) != width:
        _fail("shape_invalid", f"{path}:expected={width};actual={len(value)}")
    result = [_require_number(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if bounds is not None:
        lower, upper = bounds
        for index, item in enumerate(result):
            if item < lower - BOUND_TOLERANCE or item > upper + BOUND_TOLERANCE:
                _fail(bounds_reason, f"{path}[{index}]={item}")
    return result


def _require_positive_number(value: Any, *, path: str) -> float:
    numeric = _require_number(value, path=path)
    if numeric <= 0.0:
        _fail("context_value_invalid", path)
    return numeric


def _catalog_record(configuration: Any) -> Mapping[str, Any]:
    if not isinstance(configuration, str) or not configuration:
        _fail("configuration_unknown", str(configuration))
    from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS, qualification_record

    if configuration not in SUPPORTED_EMBODIMENTS:
        _fail("configuration_unknown", configuration)
    return qualification_record(configuration)


def _validate_platform_context(value: Any) -> tuple[str, Mapping[str, Any]]:
    context = _require_exact_mapping(
        value, PLATFORM_CONTEXT_FIELDS, path="platform_context"
    )
    configuration = context["configuration"]
    topology = _catalog_record(configuration)

    expected_values = {
        "thruster_count": topology["thruster_count"],
        "control_channels": list(topology["control_channels"]),
        "control_mask": list(topology["control_mask"]),
        "allocation_mode": topology["allocation_mode"],
        "declared_control_rank": topology["declared_control_rank"],
    }
    for field, expected in expected_values.items():
        actual = context[field]
        if field in {"thruster_count", "declared_control_rank"}:
            _require_int(actual, path=f"platform_context.{field}")
        if field == "control_mask":
            if not isinstance(actual, list) or any(type(item) is not int for item in actual):
                _fail("type_invalid", f"platform_context.{field}")
        if actual != expected:
            _fail("topology_mismatch", f"platform_context.{field}")

    _require_positive_number(context["mass_kg"], path="platform_context.mass_kg")
    inertia = _require_vector(
        context["inertia_diagonal_kg_m2"],
        3,
        path="platform_context.inertia_diagonal_kg_m2",
    )
    if any(item <= 0.0 for item in inertia):
        _fail("context_value_invalid", "platform_context.inertia_diagonal_kg_m2")
    _require_vector(
        context["com_to_cob_offset_m"],
        3,
        path="platform_context.com_to_cob_offset_m",
    )
    _require_positive_number(context["volume_m3"], path="platform_context.volume_m3")
    _require_positive_number(
        context["drag_multiplier"], path="platform_context.drag_multiplier"
    )
    _require_positive_number(
        context["thruster_dynamics_time_constant_s"],
        path="platform_context.thruster_dynamics_time_constant_s",
    )
    return configuration, topology


def _validate_metadata_maps(
    context: Mapping[str, Any], *, path: str, expected_keys: set[str]
) -> None:
    for namespace in ("units", "frames", "value_provenance"):
        mapping = context[namespace]
        if not isinstance(mapping, Mapping) or set(mapping) != expected_keys:
            _fail("context_provenance_invalid", f"{path}.{namespace}")
        for key, value in mapping.items():
            _require_nonempty_string(value, path=f"{path}.{namespace}.{key}")


def _validate_finite_context_value(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _validate_finite_context_value(nested, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, nested in enumerate(value):
            _validate_finite_context_value(nested, path=f"{path}[{index}]")
        return
    _require_number(value, path=path)


def _validate_oracle_context(value: Any, *, thruster_count: int) -> Mapping[str, Any]:
    context = _require_exact_mapping(
        value, ENVIRONMENT_CONTEXT_FIELDS, path="environment_context_oracle"
    )
    if context["available"] is not True:
        _fail("context_unavailable_invalid", "environment_context_oracle.available")
    _require_nonempty_string(
        context["method"], path="environment_context_oracle.method"
    )
    _require_nonempty_string(
        context["method_version"],
        path="environment_context_oracle.method_version",
    )
    if context["source_kind"] != "simulator_ground_truth":
        _fail("context_provenance_invalid", "environment_context_oracle.source_kind")
    signals = context["source_signals"]
    if not isinstance(signals, list) or not signals or any(
        not isinstance(item, str) or not item for item in signals
    ):
        _fail("context_provenance_invalid", "environment_context_oracle.source_signals")
    values = context["values"]
    if not isinstance(values, Mapping) or set(values) != ORACLE_VALUE_FIELDS:
        _fail("field_set_mismatch", "environment_context_oracle.values")
    _require_vector(
        values["fluid_velocity_world_3"],
        3,
        path="environment_context_oracle.values.fluid_velocity_world_3",
    )
    _require_positive_number(
        values["water_density_kg_m3"],
        path="environment_context_oracle.values.water_density_kg_m3",
    )
    _require_positive_number(
        values["dynamic_viscosity_pa_s"],
        path="environment_context_oracle.values.dynamic_viscosity_pa_s",
    )
    _require_positive_number(
        values["drag_multiplier"],
        path="environment_context_oracle.values.drag_multiplier",
    )
    _require_vector(
        values["thruster_efficiency_n"],
        thruster_count,
        path="environment_context_oracle.values.thruster_efficiency_n",
    )
    _validate_metadata_maps(
        context,
        path="environment_context_oracle",
        expected_keys=set(values),
    )
    if context["units"]["fluid_velocity_world_3"] != "m/s":
        _fail("context_provenance_invalid", "environment_context_oracle.units.fluid_velocity_world_3")
    if context["frames"]["fluid_velocity_world_3"] != "world":
        _fail("context_provenance_invalid", "environment_context_oracle.frames.fluid_velocity_world_3")
    return context


def _validate_estimated_context(
    value: Any, *, oracle: Mapping[str, Any]
) -> None:
    if value is oracle:
        _fail("oracle_as_estimate", "object_alias")
    context = _require_exact_mapping(
        value, ENVIRONMENT_CONTEXT_FIELDS, path="environment_context_estimated"
    )
    if context["available"] is False:
        expected_empty = {
            "method": "",
            "method_version": "",
            "source_kind": "unavailable",
            "source_signals": [],
            "values": {},
            "units": {},
            "frames": {},
            "value_provenance": {},
        }
        for field, expected in expected_empty.items():
            if context[field] != expected:
                _fail("context_unavailable_invalid", f"environment_context_estimated.{field}")
        return
    if context["available"] is not True:
        _fail("type_invalid", "environment_context_estimated.available")

    copied_namespaces = ("values", "units", "frames", "value_provenance")
    if all(context[field] == oracle[field] for field in copied_namespaces):
        _fail("oracle_as_estimate", "copied_oracle_payload")
    if context["source_kind"] != "deployable_observation":
        _fail("oracle_as_estimate", "source_kind")
    for field in ("method", "method_version"):
        value = context[field]
        if not isinstance(value, str) or not value.strip():
            _fail(
                "context_provenance_invalid",
                f"environment_context_estimated.{field}",
            )
    signals = context["source_signals"]
    if not isinstance(signals, list) or not signals or any(
        not isinstance(item, str) or not item for item in signals
    ):
        _fail("context_provenance_invalid", "environment_context_estimated.source_signals")
    values = context["values"]
    if not isinstance(values, Mapping) or not values:
        _fail("context_provenance_invalid", "environment_context_estimated.values")
    for key, nested in values.items():
        if not isinstance(key, str) or not key:
            _fail("context_provenance_invalid", "environment_context_estimated.values")
        _validate_finite_context_value(
            nested, path=f"environment_context_estimated.values.{key}"
        )
    _validate_metadata_maps(
        context,
        path="environment_context_estimated",
        expected_keys=set(values),
    )


def _validate_episode_provenance(
    value: Any, *, configuration: str
) -> Mapping[str, Any]:
    provenance = _require_exact_mapping(
        value, EPISODE_PROVENANCE_FIELDS, path="episode_provenance"
    )
    if provenance["configuration"] != configuration:
        _fail("topology_mismatch", "episode_provenance.configuration")
    for field in (
        "configuration",
        "scenario",
        "episode_id",
        "task_id",
        "controller_mode",
    ):
        _require_nonempty_string(provenance[field], path=f"episode_provenance.{field}")
    step_index = _require_int(
        provenance["step_index"], path="episode_provenance.step_index"
    )
    if step_index < 0:
        _fail("context_value_invalid", "episode_provenance.step_index")
    _require_int(provenance["seed"], path="episode_provenance.seed")
    simulation_time = _require_number(
        provenance["simulation_time_s"],
        path="episode_provenance.simulation_time_s",
    )
    if simulation_time < 0.0:
        _fail("context_value_invalid", "episode_provenance.simulation_time_s")
    _require_positive_number(
        provenance["control_dt_s"], path="episode_provenance.control_dt_s"
    )
    source_commit = provenance["source_commit"]
    if not isinstance(source_commit, str) or not _SOURCE_COMMIT_PATTERN.fullmatch(
        source_commit
    ):
        _fail("source_commit_invalid")
    if provenance["evidence_level"] not in {
        LOCAL_EVIDENCE_LEVEL,
        SERVER_EVIDENCE_LEVEL,
    }:
        _fail("evidence_level_invalid")
    return provenance


def validate_transition_v2(transition: Any) -> None:
    """Validate one schema-v2 transition without mutating caller-owned data."""
    payload = _require_exact_mapping(
        transition, TRANSITION_FIELDS, path="transition"
    )
    if payload["schema_version"] != KOOPMAN_TRANSITION_SCHEMA_V2:
        _fail("schema_version_mismatch")

    _require_vector(payload["state_11"], STATE_DIM, path="state_11")
    _require_vector(payload["reference_5"], REFERENCE_DIM, path="reference_5")
    _require_vector(
        payload["raw_action_4"],
        ACTION_DIM,
        path="raw_action_4",
        bounds=(-CONTROL_BOUND, CONTROL_BOUND),
    )
    virtual_control = _require_vector(
        payload["virtual_control_4"],
        ACTION_DIM,
        path="virtual_control_4",
        bounds=(-CONTROL_BOUND, CONTROL_BOUND),
    )
    pwm = _require_vector(
        payload["motor_pwm_padded_8"],
        PWM_PADDED_DIM,
        path="motor_pwm_padded_8",
        bounds=(-CONTROL_BOUND, CONTROL_BOUND),
        bounds_reason="pwm_out_of_bounds",
    )
    mask = payload["thruster_mask_8"]
    if isinstance(mask, (str, bytes)) or not isinstance(mask, Sequence):
        _fail("type_invalid", "thruster_mask_8")
    if len(mask) != PWM_PADDED_DIM:
        _fail("shape_invalid", "thruster_mask_8")
    if any(type(item) is not int for item in mask):
        _fail("type_invalid", "thruster_mask_8")
    if any(item not in (0, 1) for item in mask):
        _fail("mask_mismatch", "thruster_mask_8")
    _require_vector(
        payload["applied_wrench_6"], WRENCH_DIM, path="applied_wrench_6"
    )
    _require_vector(payload["next_state_11"], STATE_DIM, path="next_state_11")

    configuration, topology = _validate_platform_context(payload["platform_context"])
    expected_mask = [1] * topology["thruster_count"] + [0] * (
        PWM_PADDED_DIM - topology["thruster_count"]
    )
    if list(mask) != expected_mask:
        _fail("mask_mismatch", configuration)
    for index, enabled in enumerate(mask):
        if enabled == 0 and pwm[index] != 0.0:
            _fail("padding_nonzero", f"motor_pwm_padded_8[{index}]")
    if configuration.startswith("uuv4") and virtual_control[2] != 0.0:
        _fail("underactuated_yaw_nonzero", configuration)

    oracle = _validate_oracle_context(
        payload["environment_context_oracle"],
        thruster_count=topology["thruster_count"],
    )
    _validate_estimated_context(
        payload["environment_context_estimated"], oracle=oracle
    )
    _validate_episode_provenance(
        payload["episode_provenance"], configuration=configuration
    )


def build_local_transition_v2(**fields: Any) -> dict[str, Any]:
    """Return a fresh validated transition that can claim only local evidence."""
    transition = deepcopy(fields)
    validate_transition_v2(transition)
    provenance = transition["episode_provenance"]
    if provenance["evidence_level"] != LOCAL_EVIDENCE_LEVEL:
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
        _fail("serialization_invalid", str(exc))
    return (text + "\n").encode("utf-8")


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _episode_invariants(row: Mapping[str, Any]) -> dict[str, Any]:
    provenance = row["episode_provenance"]
    return {field: deepcopy(provenance[field]) for field in sorted(EPISODE_INVARIANT_FIELDS)}


def validate_episode_v2(
    transitions: Sequence[Mapping[str, Any]],
    *,
    numeric_tolerance: float = DEFAULT_NUMERIC_TOLERANCE,
) -> dict[str, Any]:
    """Validate one immutable, contiguous two-or-more-row episode."""
    tolerance = _require_number(numeric_tolerance, path="numeric_tolerance")
    if tolerance < 0.0:
        _fail("context_value_invalid", "numeric_tolerance")
    if isinstance(transitions, (str, bytes)) or not isinstance(transitions, Sequence):
        _fail("type_invalid", "transitions")
    if len(transitions) < 2:
        _fail("episode_too_short", str(len(transitions)))

    # Classify ordering before per-row validation so duplicate/reordered/gapped
    # artifacts receive distinct, deterministic episode-level reasons.
    step_indices: list[int] = []
    for index, row in enumerate(transitions):
        if not isinstance(row, Mapping):
            _fail("type_invalid", f"transitions[{index}]")
        provenance = row.get("episode_provenance")
        if not isinstance(provenance, Mapping):
            _fail("type_invalid", f"transitions[{index}].episode_provenance")
        step_indices.append(
            _require_int(
                provenance.get("step_index"),
                path=f"transitions[{index}].episode_provenance.step_index",
            )
        )
    for previous, current in zip(step_indices, step_indices[1:]):
        if current == previous:
            _fail("step_duplicate")
        if current < previous:
            _fail("step_reordered")
        if current != previous + 1:
            _fail("step_discontinuity")

    for row in transitions:
        validate_transition_v2(row)

    first = transitions[0]
    first_provenance = first["episode_provenance"]
    invariants = _episode_invariants(first)
    platform_digest = _canonical_digest(first["platform_context"])
    previous = first
    for index, current in enumerate(transitions[1:], start=1):
        current_provenance = current["episode_provenance"]
        for field in EPISODE_INVARIANT_FIELDS:
            if current_provenance[field] != first_provenance[field]:
                _fail("episode_invariant_drift", f"row={index};field={field}")
        if _canonical_digest(current["platform_context"]) != platform_digest:
            _fail("platform_context_drift", f"row={index}")

        expected_time = (
            float(previous["episode_provenance"]["simulation_time_s"])
            + float(first_provenance["control_dt_s"])
        )
        actual_time = float(current_provenance["simulation_time_s"])
        if abs(actual_time - expected_time) > tolerance:
            _fail(
                "time_discontinuity",
                f"row={index};expected={expected_time};actual={actual_time}",
            )
        for component, (expected, actual) in enumerate(
            zip(previous["next_state_11"], current["state_11"], strict=True)
        ):
            if abs(float(actual) - float(expected)) > tolerance:
                _fail(
                    "state_transition_discontinuity",
                    f"row={index};component={component}",
                )
        previous = current

    last_provenance = transitions[-1]["episode_provenance"]
    return {
        "record_count": len(transitions),
        "first_step_index": step_indices[0],
        "last_step_index": step_indices[-1],
        "first_simulation_time_s": float(first_provenance["simulation_time_s"]),
        "last_simulation_time_s": float(last_provenance["simulation_time_s"]),
        "episode_invariants": invariants,
        "platform_context_sha256": platform_digest,
    }


def _reject_json_constant(token: str) -> None:
    _fail("nonfinite_json_constant", token)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key", key)
        result[key] = value
    return result


def _parse_json_object(text: str, *, path: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json:{path}:{exc.msg}") from exc
    if not isinstance(payload, dict):
        _fail("root_not_object", path)
    return payload


def load_episode_jsonl_v2(
    path: str | Path,
    *,
    max_bytes: int = MAX_JSONL_BYTES,
    max_line_bytes: int = MAX_JSONL_LINE_BYTES,
    max_lines: int = MAX_JSONL_LINES,
    numeric_tolerance: float = DEFAULT_NUMERIC_TOLERANCE,
) -> list[dict[str, Any]]:
    """Load a bounded canonical episode and reject partial or unsafe JSON."""
    artifact_path = Path(path)
    if artifact_path.name.endswith(".part"):
        _fail("partial_artifact_refused", str(artifact_path))
    for name, value in (
        ("max_bytes", max_bytes),
        ("max_line_bytes", max_line_bytes),
        ("max_lines", max_lines),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            _fail("type_invalid", name)
    if not artifact_path.exists():
        _fail("artifact_not_found", str(artifact_path))
    if not artifact_path.is_file():
        _fail("artifact_not_regular_file", str(artifact_path))
    size = artifact_path.stat().st_size
    if size > max_bytes:
        _fail("artifact_too_large", str(size))
    raw = artifact_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("artifact_not_utf8") from exc
    lines = text.splitlines()
    if len(lines) > max_lines:
        _fail("line_count_exceeded", str(len(lines)))
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            _fail("empty_line", str(line_number))
        if len(line.encode("utf-8")) > max_line_bytes:
            _fail("line_too_large", str(line_number))
        payload = _parse_json_object(line, path=f"line={line_number}")
        validate_transition_v2(payload)
        records.append(payload)
    validate_episode_v2(records, numeric_tolerance=numeric_tolerance)
    return records


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        _fail("manifest_not_found", str(path))
    if not path.is_file():
        _fail("manifest_not_regular_file", str(path))
    size = path.stat().st_size
    if size > MAX_MANIFEST_BYTES:
        _fail("manifest_too_large", str(size))
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("manifest_not_utf8") from exc
    return _parse_json_object(text, path="manifest")


def _validate_manifest_v1(
    manifest: Any,
    *,
    transition_path: Path,
    transition_bytes: bytes,
    records: Sequence[Mapping[str, Any]],
    numeric_tolerance: float,
) -> dict[str, Any]:
    payload = _require_exact_mapping(manifest, MANIFEST_FIELDS, path="manifest")
    if payload["manifest_version"] != KOOPMAN_EPISODE_MANIFEST_V1:
        _fail("manifest_version_mismatch")
    if payload["transition_schema_version"] != KOOPMAN_TRANSITION_SCHEMA_V2:
        _fail("schema_version_mismatch", "manifest.transition_schema_version")
    if payload["transition_file"] != transition_path.name:
        _fail("manifest_transition_file_mismatch")
    transition_hash = payload["transition_sha256"]
    if not isinstance(transition_hash, str) or not _SHA256_PATTERN.fullmatch(
        transition_hash
    ):
        _fail("manifest_hash_invalid")
    actual_hash = hashlib.sha256(transition_bytes).hexdigest()
    if transition_hash != actual_hash:
        _fail("manifest_hash_mismatch")

    summary = validate_episode_v2(records, numeric_tolerance=numeric_tolerance)
    int_fields = ("record_count", "first_step_index", "last_step_index")
    for field in int_fields:
        _require_int(payload[field], path=f"manifest.{field}")
        if payload[field] != summary[field]:
            _fail("manifest_episode_mismatch", field)
    time_fields = ("first_simulation_time_s", "last_simulation_time_s")
    for field in time_fields:
        actual = _require_number(payload[field], path=f"manifest.{field}")
        if abs(actual - summary[field]) > numeric_tolerance:
            _fail("manifest_episode_mismatch", field)
    invariants = _require_exact_mapping(
        payload["episode_invariants"],
        EPISODE_INVARIANT_FIELDS,
        path="manifest.episode_invariants",
    )
    if dict(invariants) != summary["episode_invariants"]:
        _fail("manifest_episode_mismatch", "episode_invariants")
    platform_digest = payload["platform_context_sha256"]
    if not isinstance(platform_digest, str) or not _SHA256_PATTERN.fullmatch(
        platform_digest
    ):
        _fail("manifest_hash_invalid", "platform_context_sha256")
    if platform_digest != summary["platform_context_sha256"]:
        _fail("platform_context_drift", "manifest")
    runtime_provenance = payload["runtime_provenance"]
    if not isinstance(runtime_provenance, Mapping):
        _fail("type_invalid", "manifest.runtime_provenance")
    if any(not isinstance(key, str) or not key for key in runtime_provenance):
        _fail("type_invalid", "manifest.runtime_provenance")
    evidence_level = payload["evidence_level"]
    if evidence_level != summary["episode_invariants"]["evidence_level"]:
        _fail("manifest_episode_mismatch", "evidence_level")
    if evidence_level not in {LOCAL_EVIDENCE_LEVEL, SERVER_EVIDENCE_LEVEL}:
        _fail("evidence_level_invalid")
    return summary


def validate_episode_artifact_v2(
    jsonl_path: str | Path,
    manifest_path: str | Path,
    *,
    numeric_tolerance: float = DEFAULT_NUMERIC_TOLERANCE,
) -> dict[str, Any]:
    """Validate transition bytes, episode semantics and their manifest as a pair."""
    transition_path = Path(jsonl_path)
    records = load_episode_jsonl_v2(
        transition_path, numeric_tolerance=numeric_tolerance
    )
    manifest = _load_manifest(Path(manifest_path))
    summary = _validate_manifest_v1(
        manifest,
        transition_path=transition_path,
        transition_bytes=transition_path.read_bytes(),
        records=records,
        numeric_tolerance=numeric_tolerance,
    )
    return {
        "validation_gate": "schema_v2_episode_valid",
        "evidence_level": manifest["evidence_level"],
        "record_count": summary["record_count"],
        "configuration": summary["episode_invariants"]["configuration"],
        "episode_id": summary["episode_invariants"]["episode_id"],
        "transition_sha256": manifest["transition_sha256"],
        "warnings": [],
    }


def _write_manifest_temp(path: Path, payload: Mapping[str, Any]) -> Path:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(_canonical_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        return temporary_path
    except Exception:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
        raise


class KoopmanEpisodeLoggerV2:
    """Write one new local-contract episode through a retained ``.part`` file."""

    def __init__(
        self,
        jsonl_path: str | Path,
        *,
        manifest_path: str | Path | None = None,
        numeric_tolerance: float = DEFAULT_NUMERIC_TOLERANCE,
    ) -> None:
        self.path = Path(jsonl_path)
        if self.path.name.endswith(".part"):
            _fail("partial_target_invalid", str(self.path))
        self.manifest_path = (
            Path(manifest_path)
            if manifest_path is not None
            else self.path.with_name(f"{self.path.name}.manifest.json")
        )
        self.part_path = self.path.with_name(f"{self.path.name}.part")
        self.numeric_tolerance = _require_number(
            numeric_tolerance, path="numeric_tolerance"
        )
        if self.numeric_tolerance < 0.0:
            _fail("context_value_invalid", "numeric_tolerance")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        for candidate in (self.path, self.manifest_path, self.part_path):
            if candidate.exists():
                _fail("artifact_exists", str(candidate))
        self._stream = self.part_path.open("xb")
        self._records: list[dict[str, Any]] = []
        self._finalized = False

    def write(self, transition: Mapping[str, Any]) -> None:
        if self._stream.closed or self._finalized:
            _fail("logger_closed")
        validate_transition_v2(transition)
        if transition["episode_provenance"]["evidence_level"] != LOCAL_EVIDENCE_LEVEL:
            _fail("local_evidence_required")
        row = deepcopy(dict(transition))
        encoded = _canonical_json_bytes(row)
        self._stream.write(encoded)
        self._stream.flush()
        self._records.append(row)

    def finalize(self) -> dict[str, Any]:
        if self._stream.closed or self._finalized:
            _fail("logger_closed")
        summary = validate_episode_v2(
            self._records, numeric_tolerance=self.numeric_tolerance
        )
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._stream.close()
        transition_bytes = self.part_path.read_bytes()
        manifest: dict[str, Any] = {
            "manifest_version": KOOPMAN_EPISODE_MANIFEST_V1,
            "transition_schema_version": KOOPMAN_TRANSITION_SCHEMA_V2,
            "transition_file": self.path.name,
            "transition_sha256": hashlib.sha256(transition_bytes).hexdigest(),
            "record_count": summary["record_count"],
            "first_step_index": summary["first_step_index"],
            "last_step_index": summary["last_step_index"],
            "first_simulation_time_s": summary["first_simulation_time_s"],
            "last_simulation_time_s": summary["last_simulation_time_s"],
            "episode_invariants": summary["episode_invariants"],
            "platform_context_sha256": summary["platform_context_sha256"],
            "runtime_provenance": {
                "artifact_origin": LOCAL_EVIDENCE_LEVEL,
                "generator": "KoopmanEpisodeLoggerV2",
            },
            "evidence_level": LOCAL_EVIDENCE_LEVEL,
        }
        _validate_manifest_v1(
            manifest,
            transition_path=self.path,
            transition_bytes=transition_bytes,
            records=self._records,
            numeric_tolerance=self.numeric_tolerance,
        )
        manifest_temporary = _write_manifest_temp(self.manifest_path, manifest)
        try:
            os.replace(self.part_path, self.path)
            os.replace(manifest_temporary, self.manifest_path)
        finally:
            if manifest_temporary.exists():
                manifest_temporary.unlink()
        self._finalized = True
        return deepcopy(manifest)

    def close(self) -> None:
        if not self._stream.closed:
            self._stream.flush()
            self._stream.close()

    def __enter__(self) -> "KoopmanEpisodeLoggerV2":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

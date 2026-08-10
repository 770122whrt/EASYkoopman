"""Strict, Isaac-free contract for EasyUUV v2 qualification artifacts."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import Path
import re
from typing import Any


QUALIFICATION_SCHEMA_VERSION = "easyuuv-v2-qualification-v1"
SERVER_EVIDENCE_LEVEL = "server_isaac_smoke"
LOCAL_EVIDENCE_LEVEL = "local_contract"
EXPECTED_TASK_ID = "EasyUUV-Direct-v1"
EXPECTED_ISAAC_SIM_VERSION = "5.0"
EXPECTED_ISAAC_LAB_VERSION = "2.2.1"
CONTROL_CHANNELS = ("roll", "pitch", "yaw", "depth")
CONTROL_BOUND = 1.0
BOUND_TOLERANCE = 1e-6
MAX_ARTIFACT_BYTES = 10 * 1024 * 1024

TOP_LEVEL_REQUIRED_FIELDS = (
    "schema_version",
    "evidence_level",
    "expected_isaac_sim",
    "expected_isaac_lab",
    "actual_isaac_sim",
    "actual_isaac_lab",
    "task_id",
    "source_commit",
    "results",
)

ROW_REQUIRED_FIELDS = (
    "configuration",
    "thruster_count",
    "control_channels",
    "control_mask",
    "declared_control_rank",
    "environment_created",
    "reset_passed",
    "steps_completed",
    "action_min",
    "action_max",
    "motor_min",
    "motor_max",
    "motor_vector_length",
    "nonfinite_count",
    "dimension_mismatch_count",
    "seed",
    "status",
    "reason_codes",
)

CONTROL_VALUE_FIELDS = ("action_min", "action_max", "motor_min", "motor_max")
_SOURCE_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_RUNTIME_PROVENANCE_FIELDS = {
    "isaac_sim_distribution",
    "isaac_lab_distribution",
    "isaac_lab_repo_commit",
    "isaac_lab_repo_tag",
}
_SIM_DISTRIBUTION_PATTERN = re.compile(r"^(\d+)\.(\d+)(?:\.|$)")


def _fail(reason: str, detail: str | None = None) -> None:
    message = reason if not detail else f"{reason}:{detail}"
    raise ValueError(message)


def _reject_json_constant(token: str) -> None:
    _fail("nonfinite_json_constant", token)


def load_qualification_payload(path: str | Path) -> dict[str, Any]:
    """Load one strict JSON object from a bounded regular file."""
    artifact_path = Path(path)
    if not artifact_path.exists():
        _fail("artifact_not_found", str(artifact_path))
    if not artifact_path.is_file():
        _fail("artifact_not_regular_file", str(artifact_path))
    if artifact_path.stat().st_size > MAX_ARTIFACT_BYTES:
        _fail("artifact_too_large", str(artifact_path.stat().st_size))

    try:
        text = artifact_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("artifact_not_utf8") from exc

    try:
        payload = json.loads(text, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json:{exc.msg}") from exc
    if not isinstance(payload, dict):
        _fail("root_not_object")
    return payload


def _expected_topology_from_catalog() -> dict[str, dict[str, Any]]:
    """Load catalog truth lazily so importing this validator never imports Isaac."""
    from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS, qualification_record

    return {
        name: {
            "thruster_count": qualification_record(name)["thruster_count"],
            "control_mask": qualification_record(name)["control_mask"],
            "declared_control_rank": qualification_record(name)["declared_control_rank"],
        }
        for name in SUPPORTED_EMBODIMENTS
    }


def _require_fields(payload: Mapping[str, Any], required: tuple[str, ...], reason: str) -> None:
    missing = sorted(field for field in required if field not in payload)
    if missing:
        _fail(reason, ",".join(missing))


def _require_nonempty_version(payload: Mapping[str, Any], field: str, reason: str) -> str:
    value = payload[field]
    if not isinstance(value, str) or not value.strip():
        _fail(reason, field)
    return value.strip()


def _require_int(row: Mapping[str, Any], field: str, configuration: str) -> int:
    value = row[field]
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("integer_field_invalid", f"{configuration}:{field}")
    return value


def _require_finite_control(row: Mapping[str, Any], field: str, configuration: str) -> float:
    value = row[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("control_value_invalid", f"{configuration}:{field}")
    numeric = float(value)
    if not math.isfinite(numeric):
        _fail("nonfinite_control", f"{configuration}:{field}")
    if abs(numeric) > CONTROL_BOUND + BOUND_TOLERANCE:
        _fail("control_out_of_bounds", f"{configuration}:{field}={numeric}")
    return numeric


def _validate_runtime_provenance(payload: Mapping[str, Any]) -> None:
    if "runtime_provenance" not in payload:
        _fail("runtime_provenance_missing")
    provenance = payload["runtime_provenance"]
    if not isinstance(provenance, Mapping) or set(provenance) != _RUNTIME_PROVENANCE_FIELDS:
        _fail("runtime_provenance_invalid", "fields")
    if any(
        not isinstance(provenance[field], str) or not provenance[field].strip()
        for field in _RUNTIME_PROVENANCE_FIELDS
    ):
        _fail("runtime_provenance_invalid", "values")

    sim_match = _SIM_DISTRIBUTION_PATTERN.match(
        provenance["isaac_sim_distribution"].strip()
    )
    normalized_sim = (
        f"{sim_match.group(1)}.{sim_match.group(2)}" if sim_match else ""
    )
    if normalized_sim != payload["actual_isaac_sim"]:
        _fail("runtime_provenance_invalid", "isaac_sim_distribution")
    if provenance["isaac_lab_repo_tag"].strip() != f"v{payload['actual_isaac_lab']}":
        _fail("runtime_provenance_invalid", "isaac_lab_repo_tag")
    if not _SOURCE_COMMIT_PATTERN.fullmatch(
        provenance["isaac_lab_repo_commit"].strip()
    ):
        _fail("runtime_provenance_invalid", "isaac_lab_repo_commit")


def _normalize_expected_topology(
    expected_topology: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    source = _expected_topology_from_catalog() if expected_topology is None else expected_topology
    normalized: dict[str, dict[str, Any]] = {}
    for name, values in source.items():
        normalized[str(name)] = {
            "thruster_count": int(values["thruster_count"]),
            "control_mask": tuple(int(value) for value in values["control_mask"]),
            "declared_control_rank": int(values["declared_control_rank"]),
        }
    return normalized


def _validate_top_level(payload: Mapping[str, Any], *, catalog_only: bool) -> None:
    _require_fields(payload, TOP_LEVEL_REQUIRED_FIELDS, "missing_top_level_fields")
    if payload["schema_version"] != QUALIFICATION_SCHEMA_VERSION:
        _fail("schema_version_mismatch")

    evidence_level = payload["evidence_level"]
    if evidence_level not in {SERVER_EVIDENCE_LEVEL, LOCAL_EVIDENCE_LEVEL}:
        _fail("evidence_level_invalid")
    if catalog_only:
        if evidence_level != LOCAL_EVIDENCE_LEVEL:
            _fail("local_evidence_required")
    elif evidence_level != SERVER_EVIDENCE_LEVEL:
        _fail("server_evidence_required")

    if payload["task_id"] != EXPECTED_TASK_ID:
        _fail("task_id_mismatch")
    if not isinstance(payload["source_commit"], str) or not _SOURCE_COMMIT_PATTERN.fullmatch(
        payload["source_commit"]
    ):
        _fail("source_commit_invalid")

    expected_sim = _require_nonempty_version(payload, "expected_isaac_sim", "expected_version_missing")
    expected_lab = _require_nonempty_version(payload, "expected_isaac_lab", "expected_version_missing")
    if (
        expected_sim != EXPECTED_ISAAC_SIM_VERSION
        or expected_lab != EXPECTED_ISAAC_LAB_VERSION
    ):
        _fail("expected_version_mismatch")
    if not catalog_only:
        actual_sim = _require_nonempty_version(payload, "actual_isaac_sim", "actual_version_missing")
        actual_lab = _require_nonempty_version(payload, "actual_isaac_lab", "actual_version_missing")
        if actual_sim != expected_sim or actual_lab != expected_lab:
            _fail("actual_version_mismatch")
        _validate_runtime_provenance(payload)

    if not isinstance(payload["results"], list):
        _fail("results_not_list")


def _index_rows(
    results: list[Any], expected_names: tuple[str, ...]
) -> dict[str, Mapping[str, Any]]:
    names: list[str] = []
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(results):
        if not isinstance(row, Mapping):
            _fail("row_not_object", str(index))
        if "configuration" not in row:
            _fail("missing_row_fields", f"row_{index}:configuration")
        name = row["configuration"]
        if not isinstance(name, str) or not name:
            _fail("configuration_name_invalid", str(index))
        names.append(name)
        rows.append(row)

    seen: set[str] = set()
    duplicates: set[str] = set()
    for name in names:
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    if duplicates:
        _fail("duplicate_configuration", ",".join(sorted(duplicates)))

    expected_set = set(expected_names)
    actual_set = set(names)
    if actual_set != expected_set:
        missing = ",".join(sorted(expected_set - actual_set)) or "none"
        extra = ",".join(sorted(actual_set - expected_set)) or "none"
        _fail("configuration_set_mismatch", f"missing={missing};extra={extra}")
    return dict(zip(names, rows, strict=True))


def _validate_row(
    row: Mapping[str, Any],
    *,
    configuration: str,
    expected: Mapping[str, Any],
    catalog_only: bool,
) -> None:
    _require_fields(row, ROW_REQUIRED_FIELDS, f"missing_row_fields:{configuration}")

    thruster_count = _require_int(row, "thruster_count", configuration)
    if thruster_count != expected["thruster_count"]:
        _fail("thruster_count_mismatch", configuration)
    if row["control_channels"] != list(CONTROL_CHANNELS):
        _fail("control_channels_mismatch", configuration)
    control_mask = row["control_mask"]
    if (
        not isinstance(control_mask, list)
        or any(type(value) is not int for value in control_mask)
        or control_mask != list(expected["control_mask"])
    ):
        _fail("control_mask_mismatch", configuration)
    rank = _require_int(row, "declared_control_rank", configuration)
    if rank != expected["declared_control_rank"]:
        _fail("declared_control_rank_mismatch", configuration)

    if not catalog_only:
        if row["environment_created"] is not True:
            _fail("environment_not_created", configuration)
        if row["reset_passed"] is not True:
            _fail("reset_failed", configuration)
        steps_completed = _require_int(row, "steps_completed", configuration)
        minimum_steps = 64 if configuration == "base" else 8
        if steps_completed < minimum_steps:
            _fail("insufficient_steps", f"{configuration}:{steps_completed}<{minimum_steps}")

    control_values = {
        field: _require_finite_control(row, field, configuration)
        for field in CONTROL_VALUE_FIELDS
    }
    for prefix in ("action", "motor"):
        if control_values[f"{prefix}_min"] > control_values[f"{prefix}_max"]:
            _fail("control_range_inverted", f"{configuration}:{prefix}")

    motor_length = _require_int(row, "motor_vector_length", configuration)
    if motor_length != thruster_count:
        _fail("motor_dimension_mismatch", configuration)
    if _require_int(row, "nonfinite_count", configuration) != 0:
        _fail("nonfinite_count_nonzero", configuration)
    if _require_int(row, "dimension_mismatch_count", configuration) != 0:
        _fail("dimension_mismatch_count_nonzero", configuration)
    _require_int(row, "seed", configuration)

    if row["status"] != "pass":
        _fail("row_status_failed", configuration)
    if not isinstance(row["reason_codes"], list):
        _fail("row_reason_codes_invalid", configuration)
    if row["reason_codes"]:
        _fail("row_reason_codes_present", configuration)


def validate_qualification_payload(
    payload: dict[str, Any],
    *,
    catalog_only: bool = False,
    expected_topology: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate one parsed qualification payload and return a deterministic gate summary."""
    if not isinstance(payload, dict):
        _fail("root_not_object")
    _validate_top_level(payload, catalog_only=catalog_only)
    topology = _normalize_expected_topology(expected_topology)
    expected_names = tuple(topology)
    rows = _index_rows(payload["results"], expected_names)

    for configuration in expected_names:
        _validate_row(
            rows[configuration],
            configuration=configuration,
            expected=topology[configuration],
            catalog_only=catalog_only,
        )

    return {
        "qualification_gate": "local_contract_pass" if catalog_only else "server_pass",
        "evidence_level": payload["evidence_level"],
        "configuration_count": len(rows),
        "passed_configurations": list(expected_names),
        "actual_versions": {
            "isaac_sim": payload["actual_isaac_sim"],
            "isaac_lab": payload["actual_isaac_lab"],
        },
        "warnings": [],
    }


def validate_qualification_file(
    path: str | Path,
    *,
    catalog_only: bool = False,
    expected_topology: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Load and validate one qualification file through the public file API."""
    payload = load_qualification_payload(path)
    return validate_qualification_payload(
        payload,
        catalog_only=catalog_only,
        expected_topology=expected_topology,
    )

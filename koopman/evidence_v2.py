"""Additive external Phase 8 evidence envelopes.

Transition rows keep the frozen Phase 7 origin vocabulary.  This module binds
validated collections to a separate qualification vocabulary and re-reads every
referenced byte before accepting that qualification.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any


PHASE8_EVIDENCE_ENVELOPE_V1 = "phase8-evidence-envelope-v1"
LOCAL_QUALIFICATION_LEVEL = "local_contract"
PILOT_QUALIFICATION_LEVEL = "server_isaac_identification_pilot"
QUALIFICATION_LEVELS = (
    LOCAL_QUALIFICATION_LEVEL,
    PILOT_QUALIFICATION_LEVEL,
    "server_isaac_identification_dataset",
    "offline_koopman_ood_evaluation",
    "koopman_selection",
    "no_selection",
)
ARTIFACT_ORIGIN_LEVELS = ("local_contract", "server_isaac_smoke")
PILOT_ALLOWED_CLAIMS = ("exact_eight_collection_health", "collection_chain_ready")
PILOT_DISALLOWED_CLAIMS = (
    "koopman_identifiability",
    "feature_or_horizon_selection",
    "prediction_or_rollout_performance",
    "ood_generalization",
    "mpc_or_closed_loop_effectiveness",
)
MAIN_DATASET_QUALIFICATION_LEVEL = "server_isaac_identification_dataset"
MAIN_DATASET_ALLOWED_CLAIMS = (
    "exact_eight_main_dataset_ready",
    "immutable_role_inventory_ready",
    "loco_split_ready",
)
MAIN_DATASET_DISALLOWED_CLAIMS = (
    "model_identified",
    "feature_or_horizon_selected",
    "prediction_or_rollout_performance",
    "ood_generalization",
    "mpc_or_closed_loop_effectiveness",
)
MAX_ENVELOPE_BYTES = 2 * 1024 * 1024
MAX_REFERENCED_FILES = 10_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ENVELOPE_FIELDS = frozenset(
    {
        "envelope_version",
        "experiment_id",
        "artifact_origin_level",
        "qualification_level",
        "source_commit",
        "protocol_sha256",
        "runtime_provenance",
        "runtime_sha256",
        "inventory_sha256",
        "decision_sha256",
        "referenced_files",
        "allowed_claims",
        "disallowed_claims",
        "validator",
    }
)
_REFERENCE_FIELDS = frozenset({"path", "sha256", "size_bytes"})
_VALIDATOR_FIELDS = frozenset({"name", "external_validation", "status"})


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key", key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    _fail("nonfinite_json_constant", value)


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
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


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_bounded_json(path: str | Path, *, max_bytes: int = MAX_ENVELOPE_BYTES) -> dict[str, Any]:
    artifact = Path(path)
    if artifact.is_symlink() or not artifact.exists() or not artifact.is_file():
        _fail("artifact_not_regular_file", str(artifact))
    raw = artifact.read_bytes()
    if len(raw) > max_bytes:
        _fail("artifact_too_large", str(len(raw)))
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise ValueError("artifact_not_utf8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"json_decode_error:{exc.msg}") from exc
    if not isinstance(payload, dict):
        _fail("root_not_object")
    return payload


def atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    if target.exists():
        _fail("artifact_exists", str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(canonical_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            _fail("artifact_exists", str(target))
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _exact_mapping(value: Any, fields: frozenset[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("type_invalid", path)
    actual = set(value)
    if actual != fields:
        missing = ",".join(sorted(fields - actual)) or "none"
        extra = ",".join(sorted(actual - fields)) or "none"
        _fail("field_set_mismatch", f"{path}:missing={missing};extra={extra}")
    return value


def _relative_reference(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    if path.is_symlink() or not path.exists() or not path.is_file():
        _fail("artifact_not_regular_file", str(path))
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root):
        _fail("reference_path_invalid", str(path))
    relative = resolved.relative_to(resolved_root).as_posix()
    if relative in {"", "."}:
        _fail("reference_path_invalid", str(path))
    return relative


def referenced_file_records(root: str | Path, paths: Sequence[str | Path]) -> list[dict[str, Any]]:
    reference_root = Path(root).resolve()
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = reference_root / path
        relative = _relative_reference(reference_root, path)
        if relative in seen:
            _fail("duplicate_reference", relative)
        seen.add(relative)
        records.append(
            {
                "path": relative,
                "sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return sorted(records, key=lambda item: item["path"])


def _build_envelope(
    *,
    experiment_id: str,
    artifact_origin_level: str,
    qualification_level: str,
    source_commit: str,
    protocol_sha256: str,
    runtime_provenance: Mapping[str, Any],
    inventory_sha256: str,
    decision_sha256: str,
    referenced_files: Sequence[Mapping[str, Any]],
    allowed_claims: Sequence[str],
    disallowed_claims: Sequence[str],
    validator_name: str,
    external_validation: bool,
) -> dict[str, Any]:
    return {
        "envelope_version": PHASE8_EVIDENCE_ENVELOPE_V1,
        "experiment_id": experiment_id,
        "artifact_origin_level": artifact_origin_level,
        "qualification_level": qualification_level,
        "source_commit": source_commit,
        "protocol_sha256": protocol_sha256,
        "runtime_provenance": dict(runtime_provenance),
        "runtime_sha256": canonical_sha256(runtime_provenance),
        "inventory_sha256": inventory_sha256,
        "decision_sha256": decision_sha256,
        "referenced_files": [dict(item) for item in referenced_files],
        "allowed_claims": list(allowed_claims),
        "disallowed_claims": list(disallowed_claims),
        "validator": {
            "name": validator_name,
            "external_validation": external_validation,
            "status": "pass",
        },
    }


def build_local_phase8_envelope(
    output_path: str | Path,
    *,
    experiment_id: str,
    source_commit: str,
    protocol_sha256: str,
    runtime_provenance: Mapping[str, Any],
    referenced_paths: Sequence[str | Path],
    qualification_level: str = LOCAL_QUALIFICATION_LEVEL,
) -> dict[str, Any]:
    """Build a local-only envelope; callers cannot request promotion."""
    if qualification_level != LOCAL_QUALIFICATION_LEVEL:
        _fail("local_self_promotion")
    output = Path(output_path).resolve()
    records = referenced_file_records(output.parent, referenced_paths)
    envelope = _build_envelope(
        experiment_id=experiment_id,
        artifact_origin_level="local_contract",
        qualification_level=LOCAL_QUALIFICATION_LEVEL,
        source_commit=source_commit,
        protocol_sha256=protocol_sha256,
        runtime_provenance=runtime_provenance,
        inventory_sha256=canonical_sha256({"referenced_files": records}),
        decision_sha256=canonical_sha256({"decision": "local_contract"}),
        referenced_files=records,
        allowed_claims=("local_contract_validation",),
        disallowed_claims=("server_runtime_qualification",),
        validator_name="build_local_phase8_envelope",
        external_validation=False,
    )
    atomic_write_json(output, envelope)
    validate_phase8_evidence(output)
    return envelope


def build_external_phase8_envelope(
    output_path: str | Path,
    *,
    experiment_id: str,
    source_commit: str,
    protocol_sha256: str,
    runtime_provenance: Mapping[str, Any],
    inventory_path: str | Path,
    decision_path: str | Path,
    referenced_paths: Sequence[str | Path],
) -> dict[str, Any]:
    """Write the pilot envelope after the audit has independently passed."""
    output = Path(output_path).resolve()
    inventory = Path(inventory_path).resolve()
    decision = Path(decision_path).resolve()
    records = referenced_file_records(output.parent, referenced_paths)
    envelope = _build_envelope(
        experiment_id=experiment_id,
        artifact_origin_level="server_isaac_smoke",
        qualification_level=PILOT_QUALIFICATION_LEVEL,
        source_commit=source_commit,
        protocol_sha256=protocol_sha256,
        runtime_provenance=runtime_provenance,
        inventory_sha256=file_sha256(inventory),
        decision_sha256=file_sha256(decision),
        referenced_files=records,
        allowed_claims=PILOT_ALLOWED_CLAIMS,
        disallowed_claims=PILOT_DISALLOWED_CLAIMS,
        validator_name="audit_koopman_v2_pilot",
        external_validation=True,
    )
    atomic_write_json(output, envelope)
    validate_phase8_evidence(output, required_qualification=PILOT_QUALIFICATION_LEVEL)
    return envelope


def build_external_main_dataset_envelope(
    output_path: str | Path,
    *,
    experiment_id: str,
    source_commit: str,
    role_protocol_path: str | Path,
    analysis_policy_path: str | Path,
    runtime_provenance: Mapping[str, Any],
    inventory_path: str | Path,
    split_path: str | Path,
    referenced_paths: Sequence[str | Path],
) -> dict[str, Any]:
    """Write the exact-eight main dataset envelope after all bytes exist."""
    from koopman.protocol_v2 import (
        validate_analysis_policy_v1,
        validate_main_role_protocol_v1,
    )

    output = Path(output_path).resolve()
    role_protocol = Path(role_protocol_path).resolve()
    analysis_policy = Path(analysis_policy_path).resolve()
    inventory = Path(inventory_path).resolve()
    split = Path(split_path).resolve()
    validate_main_role_protocol_v1(load_bounded_json(role_protocol))
    validate_analysis_policy_v1(load_bounded_json(analysis_policy))
    inventory_payload = load_bounded_json(inventory)
    split_payload = load_bounded_json(split)
    role_sha256 = file_sha256(role_protocol)
    runtime_sha256 = canonical_sha256(runtime_provenance)
    if inventory_payload.get("role_protocol_sha256") != role_sha256:
        _fail("protocol_hash_mismatch", "inventory")
    if inventory_payload.get("runtime_sha256") != runtime_sha256:
        _fail("runtime_hash_mismatch", "inventory")
    if inventory_payload.get("source_commit") != source_commit:
        _fail("source_commit_mismatch", "inventory")
    if split_payload.get("role_protocol_sha256") != role_sha256:
        _fail("protocol_hash_mismatch", "split")
    if split_payload.get("inventory_sha256") != inventory_payload.get("inventory_sha256"):
        _fail("inventory_hash_mismatch", "split")
    records = referenced_file_records(output.parent, referenced_paths)
    envelope = _build_envelope(
        experiment_id=experiment_id,
        artifact_origin_level="server_isaac_smoke",
        qualification_level=MAIN_DATASET_QUALIFICATION_LEVEL,
        source_commit=source_commit,
        protocol_sha256=role_sha256,
        runtime_provenance=runtime_provenance,
        inventory_sha256=file_sha256(inventory),
        decision_sha256=file_sha256(split),
        referenced_files=records,
        allowed_claims=MAIN_DATASET_ALLOWED_CLAIMS,
        disallowed_claims=MAIN_DATASET_DISALLOWED_CLAIMS,
        validator_name="build_phase8_main_dataset_envelope",
        external_validation=True,
    )
    atomic_write_json(output, envelope)
    validate_phase8_evidence(
        output, required_qualification=MAIN_DATASET_QUALIFICATION_LEVEL
    )
    return envelope


def _validate_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail("hash_invalid", field)
    return value


def validate_phase8_evidence(
    envelope_path: str | Path,
    *,
    required_qualification: str | None = None,
) -> dict[str, Any]:
    """Validate envelope semantics and independently re-read referenced bytes."""
    path = Path(envelope_path).resolve()
    payload = _exact_mapping(load_bounded_json(path), _ENVELOPE_FIELDS, "envelope")
    if payload["envelope_version"] != PHASE8_EVIDENCE_ENVELOPE_V1:
        _fail("envelope_version_mismatch")
    if not isinstance(payload["experiment_id"], str) or not payload["experiment_id"]:
        _fail("type_invalid", "experiment_id")
    origin = payload["artifact_origin_level"]
    qualification = payload["qualification_level"]
    if origin not in ARTIFACT_ORIGIN_LEVELS:
        _fail("artifact_origin_invalid")
    if qualification not in QUALIFICATION_LEVELS:
        _fail("qualification_level_invalid")
    if required_qualification is not None:
        if required_qualification not in QUALIFICATION_LEVELS:
            _fail("qualification_level_invalid", "required")
        if qualification != required_qualification:
            _fail("qualification_mismatch", f"required={required_qualification};actual={qualification}")
    validator = _exact_mapping(payload["validator"], _VALIDATOR_FIELDS, "validator")
    if validator["status"] != "pass" or not isinstance(validator["name"], str):
        _fail("validator_status_invalid")
    external = validator["external_validation"]
    if type(external) is not bool:
        _fail("type_invalid", "validator.external_validation")
    if origin == "local_contract" and (
        qualification != LOCAL_QUALIFICATION_LEVEL or external
    ):
        _fail("local_self_promotion")
    if qualification != LOCAL_QUALIFICATION_LEVEL and (
        origin != "server_isaac_smoke" or external is not True
    ):
        _fail("local_self_promotion")
    source_commit = payload["source_commit"]
    if not isinstance(source_commit, str) or not _COMMIT_RE.fullmatch(source_commit):
        _fail("source_commit_invalid")
    for field in (
        "protocol_sha256",
        "runtime_sha256",
        "inventory_sha256",
        "decision_sha256",
    ):
        _validate_hash(payload[field], field)
    runtime = payload["runtime_provenance"]
    if not isinstance(runtime, Mapping):
        _fail("type_invalid", "runtime_provenance")
    if canonical_sha256(runtime) != payload["runtime_sha256"]:
        _fail("runtime_hash_mismatch")
    for field in ("allowed_claims", "disallowed_claims"):
        values = payload[field]
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) or not item for item in values)
            or len(set(values)) != len(values)
        ):
            _fail("claim_set_invalid", field)
    if qualification == PILOT_QUALIFICATION_LEVEL:
        if tuple(payload["allowed_claims"]) != PILOT_ALLOWED_CLAIMS:
            _fail("claim_set_invalid", "allowed_claims")
        if tuple(payload["disallowed_claims"]) != PILOT_DISALLOWED_CLAIMS:
            _fail("claim_set_invalid", "disallowed_claims")
    if qualification == MAIN_DATASET_QUALIFICATION_LEVEL:
        if tuple(payload["allowed_claims"]) != MAIN_DATASET_ALLOWED_CLAIMS:
            _fail("claim_set_invalid", "allowed_claims")
        if tuple(payload["disallowed_claims"]) != MAIN_DATASET_DISALLOWED_CLAIMS:
            _fail("claim_set_invalid", "disallowed_claims")
    references = payload["referenced_files"]
    if (
        not isinstance(references, list)
        or not references
        or len(references) > MAX_REFERENCED_FILES
    ):
        _fail("reference_set_invalid")
    root = path.parent.resolve()
    expected_paths: set[str] = set()
    for index, value in enumerate(references):
        item = _exact_mapping(value, _REFERENCE_FIELDS, f"referenced_files[{index}]")
        relative = item["path"]
        if (
            not isinstance(relative, str)
            or not relative
            or "\\" in relative
            or Path(relative).is_absolute()
            or Path(relative).as_posix() != relative
        ):
            _fail("reference_path_invalid", str(relative))
        if relative in expected_paths:
            _fail("duplicate_reference", relative)
        expected_paths.add(relative)
        candidate = root / relative
        if candidate.is_symlink() or not candidate.exists() or not candidate.is_file():
            _fail("reference_missing", relative)
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            _fail("reference_path_invalid", relative)
        size = item["size_bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            _fail("type_invalid", f"referenced_files[{index}].size_bytes")
        expected_hash = _validate_hash(item["sha256"], f"referenced_files[{index}].sha256")
        if file_sha256(resolved) != expected_hash:
            _fail("artifact_hash_mismatch", relative)
        if resolved.stat().st_size != size:
            _fail("artifact_size_mismatch", relative)
    actual_paths = {
        candidate.relative_to(root).as_posix()
        for candidate in root.rglob("*")
        if candidate.is_file() or candidate.is_symlink()
    }
    actual_paths.discard(path.relative_to(root).as_posix())
    if actual_paths != expected_paths:
        missing = ",".join(sorted(expected_paths - actual_paths)) or "none"
        extra = ",".join(sorted(actual_paths - expected_paths)) or "none"
        _fail("reference_set_mismatch", f"missing={missing};extra={extra}")
    if qualification == PILOT_QUALIFICATION_LEVEL:
        policy_ref = next((item for item in references if item["path"] == "pilot_collection_policy.json"), None)
        inventory_ref = next((item for item in references if item["path"] == "pilot_inventory.json"), None)
        decision_ref = next((item for item in references if item["path"] == "pilot_health_decision.json"), None)
        if policy_ref is None or inventory_ref is None or decision_ref is None:
            _fail("reference_set_invalid", "pilot_core_files")
        if policy_ref["sha256"] != payload["protocol_sha256"]:
            _fail("protocol_hash_mismatch")
        if inventory_ref["sha256"] != payload["inventory_sha256"]:
            _fail("inventory_hash_mismatch")
        if decision_ref["sha256"] != payload["decision_sha256"]:
            _fail("decision_hash_mismatch")
    if qualification == MAIN_DATASET_QUALIFICATION_LEVEL:
        core_paths = {
            "main_role_assignment_protocol.json",
            "analysis_policy.json",
            "dataset_inventory.json",
            "loco_split_manifest.json",
            "runtime_provenance.json",
        }
        by_path = {item["path"]: item for item in references}
        if not core_paths.issubset(by_path):
            _fail("reference_set_invalid", "main_dataset_core_files")
        if by_path["main_role_assignment_protocol.json"]["sha256"] != payload["protocol_sha256"]:
            _fail("protocol_hash_mismatch")
        if by_path["dataset_inventory.json"]["sha256"] != payload["inventory_sha256"]:
            _fail("inventory_hash_mismatch")
        if by_path["loco_split_manifest.json"]["sha256"] != payload["decision_sha256"]:
            _fail("decision_hash_mismatch")
        inventory_payload = load_bounded_json(root / "dataset_inventory.json")
        split_payload = load_bounded_json(root / "loco_split_manifest.json")
        if inventory_payload.get("role_protocol_sha256") != payload["protocol_sha256"]:
            _fail("protocol_hash_mismatch", "inventory")
        if inventory_payload.get("runtime_sha256") != payload["runtime_sha256"]:
            _fail("runtime_hash_mismatch", "inventory")
        if inventory_payload.get("source_commit") != payload["source_commit"]:
            _fail("source_commit_mismatch", "inventory")
        if split_payload.get("role_protocol_sha256") != payload["protocol_sha256"]:
            _fail("protocol_hash_mismatch", "split")
        if split_payload.get("inventory_sha256") != inventory_payload.get("inventory_sha256"):
            _fail("inventory_hash_mismatch", "split")
    return {
        "validation_gate": "phase8_external_evidence_valid",
        "artifact_origin_level": origin,
        "qualification_level": qualification,
        "source_commit": source_commit,
        "referenced_file_count": len(references),
        "warnings": [],
    }

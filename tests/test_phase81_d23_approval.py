from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from koopman import d23_approval_v21
from koopman.d23_approval_v21 import (
    APPROVAL_RECORD_VERSION_V21,
    ATTESTATION_SCOPE_V21,
    EXPERIMENT_ID_V21,
    IDENTITY_ASSURANCE_V21,
    build_analysis_policy_proposal_v21,
    build_role_protocol_proposal_v21,
    load_and_validate_d23_approval_v21,
    require_canonical_d23_approval_v21,
    validate_d23_approval_v21,
)


def _canonical_bytes(payload: dict) -> bytes:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write(path: Path, payload: dict) -> None:
    path.write_bytes(_canonical_bytes(payload))


def _protocols(tmp_path: Path) -> tuple[Path, Path]:
    role = tmp_path / "role.json"
    policy = tmp_path / "policy.json"
    _write(role, build_role_protocol_proposal_v21(frozen_at="2026-08-30T06:00:00Z"))
    _write(policy, build_analysis_policy_proposal_v21())
    return role, policy


def _record(role: Path, policy: Path) -> dict:
    return {
        "analysis_policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
        "approval_record_version": APPROVAL_RECORD_VERSION_V21,
        "attestation_scope": ATTESTATION_SCOPE_V21,
        "decision": "approved",
        "experiment_id": EXPERIMENT_ID_V21,
        "identity_assurance": IDENTITY_ASSURANCE_V21,
        "role_protocol_sha256": hashlib.sha256(role.read_bytes()).hexdigest(),
    }


def _bind_canonical_paths(
    monkeypatch: pytest.MonkeyPatch,
    *,
    approval: Path,
    role: Path,
    policy: Path,
) -> None:
    monkeypatch.setattr(
        d23_approval_v21, "CANONICAL_APPROVAL_RECORD_PATH_V21", approval, raising=False
    )
    monkeypatch.setattr(
        d23_approval_v21, "CANONICAL_ROLE_PROTOCOL_PATH_V21", role, raising=False
    )
    monkeypatch.setattr(
        d23_approval_v21, "CANONICAL_ANALYSIS_POLICY_PATH_V21", policy, raising=False
    )


def test_valid_record_binds_exact_protocol_bytes_without_identity_claim(tmp_path: Path):
    role, policy = _protocols(tmp_path)
    record = _record(role, policy)
    before = (role.read_bytes(), policy.read_bytes())

    validated = validate_d23_approval_v21(
        record,
        role_protocol_path=role,
        analysis_policy_path=policy,
    )

    assert validated == record
    assert validated["attestation_scope"] == "protocol_hash_decision_binding_only"
    assert validated["identity_assurance"] == "none"
    assert (role.read_bytes(), policy.read_bytes()) == before


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("approval_record_version", "phase8-d23", "d23_approval_record_version_mismatch"),
        ("attestation_scope", "human_identity", "d23_attestation_scope_mismatch"),
        ("decision", "pending", "d23_approval_decision_invalid"),
        ("experiment_id", "phase8-main-identification-v2-proposal", "d23_approval_experiment_mismatch"),
        ("identity_assurance", "verified", "d23_identity_assurance_mismatch"),
        ("role_protocol_sha256", "0" * 64, "d23_role_protocol_hash_mismatch"),
        ("analysis_policy_sha256", "0" * 64, "d23_analysis_policy_hash_mismatch"),
    ],
)
def test_record_mutations_fail_closed(tmp_path: Path, field: str, value: str, reason: str):
    role, policy = _protocols(tmp_path)
    record = _record(role, policy)
    record[field] = value

    with pytest.raises(ValueError, match=reason):
        validate_d23_approval_v21(
            record,
            role_protocol_path=role,
            analysis_policy_path=policy,
        )


def test_extra_or_missing_record_fields_fail_closed(tmp_path: Path):
    role, policy = _protocols(tmp_path)
    extra = _record(role, policy)
    extra["approval_authority"] = "human_user"
    missing = deepcopy(extra)
    missing.pop("approval_authority")
    missing.pop("decision")

    with pytest.raises(ValueError, match="d23_approval_field_set_mismatch"):
        validate_d23_approval_v21(
            extra, role_protocol_path=role, analysis_policy_path=policy
        )
    with pytest.raises(ValueError, match="d23_approval_field_set_mismatch"):
        validate_d23_approval_v21(
            missing, role_protocol_path=role, analysis_policy_path=policy
        )


def test_protocol_byte_mutation_invalidates_existing_binding(tmp_path: Path):
    role, policy = _protocols(tmp_path)
    record = _record(role, policy)
    role.write_bytes(role.read_bytes() + b" ")

    with pytest.raises(ValueError, match="d23_role_protocol_hash_mismatch"):
        validate_d23_approval_v21(
            record, role_protocol_path=role, analysis_policy_path=policy
        )


def test_loader_rejects_duplicate_keys_and_missing_canonical_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    role, policy = _protocols(tmp_path)
    duplicate = tmp_path / "approval.json"
    duplicate.write_text(
        '{"decision":"approved","decision":"approved"}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="duplicate_json_key"):
        load_and_validate_d23_approval_v21(
            duplicate, role_protocol_path=role, analysis_policy_path=policy
        )

    missing = tmp_path / "missing.json"
    _bind_canonical_paths(
        monkeypatch,
        approval=missing,
        role=role,
        policy=policy,
    )
    with pytest.raises(ValueError, match="d23_approval_required"):
        require_canonical_d23_approval_v21(
            missing,
            role_protocol_path=role,
            analysis_policy_path=policy,
        )


@pytest.mark.parametrize(
    "path_kind",
    ["approval_record", "role_protocol", "analysis_policy"],
)
def test_formal_gate_rejects_noncanonical_paths_even_when_bytes_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_kind: str,
) -> None:
    canonical_root = tmp_path / "canonical"
    canonical_root.mkdir()
    canonical_role, canonical_policy = _protocols(canonical_root)
    canonical_approval = canonical_root / "approval.json"
    _write(canonical_approval, _record(canonical_role, canonical_policy))
    _bind_canonical_paths(
        monkeypatch,
        approval=canonical_approval,
        role=canonical_role,
        policy=canonical_policy,
    )

    alternate_root = tmp_path / "alternate"
    alternate_root.mkdir()
    alternate_role = alternate_root / "role.json"
    alternate_policy = alternate_root / "policy.json"
    alternate_approval = alternate_root / "approval.json"
    alternate_role.write_bytes(canonical_role.read_bytes())
    alternate_policy.write_bytes(canonical_policy.read_bytes())
    alternate_approval.write_bytes(canonical_approval.read_bytes())
    supplied = {
        "approval_record": canonical_approval,
        "role_protocol": canonical_role,
        "analysis_policy": canonical_policy,
    }
    supplied[path_kind] = {
        "approval_record": alternate_approval,
        "role_protocol": alternate_role,
        "analysis_policy": alternate_policy,
    }[path_kind]

    with pytest.raises(ValueError, match=f"d23_canonical_path_required:{path_kind}"):
        require_canonical_d23_approval_v21(
            supplied["approval_record"],
            role_protocol_path=supplied["role_protocol"],
            analysis_policy_path=supplied["analysis_policy"],
        )


def test_independent_loader_still_validates_noncanonical_paths(tmp_path: Path) -> None:
    role, policy = _protocols(tmp_path)
    approval = tmp_path / "approval.json"
    record = _record(role, policy)
    _write(approval, record)

    assert load_and_validate_d23_approval_v21(
        approval,
        role_protocol_path=role,
        analysis_policy_path=policy,
    ) == record

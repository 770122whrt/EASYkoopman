from __future__ import annotations

from pathlib import Path
import hashlib
import json

import pytest

from koopman import d23_approval_v21
from workflows import collect_koopman_v21_identification
from workflows import run_koopman_v21_loco
from workflows import select_koopman_v21


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROLE_PATH = PROJECT_ROOT / "protocols" / "phase8_1" / "main_role_assignment_protocol.json"
POLICY_PATH = PROJECT_ROOT / "protocols" / "phase8_1" / "analysis_policy.json"


def _canonical_bytes(payload: dict) -> bytes:
    return (
        json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


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


def test_collection_contract_binds_server_origin_zero_memory_and_zero_warmup() -> None:
    payload = json.loads(ROLE_PATH.read_text(encoding="utf-8"))
    assert collect_koopman_v21_identification._validate_collection_protocol_contract(
        payload, expected_evidence_level="server_isaac_smoke"
    ) == "server_isaac_smoke"

    mutations = (
        {"artifact_origin_level": "local_contract"},
        {"actuator_memory_initial_value_4": [1.0, 0.0, 0.0, 0.0]},
        {"unrecorded_warmup_control_intervals": 1},
    )
    for mutation in mutations:
        changed = dict(payload)
        changed.update(mutation)
        with pytest.raises(ValueError, match="collection_protocol_contract_mismatch"):
            collect_koopman_v21_identification._validate_collection_protocol_contract(
                changed, expected_evidence_level="server_isaac_smoke"
            )


@pytest.mark.parametrize(
    "module,runner_name",
    [
        (collect_koopman_v21_identification, "_run_authorized_collection"),
        (run_koopman_v21_loco, "_run_authorized_loco"),
        (select_koopman_v21, "_run_authorized_selection"),
    ],
)
def test_missing_d23_fails_before_resource_or_output_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module,
    runner_name: str,
):
    touched = []

    def forbidden_runner(**_kwargs):
        touched.append(True)
        raise AssertionError("resource access occurred before D-23 authorization")

    monkeypatch.setattr(module, runner_name, forbidden_runner)
    _bind_canonical_paths(
        monkeypatch,
        approval=tmp_path / "missing-approval.json",
        role=ROLE_PATH,
        policy=POLICY_PATH,
    )
    output = tmp_path / "must-not-exist"
    status = module.main(
        [
            "--approval-record",
            str(tmp_path / "missing-approval.json"),
            "--role-protocol",
            str(ROLE_PATH),
            "--analysis-policy",
            str(POLICY_PATH),
            "--output-root",
            str(output),
        ]
    )

    assert status != 0
    assert "d23_approval_required" in capsys.readouterr().err
    assert touched == []
    assert not output.exists()


@pytest.mark.parametrize(
    "module,required_source_tokens",
    [
        (collect_koopman_v21_identification, ("koopman_bridge_v21", "schema_v21")),
        (run_koopman_v21_loco, ("evaluation_v21", "d23_approval_v21")),
        (select_koopman_v21, ("selection_v21", "d23_approval_v21")),
    ],
)
def test_entrypoints_are_additive_and_reference_only_v21_paths(module, required_source_tokens):
    source = Path(module.__file__).read_text(encoding="utf-8")
    for token in required_source_tokens:
        assert token in source
    assert "protocols/phase8/" not in source.replace("\\", "/")


@pytest.mark.parametrize(
    "module,runner_name",
    [
        (collect_koopman_v21_identification, "_run_authorized_collection"),
        (run_koopman_v21_loco, "_run_authorized_loco"),
        (select_koopman_v21, "_run_authorized_selection"),
    ],
)
def test_exact_synthetic_approval_unlocks_only_the_injected_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module,
    runner_name: str,
):
    role = tmp_path / "role.json"
    policy = tmp_path / "policy.json"
    approval = tmp_path / "approval.json"
    role.write_bytes(ROLE_PATH.read_bytes())
    policy.write_bytes(POLICY_PATH.read_bytes())
    approval.write_bytes(
        _canonical_bytes(
            {
                "analysis_policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
                "approval_record_version": "phase8.1-d23-approval-v1",
                "attestation_scope": "protocol_hash_decision_binding_only",
                "decision": "approved",
                "experiment_id": "phase8.1-main-identification-v1",
                "identity_assurance": "none",
                "role_protocol_sha256": hashlib.sha256(role.read_bytes()).hexdigest(),
            }
        )
    )
    _bind_canonical_paths(
        monkeypatch,
        approval=approval,
        role=role,
        policy=policy,
    )
    observed = []

    def runner(**kwargs):
        observed.append(kwargs["approval"]["decision"])
        return 0

    monkeypatch.setattr(module, runner_name, runner)
    if module is collect_koopman_v21_identification:
        monkeypatch.setattr(
            module,
            "_repository_commit",
            lambda *, expected_source_commit=None: "1" * 40,
        )
    status = module.main(
        [
            "--approval-record",
            str(approval),
            "--role-protocol",
            str(role),
            "--analysis-policy",
            str(policy),
            "--output-root",
            str(tmp_path / "output"),
        ]
    )

    assert status == 0
    assert observed == ["approved"]
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    "module,runner_name",
    [
        (collect_koopman_v21_identification, "_run_authorized_collection"),
        (run_koopman_v21_loco, "_run_authorized_loco"),
        (select_koopman_v21, "_run_authorized_selection"),
    ],
)
def test_formal_entrypoints_reject_noncanonical_approval_before_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module,
    runner_name: str,
) -> None:
    role = tmp_path / "canonical-role.json"
    policy = tmp_path / "canonical-policy.json"
    approval = tmp_path / "canonical-approval.json"
    role.write_bytes(ROLE_PATH.read_bytes())
    policy.write_bytes(POLICY_PATH.read_bytes())
    approval.write_bytes(
        _canonical_bytes(
            {
                "analysis_policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
                "approval_record_version": "phase8.1-d23-approval-v1",
                "attestation_scope": "protocol_hash_decision_binding_only",
                "decision": "approved",
                "experiment_id": "phase8.1-main-identification-v1",
                "identity_assurance": "none",
                "role_protocol_sha256": hashlib.sha256(role.read_bytes()).hexdigest(),
            }
        )
    )
    alternate = tmp_path / "alternate-approval.json"
    alternate.write_bytes(approval.read_bytes())
    _bind_canonical_paths(
        monkeypatch,
        approval=approval,
        role=role,
        policy=policy,
    )
    touched: list[bool] = []

    def forbidden_runner(**_kwargs):
        touched.append(True)
        raise AssertionError("runner accessed after noncanonical approval")

    monkeypatch.setattr(module, runner_name, forbidden_runner)
    status = module.main(
        [
            "--approval-record",
            str(alternate),
            "--role-protocol",
            str(role),
            "--analysis-policy",
            str(policy),
            "--output-root",
            str(tmp_path / "output"),
        ]
    )

    assert status != 0
    assert "d23_canonical_path_required:approval_record" in capsys.readouterr().err
    assert touched == []

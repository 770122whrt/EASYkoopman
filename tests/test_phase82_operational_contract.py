from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROLE = PROJECT_ROOT / "protocols" / "phase8_1" / "main_role_assignment_protocol.json"
POLICY = PROJECT_ROOT / "protocols" / "phase8_1" / "analysis_policy.json"
APPROVAL = PROJECT_ROOT / "protocols" / "phase8_1" / "d23_approval.json"
SCRIPTS = PROJECT_ROOT / "scripts"


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _fake_dataset(root: Path, source_commit: str) -> None:
    role = json.loads(ROLE.read_text(encoding="utf-8"))
    for entry in role["entries"]:
        transition = root / entry["transition_path"]
        manifest = root / entry["manifest_path"]
        log = root / "logs" / f"{entry['episode_id']}.log"
        transition.parent.mkdir(parents=True, exist_ok=True)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        log.parent.mkdir(parents=True, exist_ok=True)
        transition.write_bytes(f"{entry['episode_id']}\n".encode())
        transition_sha = hashlib.sha256(transition.read_bytes()).hexdigest()
        manifest.write_bytes(
            _canonical(
                {
                    "episode_invariants": {
                        "configuration": entry["configuration"],
                        "episode_id": entry["episode_id"],
                        "source_commit": source_commit,
                    },
                    "record_count": 512,
                    "transition_sha256": transition_sha,
                }
            )
        )
        log.write_text(
            f"episode_id={entry['episode_id']}\n"
            f"configuration={entry['configuration']}\n"
            f"record_count=512\nsemantic_status=pass\n",
            encoding="utf-8",
        )


def _stub_validator(jsonl: Path, manifest: Path) -> dict[str, object]:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    invariants = payload["episode_invariants"]
    return {
        "configuration": invariants["configuration"],
        "episode_id": invariants["episode_id"],
        "evidence_level": "server_isaac_smoke",
        "record_count": 512,
        "transition_sha256": hashlib.sha256(jsonl.read_bytes()).hexdigest(),
        "validation_gate": "schema_v21_episode_valid",
        "warnings": [],
    }


def test_canonical_d23_record_binds_the_approved_protocol_hashes() -> None:
    from koopman.d23_approval_v21 import require_canonical_d23_approval_v21

    record = require_canonical_d23_approval_v21(
        APPROVAL, role_protocol_path=ROLE, analysis_policy_path=POLICY
    )
    assert record["decision"] == "approved"
    assert record["role_protocol_sha256"] == hashlib.sha256(ROLE.read_bytes()).hexdigest()
    assert record["analysis_policy_sha256"] == hashlib.sha256(POLICY.read_bytes()).hexdigest()


def test_dataset_index_builds_and_revalidates_exact_protocol_set(tmp_path: Path) -> None:
    from workflows.build_phase82_dataset_index import (
        build_phase82_dataset_index,
        validate_phase82_dataset_index,
    )

    source_commit = "a" * 40
    dataset = tmp_path / "dataset"
    _fake_dataset(dataset, source_commit)
    inventory = dataset / "dataset_inventory.json"
    split = dataset / "loco_split_manifest.json"
    result = build_phase82_dataset_index(
        dataset_root=dataset,
        role_protocol_path=ROLE,
        inventory_path=inventory,
        split_path=split,
        expected_source_commit=source_commit,
        artifact_validator=_stub_validator,
    )
    assert result == {"episode_count": 96, "validation_gate": "phase82_dataset_index_valid"}
    assert inventory.is_file() and split.is_file()
    assert validate_phase82_dataset_index(
        dataset_root=dataset,
        role_protocol_path=ROLE,
        inventory_path=inventory,
        split_path=split,
        expected_source_commit=source_commit,
        artifact_validator=_stub_validator,
    ) == result

    (dataset / "episodes" / "unexpected.jsonl").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="dataset_file_set_mismatch"):
        validate_phase82_dataset_index(
            dataset_root=dataset,
            role_protocol_path=ROLE,
            inventory_path=inventory,
            split_path=split,
            expected_source_commit=source_commit,
            artifact_validator=_stub_validator,
        )


def test_dataset_index_fails_closed_on_source_or_semantic_drift(tmp_path: Path) -> None:
    from workflows.build_phase82_dataset_index import build_phase82_dataset_index

    dataset = tmp_path / "dataset"
    _fake_dataset(dataset, "b" * 40)
    role = json.loads(ROLE.read_text(encoding="utf-8"))
    first = role["entries"][0]
    (dataset / "logs" / f"{first['episode_id']}.log").write_text(
        "semantic_status=fail\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="success_log_invalid"):
        build_phase82_dataset_index(
            dataset_root=dataset,
            role_protocol_path=ROLE,
            inventory_path=dataset / "dataset_inventory.json",
            split_path=dataset / "loco_split_manifest.json",
            expected_source_commit="b" * 40,
            artifact_validator=_stub_validator,
        )


@pytest.mark.parametrize(
    ("name", "required"),
    [
        ("phase8_2_local_preflight.ps1", ("validate_phase81_d23_approval.py", "worktree_clean", "phase8_2_operational_contract")),
        ("phase8_2_prepare_bundle.ps1", ("phase8_2_local_preflight.ps1", "git bundle verify", "git clone", "EasyUUV-phase8-2-v2.bundle")),
        ("phase8_2_server_bootstrap.sh", ("/root/EASYkoopman-phase8-2-v2", "/root/EASYkoopman-phase8-2-results-v2", "bundle verify", "git clone")),
        ("phase8_2_server_collect.sh", ("collect_koopman_v21_identification.py", "build_phase82_dataset_index.py", "runner_failure_blocks_inventory", "exact_96_set_failed")),
        ("phase8_2_pullback.ps1", ("validate_phase82_dataset_index.py", ".pytest-tmp/phase8-2-pullback-", "Move-Item", "source/results/koopman_phase8_2/dataset")),
        ("phase8_2_formal_local.ps1", ("run_koopman_v21_loco.py", "select_koopman_v21.py", "source/results/koopman_phase8_2/evaluation", "source/results/koopman_phase8_2/selection")),
        ("phase8_2_closeout_local.ps1", ("close_phase82.py", "source/results/koopman_phase8_2/closeout", "worktree_dirty", "post_collection_source_drift")),
    ],
)
def test_operational_scripts_freeze_versioned_paths_and_gates(
    name: str, required: tuple[str, ...]
) -> None:
    source = (SCRIPTS / name).read_text(encoding="utf-8")
    for token in required:
        assert token in source


def test_local_preflight_and_bundle_do_not_ssh_or_open_formal_test() -> None:
    for name in ("phase8_2_local_preflight.ps1", "phase8_2_prepare_bundle.ps1"):
        source = (SCRIPTS / name).read_text(encoding="utf-8").lower()
        assert "ssh " not in source
        assert "scp " not in source
        assert "run_koopman_v21_loco.py" not in source
        assert "select_koopman_v21.py" not in source


def test_local_preflight_git_helper_treats_stderr_warning_by_exit_code() -> None:
    source = (SCRIPTS / "phase8_2_local_preflight.ps1").read_text(encoding="utf-8")
    assert "[IO.Path]::GetTempFileName()" in source
    assert '1> $stdout 2> $stderr' in source
    assert '$nativeExitCode = $LASTEXITCODE' in source
    assert '$nativeExitCode -ne 0' in source


def test_server_bootstrap_does_not_reassign_its_readonly_result_variable() -> None:
    source = (SCRIPTS / "phase8_2_server_bootstrap.sh").read_text(encoding="utf-8")
    assert 'readonly SERVER_RESULT_ROOT="/root/EASYkoopman-phase8-2-results-v2"' in source
    assert 'RESULT_ROOT="$SERVER_RESULT_ROOT" bash' in source
    assert "readonly RESULT_ROOT=" not in source


def test_formal_runner_orders_evaluation_before_selection() -> None:
    source = (SCRIPTS / "phase8_2_formal_local.ps1").read_text(encoding="utf-8")
    assert source.index("run_koopman_v21_loco.py") < source.index("select_koopman_v21.py")


def test_closeout_validator_accepts_only_bound_terminal_artifacts(tmp_path: Path) -> None:
    from workflows.close_phase82 import close_phase82

    source_commit = "c" * 40
    dataset = tmp_path / "dataset"
    _fake_dataset(dataset, source_commit)
    from workflows.build_phase82_dataset_index import build_phase82_dataset_index

    inventory = dataset / "dataset_inventory.json"
    split = dataset / "loco_split_manifest.json"
    build_phase82_dataset_index(
        dataset_root=dataset,
        role_protocol_path=ROLE,
        inventory_path=inventory,
        split_path=split,
        expected_source_commit=source_commit,
        artifact_validator=_stub_validator,
    )
    role_sha = hashlib.sha256(ROLE.read_bytes()).hexdigest()
    policy_sha = hashlib.sha256(POLICY.read_bytes()).hexdigest()
    inventory_payload = json.loads(inventory.read_text(encoding="utf-8"))
    evaluation = tmp_path / "evaluation"
    evaluation.mkdir()
    summary = {
        "analysis_policy_sha256": policy_sha,
        "evaluation_version": "phase8.1-formal-loco-evaluation-v1",
        "experiment_id": "phase8.1-main-identification-v1",
        "folds": [
            {"heldout_configuration": value, "state": "TEST_OPENED"}
            for value in (
                "base", "long_body", "heavy_moderate", "asymmetric",
                "uuv6", "uuv6_angled", "uuv4", "uuv4_angled",
            )
        ],
        "inventory_sha256": inventory_payload["inventory_sha256"],
        "role_protocol_sha256": role_sha,
        "source_commit": source_commit,
        "split_sha256": hashlib.sha256(split.read_bytes()).hexdigest(),
    }
    summary_path = evaluation / "evaluation_summary.json"
    summary_path.write_bytes(_canonical(summary))
    envelope = {
        "analysis_policy_sha256": policy_sha,
        "envelope_version": "phase8.1-formal-loco-evaluation-envelope-v1",
        "evaluation_summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "experiment_id": "phase8.1-main-identification-v1",
        "fold_count": 8,
        "inventory_sha256": inventory_payload["inventory_sha256"],
        "role_protocol_sha256": role_sha,
        "source_commit": source_commit,
        "status": "complete",
    }
    (evaluation / "evaluation_envelope.json").write_bytes(_canonical(envelope))
    selection = tmp_path / "selection"
    selection.mkdir()
    result = {
        "outer_decision": {"status": "NO_SELECTION"},
        "reason_code": "outer_family_gate_no_selection",
        "selected_candidate_id": None,
        "selected_family": None,
        "selected_model_path": None,
        "status": "NO_SELECTION",
        "zero_test_read_audit": True,
    }
    result_path = selection / "selection_result.json"
    result_path.write_bytes(_canonical(result))
    selection_envelope = {
        "analysis_policy_sha256": policy_sha,
        "envelope_version": "phase8.1-formal-selection-envelope-v1",
        "evaluation_envelope_sha256": hashlib.sha256(
            (evaluation / "evaluation_envelope.json").read_bytes()
        ).hexdigest(),
        "experiment_id": "phase8.1-main-identification-v1",
        "inventory_sha256": inventory_payload["inventory_sha256"],
        "role_protocol_sha256": role_sha,
        "selection_result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "source_commit": source_commit,
        "status": "NO_SELECTION",
    }
    (selection / "selection_envelope.json").write_bytes(_canonical(selection_envelope))
    output = tmp_path / "closeout"
    closed = close_phase82(
        approval_record=APPROVAL,
        role_protocol=ROLE,
        analysis_policy=POLICY,
        dataset_root=dataset,
        inventory=inventory,
        split=split,
        evaluation_root=evaluation,
        selection_root=selection,
        source_commit=source_commit,
        output_root=output,
        dataset_validator=lambda **_: {
            "episode_count": 96,
            "validation_gate": "phase82_dataset_index_valid",
        },
    )
    assert closed["terminal_decision"] == "NO_SELECTION"
    assert closed["model_handoff"] is False
    assert (output / "closeout.json").is_file()

    selection_envelope["status"] = "SELECTION"
    (selection / "selection_envelope.json").write_bytes(_canonical(selection_envelope))
    with pytest.raises(ValueError, match="selection_envelope_binding_mismatch"):
        close_phase82(
            approval_record=APPROVAL,
            role_protocol=ROLE,
            analysis_policy=POLICY,
            dataset_root=dataset,
            inventory=inventory,
            split=split,
            evaluation_root=evaluation,
            selection_root=selection,
            source_commit=source_commit,
            output_root=tmp_path / "rejected-closeout",
            dataset_validator=lambda **_: {
                "episode_count": 96,
                "validation_gate": "phase82_dataset_index_valid",
            },
        )

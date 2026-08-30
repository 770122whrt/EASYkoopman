"""Independently close a complete Phase 8.2 dataset/evaluation/selection chain."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.d23_approval_v21 import (
    EXPERIMENT_ID_V21,
    require_canonical_d23_approval_v21,
)
from koopman.evaluation_v21 import load_protocol_episode_registry_v21
from koopman.evidence_v2 import canonical_json_bytes
from workflows.build_phase82_dataset_index import validate_phase82_dataset_index


_COMMIT = re.compile(r"^[0-9a-f]{40}$")
DatasetValidator = Callable[..., Mapping[str, Any]]


def _fail(reason: str) -> None:
    raise ValueError(reason)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path, reason: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(reason) from exc
    if not isinstance(payload, dict):
        _fail(reason)
    return payload


def _validate_evaluation(
    *,
    evaluation_root: Path,
    role_sha: str,
    policy_sha: str,
    inventory_sha: str,
    source_commit: str,
) -> tuple[dict[str, Any], Path]:
    envelope_path = evaluation_root / "evaluation_envelope.json"
    summary_path = evaluation_root / "evaluation_summary.json"
    envelope = _load(envelope_path, "evaluation_envelope_invalid")
    summary = _load(summary_path, "evaluation_summary_invalid")
    if (
        envelope.get("envelope_version")
        != "phase8.1-formal-loco-evaluation-envelope-v1"
        or envelope.get("status") != "complete"
        or envelope.get("fold_count") != 8
        or envelope.get("experiment_id") != EXPERIMENT_ID_V21
        or envelope.get("role_protocol_sha256") != role_sha
        or envelope.get("analysis_policy_sha256") != policy_sha
        or envelope.get("inventory_sha256") != inventory_sha
        or envelope.get("source_commit") != source_commit
        or envelope.get("evaluation_summary_sha256") != _sha(summary_path)
        or summary.get("experiment_id") != EXPERIMENT_ID_V21
        or summary.get("role_protocol_sha256") != role_sha
        or summary.get("analysis_policy_sha256") != policy_sha
        or summary.get("inventory_sha256") != inventory_sha
        or summary.get("source_commit") != source_commit
    ):
        _fail("evaluation_envelope_binding_mismatch")
    folds = summary.get("folds")
    if not isinstance(folds, list) or len(folds) != 8:
        _fail("evaluation_fold_set_invalid")
    if tuple(fold.get("heldout_configuration") for fold in folds) != tuple(
        SUPPORTED_EMBODIMENTS
    ) or any(fold.get("state") != "TEST_OPENED" for fold in folds):
        _fail("evaluation_fold_set_invalid")
    return envelope, envelope_path


def _validate_selection(
    *,
    selection_root: Path,
    evaluation_envelope_path: Path,
    role_sha: str,
    policy_sha: str,
    inventory_sha: str,
    source_commit: str,
) -> tuple[str, dict[str, Any], Path]:
    envelope_path = selection_root / "selection_envelope.json"
    result_path = selection_root / "selection_result.json"
    envelope = _load(envelope_path, "selection_envelope_invalid")
    result = _load(result_path, "selection_result_invalid")
    terminal = result.get("status")
    if (
        envelope.get("envelope_version") != "phase8.1-formal-selection-envelope-v1"
        or terminal not in {"SELECTION", "NO_SELECTION"}
        or envelope.get("status") != terminal
        or envelope.get("experiment_id") != EXPERIMENT_ID_V21
        or envelope.get("role_protocol_sha256") != role_sha
        or envelope.get("analysis_policy_sha256") != policy_sha
        or envelope.get("inventory_sha256") != inventory_sha
        or envelope.get("source_commit") != source_commit
        or envelope.get("evaluation_envelope_sha256")
        != _sha(evaluation_envelope_path)
        or envelope.get("selection_result_sha256") != _sha(result_path)
        or not isinstance(result.get("outer_decision"), Mapping)
        or result["outer_decision"].get("status") != terminal
        or result.get("zero_test_read_audit") is not True
    ):
        _fail("selection_envelope_binding_mismatch")
    if terminal == "NO_SELECTION":
        if (
            result.get("selected_family") is not None
            or result.get("selected_candidate_id") is not None
            or result.get("selected_model_path") is not None
            or not result.get("reason_code")
        ):
            _fail("terminal_no_selection_path_invalid")
    else:
        if (
            result.get("selected_family") not in {"pooled", "conditional"}
            or not result.get("selected_candidate_id")
            or result.get("selected_model_path") != "selected_model/selected_model.bin"
            or result.get("reason_code") is not None
            or not (selection_root / "selected_model" / "selected_model.bin").is_file()
        ):
            _fail("terminal_selection_path_invalid")
    return str(terminal), envelope, envelope_path


def close_phase82(
    *,
    approval_record: str | Path,
    role_protocol: str | Path,
    analysis_policy: str | Path,
    dataset_root: str | Path,
    inventory: str | Path,
    split: str | Path,
    evaluation_root: str | Path,
    selection_root: str | Path,
    source_commit: str,
    output_root: str | Path,
    dataset_validator: DatasetValidator = validate_phase82_dataset_index,
) -> dict[str, Any]:
    if not _COMMIT.fullmatch(source_commit):
        _fail("source_commit_invalid")
    approval = require_canonical_d23_approval_v21(
        approval_record,
        role_protocol_path=role_protocol,
        analysis_policy_path=analysis_policy,
    )
    dataset_result = dict(
        dataset_validator(
            dataset_root=dataset_root,
            role_protocol_path=role_protocol,
            inventory_path=inventory,
            split_path=split,
            expected_source_commit=source_commit,
        )
    )
    if dataset_result != {
        "episode_count": 96,
        "validation_gate": "phase82_dataset_index_valid",
    }:
        _fail("dataset_closeout_validation_failed")
    registry = load_protocol_episode_registry_v21(
        role_protocol_path=role_protocol, inventory_path=inventory
    )
    policy_sha = _sha(Path(analysis_policy))
    if (
        approval["role_protocol_sha256"] != registry.role_protocol_sha256
        or approval["analysis_policy_sha256"] != policy_sha
    ):
        _fail("closeout_approval_binding_mismatch")
    _, evaluation_envelope_path = _validate_evaluation(
        evaluation_root=Path(evaluation_root),
        role_sha=registry.role_protocol_sha256,
        policy_sha=policy_sha,
        inventory_sha=registry.inventory_sha256,
        source_commit=source_commit,
    )
    terminal, _, selection_envelope_path = _validate_selection(
        selection_root=Path(selection_root),
        evaluation_envelope_path=evaluation_envelope_path,
        role_sha=registry.role_protocol_sha256,
        policy_sha=policy_sha,
        inventory_sha=registry.inventory_sha256,
        source_commit=source_commit,
    )
    result = {
        "allowed_claim": "fixed_exact_eight_catalog_new_episode_loco_prediction_evaluation",
        "analysis_policy_sha256": policy_sha,
        "closeout_version": "phase8.2-independent-closeout-v1",
        "dataset_inventory_sha256": registry.inventory_sha256,
        "evaluation_envelope_sha256": _sha(evaluation_envelope_path),
        "experiment_id": EXPERIMENT_ID_V21,
        "fold_count": 8,
        "model_handoff": terminal == "SELECTION",
        "role_protocol_sha256": registry.role_protocol_sha256,
        "selection_envelope_sha256": _sha(selection_envelope_path),
        "source_commit": source_commit,
        "status": "VERIFIED",
        "terminal_decision": terminal,
    }
    output = Path(output_root).resolve()
    if output.exists() or output.is_symlink():
        _fail("closeout_output_exists")
    staging = output.with_name(f".{output.name}.staging-{os.getpid()}")
    if staging.exists() or staging.is_symlink():
        _fail("closeout_output_exists")
    staging.mkdir(parents=True)
    try:
        (staging / "closeout.json").write_bytes(canonical_json_bytes(result))
        os.replace(staging, output)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return result


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-record", required=True, type=Path)
    parser.add_argument("--role-protocol", required=True, type=Path)
    parser.add_argument("--analysis-policy", required=True, type=Path)
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--split", required=True, type=Path)
    parser.add_argument("--evaluation-root", required=True, type=Path)
    parser.add_argument("--selection-root", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        result = close_phase82(
            approval_record=args.approval_record,
            role_protocol=args.role_protocol,
            analysis_policy=args.analysis_policy,
            dataset_root=args.dataset_root,
            inventory=args.inventory,
            split=args.split,
            evaluation_root=args.evaluation_root,
            selection_root=args.selection_root,
            source_commit=args.source_commit,
            output_root=args.output_root,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

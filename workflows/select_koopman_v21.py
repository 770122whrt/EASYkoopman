"""D-23-guarded Phase 8.1 selection/publication entrypoint."""

from __future__ import annotations

import argparse
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

from koopman.d23_approval_v21 import require_canonical_d23_approval_v21


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select/publish Phase 8.1 model family.")
    parser.add_argument("--approval-record", required=True, type=Path)
    parser.add_argument("--role-protocol", required=True, type=Path)
    parser.add_argument("--analysis-policy", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--evaluation-root", type=Path)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--source-commit")
    return parser


_COMMIT_RE = re.compile(r"[0-9a-f]{40}")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    from koopman.evidence_v2 import canonical_json_bytes

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _default_final_backend(
    args: argparse.Namespace, *, expected_evidence_level: str
) -> Any:
    from koopman.selection_v21 import DatasetFinalRefitBackendV21

    return DatasetFinalRefitBackendV21(
        dataset_root=args.dataset_root,
        analysis_policy_path=args.analysis_policy,
        expected_source_commit=args.source_commit,
        expected_evidence_level=expected_evidence_level,
    )


def _run_authorized_selection(**kwargs: Any) -> int:
    """Validate the evaluation envelope, select a family and publish atomically."""

    # Evaluation/test artifacts remain unreadable until main() accepts D-23.
    from koopman.d23_approval_v21 import EXPERIMENT_ID_V21
    from koopman.evaluation_v21 import load_protocol_episode_registry_v21
    from koopman.selection_v21 import (
        FinalRefitDataSourceV21,
        FinalRefitPublisherV21,
        fold_outer_evidence_from_dict_v21,
        select_outer_family_v21,
    )

    args = kwargs["args"]
    approval = kwargs["approval"]
    backend = kwargs.get("backend")
    if (
        args.evaluation_root is None
        or args.dataset_root is None
        or args.inventory is None
    ):
        raise ValueError("formal_selection_input_required")
    if not _COMMIT_RE.fullmatch(str(args.source_commit or "")):
        raise ValueError("source_commit_invalid")
    registry = load_protocol_episode_registry_v21(
        role_protocol_path=args.role_protocol,
        inventory_path=args.inventory,
    )
    policy_sha256 = _file_sha256(Path(args.analysis_policy))
    if (
        approval.get("decision") != "approved"
        or approval.get("experiment_id") != EXPERIMENT_ID_V21
        or approval.get("role_protocol_sha256") != registry.role_protocol_sha256
        or approval.get("analysis_policy_sha256") != policy_sha256
    ):
        raise ValueError("formal_selection_approval_binding_mismatch")

    evaluation_root = Path(args.evaluation_root).resolve()
    envelope_path = evaluation_root / "evaluation_envelope.json"
    summary_path = evaluation_root / "evaluation_summary.json"
    try:
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("evaluation_envelope_invalid") from exc
    if (
        not isinstance(envelope, dict)
        or envelope.get("envelope_version")
        != "phase8.1-formal-loco-evaluation-envelope-v1"
        or envelope.get("status") != "complete"
        or envelope.get("fold_count") != 8
        or envelope.get("evaluation_summary_sha256") != _file_sha256(summary_path)
        or envelope.get("experiment_id") != EXPERIMENT_ID_V21
        or envelope.get("role_protocol_sha256") != registry.role_protocol_sha256
        or envelope.get("analysis_policy_sha256") != policy_sha256
        or envelope.get("inventory_sha256") != registry.inventory_sha256
        or envelope.get("source_commit") != args.source_commit
        or summary.get("source_commit") != args.source_commit
    ):
        raise ValueError("evaluation_envelope_binding_mismatch")
    raw_folds = summary.get("folds")
    if not isinstance(raw_folds, list) or len(raw_folds) != 8:
        raise ValueError("evaluation_fold_set_invalid")
    folds = []
    for raw in raw_folds:
        if not isinstance(raw, dict) or raw.get("state") != "TEST_OPENED":
            raise ValueError("evaluation_fold_set_invalid")
        fold_payload = dict(raw)
        fold_payload.pop("state")
        folds.append(fold_outer_evidence_from_dict_v21(fold_payload))
    outer = select_outer_family_v21(tuple(folds))

    output = Path(args.output_root).resolve()
    if output.exists() or output.is_symlink():
        raise ValueError(f"output_root_exists:{output}")
    staging = output.with_name(f".{output.name}.staging-{os.getpid()}")
    if staging.exists() or staging.is_symlink():
        raise ValueError(f"output_root_exists:{staging}")
    staging.mkdir(parents=True)
    try:
        if outer.status == "NO_SELECTION":
            result = {
                "outer_decision": outer.to_dict(),
                "reason_code": "outer_family_gate_no_selection",
                "selected_candidate_id": None,
                "selected_family": None,
                "selected_model_path": None,
                "status": "NO_SELECTION",
                "zero_test_read_audit": True,
            }
        else:
            if backend is None:
                backend = _default_final_backend(
                    args, expected_evidence_level=registry.artifact_origin_level
                )
            selected_family = outer.selected_family
            assert selected_family is not None
            source = FinalRefitDataSourceV21(
                registered_episodes=registry.all_non_test(),
                role_protocol_sha256=registry.role_protocol_sha256,
                opener=backend.open_episode,
            )
            candidates = tuple(backend.candidates(selected_family))
            publisher = FinalRefitPublisherV21(
                data_source=source,
                candidates_by_family={selected_family: candidates},
                inner_selector=backend.inner_select,
                final_fitter=backend.final_fit,
                serializer=backend.serialize,
                loader=backend.load,
                model_identity=backend.model_identity,
                publication_root=staging / "selected_model",
            )
            publication = publisher.publish(selected_family)
            result = publication.to_dict() | {"outer_decision": outer.to_dict()}
            if publication.status == "SELECTION":
                result["selected_model_path"] = "selected_model/selected_model.bin"
        result_path = staging / "selection_result.json"
        _write_json(result_path, result)
        selection_envelope = {
            "analysis_policy_sha256": policy_sha256,
            "envelope_version": "phase8.1-formal-selection-envelope-v1",
            "evaluation_envelope_sha256": _file_sha256(envelope_path),
            "experiment_id": EXPERIMENT_ID_V21,
            "inventory_sha256": registry.inventory_sha256,
            "role_protocol_sha256": registry.role_protocol_sha256,
            "selection_result_sha256": _file_sha256(result_path),
            "source_commit": args.source_commit,
            "status": result["status"],
        }
        _write_json(staging / "selection_envelope.json", selection_envelope)
        os.replace(staging, output)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        approval = require_canonical_d23_approval_v21(
            args.approval_record,
            role_protocol_path=args.role_protocol,
            analysis_policy_path=args.analysis_policy,
        )
        return int(_run_authorized_selection(args=args, approval=approval))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

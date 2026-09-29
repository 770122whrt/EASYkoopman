"""Publish the frozen Phase 8 selection or no-selection terminal envelope."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.evidence_v2 import (
    PHASE8_EVIDENCE_ENVELOPE_V1,
    atomic_write_json,
    canonical_sha256,
    file_sha256,
    referenced_file_records,
    validate_phase8_evidence,
)
from koopman.selection_v2 import select_phase8_candidate


_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish the frozen Phase 8 selector result.")
    parser.add_argument("--evaluation-envelope", required=True, type=Path)
    parser.add_argument("--analysis-policy", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    return parser


def publish_terminal_result(
    *,
    evaluation_envelope: Path,
    analysis_policy: Path,
    source_commit: str,
    output_root: Path,
) -> Path:
    if not _COMMIT_RE.fullmatch(source_commit):
        raise ValueError("source_commit_invalid")
    output = output_root.resolve()
    if output.exists() or output.is_symlink():
        raise ValueError(f"output_root_exists:{output}")
    result = select_phase8_candidate(evaluation_envelope, analysis_policy)
    if result.status == "koopman_selection":
        raise ValueError("final_refit_required_before_selection_publication")
    staging = output.with_name(f".{output.name}.staging-{os.getpid()}")
    if staging.exists() or staging.is_symlink():
        raise ValueError(f"output_root_exists:{staging}")
    staging.mkdir(parents=True)
    result_path = staging / "selection_result.json"
    atomic_write_json(result_path, result.to_dict())
    runtime = {
        "evaluation_envelope_sha256": result.evaluation_envelope_sha256,
        "execution": "local_offline_frozen_selector",
        "selector_version": result.version,
    }
    envelope = {
        "envelope_version": PHASE8_EVIDENCE_ENVELOPE_V1,
        "experiment_id": "phase8-08-05-terminal-selection-v1",
        "artifact_origin_level": "server_isaac_smoke",
        "qualification_level": "no_selection",
        "source_commit": source_commit,
        "protocol_sha256": file_sha256(analysis_policy),
        "runtime_provenance": runtime,
        "runtime_sha256": canonical_sha256(runtime),
        "inventory_sha256": result.evaluation_envelope_sha256,
        "decision_sha256": file_sha256(result_path),
        "referenced_files": referenced_file_records(staging, (result_path,)),
        "allowed_claims": ["no_eligible_koopman_family_under_frozen_gate"],
        "disallowed_claims": [
            "selected_model_available",
            "closed_loop_control_effectiveness",
            "environment_transfer",
            "agentic_behavior",
            "hardware_validity",
        ],
        "validator": {
            "name": "select_koopman_v2",
            "external_validation": True,
            "status": "pass",
        },
    }
    atomic_write_json(staging / "selection_envelope.json", envelope)
    validate_phase8_evidence(
        staging / "selection_envelope.json", required_qualification="no_selection"
    )
    os.replace(staging, output)
    return output / "selection_envelope.json"


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        path = publish_terminal_result(
            evaluation_envelope=args.evaluation_envelope,
            analysis_policy=args.analysis_policy,
            source_commit=args.source_commit,
            output_root=args.output_root,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

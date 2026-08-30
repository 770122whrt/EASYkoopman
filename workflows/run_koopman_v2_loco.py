"""Execute the exact-eight freeze-before-test Phase 8 LOCO evaluation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.collection_v2 import DatasetInventoryV2
from koopman.evaluation_v2 import run_phase8_loco_evaluation_v2
from koopman.evidence_v2 import load_bounded_json
from koopman.protocol_v2 import load_analysis_policy_v1
from koopman.splits_v2 import LOCOSplitManifestV2


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the frozen exact-eight Phase 8 LOCO evaluation."
    )
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--dataset-envelope", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--split", required=True, type=Path)
    parser.add_argument("--role-protocol", required=True, type=Path)
    parser.add_argument("--analysis-policy", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--fold",
        default="all",
        help="Formal 08-05 accepts only 'all' (the exact eight folds).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    if args.fold != "all":
        print("ERROR: formal_evaluation_requires_exact_eight", file=sys.stderr)
        return 1
    try:
        inventory = DatasetInventoryV2.from_dict(load_bounded_json(args.inventory))
        split = LOCOSplitManifestV2.from_dict(load_bounded_json(args.split))
        role_protocol = load_bounded_json(args.role_protocol)
        analysis_policy = load_analysis_policy_v1(args.analysis_policy)
        envelope = run_phase8_loco_evaluation_v2(
            dataset_root=args.dataset_root,
            dataset_envelope_path=args.dataset_envelope,
            inventory_path=args.inventory,
            split_path=args.split,
            role_protocol_path=args.role_protocol,
            inventory=inventory,
            split=split,
            role_protocol=role_protocol,
            analysis_policy=analysis_policy,
            output_root=args.output_root,
            source_commit=args.source_commit,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(envelope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

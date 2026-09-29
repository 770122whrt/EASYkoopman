"""Build the external Phase 8 main-dataset envelope after exact collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.evidence_v2 import (
    build_external_main_dataset_envelope,
    load_bounded_json,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build exact Phase 8 main envelope.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--role-protocol", required=True, type=Path)
    parser.add_argument("--analysis-policy", required=True, type=Path)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--split", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        root = args.root.resolve()
        output = args.output.resolve()
        references = sorted(
            path for path in root.rglob("*") if path.is_file() and path.resolve() != output
        )
        envelope = build_external_main_dataset_envelope(
            output,
            experiment_id=args.experiment_id,
            source_commit=args.source_commit,
            role_protocol_path=args.role_protocol,
            analysis_policy_path=args.analysis_policy,
            runtime_provenance=load_bounded_json(args.runtime),
            inventory_path=args.inventory,
            split_path=args.split,
            referenced_paths=references,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "qualification_level": envelope["qualification_level"],
                "referenced_file_count": len(envelope["referenced_files"]),
                "source_commit": envelope["source_commit"],
            },
            allow_nan=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

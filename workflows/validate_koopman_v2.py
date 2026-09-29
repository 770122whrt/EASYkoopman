"""Deterministic CLI for a Koopman schema-v2 episode and manifest pair."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.schema_v2 import validate_episode_artifact_v2
from workflows.merge_koopman_v2_evidence import validate_aggregate_evidence


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one strict Koopman schema-v2 episode and manifest."
    )
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--aggregate",
        type=Path,
        help="Strictly validate exact-three server evidence and every referenced byte.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print deterministic JSON output."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        if args.aggregate is not None:
            if args.jsonl is not None or args.manifest is not None:
                raise ValueError("validator_mode_conflict")
            result = validate_aggregate_evidence(args.aggregate, require_server=True)
        else:
            if args.jsonl is None or args.manifest is None:
                raise ValueError("validator_input_missing")
            result = validate_episode_artifact_v2(args.jsonl, args.manifest)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, allow_nan=False, indent=2, sort_keys=True))
    else:
        print(f"validation_gate={result['validation_gate']}")
        print(f"evidence_level={result['evidence_level']}")
        if args.aggregate is not None:
            print(f"source_commit={result['source_commit']}")
            print(f"configuration_count={result['configuration_count']}")
        else:
            print(f"configuration={result['configuration']}")
            print(f"episode_id={result['episode_id']}")
            print(f"record_count={result['record_count']}")
            print(f"transition_sha256={result['transition_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one strict Koopman schema-v2 episode and manifest."
    )
    parser.add_argument("--jsonl", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--json", action="store_true", help="Print deterministic JSON output."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        result = validate_episode_artifact_v2(args.jsonl, args.manifest)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, allow_nan=False, indent=2, sort_keys=True))
    else:
        print(f"validation_gate={result['validation_gate']}")
        print(f"evidence_level={result['evidence_level']}")
        print(f"configuration={result['configuration']}")
        print(f"episode_id={result['episode_id']}")
        print(f"record_count={result['record_count']}")
        print(f"transition_sha256={result['transition_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

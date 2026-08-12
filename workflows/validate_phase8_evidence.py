"""Deterministic CLI for strict external Phase 8 evidence envelopes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.evidence_v2 import QUALIFICATION_LEVELS, validate_phase8_evidence


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate external Phase 8 evidence.")
    parser.add_argument("--envelope", required=True, type=Path)
    parser.add_argument("--qualification", choices=QUALIFICATION_LEVELS)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        result = validate_phase8_evidence(
            args.envelope, required_qualification=args.qualification
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, allow_nan=False, indent=2, sort_keys=True))
    else:
        for key in (
            "validation_gate",
            "artifact_origin_level",
            "qualification_level",
            "source_commit",
            "referenced_file_count",
        ):
            print(f"{key}={result[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


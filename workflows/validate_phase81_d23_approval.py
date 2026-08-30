"""Validate a Phase 8.1 protocol-hash decision-binding record."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.d23_approval_v21 import load_and_validate_d23_approval_v21


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a Phase 8.1 D-23 decision-binding record."
    )
    parser.add_argument("--approval-record", required=True, type=Path)
    parser.add_argument("--role-protocol", required=True, type=Path)
    parser.add_argument("--analysis-policy", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        load_and_validate_d23_approval_v21(
            args.approval_record,
            role_protocol_path=args.role_protocol,
            analysis_policy_path=args.analysis_policy,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("phase81_d23_approval_valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

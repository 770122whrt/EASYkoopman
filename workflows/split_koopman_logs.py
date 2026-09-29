from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.splits import create_explicit_split, write_split_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a log-level Koopman train/validation/test split manifest.")
    parser.add_argument("--train-log", action="append", required=True, type=Path, help="Training JSONL log path.")
    parser.add_argument(
        "--validation-log",
        action="append",
        required=True,
        type=Path,
        help="Validation JSONL log path.",
    )
    parser.add_argument("--test-log", action="append", required=True, type=Path, help="Held-out test JSONL log path.")
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output split manifest JSON path.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Optional split seed for reproducibility notes.")
    parser.add_argument("--notes", default="", help="Optional split notes.")
    args = parser.parse_args(argv)

    manifest = create_explicit_split(
        train_logs=args.train_log,
        validation_logs=args.validation_log,
        test_logs=args.test_log,
        seed=args.seed,
        notes=args.notes,
    )
    write_split_manifest(manifest, args.output)
    print(f"[INFO] wrote split manifest to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

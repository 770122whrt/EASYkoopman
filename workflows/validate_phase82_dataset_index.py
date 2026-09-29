"""Validate an existing Phase 8.2 dataset index."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from workflows.build_phase82_dataset_index import main as index_main


def main(argv: list[str] | None = None) -> int:
    return index_main(["validate", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(main())

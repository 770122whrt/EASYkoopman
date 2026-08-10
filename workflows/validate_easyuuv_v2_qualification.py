"""Command-line gate for strict EasyUUV v2 qualification artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from workflows.easyuuv_v2_qualification_artifact import validate_qualification_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an EasyUUV v2 qualification artifact.")
    parser.add_argument("path", type=Path, help="Qualification JSON artifact path.")
    parser.add_argument(
        "--catalog-only",
        action="store_true",
        help="Validate local catalog evidence without claiming an Isaac server pass.",
    )
    parser.add_argument("--json", action="store_true", help="Print deterministic JSON output.")
    args = parser.parse_args(argv)

    try:
        result = validate_qualification_file(args.path, catalog_only=args.catalog_only)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"qualification_gate={result['qualification_gate']}")
        print(f"evidence_level={result['evidence_level']}")
        print(f"configuration_count={result['configuration_count']}")
        print("passed_configurations=" + ",".join(result["passed_configurations"]))
        for warning in result["warnings"]:
            print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

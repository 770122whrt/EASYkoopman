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
    parser.add_argument(
        "--expected-source-commit-file",
        type=Path,
        help="Bind server evidence to the locally transferred tested-HEAD sidecar.",
    )
    parser.add_argument(
        "--expected-isaaclab-commit-file",
        type=Path,
        help="Bind runtime provenance to the pulled server IsaacLab commit record.",
    )
    parser.add_argument(
        "--expected-isaaclab-release-file",
        type=Path,
        help="Bind runtime provenance to the pulled IsaacLab release tag record.",
    )
    parser.add_argument(
        "--expected-isaaclab-release-commit-file",
        type=Path,
        help="Bind runtime provenance to the official IsaacLab release commit.",
    )
    parser.add_argument(
        "--expected-isaaclab-patch-sha256-file",
        type=Path,
        help="Bind runtime provenance to the unchanged server patch hash.",
    )
    parser.add_argument(
        "--expected-isaaclab-dirty-files-file",
        type=Path,
        help="Bind runtime provenance to the exact allowed server dirty files.",
    )
    args = parser.parse_args(argv)

    try:
        expected_source_commit = (
            args.expected_source_commit_file.read_text(encoding="utf-8").strip()
            if args.expected_source_commit_file
            else None
        )
        expected_isaaclab_commit = (
            args.expected_isaaclab_commit_file.read_text(encoding="utf-8").strip()
            if args.expected_isaaclab_commit_file
            else None
        )
        expected_isaaclab_release = (
            args.expected_isaaclab_release_file.read_text(encoding="utf-8").strip()
            if args.expected_isaaclab_release_file
            else None
        )
        expected_isaaclab_release_commit = (
            args.expected_isaaclab_release_commit_file.read_text(
                encoding="utf-8"
            ).strip()
            if args.expected_isaaclab_release_commit_file
            else None
        )
        expected_isaaclab_patch_sha256 = (
            args.expected_isaaclab_patch_sha256_file.read_text(
                encoding="utf-8"
            ).strip()
            if args.expected_isaaclab_patch_sha256_file
            else None
        )
        expected_isaaclab_dirty_files = (
            tuple(
                line.strip()
                for line in args.expected_isaaclab_dirty_files_file.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            )
            if args.expected_isaaclab_dirty_files_file
            else None
        )
        result = validate_qualification_file(
            args.path,
            catalog_only=args.catalog_only,
            expected_source_commit=expected_source_commit,
            expected_isaaclab_repo_commit=expected_isaaclab_commit,
            expected_isaaclab_release_tag=expected_isaaclab_release,
            expected_isaaclab_release_commit=expected_isaaclab_release_commit,
            expected_isaaclab_patch_sha256=expected_isaaclab_patch_sha256,
            expected_isaaclab_dirty_files=expected_isaaclab_dirty_files,
        )
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

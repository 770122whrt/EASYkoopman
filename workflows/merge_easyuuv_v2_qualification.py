"""Merge eight server-produced EasyUUV v2 qualification rows."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from workflows.easyuuv_v2_qualification_artifact import (
    load_qualification_payload,
    validate_qualification_payload,
)
from workflows.qualify_easyuuv_v2 import DEFAULT_RESULT_ROOT, resolve_output_path


_VERSION_FIELDS = ("actual_isaac_sim", "actual_isaac_lab")
_SHARED_METADATA_FIELDS = (
    "schema_version",
    "evidence_level",
    "expected_isaac_sim",
    "expected_isaac_lab",
    "task_id",
    "source_commit",
    "runtime_provenance",
)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(payload, stream, allow_nan=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _single_result(path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = load_qualification_payload(path)
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != 1:
        raise ValueError(f"single_result_required:{path}")
    row = results[0]
    if not isinstance(row, dict):
        raise ValueError(f"row_not_object:{path}")
    configuration = row.get("configuration")
    if not isinstance(configuration, str) or not configuration:
        raise ValueError(f"configuration_name_invalid:{path}")
    return payload, row


def merge_qualification_results(
    input_paths: Iterable[str | Path], output_path: str | Path
) -> dict[str, Any]:
    """Validate and atomically write the exact-eight merged server artifact."""
    pairs = [_single_result(path) for path in input_paths]
    if not pairs:
        raise ValueError("configuration_set_mismatch:missing=all;extra=none")

    names = [row["configuration"] for _, row in pairs]
    seen: set[str] = set()
    duplicates: set[str] = set()
    for name in names:
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    if duplicates:
        raise ValueError("duplicate_configuration:" + ",".join(sorted(duplicates)))

    expected = set(SUPPORTED_EMBODIMENTS)
    actual = set(names)
    if actual != expected:
        missing = ",".join(sorted(expected - actual)) or "none"
        extra = ",".join(sorted(actual - expected)) or "none"
        raise ValueError(
            f"configuration_set_mismatch:missing={missing};extra={extra}"
        )

    reference = pairs[0][0]
    for payload, _ in pairs[1:]:
        if any(payload.get(field) != reference.get(field) for field in _VERSION_FIELDS):
            raise ValueError("actual_version_disagreement")
        if any(
            payload.get(field) != reference.get(field)
            for field in _SHARED_METADATA_FIELDS
        ):
            raise ValueError("metadata_disagreement")

    merged = {
        field: reference.get(field)
        for field in (*_SHARED_METADATA_FIELDS, *_VERSION_FIELDS)
    }
    rows_by_name = {row["configuration"]: row for _, row in pairs}
    merged["results"] = [rows_by_name[name] for name in SUPPORTED_EMBODIMENTS]

    # This is the mandatory server-mode validation.  No file is replaced first.
    validate_qualification_payload(merged)
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(output, merged)
    return merged


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge exact-eight EasyUUV v2 qualification rows."
    )
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--result-root", type=Path, default=DEFAULT_RESULT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        output = resolve_output_path(args.output, args.result_root)
        payload = merge_qualification_results(args.input, output)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"qualification_artifact={output}")
    print(f"configuration_count={len(payload['results'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Strict SHA-256 inventory validation for pulled server evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Sequence


_INVENTORY_LINE = re.compile(r"^([0-9a-f]{64})  ([^\r\n]+)$")


class EvidenceInventoryError(ValueError):
    """Raised when an evidence inventory cannot be trusted."""


def _fail(reason: str) -> None:
    raise EvidenceInventoryError(reason)


def _confined_file(root: Path, relative: PurePosixPath) -> Path:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in ("", ".", "..") for part in relative.parts)
        or "\\" in relative.as_posix()
    ):
        _fail(f"inventory_path_invalid:{relative.as_posix()}")
    candidate = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _fail(f"inventory_path_invalid:{relative.as_posix()}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, OSError, ValueError):
        _fail(f"inventory_path_invalid:{relative.as_posix()}")
    if not resolved.is_file():
        _fail(f"inventory_path_invalid:{relative.as_posix()}")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_sha256_inventory(root: Path, inventory: Path) -> dict[str, object]:
    """Validate a relative, exact inventory that intentionally excludes itself."""

    try:
        resolved_root = root.resolve(strict=True)
        resolved_inventory = inventory.resolve(strict=True)
        inventory_relative = resolved_inventory.relative_to(resolved_root).as_posix()
    except (FileNotFoundError, OSError, ValueError):
        _fail("inventory_path_invalid:all_files.sha256")
    if not resolved_root.is_dir() or not resolved_inventory.is_file():
        _fail("inventory_path_invalid:all_files.sha256")

    entries: dict[str, str] = {}
    try:
        lines = resolved_inventory.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        _fail("inventory_read_failed")
    if not lines:
        _fail("inventory_empty")

    for line_number, line in enumerate(lines, start=1):
        match = _INVENTORY_LINE.fullmatch(line)
        if match is None:
            _fail(f"inventory_line_invalid:{line_number}")
        expected_hash, serialized_path = match.groups()
        if not serialized_path.startswith("./"):
            _fail(f"inventory_path_invalid:{serialized_path}")
        relative = PurePosixPath(serialized_path[2:])
        normalized = relative.as_posix()
        if serialized_path != f"./{normalized}":
            _fail(f"inventory_path_invalid:{serialized_path}")
        if normalized == inventory_relative:
            _fail("inventory_self_reference")
        if normalized in entries:
            _fail(f"inventory_duplicate_path:{normalized}")
        entries[normalized] = expected_hash

    actual_files: set[str] = set()
    for candidate in resolved_root.rglob("*"):
        relative = candidate.relative_to(resolved_root)
        if candidate.is_symlink():
            _fail(f"inventory_path_invalid:{relative.as_posix()}")
        if candidate.is_file() and candidate.resolve() != resolved_inventory:
            actual_files.add(relative.as_posix())
    listed_files = set(entries)
    if listed_files != actual_files:
        missing = sorted(actual_files - listed_files)
        extra = sorted(listed_files - actual_files)
        _fail(
            "inventory_file_set_mismatch:"
            f"unlisted={','.join(missing)};missing={','.join(extra)}"
        )

    for relative, expected_hash in entries.items():
        actual_hash = _sha256(_confined_file(resolved_root, PurePosixPath(relative)))
        if actual_hash != expected_hash:
            _fail(f"inventory_sha256_mismatch:{relative}")

    return {
        "file_count": len(entries),
        "validation_gate": "sha256_inventory_valid",
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        result = validate_sha256_inventory(args.root, args.inventory)
    except EvidenceInventoryError as error:
        print(f"inventory_validation_failed:{error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        print("validation_gate=sha256_inventory_valid")
        print(f"file_count={result['file_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

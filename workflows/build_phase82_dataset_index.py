"""Build or validate the Phase 8.2 protocol-bound v2.1 dataset index.

This workflow performs artifact/schema validation only.  It does not construct
model views, rank candidates, or authorize held-out test access.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.d23_approval_v21 import (
    EXPERIMENT_ID_V21,
    validate_role_protocol_proposal_v21,
)
from koopman.evaluation_v21 import (
    ProtocolEpisodeBindingV21,
    ProtocolEpisodeRegistryV21,
    load_protocol_episode_registry_v21,
)
from koopman.evidence_v2 import canonical_json_bytes
from koopman.schema_v21 import validate_episode_artifact_v21


_COMMIT = re.compile(r"^[0-9a-f]{40}$")
ArtifactValidator = Callable[[Path, Path], Mapping[str, Any]]


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _load_role(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("role_protocol_invalid") from exc
    validate_role_protocol_proposal_v21(value)
    return value, hashlib.sha256(raw).hexdigest()


def _confined(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        _fail("dataset_path_invalid", relative)
    target = root / rel
    if target.is_symlink():
        _fail("dataset_symlink_refused", relative)
    return target


def _require_regular(path: Path, *, reason: str) -> None:
    if not path.is_file() or path.is_symlink():
        _fail(reason, path.as_posix())


def _expected_files(role: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for entry in role["entries"]:
        result.add(str(entry["transition_path"]).replace("\\", "/"))
        result.add(str(entry["manifest_path"]).replace("\\", "/"))
        result.add(f"logs/{entry['episode_id']}.log")
    return result


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("dataset_index_path_outside_root") from exc


def _validate_exact_files(root: Path, expected: set[str]) -> None:
    if not root.is_dir() or root.is_symlink():
        _fail("dataset_root_invalid")
    actual: set[str] = set()
    for item in root.rglob("*"):
        if item.is_symlink():
            _fail("dataset_symlink_refused", _relative(root, item))
        if item.is_file():
            relative = _relative(root, item)
            if relative.endswith(".part"):
                _fail("partial_artifact_refused", relative)
            actual.add(relative)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _fail("dataset_file_set_mismatch", f"missing={missing[:1]};extra={extra[:1]}")


def _validate_success_log(path: Path, entry: Mapping[str, Any]) -> None:
    _require_regular(path, reason="success_log_missing")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        parsed = dict(line.split("=", 1) for line in lines if "=" in line)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("success_log_invalid") from exc
    expected = {
        "configuration": str(entry["configuration"]),
        "episode_id": str(entry["episode_id"]),
        "record_count": str(entry["transition_count"]),
        "semantic_status": "pass",
    }
    if any(parsed.get(key) != value for key, value in expected.items()):
        _fail("success_log_invalid", str(entry["episode_id"]))


def _validate_manifest_source(path: Path, expected_source_commit: str) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        actual = payload["episode_invariants"]["source_commit"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("manifest_source_commit_invalid") from exc
    if actual != expected_source_commit:
        _fail("manifest_source_commit_mismatch")


def _validated_bindings(
    *,
    dataset_root: Path,
    role: Mapping[str, Any],
    role_sha256: str,
    expected_source_commit: str,
    artifact_validator: ArtifactValidator,
) -> tuple[ProtocolEpisodeBindingV21, ...]:
    bindings: list[ProtocolEpisodeBindingV21] = []
    expected_origin = str(role["artifact_origin_level"])
    for entry in role["entries"]:
        transition = _confined(dataset_root, str(entry["transition_path"]))
        manifest = _confined(dataset_root, str(entry["manifest_path"]))
        log = _confined(dataset_root, f"logs/{entry['episode_id']}.log")
        _require_regular(transition, reason="transition_missing")
        _require_regular(manifest, reason="manifest_missing")
        _validate_success_log(log, entry)
        _validate_manifest_source(manifest, expected_source_commit)
        summary = dict(artifact_validator(transition, manifest))
        transition_sha = hashlib.sha256(transition.read_bytes()).hexdigest()
        expected_summary = {
            "configuration": entry["configuration"],
            "episode_id": entry["episode_id"],
            "evidence_level": expected_origin,
            "record_count": entry["transition_count"],
            "transition_sha256": transition_sha,
            "validation_gate": "schema_v21_episode_valid",
            "warnings": [],
        }
        if any(summary.get(key) != value for key, value in expected_summary.items()):
            _fail("episode_validation_mismatch", str(entry["episode_id"]))
        bindings.append(
            ProtocolEpisodeBindingV21(
                episode_id=str(entry["episode_id"]),
                configuration=str(entry["configuration"]),
                role=str(entry["role"]),
                family_repetition=(
                    f"{entry['excitation_family']}-r{entry['repetition']}"
                ),
                transition_sha256=transition_sha,
                transition_path=str(entry["transition_path"]),
                manifest_path=str(entry["manifest_path"]),
                transition_count=int(entry["transition_count"]),
                role_protocol_sha256=role_sha256,
            )
        )
    return tuple(bindings)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        _fail("dataset_index_exists", path.as_posix())
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".part", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(canonical_json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_phase82_dataset_index(
    *,
    dataset_root: str | Path,
    role_protocol_path: str | Path,
    inventory_path: str | Path,
    split_path: str | Path,
    expected_source_commit: str,
    artifact_validator: ArtifactValidator = validate_episode_artifact_v21,
) -> dict[str, Any]:
    """Validate exact collected artifacts, then atomically build inventory/split."""

    if not _COMMIT.fullmatch(expected_source_commit):
        _fail("source_commit_invalid")
    root = Path(dataset_root).resolve()
    inventory = Path(inventory_path).resolve()
    split = Path(split_path).resolve()
    role, role_sha = _load_role(Path(role_protocol_path))
    expected = _expected_files(role)
    _validate_exact_files(root, expected)
    if _relative(root, inventory) in expected or _relative(root, split) in expected:
        _fail("dataset_index_path_collision")
    bindings = _validated_bindings(
        dataset_root=root,
        role=role,
        role_sha256=role_sha,
        expected_source_commit=expected_source_commit,
        artifact_validator=artifact_validator,
    )
    registry = ProtocolEpisodeRegistryV21(
        experiment_id=EXPERIMENT_ID_V21,
        role_protocol_sha256=role_sha,
        episodes=bindings,
        artifact_origin_level=str(role["artifact_origin_level"]),
    )
    _atomic_json(inventory, registry.to_dict())
    try:
        _atomic_json(split, registry.expected_split_payload())
    except BaseException:
        inventory.unlink(missing_ok=True)
        raise
    return validate_phase82_dataset_index(
        dataset_root=root,
        role_protocol_path=role_protocol_path,
        inventory_path=inventory,
        split_path=split,
        expected_source_commit=expected_source_commit,
        artifact_validator=artifact_validator,
    )


def validate_phase82_dataset_index(
    *,
    dataset_root: str | Path,
    role_protocol_path: str | Path,
    inventory_path: str | Path,
    split_path: str | Path,
    expected_source_commit: str,
    artifact_validator: ArtifactValidator = validate_episode_artifact_v21,
) -> dict[str, Any]:
    """Revalidate an existing Phase 8.2 dataset without model/test semantics."""

    if not _COMMIT.fullmatch(expected_source_commit):
        _fail("source_commit_invalid")
    root = Path(dataset_root).resolve()
    inventory = Path(inventory_path).resolve()
    split = Path(split_path).resolve()
    role, role_sha = _load_role(Path(role_protocol_path))
    expected = _expected_files(role) | {_relative(root, inventory), _relative(root, split)}
    _validate_exact_files(root, expected)
    _validated_bindings(
        dataset_root=root,
        role=role,
        role_sha256=role_sha,
        expected_source_commit=expected_source_commit,
        artifact_validator=artifact_validator,
    )
    registry = load_protocol_episode_registry_v21(
        role_protocol_path=role_protocol_path, inventory_path=inventory
    )
    registry.validate_split_path(split)
    return {"episode_count": len(registry.episodes), "validation_gate": "phase82_dataset_index_valid"}


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "validate"))
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--role-protocol", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--split", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    operation = (
        build_phase82_dataset_index
        if args.mode == "build"
        else validate_phase82_dataset_index
    )
    try:
        result = operation(
            dataset_root=args.dataset_root,
            role_protocol_path=args.role_protocol,
            inventory_path=args.inventory,
            split_path=args.split,
            expected_source_commit=args.source_commit,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

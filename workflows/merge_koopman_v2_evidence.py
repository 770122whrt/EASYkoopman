"""Merge and independently validate exact-three Koopman-v2 evidence."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
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

from koopman.schema_v2 import (
    LOCAL_EVIDENCE_LEVEL,
    SERVER_EVIDENCE_LEVEL,
    validate_episode_artifact_v2,
)
from workflows.easyuuv_v2_qualification_artifact import (
    EXPECTED_ISAAC_LAB_DIRTY_FILES,
    EXPECTED_ISAAC_LAB_PATCH_SHA256,
    EXPECTED_ISAAC_LAB_RELEASE_COMMIT,
    EXPECTED_ISAAC_LAB_RELEASE_TAG,
    EXPECTED_ISAAC_LAB_REPO_COMMIT,
)


AGGREGATE_SCHEMA_VERSION = "easyuuv-koopman-evidence-aggregate-v1"
EXPECTED_CONFIGURATIONS = ("base", "uuv6", "uuv4")
MINIMUM_SERVER_TRANSITIONS = 8
MAX_AGGREGATE_BYTES = 1_000_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_AGGREGATE_FIELDS = {
    "aggregate_version",
    "evidence_level",
    "source_commit",
    "actual_isaac_sim",
    "actual_isaac_lab",
    "runtime_provenance",
    "configurations",
    "episodes",
}
_EPISODE_FIELDS = {
    "configuration",
    "episode_file",
    "manifest_file",
    "log_file",
    "episode_sha256",
    "manifest_sha256",
    "log_sha256",
    "record_count",
    "episode_id",
}
_SERVER_RUNTIME_FIELDS = {
    "artifact_origin",
    "actual_isaac_sim",
    "actual_isaac_lab",
    "isaac_lab_release_tag",
    "isaac_lab_release_commit",
    "isaac_lab_repo_commit",
    "isaac_lab_repo_parent_commit",
    "isaac_lab_repo_patch_sha256",
    "isaac_lab_repo_dirty_files",
    "native_status",
    "tee_status",
    "semantic_status",
    "wrench_source",
    "context_source",
}


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key", key)
        result[key] = value
    return result


def _load_json(path: Path, *, max_bytes: int = MAX_AGGREGATE_BYTES) -> dict[str, Any]:
    if not path.exists():
        _fail("artifact_not_found", str(path))
    if not path.is_file() or path.is_symlink():
        _fail("artifact_not_regular_file", str(path))
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        _fail("artifact_too_large", str(path))
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=lambda value: _fail("nonfinite_json_constant", value),
        )
    except UnicodeDecodeError as exc:
        raise ValueError("artifact_not_utf8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"json_decode_error:{exc.msg}") from exc
    if not isinstance(payload, dict):
        _fail("root_not_object")
    return payload


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_exact_fields(payload: Mapping[str, Any], expected: set[str], path: str) -> None:
    actual = set(payload)
    if actual != expected:
        missing = ",".join(sorted(expected - actual)) or "none"
        extra = ",".join(sorted(actual - expected)) or "none"
        _fail("field_set_mismatch", f"{path};missing={missing};extra={extra}")


def _configuration_set(names: Iterable[Any]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    for name in names:
        if not isinstance(name, str) or not name:
            _fail("configuration_invalid")
        if name in seen:
            duplicates.add(name)
        seen.add(name)
        normalized.append(name)
    if duplicates:
        _fail("duplicate_configuration", ",".join(sorted(duplicates)))
    expected = set(EXPECTED_CONFIGURATIONS)
    actual = set(normalized)
    if actual != expected or len(normalized) != len(EXPECTED_CONFIGURATIONS):
        missing = ",".join(sorted(expected - actual)) or "none"
        extra = ",".join(sorted(actual - expected)) or "none"
        _fail("configuration_set_mismatch", f"missing={missing};extra={extra}")
    return tuple(normalized)


def _basename(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or Path(value).name != value:
        _fail("reference_path_invalid", field)
    return value


def _referenced_file(root: Path, value: Any, field: str) -> Path:
    name = _basename(value, field)
    path = root / name
    if path.is_symlink() or not path.exists() or not path.is_file():
        _fail("reference_missing", f"{field}:{name}")
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root):
        _fail("reference_path_invalid", field)
    return resolved


def _validate_server_runtime(
    runtime: Mapping[str, Any], actual_sim: str, actual_lab: str
) -> None:
    missing = _SERVER_RUNTIME_FIELDS - set(runtime)
    if missing:
        _fail("runtime_provenance_missing", ",".join(sorted(missing)))
    if runtime.get("artifact_origin") != SERVER_EVIDENCE_LEVEL:
        _fail("server_evidence_required")
    if runtime.get("actual_isaac_sim") != actual_sim or actual_sim != "5.0.0":
        _fail("runtime_version_mismatch", "isaac_sim")
    if runtime.get("actual_isaac_lab") != actual_lab or actual_lab != "2.2.1":
        _fail("runtime_version_mismatch", "isaac_lab")
    if runtime.get("isaac_lab_release_tag") != EXPECTED_ISAAC_LAB_RELEASE_TAG:
        _fail("runtime_version_mismatch", "isaac_lab_release_tag")
    expected_locked_values = {
        "isaac_lab_release_commit": EXPECTED_ISAAC_LAB_RELEASE_COMMIT,
        "isaac_lab_repo_commit": EXPECTED_ISAAC_LAB_REPO_COMMIT,
        "isaac_lab_repo_parent_commit": EXPECTED_ISAAC_LAB_RELEASE_COMMIT,
        "isaac_lab_repo_patch_sha256": EXPECTED_ISAAC_LAB_PATCH_SHA256,
        "isaac_lab_repo_dirty_files": list(EXPECTED_ISAAC_LAB_DIRTY_FILES),
    }
    for field, expected in expected_locked_values.items():
        if runtime.get(field) != expected:
            _fail("runtime_provenance_invalid", field)
    if runtime.get("native_status") != 0:
        _fail("native_status_failed")
    if runtime.get("tee_status") != 0:
        _fail("tee_status_failed")
    if runtime.get("semantic_status") != "pass":
        _fail("semantic_status_failed")
    if runtime.get("wrench_source") != "post_actuator_thruster_only":
        _fail("semantic_source_invalid", "wrench")
    if runtime.get("context_source") != "same_step_oracle_snapshot":
        _fail("semantic_source_invalid", "context")


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        _fail("artifact_exists", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(_canonical_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            _fail("artifact_exists", str(path))
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _manifest_metadata(path: Path) -> tuple[dict[str, Any], str, str, dict[str, Any]]:
    manifest = _load_json(path)
    invariants = manifest.get("episode_invariants")
    runtime = manifest.get("runtime_provenance")
    if not isinstance(invariants, dict) or not isinstance(runtime, dict):
        _fail("metadata_missing", str(path))
    configuration = invariants.get("configuration")
    source_commit = invariants.get("source_commit")
    if not isinstance(configuration, str) or not isinstance(source_commit, str):
        _fail("metadata_missing", str(path))
    return manifest, configuration, source_commit, runtime


def merge_koopman_v2_evidence(
    manifest_paths: Iterable[str | Path],
    log_paths: Mapping[str, str | Path],
    output_path: str | Path,
    *,
    require_server: bool = False,
) -> dict[str, Any]:
    """Validate exact-three inputs and atomically create their aggregate."""
    output = Path(output_path).resolve()
    if output.exists():
        _fail("artifact_exists", str(output))
    paths = [Path(path).resolve() for path in manifest_paths]
    metadata = [_manifest_metadata(path) for path in paths]
    names = _configuration_set(item[1] for item in metadata)
    if set(log_paths) != set(EXPECTED_CONFIGURATIONS):
        _fail("log_set_mismatch")

    source_commits = {item[2] for item in metadata}
    if len(source_commits) != 1:
        _fail("metadata_disagreement", "source_commit")
    source_commit = next(iter(source_commits))
    if not _COMMIT_RE.fullmatch(source_commit):
        _fail("source_commit_invalid")
    runtimes = [item[3] for item in metadata]
    if any(runtime != runtimes[0] for runtime in runtimes[1:]):
        _fail("runtime_provenance_disagreement")
    evidence_levels = {item[0].get("evidence_level") for item in metadata}
    if len(evidence_levels) != 1:
        _fail("metadata_disagreement", "evidence_level")
    evidence_level = next(iter(evidence_levels))
    if require_server and evidence_level != SERVER_EVIDENCE_LEVEL:
        _fail("server_evidence_required")
    if evidence_level not in {LOCAL_EVIDENCE_LEVEL, SERVER_EVIDENCE_LEVEL}:
        _fail("evidence_level_invalid")

    actual_sim = str(runtimes[0].get("actual_isaac_sim", ""))
    actual_lab = str(runtimes[0].get("actual_isaac_lab", ""))
    if require_server:
        _validate_server_runtime(runtimes[0], actual_sim, actual_lab)

    by_name = {item[1]: (path, *item) for path, item in zip(paths, metadata, strict=True)}
    episodes: list[dict[str, Any]] = []
    for configuration in EXPECTED_CONFIGURATIONS:
        manifest_path, manifest, _, _, _ = by_name[configuration]
        if manifest_path.parent != output.parent:
            _fail("reference_path_invalid", str(manifest_path))
        if require_server and manifest_path.read_bytes() != _canonical_json_bytes(manifest):
            _fail("manifest_hash_mismatch", configuration)
        transition_name = _basename(manifest.get("transition_file"), "transition_file")
        transition_path = manifest_path.parent / transition_name
        if transition_path.is_symlink() or not transition_path.is_file():
            _fail("episode_missing", configuration)
        log_candidate = Path(log_paths[configuration]).resolve()
        if log_candidate.parent != output.parent or log_candidate.is_symlink() or not log_candidate.is_file():
            _fail("log_missing", configuration)
        result = validate_episode_artifact_v2(transition_path, manifest_path)
        if result["configuration"] != configuration:
            _fail("topology_mismatch", configuration)
        if require_server and result["record_count"] < MINIMUM_SERVER_TRANSITIONS:
            _fail("record_count_below_minimum", configuration)
        episodes.append(
            {
                "configuration": configuration,
                "episode_file": transition_path.name,
                "manifest_file": manifest_path.name,
                "log_file": log_candidate.name,
                "episode_sha256": _sha256(transition_path),
                "manifest_sha256": _sha256(manifest_path),
                "log_sha256": _sha256(log_candidate),
                "record_count": result["record_count"],
                "episode_id": result["episode_id"],
            }
        )

    aggregate = {
        "aggregate_version": AGGREGATE_SCHEMA_VERSION,
        "evidence_level": evidence_level,
        "source_commit": source_commit,
        "actual_isaac_sim": actual_sim,
        "actual_isaac_lab": actual_lab,
        "runtime_provenance": runtimes[0],
        "configurations": list(EXPECTED_CONFIGURATIONS),
        "episodes": episodes,
    }
    _atomic_write(output, aggregate)
    validate_aggregate_evidence(output, require_server=require_server)
    return aggregate


def validate_aggregate_evidence(
    aggregate_path: str | Path, *, require_server: bool = False
) -> dict[str, Any]:
    """Re-read every referenced byte and enforce exact-three provenance."""
    path = Path(aggregate_path).resolve()
    payload = _load_json(path)
    _require_exact_fields(payload, _AGGREGATE_FIELDS, "aggregate")
    if payload["aggregate_version"] != AGGREGATE_SCHEMA_VERSION:
        _fail("aggregate_version_mismatch")
    configurations = payload["configurations"]
    episodes = payload["episodes"]
    if not isinstance(configurations, list) or not isinstance(episodes, list):
        _fail("type_invalid", "configurations_or_episodes")
    _configuration_set(configurations)
    episode_names = _configuration_set(
        item.get("configuration") if isinstance(item, dict) else None
        for item in episodes
    )
    if set(episode_names) != set(configurations):
        _fail("configuration_set_mismatch")
    evidence_level = payload["evidence_level"]
    if require_server and evidence_level != SERVER_EVIDENCE_LEVEL:
        _fail("server_evidence_required")
    if evidence_level not in {LOCAL_EVIDENCE_LEVEL, SERVER_EVIDENCE_LEVEL}:
        _fail("evidence_level_invalid")
    source_commit = payload["source_commit"]
    if not isinstance(source_commit, str) or not _COMMIT_RE.fullmatch(source_commit):
        _fail("source_commit_invalid")
    runtime = payload["runtime_provenance"]
    if not isinstance(runtime, dict):
        _fail("runtime_provenance_invalid")
    actual_sim = payload["actual_isaac_sim"]
    actual_lab = payload["actual_isaac_lab"]
    if not isinstance(actual_sim, str) or not isinstance(actual_lab, str):
        _fail("runtime_provenance_invalid")
    if require_server:
        _validate_server_runtime(runtime, actual_sim, actual_lab)

    root = path.parent
    for item in episodes:
        assert isinstance(item, dict)
        _require_exact_fields(item, _EPISODE_FIELDS, "aggregate.episodes")
        configuration = item["configuration"]
        episode_path = _referenced_file(root, item["episode_file"], "episode_file")
        manifest_path = _referenced_file(root, item["manifest_file"], "manifest_file")
        log_path = _referenced_file(root, item["log_file"], "log_file")
        for field, referenced in (
            ("episode_sha256", episode_path),
            ("manifest_sha256", manifest_path),
            ("log_sha256", log_path),
        ):
            expected_hash = item[field]
            if not isinstance(expected_hash, str) or not _SHA256_RE.fullmatch(expected_hash):
                _fail("hash_invalid", field)
            if _sha256(referenced) != expected_hash:
                reason = {
                    "episode_sha256": "episode_hash_mismatch",
                    "manifest_sha256": "manifest_hash_mismatch",
                    "log_sha256": "log_hash_mismatch",
                }[field]
                _fail(reason, configuration)
        result = validate_episode_artifact_v2(episode_path, manifest_path)
        if (
            result["configuration"] != configuration
            or result["record_count"] != item["record_count"]
            or result["episode_id"] != item["episode_id"]
            or result["evidence_level"] != evidence_level
        ):
            _fail("aggregate_episode_disagreement", configuration)
        manifest = _load_json(manifest_path)
        invariants = manifest.get("episode_invariants", {})
        if invariants.get("source_commit") != source_commit:
            _fail("metadata_disagreement", "source_commit")
        if manifest.get("runtime_provenance") != runtime:
            _fail("runtime_provenance_disagreement")
        if require_server and result["record_count"] < MINIMUM_SERVER_TRANSITIONS:
            _fail("record_count_below_minimum", configuration)
    return {
        "validation_gate": (
            "koopman_v2_exact_three_server_evidence_valid"
            if require_server
            else "koopman_v2_exact_three_evidence_valid"
        ),
        "evidence_level": evidence_level,
        "source_commit": source_commit,
        "configuration_count": len(episodes),
        "configurations": list(EXPECTED_CONFIGURATIONS),
        "warnings": [],
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge exact-three Koopman-v2 evidence.")
    parser.add_argument("--manifest", action="append", required=True, type=Path)
    parser.add_argument("--log", action="append", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--require-server", action="store_true")
    return parser


def _parse_logs(values: Iterable[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        configuration, separator, path = value.partition("=")
        if not separator or configuration not in EXPECTED_CONFIGURATIONS or configuration in result:
            _fail("log_argument_invalid", value)
        result[configuration] = Path(path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        payload = merge_koopman_v2_evidence(
            args.manifest,
            _parse_logs(args.log),
            args.output,
            require_server=args.require_server,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"aggregate={Path(args.output).resolve()}")
    print(f"evidence_level={payload['evidence_level']}")
    print("configuration_count=3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

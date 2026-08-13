"""Model-free exact-eight Phase 8 pilot collection-health audit."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.evidence_v2 import (
    PILOT_QUALIFICATION_LEVEL,
    atomic_write_json,
    build_external_phase8_envelope,
    canonical_sha256,
    file_sha256,
    load_bounded_json,
)
from koopman.protocol_v2 import (
    PILOT_ARTIFACT_ORIGIN,
    PILOT_CONTROLLER_MODE,
    PILOT_EXPERIMENT_ID,
    PILOT_RAW_ACTION_ABS_MAX,
    PILOT_TASK_ID,
    PUBLIC_CONFIGURATIONS,
)
from koopman.schema_v2 import load_episode_jsonl_v2, validate_episode_artifact_v2
from workflows.merge_koopman_v2_evidence import _validate_server_runtime
from workflows.validate_phase8_pilot_policy import load_operational_pilot_policy


PILOT_INVENTORY_VERSION = "phase8-pilot-inventory-v1"
PILOT_HEALTH_DECISION_VERSION = "phase8-pilot-health-decision-v1"
_FORBIDDEN_TOKENS = (
    "model",
    "fit",
    "backend",
    "feature",
    "horizon",
    "rank",
    "condition",
    "prediction",
    "rollout",
    "error",
)
_ALLOWED_SCHEMA_KEYS = {"declared_control_rank"}
_OUTPUT_NAMES = (
    "pilot_inventory.json",
    "pilot_health_decision.json",
    "pilot_envelope.json",
)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _forbidden_name(value: str) -> bool:
    lower = value.lower()
    return any(token in lower for token in _FORBIDDEN_TOKENS)


def _scan_forbidden_keys(value: Any, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key) not in _ALLOWED_SCHEMA_KEYS and _forbidden_name(str(key)):
                _fail("pilot_modeling_forbidden", f"{path}.{key}")
            _scan_forbidden_keys(nested, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, nested in enumerate(value):
            _scan_forbidden_keys(nested, f"{path}[{index}]")


def _scan_jsonl_forbidden(path: Path) -> None:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        _scan_forbidden_keys(payload, f"{path.name}:{line_number}")


def _expected_input_paths(policy: Mapping[str, Any]) -> set[str]:
    paths = {"pilot_collection_policy.json"}
    for entry in policy["entries"]:
        episode_id = entry["episode_id"]
        paths.update(
            {
                f"episodes/{episode_id}.jsonl",
                f"manifests/{episode_id}.manifest.json",
                f"logs/{episode_id}.log",
            }
        )
    return paths


def _actual_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    }


def _require_exact_input_set(root: Path, expected: set[str]) -> None:
    actual = _actual_files(root)
    for relative in actual:
        if _forbidden_name(Path(relative).name):
            _fail("pilot_modeling_forbidden", relative)
    if actual != expected:
        missing = ",".join(sorted(expected - actual)) or "none"
        extra = ",".join(sorted(actual - expected)) or "none"
        _fail("inventory_set_mismatch", f"missing={missing};extra={extra}")
    for relative in expected:
        path = root / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            _fail("reference_path_invalid", relative)


def _signed_counts(rows: Sequence[Mapping[str, Any]]) -> tuple[list[int], list[int]]:
    positive = [0, 0, 0, 0]
    negative = [0, 0, 0, 0]
    for row in rows:
        for index, value in enumerate(row["virtual_control_4"]):
            if float(value) > 1e-12:
                positive[index] += 1
            elif float(value) < -1e-12:
                negative[index] += 1
    return positive, negative


def audit_pilot_collection(
    root_path: str | Path, *, require_server: bool = False
) -> dict[str, Any]:
    """Audit exact policy/inventory/runtime/log/semantic health and write outputs."""
    root = Path(root_path).resolve()
    if not root.exists() or not root.is_dir() or root.is_symlink():
        _fail("artifact_root_invalid", str(root))
    outputs = [root / name for name in _OUTPUT_NAMES]
    for output in outputs:
        if output.exists():
            _fail("artifact_exists", str(output))
    policy_path = root / "pilot_collection_policy.json"
    policy = load_operational_pilot_policy(policy_path)
    expected_inputs = _expected_input_paths(policy)
    _require_exact_input_set(root, expected_inputs)
    policy_sha256 = file_sha256(policy_path)

    # Compare all runtime payloads before checking their fixed version values so a
    # single mutated episode receives a deterministic disagreement reason.
    manifests: dict[str, dict[str, Any]] = {}
    runtimes: list[Mapping[str, Any]] = []
    for entry in policy["entries"]:
        episode_id = entry["episode_id"]
        manifest = load_bounded_json(root / "manifests" / f"{episode_id}.manifest.json")
        _scan_forbidden_keys(manifest, f"manifest:{episode_id}")
        runtime = manifest.get("runtime_provenance")
        if not isinstance(runtime, Mapping):
            _fail("runtime_provenance_invalid", episode_id)
        manifests[episode_id] = manifest
        runtimes.append(runtime)
    if any(runtime != runtimes[0] for runtime in runtimes[1:]):
        _fail("runtime_provenance_disagreement")
    runtime = dict(runtimes[0])
    if require_server:
        _validate_server_runtime(
            runtime,
            str(runtime.get("actual_isaac_sim", "")),
            str(runtime.get("actual_isaac_lab", "")),
        )
    elif runtime.get("artifact_origin") != PILOT_ARTIFACT_ORIGIN:
        _fail("evidence_level_mismatch")

    source_commit: str | None = None
    inventory_entries: list[dict[str, Any]] = []
    rows_by_configuration: dict[str, list[Mapping[str, Any]]] = {
        configuration: [] for configuration in PUBLIC_CONFIGURATIONS
    }
    for entry in policy["entries"]:
        configuration = entry["configuration"]
        episode_id = entry["episode_id"]
        episode_relative = f"episodes/{episode_id}.jsonl"
        manifest_relative = f"manifests/{episode_id}.manifest.json"
        log_relative = f"logs/{episode_id}.log"
        episode_path = root / episode_relative
        manifest_path = root / manifest_relative
        log_path = root / log_relative
        if log_path.stat().st_size == 0:
            _fail("pilot_health_failed", f"empty_log:{episode_id}")
        _scan_jsonl_forbidden(episode_path)
        rows = load_episode_jsonl_v2(episode_path)
        manifest = manifests[episode_id]
        invariants = manifest.get("episode_invariants")
        if not isinstance(invariants, Mapping):
            _fail("pilot_health_failed", f"manifest_invariants_missing:{episode_id}")
        row_source = rows[0]["episode_provenance"]["source_commit"]
        if invariants.get("source_commit") != row_source:
            _fail("source_commit_mismatch", episode_id)
        if source_commit is None:
            source_commit = row_source
        elif source_commit != row_source:
            _fail("source_commit_mismatch", episode_id)
        expected_invariants = {
            "configuration": configuration,
            "scenario": entry["scenario"],
            "episode_id": episode_id,
            "seed": entry["seed"],
            "task_id": policy["task_id"],
            "controller_mode": policy["controller_mode"],
            "evidence_level": policy["artifact_origin_level"],
        }
        for field, expected in expected_invariants.items():
            if invariants.get(field) != expected:
                _fail("pilot_health_failed", f"protocol_drift:{episode_id}:{field}")
        validation = validate_episode_artifact_v2(episode_path, manifest_path)
        if validation["record_count"] != entry["transition_count"]:
            _fail("pilot_health_failed", f"transition_count:{episode_id}")
        if validation["evidence_level"] != PILOT_ARTIFACT_ORIGIN:
            _fail("evidence_level_mismatch", episode_id)
        for row in rows:
            if any(abs(float(value)) > PILOT_RAW_ACTION_ABS_MAX + 1e-12 for value in row["raw_action_4"]):
                _fail("pilot_health_failed", f"raw_action_out_of_bounds:{episode_id}")
        if configuration.startswith("uuv4"):
            episode_raw_yaw_nonzero = sum(
                abs(float(row["raw_action_4"][2])) > 1e-12 for row in rows
            )
            episode_virtual_yaw_nonzero = sum(
                abs(float(row["virtual_control_4"][2])) > 1e-12 for row in rows
            )
            if episode_raw_yaw_nonzero == 0:
                _fail("pilot_health_failed", f"{configuration}_raw_yaw_probe_missing")
            if episode_virtual_yaw_nonzero != 0:
                _fail("pilot_health_failed", f"{configuration}_virtual_yaw_leak")
        rows_by_configuration[configuration].extend(rows)
        inventory_entries.append(
            {
                "configuration": configuration,
                "episode_id": episode_id,
                "policy_kind": entry["policy_kind"],
                "seed": entry["seed"],
                "transition_count": len(rows),
                "episode_file": episode_relative,
                "episode_sha256": file_sha256(episode_path),
                "manifest_file": manifest_relative,
                "manifest_sha256": file_sha256(manifest_path),
                "log_file": log_relative,
                "log_sha256": file_sha256(log_path),
            }
        )
    assert source_commit is not None

    channel_health: dict[str, dict[str, Any]] = {}
    for configuration in PUBLIC_CONFIGURATIONS:
        rows = rows_by_configuration[configuration]
        positive, negative = _signed_counts(rows)
        control_mask = list(rows[0]["platform_context"]["control_mask"])
        for index, controllable in enumerate(control_mask):
            if controllable and (positive[index] == 0 or negative[index] == 0):
                _fail("pilot_health_failed", f"signed_virtual_coverage:{configuration}:{index}")
        if all(row["state_11"] == rows[0]["state_11"] for row in rows[1:]):
            _fail("pilot_health_failed", f"state_nonconstant_missing:{configuration}")
        raw_yaw_nonzero = sum(abs(float(row["raw_action_4"][2])) > 1e-12 for row in rows)
        virtual_yaw_nonzero = sum(
            abs(float(row["virtual_control_4"][2])) > 1e-12 for row in rows
        )
        if configuration.startswith("uuv4"):
            if raw_yaw_nonzero == 0:
                _fail("pilot_health_failed", f"{configuration}_raw_yaw_probe_missing")
            if virtual_yaw_nonzero != 0:
                _fail("pilot_health_failed", f"{configuration}_virtual_yaw_leak")
        channel_health[configuration] = {
            "transition_count": len(rows),
            "positive_virtual_counts": positive,
            "negative_virtual_counts": negative,
            "raw_yaw_nonzero_count": raw_yaw_nonzero,
            "virtual_yaw_nonzero_count": virtual_yaw_nonzero,
        }

    inventory = {
        "inventory_version": PILOT_INVENTORY_VERSION,
        "experiment_id": policy["experiment_id"],
        "policy_sha256": policy_sha256,
        "source_commit": source_commit,
        "runtime_provenance": runtime,
        "runtime_sha256": canonical_sha256(runtime),
        "configurations": list(PUBLIC_CONFIGURATIONS),
        "episodes": inventory_entries,
    }
    inventory_path = root / "pilot_inventory.json"
    atomic_write_json(inventory_path, inventory)
    decision = {
        "decision_version": PILOT_HEALTH_DECISION_VERSION,
        "experiment_id": PILOT_EXPERIMENT_ID,
        "pilot_health_gate": "pass",
        "decision": "collection_chain_ready",
        "policy_sha256": policy_sha256,
        "inventory_sha256": file_sha256(inventory_path),
        "source_commit": source_commit,
        "configuration_count": len(PUBLIC_CONFIGURATIONS),
        "episode_count": len(inventory_entries),
        "transition_count": sum(item["transition_count"] for item in inventory_entries),
        "channel_health": channel_health,
        "warnings": [],
    }
    decision_path = root / "pilot_health_decision.json"
    atomic_write_json(decision_path, decision)
    envelope_path = root / "pilot_envelope.json"
    referenced_paths = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    build_external_phase8_envelope(
        envelope_path,
        experiment_id=PILOT_EXPERIMENT_ID,
        source_commit=source_commit,
        protocol_sha256=policy_sha256,
        runtime_provenance=runtime,
        inventory_path=inventory_path,
        decision_path=decision_path,
        referenced_paths=referenced_paths,
    )
    return {
        "validation_gate": "pilot_health_gate",
        "decision": "collection_chain_ready",
        "qualification_level": PILOT_QUALIFICATION_LEVEL,
        "source_commit": source_commit,
        "configuration_count": len(PUBLIC_CONFIGURATIONS),
        "episode_count": len(inventory_entries),
        "transition_count": decision["transition_count"],
        "warnings": [],
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit exact-eight Phase 8 pilot health.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--require-server", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        result = audit_pilot_collection(args.root, require_server=args.require_server)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, allow_nan=False, indent=2, sort_keys=True))
    else:
        for key in ("validation_gate", "decision", "qualification_level", "source_commit"):
            print(f"{key}={result[key]}")
        print(f"configuration_count={result['configuration_count']}")
        print(f"episode_count={result['episode_count']}")
        print(f"transition_count={result['transition_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

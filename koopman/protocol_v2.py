"""Strict pre-collection protocols for Phase 8 Koopman evidence.

This module is deliberately pure Python.  A pilot protocol records collection
intent only; post-collection hashes and any modelling result are forbidden.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

from koopman.collection_v2 import EpisodeRoleIntentV2


PILOT_POLICY_VERSION = "phase8-pilot-collection-policy-v1"
PILOT_EXPERIMENT_ID = "phase8-identification-pilot-v1"
PUBLIC_CONFIGURATIONS = (
    "base",
    "long_body",
    "heavy_moderate",
    "asymmetric",
    "uuv6",
    "uuv6_angled",
    "uuv4",
    "uuv4_angled",
)
PILOT_POLICY_KINDS = ("axis_pulse", "bounded_multisine")
PILOT_POLICY_SEEDS = {"axis_pulse": 8101, "bounded_multisine": 8102}
PILOT_TRANSITION_COUNT = 128
PILOT_RAW_ACTION_ABS_MAX = 0.25
PILOT_TASK_ID = "EasyUUV-Direct-v1"
PILOT_CONTROLLER_MODE = "legacy/Ssurface"
PILOT_ARTIFACT_ORIGIN = "server_isaac_smoke"
PILOT_TRANSITION_SCHEMA = "easyuuv-koopman-transition-v2"

_POLICY_FIELDS = frozenset(
    {
        "policy_version",
        "experiment_id",
        "transition_schema_version",
        "artifact_origin_level",
        "task_id",
        "controller_mode",
        "runtime_contract",
        "raw_action_abs_max",
        "entries",
    }
)
_ENTRY_FIELDS = frozenset(
    {
        "configuration",
        "episode_id",
        "scenario",
        "policy_kind",
        "seed",
        "transition_count",
    }
)
_RUNTIME_FIELDS = frozenset(
    {
        "isaac_sim_version",
        "isaac_lab_version",
        "python_entrypoint",
    }
)
_FORBIDDEN_POLICY_TOKENS = (
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
    "sha256",
    "hash",
)
MAX_POLICY_BYTES = 256 * 1024


def _fail(detail: str) -> None:
    raise ValueError(f"pilot_policy_invalid:{detail}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    _fail(f"nonfinite_json_constant:{value}")


def _require_exact_fields(
    value: Any, expected: frozenset[str], *, path: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"type_invalid:{path}")
    actual = set(value)
    if actual != expected:
        missing = ",".join(sorted(expected - actual)) or "none"
        extra = ",".join(sorted(actual - expected)) or "none"
        _fail(f"field_set_mismatch:{path}:missing={missing};extra={extra}")
    return value


def _contains_forbidden_key(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lower = str(key).lower()
            for token in _FORBIDDEN_POLICY_TOKENS:
                if token in lower:
                    return str(key)
            found = _contains_forbidden_key(nested)
            if found is not None:
                return found
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            found = _contains_forbidden_key(nested)
            if found is not None:
                return found
    return None


def validate_pilot_collection_policy(value: Any) -> None:
    """Validate exact-eight, two-episode collection intent without mutation."""
    policy = _require_exact_fields(value, _POLICY_FIELDS, path="policy")
    forbidden = _contains_forbidden_key(policy)
    if forbidden is not None:
        _fail(f"postcollection_field_forbidden:{forbidden}")
    expected_scalars = {
        "policy_version": PILOT_POLICY_VERSION,
        "experiment_id": PILOT_EXPERIMENT_ID,
        "transition_schema_version": PILOT_TRANSITION_SCHEMA,
        "artifact_origin_level": PILOT_ARTIFACT_ORIGIN,
        "task_id": PILOT_TASK_ID,
        "controller_mode": PILOT_CONTROLLER_MODE,
    }
    for field, expected in expected_scalars.items():
        if policy[field] != expected:
            _fail(f"value_mismatch:{field}")
    raw_bound = policy["raw_action_abs_max"]
    if (
        isinstance(raw_bound, bool)
        or not isinstance(raw_bound, (int, float))
        or not math.isfinite(float(raw_bound))
        or float(raw_bound) != PILOT_RAW_ACTION_ABS_MAX
    ):
        _fail("value_mismatch:raw_action_abs_max")
    runtime = _require_exact_fields(
        policy["runtime_contract"], _RUNTIME_FIELDS, path="runtime_contract"
    )
    for field in sorted(_RUNTIME_FIELDS):
        value = runtime[field]
        if not isinstance(value, str) or not value:
            _fail(f"value_invalid:runtime_contract.{field}")
    entries = policy["entries"]
    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        _fail("type_invalid:entries")
    if len(entries) != len(PUBLIC_CONFIGURATIONS) * len(PILOT_POLICY_KINDS):
        _fail(f"entry_count:{len(entries)}")
    actual: list[tuple[str, str, int, int]] = []
    episode_ids: set[str] = set()
    for index, value_entry in enumerate(entries):
        entry = _require_exact_fields(value_entry, _ENTRY_FIELDS, path=f"entries[{index}]")
        configuration = entry["configuration"]
        policy_kind = entry["policy_kind"]
        if configuration not in PUBLIC_CONFIGURATIONS:
            _fail(f"configuration_unknown:{configuration}")
        if policy_kind not in PILOT_POLICY_KINDS:
            _fail(f"policy_kind_unknown:{policy_kind}")
        expected_seed = PILOT_POLICY_SEEDS[policy_kind]
        if isinstance(entry["seed"], bool) or entry["seed"] != expected_seed:
            _fail(f"seed_mismatch:{configuration}:{policy_kind}")
        if (
            isinstance(entry["transition_count"], bool)
            or entry["transition_count"] != PILOT_TRANSITION_COUNT
        ):
            _fail(f"transition_count_mismatch:{configuration}:{policy_kind}")
        expected_episode_id = (
            f"phase8-pilot-{configuration}-{policy_kind.replace('_', '-')}-s{expected_seed}"
        )
        if entry["episode_id"] != expected_episode_id:
            _fail(f"episode_id_mismatch:{configuration}:{policy_kind}")
        expected_scenario = f"phase8-pilot-{policy_kind.replace('_', '-')}"
        if entry["scenario"] != expected_scenario:
            _fail(f"scenario_mismatch:{configuration}:{policy_kind}")
        if entry["episode_id"] in episode_ids:
            _fail(f"duplicate_episode_id:{entry['episode_id']}")
        episode_ids.add(entry["episode_id"])
        actual.append((configuration, policy_kind, entry["seed"], entry["transition_count"]))
    expected_entries = [
        (configuration, policy_kind, PILOT_POLICY_SEEDS[policy_kind], PILOT_TRANSITION_COUNT)
        for configuration in PUBLIC_CONFIGURATIONS
        for policy_kind in PILOT_POLICY_KINDS
    ]
    if actual != expected_entries:
        _fail("entry_order_or_set_mismatch")


def load_pilot_collection_policy(path: str | Path) -> dict[str, Any]:
    """Load bounded duplicate-safe JSON and validate the pilot policy."""
    policy_path = Path(path)
    if policy_path.is_symlink() or not policy_path.exists() or not policy_path.is_file():
        _fail(f"artifact_not_regular_file:{policy_path}")
    raw = policy_path.read_bytes()
    if len(raw) > MAX_POLICY_BYTES:
        _fail(f"artifact_too_large:{len(raw)}")
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise ValueError("pilot_policy_invalid:artifact_not_utf8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"pilot_policy_invalid:json_decode_error:{exc.msg}") from exc
    validate_pilot_collection_policy(payload)
    assert isinstance(payload, dict)
    return payload


MAIN_ROLE_PROTOCOL_VERSION = "phase8-main-role-protocol-v1"
MAIN_EXPERIMENT_ID = "phase8-main-identification-v1-proposal"
MAIN_EXCITATION_FAMILIES = (
    "independent_prbs",
    "bounded_multisine",
    "coupled_chirp",
)
MAIN_TRANSITION_COUNT = 512
MAIN_RAW_ACTION_ABS_MAX = 0.25
MAIN_ROLE_COUNTS = {"fit": 6, "validation": 3, "test": 3}
_MAIN_PROTOCOL_FIELDS = frozenset(
    {
        "approval_status",
        "artifact_origin_level",
        "controller_mode",
        "entries",
        "experiment_id",
        "frozen_at",
        "proposal_only",
        "protocol_version",
        "raw_action_abs_max",
        "task_id",
        "transition_count",
        "transition_schema_version",
    }
)
_MAIN_ENTRY_FIELDS = frozenset(
    {
        "configuration",
        "episode_id",
        "excitation_family",
        "manifest_path",
        "repetition",
        "role",
        "scenario",
        "seed",
        "transition_count",
        "transition_path",
    }
)


def _main_fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _utc_timestamp(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        _main_fail("timestamp_invalid", path)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"timestamp_invalid:{path}") from exc
    if parsed.tzinfo != timezone.utc or parsed.microsecond != 0:
        _main_fail("timestamp_invalid", path)
    return value


def _main_seed(
    configuration_index: int,
    role: str,
    family_index: int,
    repetition: int,
) -> int:
    role_offset = {"fit": 1000, "validation": 2000, "test": 3000}[role]
    return 820_000 + configuration_index * 10_000 + role_offset + family_index * 10 + repetition


def _recommended_main_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for configuration_index, configuration in enumerate(PUBLIC_CONFIGURATIONS):
        for role in ("fit", "validation", "test"):
            repetitions = 2 if role == "fit" else 1
            for family_index, family in enumerate(MAIN_EXCITATION_FAMILIES):
                for repetition in range(1, repetitions + 1):
                    seed = _main_seed(
                        configuration_index,
                        role,
                        family_index,
                        repetition,
                    )
                    episode_id = (
                        f"phase8-main-{configuration}-{role}-"
                        f"{family.replace('_', '-')}-r{repetition}-s{seed}"
                    )
                    entries.append(
                        {
                            "configuration": configuration,
                            "episode_id": episode_id,
                            "excitation_family": family,
                            "manifest_path": f"manifests/{episode_id}.manifest.json",
                            "repetition": repetition,
                            "role": role,
                            "scenario": f"phase8-main-{family.replace('_', '-')}",
                            "seed": seed,
                            "transition_count": MAIN_TRANSITION_COUNT,
                            "transition_path": f"episodes/{episode_id}.jsonl",
                        }
                    )
    return entries


def build_recommended_main_role_protocol_v1(*, frozen_at: str) -> dict[str, Any]:
    """Return the exact D-23 proposal without claiming approval or evidence."""
    _utc_timestamp(frozen_at, "frozen_at")
    protocol = {
        "approval_status": "pending_d23",
        "artifact_origin_level": PILOT_ARTIFACT_ORIGIN,
        "controller_mode": PILOT_CONTROLLER_MODE,
        "entries": _recommended_main_entries(),
        "experiment_id": MAIN_EXPERIMENT_ID,
        "frozen_at": frozen_at,
        "proposal_only": True,
        "protocol_version": MAIN_ROLE_PROTOCOL_VERSION,
        "raw_action_abs_max": MAIN_RAW_ACTION_ABS_MAX,
        "task_id": PILOT_TASK_ID,
        "transition_count": MAIN_TRANSITION_COUNT,
        "transition_schema_version": PILOT_TRANSITION_SCHEMA,
    }
    validate_main_role_protocol_v1(protocol)
    return protocol


def validate_main_role_protocol_v1(value: Any) -> None:
    """Validate the ordered exact-eight 6/3/3 whole-episode proposal."""
    if not isinstance(value, Mapping):
        _main_fail("type_invalid", "protocol")
    actual_fields = set(value)
    if actual_fields != _MAIN_PROTOCOL_FIELDS:
        _main_fail("field_set_mismatch", "protocol")
    expected_scalars = {
        "approval_status": "pending_d23",
        "artifact_origin_level": PILOT_ARTIFACT_ORIGIN,
        "controller_mode": PILOT_CONTROLLER_MODE,
        "experiment_id": MAIN_EXPERIMENT_ID,
        "proposal_only": True,
        "protocol_version": MAIN_ROLE_PROTOCOL_VERSION,
        "raw_action_abs_max": MAIN_RAW_ACTION_ABS_MAX,
        "task_id": PILOT_TASK_ID,
        "transition_count": MAIN_TRANSITION_COUNT,
        "transition_schema_version": PILOT_TRANSITION_SCHEMA,
    }
    for field, expected in expected_scalars.items():
        if value[field] != expected:
            _main_fail("protocol_value_mismatch", field)
    _utc_timestamp(value["frozen_at"], "frozen_at")
    entries = value["entries"]
    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        _main_fail("type_invalid", "entries")
    expected_entries = _recommended_main_entries()
    if len(entries) != len(expected_entries):
        _main_fail("configuration_matrix_mismatch", f"count={len(entries)}")
    episode_ids: set[str] = set()
    seeds: set[int] = set()
    paths: set[str] = set()
    normalized: list[dict[str, Any]] = []
    expected_by_id = {entry["episode_id"]: entry for entry in expected_entries}
    for index, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, Mapping):
            _main_fail("type_invalid", f"entries[{index}]")
        extra = set(raw_entry) - _MAIN_ENTRY_FIELDS
        if any("row" in str(field).lower() for field in extra):
            _main_fail("row_level_split_forbidden", f"entries[{index}]")
        if set(raw_entry) != _MAIN_ENTRY_FIELDS:
            _main_fail("field_set_mismatch", f"entries[{index}]")
        entry = dict(raw_entry)
        configuration = entry["configuration"]
        if configuration not in PUBLIC_CONFIGURATIONS:
            _main_fail("configuration_set_mismatch", str(configuration))
        role = entry["role"]
        if role not in MAIN_ROLE_COUNTS:
            _main_fail("role_assignment_drift", str(role))
        if entry["excitation_family"] not in MAIN_EXCITATION_FAMILIES:
            _main_fail("configuration_matrix_mismatch", "excitation_family")
        episode_id = entry["episode_id"]
        if isinstance(episode_id, str) and episode_id.startswith("phase8-pilot-"):
            _main_fail("pilot_main_id_reuse", episode_id)
        if episode_id in episode_ids:
            _main_fail("split_episode_overlap", str(episode_id))
        episode_ids.add(episode_id)
        seed = entry["seed"]
        if seed in PILOT_POLICY_SEEDS.values():
            _main_fail("pilot_main_id_reuse", f"seed={seed}")
        if seed in seeds:
            _main_fail("split_episode_overlap", f"seed={seed}")
        seeds.add(seed)
        for field in ("transition_path", "manifest_path"):
            path = entry[field]
            if path in paths:
                _main_fail("split_episode_overlap", str(path))
            paths.add(path)
        expected_for_id = expected_by_id.get(episode_id)
        if expected_for_id is not None and role != expected_for_id["role"]:
            _main_fail("role_assignment_drift", str(episode_id))
        normalized.append(entry)
    if normalized != expected_entries:
        expected_ids = {entry["episode_id"] for entry in expected_entries}
        actual_ids = {entry["episode_id"] for entry in normalized}
        if actual_ids == expected_ids:
            _main_fail("protocol_order_drift")
        _main_fail("configuration_matrix_mismatch")


def main_role_intents_v2(value: Any) -> tuple[EpisodeRoleIntentV2, ...]:
    """Adapt the validated protocol to collection/inventory role intent."""
    validate_main_role_protocol_v1(value)
    assert isinstance(value, Mapping)
    return tuple(
        EpisodeRoleIntentV2(
            configuration=entry["configuration"],
            episode_id=entry["episode_id"],
            role=entry["role"],
            scenario=entry["scenario"],
            seed=entry["seed"],
            transition_count=entry["transition_count"],
            transition_path=entry["transition_path"],
            manifest_path=entry["manifest_path"],
        )
        for entry in value["entries"]
    )

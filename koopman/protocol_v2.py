"""Strict pre-collection protocols for Phase 8 Koopman evidence.

This module is deliberately pure Python.  A pilot protocol records collection
intent only; post-collection hashes and any modelling result are forbidden.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path
from typing import Any


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
PILOT_RUNTIME_CONTRACT = {
    "isaac_sim_version": "5.0",
    "isaac_lab_version": "2.2.1",
    "python_entrypoint": "/root/IsaacLab/isaaclab.sh -p",
}

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
_RUNTIME_FIELDS = frozenset(PILOT_RUNTIME_CONTRACT)
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
    if dict(runtime) != PILOT_RUNTIME_CONTRACT:
        _fail("value_mismatch:runtime_contract")
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


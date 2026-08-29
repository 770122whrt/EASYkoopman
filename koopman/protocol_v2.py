"""Strict pre-collection protocols for Phase 8 Koopman evidence.

This module is deliberately pure Python.  A pilot protocol records collection
intent only; post-collection hashes and any modelling result are forbidden.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
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


MAIN_ROLE_PROTOCOL_VERSION = "phase8-main-role-protocol-v2"
MAIN_EXPERIMENT_ID = "phase8-main-identification-v2-proposal"
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
        "environment_contract",
        "experiment_id",
        "frozen_at",
        "proposal_only",
        "protocol_version",
        "raw_action_abs_max",
        "seed_semantics",
        "task_id",
        "transition_count",
        "transition_schema_version",
    }
)
_MAIN_ENTRY_FIELDS = frozenset(
    {
        "configuration",
        "episode_id",
        "excitation_seed",
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


def _main_excitation_seed(role: str, repetition: int) -> int:
    if role == "fit":
        return 8200 + repetition
    if role == "validation":
        return 8301
    if role == "test":
        return 8401
    _main_fail("role_assignment_drift", role)


def _main_environment_seed(role: str, family: str, repetition: int) -> int:
    family_offset = MAIN_EXCITATION_FAMILIES.index(family) + 1
    if role == "fit":
        return 9200 + 10 * family_offset + repetition
    if role == "validation":
        return 9300 + 10 * family_offset + repetition
    if role == "test":
        return 9400 + 10 * family_offset + repetition
    _main_fail("role_assignment_drift", role)


_MAIN_SEED_SEMANTICS = {
    "environment_seed_field": "seed",
    "environment_seed_scope": "matched_across_configurations_by_role_family_repetition",
    "environment_seed_controls": ["environment_reset", "goal_reference"],
    "excitation_seed_field": "excitation_seed",
    "excitation_seed_scope": "matched_across_configurations_by_role_repetition",
}
_MAIN_ENVIRONMENT_CONTRACT = {
    "domain_randomization_enabled": False,
    "eval_mode": True,
    "reference_mode": "step",
    "sensor_noise_enabled": False,
    "disturbance_mode": "none",
}


def _recommended_main_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for configuration in PUBLIC_CONFIGURATIONS:
        for role in ("fit", "validation", "test"):
            repetitions = 2 if role == "fit" else 1
            for family in MAIN_EXCITATION_FAMILIES:
                for repetition in range(1, repetitions + 1):
                    excitation_seed = _main_excitation_seed(role, repetition)
                    seed = _main_environment_seed(role, family, repetition)
                    episode_id = (
                        f"phase8-main-{configuration}-{role}-"
                        f"{family.replace('_', '-')}-r{repetition}-"
                        f"es{excitation_seed}-rs{seed}"
                    )
                    entries.append(
                        {
                            "configuration": configuration,
                            "episode_id": episode_id,
                            "excitation_family": family,
                            "excitation_seed": excitation_seed,
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
        "environment_contract": dict(_MAIN_ENVIRONMENT_CONTRACT),
        "experiment_id": MAIN_EXPERIMENT_ID,
        "frozen_at": frozen_at,
        "proposal_only": True,
        "protocol_version": MAIN_ROLE_PROTOCOL_VERSION,
        "raw_action_abs_max": MAIN_RAW_ACTION_ABS_MAX,
        "seed_semantics": dict(_MAIN_SEED_SEMANTICS),
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
        "environment_contract": _MAIN_ENVIRONMENT_CONTRACT,
        "experiment_id": MAIN_EXPERIMENT_ID,
        "proposal_only": True,
        "protocol_version": MAIN_ROLE_PROTOCOL_VERSION,
        "raw_action_abs_max": MAIN_RAW_ACTION_ABS_MAX,
        "seed_semantics": _MAIN_SEED_SEMANTICS,
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
        excitation_seed = entry["excitation_seed"]
        if seed in PILOT_POLICY_SEEDS.values() or excitation_seed in PILOT_POLICY_SEEDS.values():
            _main_fail("pilot_main_id_reuse", f"seed={seed}")
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


def main_role_intents_v2(value: Any) -> tuple["EpisodeRoleIntentV2", ...]:
    """Adapt the validated protocol to collection/inventory role intent."""
    from koopman.collection_v2 import EpisodeRoleIntentV2

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


ANALYSIS_POLICY_VERSION_V1 = "phase8-analysis-policy-v1"
ANALYSIS_POLICY_VERSION_V2 = "phase8-analysis-policy-v2"
_ANALYSIS_POLICY_FIELDS_V2 = frozenset(
    {
        "analysis_policy_version",
        "approval_status",
        "backend",
        "bootstrap",
        "data_prefixes",
        "forbidden_inputs",
        "forbidden_roles",
        "gate_template",
        "horizons",
        "inner_decision_algorithm",
        "metric_schema",
        "normalization_candidates",
        "observable_candidates",
        "outer_fold_execution",
        "platform_schema_candidates",
        "qualification_level",
        "reference_diagnostic",
        "ridge_grid",
    }
)
_ANALYSIS_POLICY_FIELDS_V1 = _ANALYSIS_POLICY_FIELDS_V2 - {"outer_fold_execution"}
_ANALYSIS_BOOTSTRAP_FIELDS_V2 = frozenset(
    {
        "alpha",
        "aggregate",
        "configuration_sampling",
        "pairing",
        "population_scope",
        "resamples",
        "seed",
        "stratify_by",
        "unit",
    }
)
_ANALYSIS_BOOTSTRAP_FIELDS_V1 = frozenset({"alpha", "resamples", "seed", "unit"})
_ANALYSIS_ALGORITHM_FIELDS_V1 = frozenset(
    {"name", "primary_metric", "tie_break_order"}
)
_ANALYSIS_ALGORITHM_FIELDS_V2 = _ANALYSIS_ALGORITHM_FIELDS_V1 | {"source_score"}
_ANALYSIS_SOURCE_SCORE_FIELDS_V2 = frozenset(
    {
        "aggregation",
        "baseline_reference",
        "denominator_zero",
        "direction",
        "group_reduction",
        "horizon",
        "name",
        "primary_metric_groups",
    }
)
_ANALYSIS_DENOMINATOR_ZERO_FIELDS_V2 = frozenset(
    {"candidate_positive", "candidate_zero"}
)
_ANALYSIS_METRIC_FIELDS = frozenset(
    {"aggregation", "official_orientation", "row_weighted", "version"}
)
_ANALYSIS_GATE_FIELDS = frozenset(
    {
        "conditional_margin_fraction",
        "divergence_max",
        "invalid_quaternion_max",
        "minimum_improvement_fraction",
        "nonfinite_max",
        "noninferiority_fraction",
    }
)
_ANALYSIS_REFERENCE_FIELDS = frozenset(
    {"enabled", "model_id", "namespace", "selection_eligible"}
)
_ANALYSIS_OUTER_FOLD_FIELDS = frozenset(
    {
        "candidate_selection",
        "holdout_unit",
        "normalization",
        "primary_heldout_access",
        "primary_model_freeze",
    }
)
_ANALYSIS_FORBIDDEN_INPUTS = (
    "reference_5",
    "motor_pwm_padded_8",
    "thruster_mask_8",
    "applied_wrench_6",
    "environment_context_oracle",
    "environment_context_estimated",
    "configuration_identity",
    "heldout_statistics",
)
_ANALYSIS_FORBIDDEN_ROLES = (
    "heldout_expert_upper_bound_v2",
    "reference_conditioned_diagnostic_v2",
)
_ANALYSIS_TIE_BREAK_ORDER = (
    "source_worst",
    "source_macro",
    "data_prefix",
    "observable_order",
    "ridge_order",
    "normalization_order",
    "platform_schema_order",
)
SOURCE_SCORE_PRIMARY_METRICS_V2 = (
    "depth_rmse",
    "linear_velocity_rmse",
    "angular_velocity_rmse",
    "so3_geodesic_mean_radians",
    "so3_geodesic_rmse_radians",
    "so3_geodesic_max_radians",
)
MAX_ANALYSIS_POLICY_BYTES = 512 * 1024


def _analysis_fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _analysis_exact(
    value: Any, fields: frozenset[str], path: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        _analysis_fail("analysis_policy_field_set_mismatch", path)
    return value


def _analysis_sequence(value: Any, path: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _analysis_fail("analysis_policy_type_invalid", path)
    return tuple(value)


def _analysis_number(value: Any, path: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _analysis_fail("analysis_policy_value_invalid", path)
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        _analysis_fail("analysis_policy_value_invalid", path)
    return number


def validate_analysis_policy_v1(value: Any) -> None:
    """Validate the exact local fixture or pending D-23 analysis proposal."""

    if not isinstance(value, Mapping):
        _analysis_fail("analysis_policy_field_set_mismatch", "policy")
    version = value.get("analysis_policy_version")
    if version == ANALYSIS_POLICY_VERSION_V2:
        policy = _analysis_exact(value, _ANALYSIS_POLICY_FIELDS_V2, "policy")
    elif version == ANALYSIS_POLICY_VERSION_V1:
        policy = _analysis_exact(value, _ANALYSIS_POLICY_FIELDS_V1, "policy")
    else:
        _analysis_fail("analysis_policy_value_invalid", "analysis_policy_version")
    expected_scalars = {
        "analysis_policy_version": version,
        "backend": "controlled_edmd_v2",
        "qualification_level": "local_contract",
    }
    for name, expected in expected_scalars.items():
        if policy[name] != expected:
            _analysis_fail("analysis_policy_value_invalid", name)
    approval_status = policy["approval_status"]
    if approval_status not in {"local_fixture_only_not_d23", "pending_d23"}:
        _analysis_fail("analysis_policy_value_invalid", "approval_status")
    if (
        approval_status == "pending_d23" and version != ANALYSIS_POLICY_VERSION_V2
    ) or (
        approval_status == "local_fixture_only_not_d23"
        and version != ANALYSIS_POLICY_VERSION_V1
    ):
        _analysis_fail("analysis_policy_value_invalid", "analysis_policy_version")
    if _analysis_sequence(policy["data_prefixes"], "data_prefixes") != (2, 4, 6):
        _analysis_fail("analysis_policy_value_invalid", "data_prefixes")
    if _analysis_sequence(policy["observable_candidates"], "observable_candidates") != (
        "identity_v1",
        "auv_kinematic_v1",
    ):
        _analysis_fail("analysis_policy_value_invalid", "observable_candidates")
    if _analysis_sequence(policy["normalization_candidates"], "normalization_candidates") != (
        "none",
        "standard_v1",
    ):
        _analysis_fail("analysis_policy_value_invalid", "normalization_candidates")
    if _analysis_sequence(policy["platform_schema_candidates"], "platform_schema_candidates") != (
        "none",
        "platform_physical_compact_v1",
        "platform_physical_core_v1",
    ):
        _analysis_fail("analysis_policy_value_invalid", "platform_schema_candidates")
    if _analysis_sequence(policy["horizons"], "horizons") != (5, 20, 60, "full"):
        _analysis_fail("analysis_policy_value_invalid", "horizons")
    forbidden_inputs = _analysis_sequence(policy["forbidden_inputs"], "forbidden_inputs")
    if forbidden_inputs != _ANALYSIS_FORBIDDEN_INPUTS:
        _analysis_fail("analysis_policy_forbidden_input_mismatch")
    forbidden_roles = _analysis_sequence(policy["forbidden_roles"], "forbidden_roles")
    if forbidden_roles != _ANALYSIS_FORBIDDEN_ROLES:
        _analysis_fail("analysis_policy_forbidden_role_mismatch")
    ridges = _analysis_sequence(policy["ridge_grid"], "ridge_grid")
    if not ridges:
        _analysis_fail("analysis_policy_ridge_invalid")
    normalized_ridges: list[float] = []
    for ridge in ridges:
        if isinstance(ridge, bool) or not isinstance(ridge, (int, float)):
            _analysis_fail("analysis_policy_ridge_invalid")
        number = float(ridge)
        if not math.isfinite(number) or number < 0.0:
            _analysis_fail("analysis_policy_ridge_invalid")
        normalized_ridges.append(number)
    if normalized_ridges != sorted(set(normalized_ridges)):
        _analysis_fail("analysis_policy_ridge_invalid")
    if (
        approval_status == "pending_d23"
        and tuple(normalized_ridges) != (1e-08, 1e-06, 1e-04, 1e-02)
    ):
        _analysis_fail("analysis_policy_ridge_invalid")

    bootstrap = _analysis_exact(
        policy["bootstrap"],
        _ANALYSIS_BOOTSTRAP_FIELDS_V2
        if version == ANALYSIS_POLICY_VERSION_V2
        else _ANALYSIS_BOOTSTRAP_FIELDS_V1,
        "bootstrap",
    )
    alpha = _analysis_number(bootstrap["alpha"], "bootstrap.alpha")
    if not 0.0 < alpha < 1.0:
        _analysis_fail("analysis_policy_value_invalid", "bootstrap.alpha")
    if (
        isinstance(bootstrap["resamples"], bool)
        or not isinstance(bootstrap["resamples"], int)
        or bootstrap["resamples"] <= 0
        or isinstance(bootstrap["seed"], bool)
        or not isinstance(bootstrap["seed"], int)
        or bootstrap["unit"] != "episode_block"
    ):
        _analysis_fail("analysis_policy_value_invalid", "bootstrap")
    if version == ANALYSIS_POLICY_VERSION_V2:
        if (
            bootstrap["aggregate"] != "equal_configuration_macro"
            or bootstrap["configuration_sampling"] != "fixed_exact_eight"
            or bootstrap["pairing"]
            != "paired_by_configuration_role_family_repetition"
            or bootstrap["population_scope"] != "supported_exact_eight_only"
            or bootstrap["stratify_by"] != "configuration"
        ):
            _analysis_fail("analysis_policy_value_invalid", "bootstrap")
        outer_fold = _analysis_exact(
            policy["outer_fold_execution"],
            _ANALYSIS_OUTER_FOLD_FIELDS,
            "outer_fold_execution",
        )
        if outer_fold != {
            "candidate_selection": "seven_source_fit_validation_only",
            "holdout_unit": "configuration",
            "normalization": "seven_source_only",
            "primary_heldout_access": "final_test_only",
            "primary_model_freeze": "before_heldout_test_open",
        }:
            _analysis_fail("analysis_policy_value_invalid", "outer_fold_execution")

    algorithm = _analysis_exact(
        policy["inner_decision_algorithm"],
        _ANALYSIS_ALGORITHM_FIELDS_V2
        if version == ANALYSIS_POLICY_VERSION_V2
        else _ANALYSIS_ALGORITHM_FIELDS_V1,
        "inner_decision_algorithm",
    )
    if (
        algorithm["name"] != "lexicographic-paired-source-validation-v1"
        or algorithm["primary_metric"] != "full_equal_configuration_macro"
        or _analysis_sequence(algorithm["tie_break_order"], "tie_break_order")
        != _ANALYSIS_TIE_BREAK_ORDER
    ):
        _analysis_fail("analysis_policy_value_invalid", "inner_decision_algorithm")
    if version == ANALYSIS_POLICY_VERSION_V2:
        source_score = _analysis_exact(
            algorithm["source_score"],
            _ANALYSIS_SOURCE_SCORE_FIELDS_V2,
            "inner_decision_algorithm.source_score",
        )
        denominator_zero = _analysis_exact(
            source_score["denominator_zero"],
            _ANALYSIS_DENOMINATOR_ZERO_FIELDS_V2,
            "inner_decision_algorithm.source_score.denominator_zero",
        )
        if source_score != {
            "aggregation": "equal_configuration_macro",
            "baseline_reference": "minimum_error",
            "denominator_zero": denominator_zero,
            "direction": "lower_is_better",
            "group_reduction": "maximum",
            "horizon": "full",
            "name": "robust_relative_max_ratio_v1",
            "primary_metric_groups": list(SOURCE_SCORE_PRIMARY_METRICS_V2),
        } or denominator_zero != {
            "candidate_positive": "candidate_ineligible",
            "candidate_zero": "ratio_one",
        }:
            _analysis_fail(
                "analysis_policy_value_invalid",
                "inner_decision_algorithm.source_score",
            )

    metric = _analysis_exact(
        policy["metric_schema"], _ANALYSIS_METRIC_FIELDS, "metric_schema"
    )
    if (
        _analysis_sequence(metric["aggregation"], "metric_schema.aggregation")
        != (
            "per_configuration",
            "equal_configuration_macro",
            "worst_configuration",
        )
        or metric["official_orientation"] != "so3_geodesic_radians"
        or metric["row_weighted"] != "diagnostic_only"
        or metric["version"] != "phase8-episode-metrics-v1"
    ):
        _analysis_fail("analysis_policy_value_invalid", "metric_schema")

    gates = _analysis_exact(
        policy["gate_template"], _ANALYSIS_GATE_FIELDS, "gate_template"
    )
    for name in (
        "conditional_margin_fraction",
        "minimum_improvement_fraction",
        "noninferiority_fraction",
    ):
        _analysis_number(gates[name], f"gate_template.{name}")
    for name in ("divergence_max", "invalid_quaternion_max", "nonfinite_max"):
        if gates[name] != 0:
            _analysis_fail("analysis_policy_value_invalid", f"gate_template.{name}")

    reference = _analysis_exact(
        policy["reference_diagnostic"],
        _ANALYSIS_REFERENCE_FIELDS,
        "reference_diagnostic",
    )
    expected_reference_enabled = version == ANALYSIS_POLICY_VERSION_V1
    if reference["enabled"] is not expected_reference_enabled:
        _analysis_fail(
            "reference_diagnostic_not_disabled"
            if version == ANALYSIS_POLICY_VERSION_V2
            else "reference_diagnostic_not_eligible"
        )
    if (
        reference["model_id"] != "reference_conditioned_diagnostic_v2"
        or reference["namespace"] != "diagnostic/reference_conditioned_v2"
        or reference["selection_eligible"] is not False
    ):
        _analysis_fail("reference_diagnostic_not_eligible")


def build_recommended_analysis_policy_v1() -> dict[str, Any]:
    """Return the exact pending D-23 analysis proposal without approval claims."""
    policy = {
        "analysis_policy_version": ANALYSIS_POLICY_VERSION_V2,
        "approval_status": "pending_d23",
        "backend": "controlled_edmd_v2",
        "bootstrap": {
            "alpha": 0.05,
            "aggregate": "equal_configuration_macro",
            "configuration_sampling": "fixed_exact_eight",
            "pairing": "paired_by_configuration_role_family_repetition",
            "population_scope": "supported_exact_eight_only",
            "resamples": 2000,
            "seed": 80304,
            "stratify_by": "configuration",
            "unit": "episode_block",
        },
        "data_prefixes": [2, 4, 6],
        "forbidden_inputs": list(_ANALYSIS_FORBIDDEN_INPUTS),
        "forbidden_roles": list(_ANALYSIS_FORBIDDEN_ROLES),
        "gate_template": {
            "conditional_margin_fraction": 0.05,
            "divergence_max": 0,
            "invalid_quaternion_max": 0,
            "minimum_improvement_fraction": 0.01,
            "nonfinite_max": 0,
            "noninferiority_fraction": 0.1,
        },
        "horizons": [5, 20, 60, "full"],
        "inner_decision_algorithm": {
            "name": "lexicographic-paired-source-validation-v1",
            "primary_metric": "full_equal_configuration_macro",
            "source_score": {
                "aggregation": "equal_configuration_macro",
                "baseline_reference": "minimum_error",
                "denominator_zero": {
                    "candidate_positive": "candidate_ineligible",
                    "candidate_zero": "ratio_one",
                },
                "direction": "lower_is_better",
                "group_reduction": "maximum",
                "horizon": "full",
                "name": "robust_relative_max_ratio_v1",
                "primary_metric_groups": list(SOURCE_SCORE_PRIMARY_METRICS_V2),
            },
            "tie_break_order": list(_ANALYSIS_TIE_BREAK_ORDER),
        },
        "metric_schema": {
            "aggregation": [
                "per_configuration",
                "equal_configuration_macro",
                "worst_configuration",
            ],
            "official_orientation": "so3_geodesic_radians",
            "row_weighted": "diagnostic_only",
            "version": "phase8-episode-metrics-v1",
        },
        "normalization_candidates": ["none", "standard_v1"],
        "observable_candidates": ["identity_v1", "auv_kinematic_v1"],
        "outer_fold_execution": {
            "candidate_selection": "seven_source_fit_validation_only",
            "holdout_unit": "configuration",
            "normalization": "seven_source_only",
            "primary_heldout_access": "final_test_only",
            "primary_model_freeze": "before_heldout_test_open",
        },
        "platform_schema_candidates": [
            "none",
            "platform_physical_compact_v1",
            "platform_physical_core_v1",
        ],
        "qualification_level": "local_contract",
        "reference_diagnostic": {
            "enabled": False,
            "model_id": "reference_conditioned_diagnostic_v2",
            "namespace": "diagnostic/reference_conditioned_v2",
            "selection_eligible": False,
        },
        "ridge_grid": [1e-08, 1e-06, 1e-04, 1e-02],
    }
    validate_analysis_policy_v1(policy)
    return policy


def _freeze_analysis_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen: dict[str, Any] = {}
    for key, nested in value.items():
        if isinstance(nested, Mapping):
            frozen[str(key)] = _freeze_analysis_mapping(nested)
        elif isinstance(nested, Sequence) and not isinstance(nested, (str, bytes)):
            frozen[str(key)] = tuple(nested)
        else:
            frozen[str(key)] = nested
    return MappingProxyType(frozen)


@dataclass(frozen=True)
class AnalysisPolicyV2:
    data_prefixes: tuple[int, ...]
    observable_candidates: tuple[str, ...]
    ridge_grid: tuple[float, ...]
    normalization_candidates: tuple[str, ...]
    platform_schema_candidates: tuple[str, ...]
    horizons: tuple[int | str, ...]
    bootstrap: Mapping[str, Any]
    inner_decision_algorithm: Mapping[str, Any]
    metric_schema: Mapping[str, Any]
    outer_fold_execution: Mapping[str, Any]
    gate_template: Mapping[str, Any]
    forbidden_inputs: tuple[str, ...]
    forbidden_roles: tuple[str, ...]
    reference_diagnostic: Mapping[str, Any]
    approval_status: str
    qualification_level: str
    backend: str
    version: str = ANALYSIS_POLICY_VERSION_V2
    policy_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_prefixes", tuple(self.data_prefixes))
        object.__setattr__(self, "observable_candidates", tuple(self.observable_candidates))
        object.__setattr__(self, "ridge_grid", tuple(float(item) for item in self.ridge_grid))
        object.__setattr__(self, "normalization_candidates", tuple(self.normalization_candidates))
        object.__setattr__(self, "platform_schema_candidates", tuple(self.platform_schema_candidates))
        object.__setattr__(self, "horizons", tuple(self.horizons))
        object.__setattr__(self, "forbidden_inputs", tuple(self.forbidden_inputs))
        object.__setattr__(self, "forbidden_roles", tuple(self.forbidden_roles))
        for name in (
            "bootstrap",
            "inner_decision_algorithm",
            "metric_schema",
            "outer_fold_execution",
            "gate_template",
            "reference_diagnostic",
        ):
            object.__setattr__(self, name, _freeze_analysis_mapping(getattr(self, name)))
        validate_analysis_policy_v1(self.to_dict())
        from koopman.evidence_v2 import canonical_sha256

        object.__setattr__(self, "policy_sha256", canonical_sha256(self.to_dict()))

    def to_dict(self) -> dict[str, Any]:
        def thaw(value: Any) -> Any:
            if isinstance(value, Mapping):
                return {key: thaw(nested) for key, nested in value.items()}
            if isinstance(value, tuple):
                return [thaw(item) for item in value]
            return value

        payload = {
            "analysis_policy_version": self.version,
            "approval_status": self.approval_status,
            "backend": self.backend,
            "bootstrap": thaw(self.bootstrap),
            "data_prefixes": list(self.data_prefixes),
            "forbidden_inputs": list(self.forbidden_inputs),
            "forbidden_roles": list(self.forbidden_roles),
            "gate_template": thaw(self.gate_template),
            "horizons": list(self.horizons),
            "inner_decision_algorithm": thaw(self.inner_decision_algorithm),
            "metric_schema": thaw(self.metric_schema),
            "normalization_candidates": list(self.normalization_candidates),
            "observable_candidates": list(self.observable_candidates),
            "platform_schema_candidates": list(self.platform_schema_candidates),
            "qualification_level": self.qualification_level,
            "reference_diagnostic": thaw(self.reference_diagnostic),
            "ridge_grid": list(self.ridge_grid),
        }
        if self.version == ANALYSIS_POLICY_VERSION_V2:
            payload["outer_fold_execution"] = thaw(self.outer_fold_execution)
        return payload


def analysis_policy_from_mapping_v1(value: Any) -> AnalysisPolicyV2:
    validate_analysis_policy_v1(value)
    assert isinstance(value, Mapping)
    return AnalysisPolicyV2(
        data_prefixes=tuple(value["data_prefixes"]),
        observable_candidates=tuple(value["observable_candidates"]),
        ridge_grid=tuple(value["ridge_grid"]),
        normalization_candidates=tuple(value["normalization_candidates"]),
        platform_schema_candidates=tuple(value["platform_schema_candidates"]),
        horizons=tuple(value["horizons"]),
        bootstrap=dict(value["bootstrap"]),
        inner_decision_algorithm=dict(value["inner_decision_algorithm"]),
        metric_schema=dict(value["metric_schema"]),
        outer_fold_execution=dict(value.get("outer_fold_execution", {})),
        gate_template=dict(value["gate_template"]),
        forbidden_inputs=tuple(value["forbidden_inputs"]),
        forbidden_roles=tuple(value["forbidden_roles"]),
        reference_diagnostic=dict(value["reference_diagnostic"]),
        approval_status=str(value["approval_status"]),
        qualification_level=str(value["qualification_level"]),
        backend=str(value["backend"]),
        version=str(value["analysis_policy_version"]),
    )


def load_analysis_policy_v1(path: str | Path) -> AnalysisPolicyV2:
    policy_path = Path(path)
    if policy_path.is_symlink() or not policy_path.exists() or not policy_path.is_file():
        _analysis_fail("analysis_policy_artifact_invalid", str(policy_path))
    raw = policy_path.read_bytes()
    if len(raw) > MAX_ANALYSIS_POLICY_BYTES:
        _analysis_fail("analysis_policy_artifact_too_large")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, nested in values:
            if key in result:
                _analysis_fail("analysis_policy_duplicate_json_key", key)
            result[key] = nested
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda constant: _analysis_fail(
                "analysis_policy_nonfinite_json", constant
            ),
        )
    except UnicodeDecodeError as exc:
        raise ValueError("analysis_policy_artifact_not_utf8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"analysis_policy_json_invalid:{exc.msg}") from exc
    return analysis_policy_from_mapping_v1(value)

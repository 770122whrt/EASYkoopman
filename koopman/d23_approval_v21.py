"""Phase 8.1 pending-protocol and D-23 decision-binding contracts.

The approval record implemented here binds exact protocol bytes, an explicit
decision, and the stable experiment identifier.  It deliberately provides no
human identity assurance and this module never creates an approved record.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any

from koopman.contracts_v21 import (
    CONDITIONING_STRUCTURED_PCA2_V21,
    FINAL_REFIT_ALL8_SCOPE_V21,
    LOCO_SOURCE7_SCOPE_V21,
    SERVER_ARTIFACT_ORIGIN_V21,
    official_rollout_policy_payload_v21,
)
from koopman.evidence_v2 import canonical_json_bytes, canonical_sha256


EXPERIMENT_ID_V21 = "phase8.1-main-identification-v1"
TRANSITION_VERSION_V21 = "easyuuv-koopman-transition-v2.1"
ROLE_PROTOCOL_VERSION_V21 = "phase8.1-main-role-protocol-v1"
ANALYSIS_POLICY_VERSION_V21 = "phase8.1-analysis-policy-v1"
APPROVAL_RECORD_VERSION_V21 = "phase8.1-d23-approval-v1"
ATTESTATION_SCOPE_V21 = "protocol_hash_decision_binding_only"
IDENTITY_ASSURANCE_V21 = "none"
REPOSITORY_ROOT_V21 = Path(__file__).resolve().parents[1]
CANONICAL_ROLE_PROTOCOL_PATH_V21 = (
    REPOSITORY_ROOT_V21
    / "protocols"
    / "phase8_1"
    / "main_role_assignment_protocol.json"
)
CANONICAL_ANALYSIS_POLICY_PATH_V21 = (
    REPOSITORY_ROOT_V21 / "protocols" / "phase8_1" / "analysis_policy.json"
)
CANONICAL_APPROVAL_RECORD_PATH_V21 = (
    REPOSITORY_ROOT_V21 / "protocols" / "phase8_1" / "d23_approval.json"
)
PUBLIC_CONFIGURATIONS_V21 = (
    "base",
    "long_body",
    "heavy_moderate",
    "asymmetric",
    "uuv6",
    "uuv6_angled",
    "uuv4",
    "uuv4_angled",
)
EXCITATION_FAMILIES_V21 = (
    "independent_prbs",
    "bounded_multisine",
    "coupled_chirp",
)
PRIMARY_METRICS_V21 = (
    "depth_rmse",
    "linear_velocity_rmse",
    "angular_velocity_rmse",
    "so3_geodesic_mean_radians",
    "so3_geodesic_rmse_radians",
    "so3_geodesic_max_radians",
)
MAX_PROTOCOL_BYTES_V21 = 2 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_APPROVAL_FIELDS = frozenset(
    {
        "analysis_policy_sha256",
        "approval_record_version",
        "attestation_scope",
        "decision",
        "experiment_id",
        "identity_assurance",
        "role_protocol_sha256",
    }
)
_ROLE_FIELDS = frozenset(
    {
        "approval_status",
        "actuator_memory_initial_value_4",
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
        "timing_contract",
        "transition_count",
        "transition_schema_version",
        "unrecorded_warmup_control_intervals",
    }
)
_ENTRY_FIELDS = frozenset(
    {
        "configuration",
        "episode_id",
        "excitation_family",
        "excitation_seed",
        "manifest_path",
        "repetition",
        "role",
        "scenario",
        "seed",
        "transition_count",
        "transition_path",
    }
)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key", key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    _fail("nonfinite_json_constant", value)


def _load_json(path: str | Path) -> dict[str, Any]:
    artifact = Path(path)
    if not artifact.is_file():
        _fail("d23_approval_required", str(artifact))
    raw = artifact.read_bytes()
    if not raw or len(raw) > MAX_PROTOCOL_BYTES_V21:
        _fail("json_size_invalid", str(artifact))
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise ValueError("json_utf8_invalid") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("json_decode_invalid") from exc
    if not isinstance(payload, dict):
        _fail("json_object_required")
    return payload


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _require_canonical_path(
    supplied: str | Path, canonical: str | Path, *, path_kind: str
) -> Path:
    supplied_absolute = Path(os.path.abspath(Path(supplied).expanduser()))
    canonical_absolute = Path(os.path.abspath(Path(canonical).expanduser()))
    if supplied_absolute != canonical_absolute:
        _fail("d23_canonical_path_required", path_kind)
    return canonical_absolute


def _whole_second_utc(value: Any, path: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail("timestamp_invalid", path)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"timestamp_invalid:{path}") from exc
    if parsed.tzinfo != timezone.utc or parsed.microsecond != 0:
        _fail("timestamp_invalid", path)


def _excitation_seed(role: str, repetition: int) -> int:
    if role == "fit":
        return 8200 + repetition
    if role == "validation":
        return 8301
    if role == "test":
        return 8401
    _fail("role_assignment_drift", role)


def _environment_seed(role: str, family: str, repetition: int) -> int:
    family_index = EXCITATION_FAMILIES_V21.index(family) + 1
    base = {"fit": 9200, "validation": 9300, "test": 9400}.get(role)
    if base is None:
        _fail("role_assignment_drift", role)
    return base + 10 * family_index + repetition


def _role_entries() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for configuration in PUBLIC_CONFIGURATIONS_V21:
        for role in ("fit", "validation", "test"):
            repetitions = 2 if role == "fit" else 1
            for family in EXCITATION_FAMILIES_V21:
                for repetition in range(1, repetitions + 1):
                    excitation_seed = _excitation_seed(role, repetition)
                    seed = _environment_seed(role, family, repetition)
                    episode_id = (
                        f"phase8.1-main-{configuration}-{role}-"
                        f"{family.replace('_', '-')}-r{repetition}-"
                        f"es{excitation_seed}-rs{seed}"
                    )
                    result.append(
                        {
                            "configuration": configuration,
                            "episode_id": episode_id,
                            "excitation_family": family,
                            "excitation_seed": excitation_seed,
                            "manifest_path": f"manifests/{episode_id}.manifest.json",
                            "repetition": repetition,
                            "role": role,
                            "scenario": f"phase8.1-main-{family.replace('_', '-')}",
                            "seed": seed,
                            "transition_count": 512,
                            "transition_path": f"episodes/{episode_id}.jsonl",
                        }
                    )
    return result


def build_role_protocol_proposal_v21(*, frozen_at: str) -> dict[str, Any]:
    _whole_second_utc(frozen_at, "frozen_at")
    return {
        "actuator_memory_initial_value_4": [0.0, 0.0, 0.0, 0.0],
        "approval_status": "pending_d23",
        "artifact_origin_level": SERVER_ARTIFACT_ORIGIN_V21,
        "controller_mode": "deterministic_bounded_excitation",
        "entries": _role_entries(),
        "environment_contract": {
            "disturbance_mode": "none",
            "domain_randomization_enabled": False,
            "eval_mode": True,
            "reference_mode": "step",
            "sensor_noise_enabled": False,
        },
        "experiment_id": EXPERIMENT_ID_V21,
        "frozen_at": frozen_at,
        "proposal_only": True,
        "protocol_version": ROLE_PROTOCOL_VERSION_V21,
        "raw_action_abs_max": 0.25,
        "seed_semantics": {
            "environment_seed_controls": ["environment_reset", "goal_reference"],
            "environment_seed_field": "seed",
            "environment_seed_scope": "matched_across_configurations_by_role_family_repetition",
            "excitation_seed_field": "excitation_seed",
            "excitation_seed_scope": "matched_across_configurations_by_role_repetition",
        },
        "task_id": "EasyUUV-Direct-v1",
        "timing_contract": {
            "control_dt_s": 1.0 / 60.0,
            "decimation": 2,
            "physics_dt_s": 1.0 / 120.0,
        },
        "transition_count": 512,
        "transition_schema_version": TRANSITION_VERSION_V21,
        "unrecorded_warmup_control_intervals": 0,
    }


def validate_role_protocol_proposal_v21(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _ROLE_FIELDS:
        _fail("role_protocol_field_set_mismatch")
    expected = build_role_protocol_proposal_v21(frozen_at=str(value["frozen_at"]))
    if dict(value) != expected:
        _fail("role_protocol_value_mismatch")
    timing = value["timing_contract"]
    if (
        not isinstance(timing["decimation"], int)
        or isinstance(timing["decimation"], bool)
        or timing["decimation"] <= 0
        or timing["physics_dt_s"] <= 0.0
        or timing["control_dt_s"] <= 0.0
        or timing["control_dt_s"]
        != timing["physics_dt_s"] * timing["decimation"]
    ):
        _fail("timing_contract_mismatch")
    entries = value["entries"]
    if not isinstance(entries, Sequence) or len(entries) != 96:
        _fail("role_protocol_matrix_mismatch")
    if any(not isinstance(entry, Mapping) or set(entry) != _ENTRY_FIELDS for entry in entries):
        _fail("role_protocol_entry_field_set_mismatch")


def build_analysis_policy_proposal_v21() -> dict[str, Any]:
    rollout_policy = official_rollout_policy_payload_v21()
    return {
        "allowed_claims": [
            "fixed_exact_eight_catalog_new_episode_loco_prediction_evaluation"
        ],
        "analysis_policy_version": ANALYSIS_POLICY_VERSION_V21,
        "approval_status": "pending_d23",
        "backend": "controlled_edmd_so3_v21",
        "bootstrap": {
            "aggregate": "equal_configuration_macro",
            "alpha": 0.05,
            "configuration_sampling": "fixed_exact_eight",
            "pairing": "paired_by_configuration_role_family_repetition",
            "population_scope": "supported_exact_eight_only",
            "resamples": 2000,
            "seed": 80304,
            "stratify_by": "configuration",
            "unit": "episode_block",
        },
        "candidate_ledger": {
            "artifact": "source_candidate_ledger.json",
            "include_failed_candidates": True,
            "sealed_before_primary_freeze": True,
        },
        "conditional": {
            "conditioning_id": CONDITIONING_STRUCTURED_PCA2_V21,
            "descriptor_rank": 2,
            "design_layout": [
                "phi_observable",
                "z1",
                "z2",
                "z1_x_phi_linear_nonbias",
                "z2_x_phi_linear_nonbias",
            ],
            "design_rank_required": "full_width",
            "design_widths": {
                "so3_identity_v1": 66,
                "so3_kinematic_v1": 100,
            },
            "effective_rank": "diagnostic_only",
            "fold_population_scope": LOCO_SOURCE7_SCOPE_V21,
            "heldout_descriptor_in_pca": False,
            "pca_whitening": False,
            "physical_descriptor": "platform_physical_core_v1",
            "regularized_condition_max": 1.0e8,
        },
        "d23_approval": {
            "approval_record_version": APPROVAL_RECORD_VERSION_V21,
            "attestation_scope": ATTESTATION_SCOPE_V21,
            "canonical_approval_record_path": "protocols/phase8_1/d23_approval.json",
            "identity_assurance": IDENTITY_ASSURANCE_V21,
            "required_before_formal_entrypoint": True,
        },
        "data_prefixes": [2, 4, 6],
        "disallowed_claims": [
            "researcher_unseen_configuration",
            "arbitrary_auv_platform",
            "environment_transfer",
            "closed_loop_control_effectiveness",
            "hardware_or_sim2real",
            "agent_capability",
        ],
        "experiment_id": EXPERIMENT_ID_V21,
        "final_refit": {
            "allowed_input": "selected_family_only",
            "candidate_selection": "all_eight_fit_validation_same_inner_selector",
            "conditional_population_scope": FINAL_REFIT_ALL8_SCOPE_V21,
            "fit_roles": ["fit", "validation"],
            "publication": "atomic_after_save_load_roundtrip",
            "test_read_count": 0,
        },
        "forbidden_inputs": [
            "reference_5",
            "motor_pwm_padded_8",
            "thruster_mask_8",
            "applied_wrench_6",
            "environment_context_oracle",
            "environment_context_estimated",
            "simulator_actuator_truth",
            "configuration_identity",
            "heldout_statistics",
            "future_actuator_memory_truth",
        ],
        "gate_template": {
            "conditional_margin_fraction": 0.05,
            "divergence_max": 0,
            "invalid_quaternion_max": 0,
            "minimum_improvement_fraction": 0.01,
            "nonfinite_max": 0,
            "noninferiority_fraction": 0.1,
        },
        "heldout_descriptor_diagnostic": {
            "artifact": "heldout_descriptor_diagnostic.json",
            "generated_after_primary_freeze": True,
            "selection_eligible": False,
        },
        "heldout_expert": {
            "candidate_selection": "heldout_fit_then_heldout_validation",
            "conditioning": "none",
            "failure_blocks_primary_test": False,
            "independent_namespace": True,
            "selection_eligible": False,
        },
        "horizons": [5, 20, 60, "full"],
        "inner_decision_algorithm": {
            "name": "lexicographic-paired-source-validation-v21",
            "source_score": {
                "aggregation": "unweighted_maximum",
                "baseline_reference": "minimum_error",
                "denominator_zero": {
                    "candidate_positive": "candidate_ineligible",
                    "candidate_zero": "ratio_one",
                },
                "direction": "lower_is_better",
                "horizon": "full",
                "primary_metrics": list(PRIMARY_METRICS_V21),
            },
            "tie_break_order": [
                "source_score",
                "data_prefix",
                "observable_order",
                "ridge_order",
                "normalization_order",
                "family_order",
            ],
        },
        "input_contract": {
            "dimension": 19,
            "fields": ["state_11", "actuator_memory_4", "virtual_control_4"],
            "transition_schema_version": TRANSITION_VERSION_V21,
        },
        "metric_schema": {
            "aggregation": [
                "per_configuration",
                "equal_configuration_macro",
                "worst_configuration",
            ],
            "official_orientation": "so3_geodesic_radians",
            "primary_metrics": list(PRIMARY_METRICS_V21),
            "row_weighted": "diagnostic_only",
        },
        "normalization_candidates": ["none", "standard_v1"],
        "observable_candidates": ["so3_identity_v1", "so3_kinematic_v1"],
        "observable_widths": {
            "so3_identity_v1": 22,
            "so3_kinematic_v1": 56,
        },
        "outer_fold_execution": {
            "candidate_selection": "seven_source_fit_validation_only",
            "holdout_unit": "configuration",
            "primary_heldout_access": "after_primary_and_expert_freeze_only",
            "primary_model_freeze": "before_heldout_descriptor_and_test",
        },
        "proposal_only": True,
        "reference_diagnostic": {"enabled": False, "selection_eligible": False},
        "ridge_grid": [1.0e-8, 1.0e-6, 1.0e-4, 1.0e-2],
        "rollout_policy": rollout_policy,
        "rollout_policy_sha256": canonical_sha256(rollout_policy),
        "source_per_configuration": "report_all_no_ranking",
    }


def validate_analysis_policy_proposal_v21(value: Any) -> None:
    if not isinstance(value, Mapping):
        _fail("analysis_policy_field_set_mismatch")
    expected = build_analysis_policy_proposal_v21()
    if dict(value) != expected:
        _fail("analysis_policy_value_mismatch")


def validate_d23_approval_v21(
    value: Any,
    *,
    role_protocol_path: str | Path,
    analysis_policy_path: str | Path,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _APPROVAL_FIELDS:
        _fail("d23_approval_field_set_mismatch")
    record = dict(value)
    if record["approval_record_version"] != APPROVAL_RECORD_VERSION_V21:
        _fail("d23_approval_record_version_mismatch")
    if record["attestation_scope"] != ATTESTATION_SCOPE_V21:
        _fail("d23_attestation_scope_mismatch")
    if record["decision"] != "approved":
        _fail("d23_approval_decision_invalid")
    if record["experiment_id"] != EXPERIMENT_ID_V21:
        _fail("d23_approval_experiment_mismatch")
    if record["identity_assurance"] != IDENTITY_ASSURANCE_V21:
        _fail("d23_identity_assurance_mismatch")
    role_path = Path(role_protocol_path)
    policy_path = Path(analysis_policy_path)
    for name, path in (("role", role_path), ("analysis", policy_path)):
        if not path.is_file():
            _fail(f"d23_{name}_protocol_missing")
    role_payload = _load_json(role_path)
    policy_payload = _load_json(policy_path)
    for name, payload in (("role", role_payload), ("analysis", policy_payload)):
        if (
            payload.get("approval_status") != "pending_d23"
            or payload.get("proposal_only") is not True
            or payload.get("experiment_id") != EXPERIMENT_ID_V21
        ):
            _fail(f"d23_{name}_protocol_semantics_mismatch")
    expected_role = _sha256(role_path)
    expected_policy = _sha256(policy_path)
    if not isinstance(record["role_protocol_sha256"], str) or not _SHA256.fullmatch(
        record["role_protocol_sha256"]
    ) or record["role_protocol_sha256"] != expected_role:
        _fail("d23_role_protocol_hash_mismatch")
    if not isinstance(record["analysis_policy_sha256"], str) or not _SHA256.fullmatch(
        record["analysis_policy_sha256"]
    ) or record["analysis_policy_sha256"] != expected_policy:
        _fail("d23_analysis_policy_hash_mismatch")
    return record


def load_and_validate_d23_approval_v21(
    approval_record_path: str | Path,
    *,
    role_protocol_path: str | Path,
    analysis_policy_path: str | Path,
) -> dict[str, Any]:
    """Validate an explicit record/proposal set without granting formal access."""
    value = _load_json(approval_record_path)
    return validate_d23_approval_v21(
        value,
        role_protocol_path=role_protocol_path,
        analysis_policy_path=analysis_policy_path,
    )


def require_canonical_d23_approval_v21(
    approval_record_path: str | Path,
    *,
    role_protocol_path: str | Path,
    analysis_policy_path: str | Path,
) -> dict[str, Any]:
    """Authorize formal work only from the repository's canonical D-23 files."""
    approval = _require_canonical_path(
        approval_record_path,
        CANONICAL_APPROVAL_RECORD_PATH_V21,
        path_kind="approval_record",
    )
    role_protocol = _require_canonical_path(
        role_protocol_path,
        CANONICAL_ROLE_PROTOCOL_PATH_V21,
        path_kind="role_protocol",
    )
    analysis_policy = _require_canonical_path(
        analysis_policy_path,
        CANONICAL_ANALYSIS_POLICY_PATH_V21,
        path_kind="analysis_policy",
    )
    if not approval.is_file():
        _fail("d23_approval_required", str(approval))
    role_payload = _load_json(role_protocol)
    policy_payload = _load_json(analysis_policy)
    validate_role_protocol_proposal_v21(role_payload)
    validate_analysis_policy_proposal_v21(policy_payload)
    return load_and_validate_d23_approval_v21(
        approval,
        role_protocol_path=role_protocol,
        analysis_policy_path=analysis_policy,
    )


def write_protocol_proposals_v21(
    protocol_root: str | Path, *, frozen_at: str
) -> tuple[Path, Path]:
    """Write deterministic pending proposals.  Never writes an approval record."""
    root = Path(protocol_root)
    root.mkdir(parents=True, exist_ok=True)
    role_path = root / "main_role_assignment_protocol.json"
    policy_path = root / "analysis_policy.json"
    role_path.write_bytes(
        canonical_json_bytes(build_role_protocol_proposal_v21(frozen_at=frozen_at))
    )
    policy_path.write_bytes(canonical_json_bytes(build_analysis_policy_proposal_v21()))
    return role_path, policy_path

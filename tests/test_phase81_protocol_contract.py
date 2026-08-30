from __future__ import annotations

import hashlib
import json
from pathlib import Path

from koopman.d23_approval_v21 import (
    EXPERIMENT_ID_V21,
    validate_analysis_policy_proposal_v21,
    validate_role_protocol_proposal_v21,
)
from koopman.model_v21 import CONDITIONING_STRUCTURED_PCA2_V21
from koopman.metrics_v21 import OFFICIAL_ROLLOUT_POLICY_V21


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_ROOT = PROJECT_ROOT / "protocols" / "phase8_1"
ROLE_PATH = PROTOCOL_ROOT / "main_role_assignment_protocol.json"
POLICY_PATH = PROTOCOL_ROOT / "analysis_policy.json"
APPROVAL_PATH = PROTOCOL_ROOT / "d23_approval.json"
CONFIGURATIONS = (
    "base",
    "long_body",
    "heavy_moderate",
    "asymmetric",
    "uuv6",
    "uuv6_angled",
    "uuv4",
    "uuv4_angled",
)
PRIMARY_METRICS = (
    "depth_rmse",
    "linear_velocity_rmse",
    "angular_velocity_rmse",
    "so3_geodesic_mean_radians",
    "so3_geodesic_rmse_radians",
    "so3_geodesic_max_radians",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_pending_role_protocol_is_exact_eight_v21_and_timing_bound():
    payload = _load(ROLE_PATH)
    validate_role_protocol_proposal_v21(payload)

    assert payload["approval_status"] == "pending_d23"
    assert payload["proposal_only"] is True
    assert payload["experiment_id"] == EXPERIMENT_ID_V21
    assert payload["transition_schema_version"] == "easyuuv-koopman-transition-v2.1"
    assert payload["artifact_origin_level"] == "server_isaac_smoke"
    assert payload["actuator_memory_initial_value_4"] == [0.0, 0.0, 0.0, 0.0]
    assert payload["unrecorded_warmup_control_intervals"] == 0
    assert payload["timing_contract"] == {
        "control_dt_s": 1.0 / 60.0,
        "decimation": 2,
        "physics_dt_s": 1.0 / 120.0,
    }
    entries = payload["entries"]
    assert len(entries) == 96
    for configuration in CONFIGURATIONS:
        roles = [entry["role"] for entry in entries if entry["configuration"] == configuration]
        assert roles.count("fit") == 6
        assert roles.count("validation") == 3
        assert roles.count("test") == 3
    assert not APPROVAL_PATH.exists()


def test_analysis_policy_freezes_v21_without_promotion_drift():
    payload = _load(POLICY_PATH)
    validate_analysis_policy_proposal_v21(payload)

    assert payload["approval_status"] == "pending_d23"
    assert payload["proposal_only"] is True
    assert payload["experiment_id"] == EXPERIMENT_ID_V21
    assert payload["input_contract"]["dimension"] == 19
    assert payload["input_contract"]["fields"] == [
        "state_11",
        "actuator_memory_4",
        "virtual_control_4",
    ]
    assert payload["observable_candidates"] == ["so3_identity_v1", "so3_kinematic_v1"]
    assert payload["observable_widths"] == {
        "so3_identity_v1": 22,
        "so3_kinematic_v1": 56,
    }
    assert payload["conditional"]["descriptor_rank"] == 2
    assert payload["conditional"]["conditioning_id"] == CONDITIONING_STRUCTURED_PCA2_V21
    assert payload["conditional"]["fold_population_scope"] == "loco_source7"
    assert payload["conditional"]["design_widths"] == {
        "so3_identity_v1": 66,
        "so3_kinematic_v1": 100,
    }
    assert payload["conditional"]["regularized_condition_max"] == 1.0e8
    assert payload["inner_decision_algorithm"]["source_score"]["primary_metrics"] == list(PRIMARY_METRICS)
    assert payload["inner_decision_algorithm"]["source_score"]["aggregation"] == "unweighted_maximum"
    assert payload["inner_decision_algorithm"]["family_order"] == [
        "pooled",
        "conditional",
    ]
    assert payload["gate_template"] == {
        "conditional_margin_fraction": 0.05,
        "divergence_max": 0,
        "invalid_quaternion_max": 0,
        "minimum_improvement_fraction": 0.01,
        "nonfinite_max": 0,
        "noninferiority_fraction": 0.1,
    }
    assert payload["bootstrap"]["resamples"] == 2000
    assert payload["bootstrap"]["stratify_by"] == "configuration"
    assert payload["heldout_descriptor_diagnostic"]["selection_eligible"] is False
    assert payload["heldout_expert"]["selection_eligible"] is False
    assert payload["heldout_expert"]["nonpromoting"] is True
    assert payload["heldout_expert"]["data_prefixes"] == [2, 4, 6]
    assert payload["heldout_expert"]["observable_candidates"] == [
        "so3_identity_v1",
        "so3_kinematic_v1",
    ]
    assert payload["heldout_expert"]["ridge_grid"] == [1e-8, 1e-6, 1e-4, 1e-2]
    assert payload["heldout_expert"]["normalization_candidates"] == [
        "none",
        "standard_v1",
    ]
    assert payload["heldout_expert"]["source_score"] == payload[
        "inner_decision_algorithm"
    ]["source_score"]
    assert payload["source_per_configuration"] == "report_all_no_ranking"
    assert payload["final_refit"]["conditional_population_scope"] == "final_refit_all8"
    assert payload["rollout_policy"] == OFFICIAL_ROLLOUT_POLICY_V21.payload()
    assert (
        payload["rollout_policy_sha256"]
        == OFFICIAL_ROLLOUT_POLICY_V21.policy_sha256
    )
    assert payload["d23_approval"]["attestation_scope"] == "protocol_hash_decision_binding_only"
    assert payload["d23_approval"]["canonical_approval_record_path"] == (
        "protocols/phase8_1/d23_approval.json"
    )
    assert payload["d23_approval"]["identity_assurance"] == "none"


def test_proposal_hashes_are_file_byte_hashes_and_old_protocols_are_distinct():
    role_hash = hashlib.sha256(ROLE_PATH.read_bytes()).hexdigest()
    policy_hash = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
    assert len(role_hash) == len(policy_hash) == 64
    assert role_hash != hashlib.sha256(
        (PROJECT_ROOT / "protocols" / "phase8" / "main_role_assignment_protocol.json").read_bytes()
    ).hexdigest()
    assert policy_hash != hashlib.sha256(
        (PROJECT_ROOT / "protocols" / "phase8" / "analysis_policy.json").read_bytes()
    ).hexdigest()

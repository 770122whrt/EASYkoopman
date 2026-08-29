from __future__ import annotations

from dataclasses import FrozenInstanceError
import inspect
import json
from pathlib import Path

import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.evidence_v2 import canonical_json_bytes, file_sha256
from koopman.protocol_v2 import load_analysis_policy_v1


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = PROJECT_ROOT / "protocols" / "phase8" / "analysis_policy.json"
ROLE_PROTOCOL_SHA256 = "499b79089a4bfb0769ce6a902ad676f09e9c64190069a0bf5b51cd76f1d6cf26"
ROLES = (
    "persistence",
    "simple_linear_v2",
    "source_per_configuration_koopman_v2",
    "pooled_koopman_v2",
    "conditional_koopman_v2",
    "heldout_expert_upper_bound_v2",
)
HORIZONS = ("one_step", "5", "20", "60", "full")
METRICS = (
    "depth_rmse",
    "linear_velocity_rmse",
    "angular_velocity_rmse",
    "so3_geodesic_mean_radians",
    "so3_geodesic_rmse_radians",
    "so3_geodesic_max_radians",
)


def _horizon(scale: float) -> dict:
    return {
        "status": "success",
        "reason_code": None,
        "values": {name: scale for name in METRICS},
        "transition_count": 512,
        "window_count": 1,
        "nonfinite_count": 0,
        "invalid_quaternion_count": 0,
        "projection_failure_count": 0,
        "divergence_count": 0,
        "projection_count": 0,
        "projection_correction_max": 0.0,
    }


def _role(configuration: str, role: str, scale: float) -> dict:
    return {
        "role": role,
        "selection_eligible": role in {
            "pooled_koopman_v2",
            "conditional_koopman_v2",
        },
        "status": "success",
        "reason_code": None,
        "model_sha256": None if role == "persistence" else (role[0] * 64),
        "input_fields": (
            ["state_11", "virtual_control_4", "platform_physical_descriptor"]
            if role == "conditional_koopman_v2"
            else ["state_11", "virtual_control_4"]
        ),
        "episode_results": [
            {
                "configuration": configuration,
                "episode_id": f"phase8-main-{configuration}-test-family-{index}",
                "family_repetition": f"family-{index}",
                "horizons": {name: _horizon(scale) for name in HORIZONS},
            }
            for index in range(3)
        ],
    }


def _evaluation_payload() -> dict:
    policy = load_analysis_policy_v1(POLICY_PATH)
    role_scales = {
        "persistence": 1.0,
        "simple_linear_v2": 0.9,
        "source_per_configuration_koopman_v2": 0.8,
        "pooled_koopman_v2": 0.7,
        "conditional_koopman_v2": 0.69,
        "heldout_expert_upper_bound_v2": 0.5,
    }
    folds = []
    for configuration in SUPPORTED_EMBODIMENTS:
        sources = [name for name in SUPPORTED_EMBODIMENTS if name != configuration]
        candidate_id = (configuration[0] if configuration else "c") * 64
        decision_sha256 = (configuration[-1] if configuration else "d") * 64
        folds.append(
            {
                "fold_id": f"loco-holdout-{configuration}",
                "holdout_configuration": configuration,
                "source_configurations": sources,
                "source_episode_sha256s": [f"{index:064x}" for index in range(1, 64)],
                "decision": {
                    "candidate_id": candidate_id,
                    "decision_sha256": decision_sha256,
                    "test_open_count_at_seal": 0,
                },
                "pre_test_freeze": {
                    "state": "frozen",
                    "candidate_id": candidate_id,
                    "decision_sha256": decision_sha256,
                    "analysis_policy_sha256": policy.policy_sha256,
                    "source_configurations": sources,
                    "primary_model_sha256s": {
                        "simple_linear_v2": "s" * 64,
                        "source_per_configuration_koopman_v2": "r" * 64,
                        "pooled_koopman_v2": "p" * 64,
                        "conditional_koopman_v2": "c" * 64,
                    },
                    "candidate_revision": 0,
                    "model_revision": 0,
                    "test_open_count_at_freeze": 0,
                    "post_test_mutation_count": 0,
                },
                "test_access": {
                    "authorized_by_freeze": True,
                    "freeze_candidate_id": candidate_id,
                    "test_episode_ids": [
                        f"phase8-main-{configuration}-test-family-{index}"
                        for index in range(3)
                    ],
                },
                "roles": {
                    role: _role(configuration, role, role_scales[role])
                    for role in ROLES
                },
                "reference_diagnostic": {
                    "namespace": "diagnostic/reference_conditioned_v2",
                    "selection_eligible": False,
                    "status": "success",
                },
            }
        )
    return {
        "evaluation_version": "phase8-ood-evaluation-v1",
        "analysis_policy_sha256": policy.policy_sha256,
        "analysis_gate_template": dict(policy.gate_template),
        "bootstrap_policy": dict(policy.bootstrap),
        "role_protocol_sha256": ROLE_PROTOCOL_SHA256,
        "dataset_inventory_sha256": "d" * 64,
        "loco_split_sha256": "l" * 64,
        "folds": folds,
    }


def _write_envelope(tmp_path: Path, payload: dict) -> Path:
    root = tmp_path / "evaluation"
    root.mkdir()
    summary = root / "evaluation_summary.json"
    summary.write_bytes(canonical_json_bytes(payload))
    envelope = {
        "envelope_version": "phase8-evidence-envelope-v1",
        "experiment_id": "phase8-test-evaluation",
        "artifact_origin_level": "server_isaac_smoke",
        "qualification_level": "offline_koopman_ood_evaluation",
        "source_commit": "a" * 40,
        "protocol_sha256": ROLE_PROTOCOL_SHA256,
        "runtime_provenance": {},
        "runtime_sha256": "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b",
        "inventory_sha256": "d" * 64,
        "decision_sha256": file_sha256(summary),
        "referenced_files": [
            {
                "path": "evaluation_summary.json",
                "sha256": file_sha256(summary),
                "size_bytes": summary.stat().st_size,
            }
        ],
        "allowed_claims": ["heldout_configuration_prediction_evaluation"],
        "disallowed_claims": ["closed_loop_control_effectiveness"],
        "validator": {
            "name": "test_fixture",
            "external_validation": True,
            "status": "pass",
        },
    }
    path = root / "evaluation_envelope.json"
    path.write_bytes(canonical_json_bytes(envelope))
    return path


def test_exact_eight_selector_recomputes_gates_and_selects_pooled(tmp_path) -> None:
    from koopman.selection_v2 import select_phase8_candidate

    envelope = _write_envelope(tmp_path, _evaluation_payload())
    result = select_phase8_candidate(envelope, POLICY_PATH)

    assert result.status == "koopman_selection"
    assert result.selected_family == "pooled_koopman_v2"
    assert result.selected_model_path is None  # final refit is a separate test-free step
    assert result.family_diagnostics["pooled_koopman_v2"]["all_hard_gates_pass"] is True
    assert result.family_diagnostics["conditional_koopman_v2"]["baseline_gates_pass"] is True
    assert result.family_diagnostics["conditional_koopman_v2"]["conditional_margin_pass"] is False


def test_no_selection_is_reason_coded_and_has_no_model_path(tmp_path) -> None:
    from koopman.selection_v2 import select_phase8_candidate

    payload = _evaluation_payload()
    for fold in payload["folds"]:
        fold["roles"]["pooled_koopman_v2"] = _role(
            fold["holdout_configuration"], "pooled_koopman_v2", 1.2
        )
        fold["roles"]["conditional_koopman_v2"] = _role(
            fold["holdout_configuration"], "conditional_koopman_v2", 1.1
        )
    result = select_phase8_candidate(_write_envelope(tmp_path, payload), POLICY_PATH)

    assert result.status == "no_selection"
    assert result.selected_family is None
    assert result.selected_model_path is None
    assert "baseline_improvement_failed" in result.reason_codes


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda value: value["folds"].pop(), "fold_set_mismatch"),
        (
            lambda value: value["folds"][0]["roles"].pop("persistence"),
            "role_matrix_incomplete",
        ),
        (
            lambda value: value["folds"][0]["roles"]["pooled_koopman_v2"][
                "episode_results"
            ][0]["horizons"].pop("60"),
            "aggregate_horizon_set_mismatch",
        ),
        (
            lambda value: value["folds"][0]["pre_test_freeze"].update(
                post_test_mutation_count=1
            ),
            "post_test_retune",
        ),
        (
            lambda value: value["folds"][0]["pre_test_freeze"].update(
                candidate_id="f" * 64
            ),
            "freeze_candidate_mismatch",
        ),
        (
            lambda value: value["folds"][0]["roles"][
                "heldout_expert_upper_bound_v2"
            ].update(selection_eligible=True),
            "expert_promotion_forbidden",
        ),
        (
            lambda value: value["folds"][0]["roles"]["pooled_koopman_v2"].update(
                input_fields=["state_11", "virtual_control_4", "reference_5"]
            ),
            "model_input_forbidden",
        ),
        (
            lambda value: value["analysis_gate_template"].update(
                minimum_improvement_fraction=0.0
            ),
            "analysis_policy_drift",
        ),
    ],
)
def test_selector_rejects_incomplete_forged_or_leaky_evidence(
    tmp_path, mutation, reason
) -> None:
    from koopman.selection_v2 import select_phase8_candidate

    payload = _evaluation_payload()
    mutation(payload)
    with pytest.raises(ValueError, match=reason):
        select_phase8_candidate(_write_envelope(tmp_path, payload), POLICY_PATH)


def test_primary_freeze_is_immutable_and_required_before_test_access() -> None:
    from koopman.loco_v2 import FrozenPrimaryStateV2, authorize_primary_test_access_v2

    policy = load_analysis_policy_v1(POLICY_PATH)
    state = FrozenPrimaryStateV2(
        fold_id="loco-holdout-base",
        holdout_configuration="base",
        source_configurations=tuple(name for name in SUPPORTED_EMBODIMENTS if name != "base"),
        source_episode_sha256s=tuple(f"{index:064x}" for index in range(1, 64)),
        candidate_id="c" * 64,
        decision_sha256="d" * 64,
        analysis_policy_sha256=policy.policy_sha256,
        primary_model_sha256s={"pooled_koopman_v2": "p" * 64},
        frozen_at="2026-08-29T15:00:00Z",
    )
    token = authorize_primary_test_access_v2(
        state,
        analysis_policy=policy,
        fold_id=state.fold_id,
        holdout_configuration="base",
        test_episode_ids=("base-test-1", "base-test-2", "base-test-3"),
    )
    assert token.freeze_state_sha256 == state.freeze_state_sha256
    assert token.freeze_candidate_id == state.candidate_id
    with pytest.raises(FrozenInstanceError):
        state.candidate_id = "e" * 64


def test_final_refit_api_cannot_accept_test_results_or_test_episode_roles() -> None:
    from koopman.selection_v2 import FinalRefitEpisodeV2, refit_without_outer_test

    assert all("test" not in name.lower() for name in inspect.signature(refit_without_outer_test).parameters)
    with pytest.raises(ValueError, match="final_refit_test_access"):
        FinalRefitEpisodeV2(
            episode_id="base-test",
            configuration="base",
            role="test",
            transition_sha256="a" * 64,
            payload=object(),
        )

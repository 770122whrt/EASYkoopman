import json
from pathlib import Path

import pytest

from workflows.validate_phase5_1_stability_summary import validate_phase5_1_stability_summary


def valid_summary(checkpoint: Path) -> dict:
    return {
        "checkpoint_found": True,
        "selected_checkpoint": str(checkpoint),
        "selected_rule": "latest_valid_after_stability_validator",
        "checkpoint_provenance": "phase5_1_stability_candidate",
        "result_bucket": "retrained_ppo_koopman_mpc",
        "ppo_evidence_level": "stability_candidate",
        "controller_path": "koopman_mpc/direct_state",
        "adapter_mode": "heuristic_reference_delta_v0",
        "koopman_backend": "direct_state",
        "reward_profile": "legacy_easyuuv_v0",
        "observation_dim": 9,
        "action_dim": 4,
        "adapter_refresh_count": 12,
        "adapter_refresh_before_env_step": True,
        "policy_action_clip_rate": 0.1,
        "training_loop_fallback_rate": 0.0,
        "training_loop_latency_ms_mean": 12.0,
        "training_loop_latency_ms_max": 18.0,
        "training_loop_pwm_min": -0.5,
        "training_loop_pwm_max": 0.5,
        "nonfinite_observation_count": 0,
        "nonfinite_action_count": 0,
        "nonfinite_reward_count": 0,
        "completion_status": "completed",
        "training_reference_source": "env_goal_quat_plus_zero_depth",
        "depth_reference_source": "zero_depth_default",
        "selected_weight_status": "candidate_only",
    }


def write_summary(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_validate_phase5_1_stability_summary_accepts_valid_candidate(tmp_path):
    checkpoint = tmp_path / "model_25.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = write_summary(tmp_path / "summary.json", valid_summary(checkpoint))

    result = validate_phase5_1_stability_summary(summary_path)

    assert result["stable_training_gate"] == "pass"
    assert result["selected_weight_status"] == "candidate_only"
    assert result["warnings"] == []


def test_validate_phase5_1_stability_summary_hard_fails_nonfinite_counts(tmp_path):
    checkpoint = tmp_path / "model_25.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    payload = valid_summary(checkpoint)
    payload["nonfinite_action_count"] = 1
    summary_path = write_summary(tmp_path / "summary.json", payload)

    with pytest.raises(ValueError, match="nonfinite_action_count"):
        validate_phase5_1_stability_summary(summary_path)


def test_validate_phase5_1_stability_summary_warns_without_hard_failure(tmp_path):
    checkpoint = tmp_path / "model_25.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    payload = valid_summary(checkpoint)
    payload["training_loop_fallback_rate"] = 0.25
    summary_path = write_summary(tmp_path / "summary.json", payload)

    result = validate_phase5_1_stability_summary(summary_path)

    assert result["stable_training_gate"] == "pass_with_warnings"
    assert "training_loop_fallback_rate" in result["warnings"][0]

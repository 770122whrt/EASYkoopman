import json
from pathlib import Path

import pytest

from workflows.validate_phase5_4_checkpoint_provenance import validate_phase5_4_checkpoint_provenance


def write_phase5_4_summary(path: Path, checkpoint: Path, **overrides):
    payload = {
        "checkpoint_found": True,
        "checkpoint_path": str(checkpoint),
        "selected_checkpoint": str(checkpoint),
        "selected_rule": "latest_valid_after_phase5_4_pareto_validator",
        "checkpoint_provenance": "phase5_4_pareto_candidate",
        "result_bucket": "retrained_ppo_koopman_mpc",
        "ppo_evidence_level": "phase5_4_pareto_candidate",
        "controller_path": "koopman_mpc/direct_state",
        "adapter_mode": "heuristic_reference_delta_v0",
        "koopman_backend": "direct_state",
        "profile_id": "r_pwm030",
        "phase5_4_track": "R",
        "reward_profile": "koopman_mpc_stability_v1",
        "adapter_profile": "heuristic_reference_delta_v0_default",
        "mpc_profile": "mpc_default_v0",
        "changed_axis": "reward",
        "sweep_round": "round1",
        "parent_profile_id": "reward_v1_only",
        "parameter_distance_from_parent": 2.0,
        "changed_parameter_count": 1,
        "parameter_step_count": {"phase5_2_w_pwm_sat": 2.0},
        "protected_strengths": ["reward_v1_fallback"],
        "training_ladder_stage": "candidate",
        "comparison_baseline": "reward_v1_only",
        "health_floor": "baseline_rerun",
        "source_phase5_2_summary_path": "/root/EASYkoopman/source/results/koopman_phase5_2/summary.json",
        "source_phase5_3_summary_path": "/root/EASYkoopman/source/results/koopman_phase5_3/selection.json",
        "observation_dim": 9,
        "action_dim": 4,
        "pwm_dim": 8,
        "source_git_commit": "abc123",
        "source_git_dirty": False,
        "source_checkpoint_mtime": checkpoint.stat().st_mtime,
        "adapter_refresh_count": 10,
        "adapter_refresh_before_env_step": True,
        "nonfinite_observation_count": 0,
        "nonfinite_action_count": 0,
        "completion_status": "completed",
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_validate_phase5_4_checkpoint_provenance_accepts_candidate_for_matched_eval(tmp_path):
    checkpoint = tmp_path / "model_199.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = write_phase5_4_summary(tmp_path / "summary.json", checkpoint)

    result = validate_phase5_4_checkpoint_provenance(
        checkpoint,
        summary_path,
        expected_evidence_level="phase5_4_pareto_matched_eval",
    )

    assert result["checkpoint_provenance_valid"] is True
    assert result["checkpoint_provenance"] == "phase5_4_pareto_candidate"
    assert result["source_profile_id"] == "r_pwm030"
    assert result["source_phase5_4_track"] == "R"
    assert result["source_parameter_distance_from_parent"] == pytest.approx(2.0)


def test_validate_phase5_4_checkpoint_provenance_rejects_phase5_3_relabel(tmp_path):
    checkpoint = tmp_path / "model_199.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = write_phase5_4_summary(
        tmp_path / "summary.json",
        checkpoint,
        checkpoint_provenance="phase5_3_cross_candidate",
        ppo_evidence_level="phase5_3_cross_candidate",
    )

    with pytest.raises(ValueError, match="checkpoint_provenance"):
        validate_phase5_4_checkpoint_provenance(
            checkpoint,
            summary_path,
            expected_evidence_level="phase5_4_pareto_matched_eval",
        )


def test_validate_phase5_4_checkpoint_provenance_requires_source_evidence_paths(tmp_path):
    checkpoint = tmp_path / "model_199.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = write_phase5_4_summary(
        tmp_path / "summary.json",
        checkpoint,
        source_phase5_3_summary_path="",
    )

    with pytest.raises(ValueError, match="source_phase5_3_summary_path"):
        validate_phase5_4_checkpoint_provenance(
            checkpoint,
            summary_path,
            expected_evidence_level="phase5_4_pareto_candidate",
        )

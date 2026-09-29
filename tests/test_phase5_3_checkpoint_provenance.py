import json
from pathlib import Path

import pytest

from workflows.validate_phase5_3_checkpoint_provenance import validate_phase5_3_checkpoint_provenance


def write_phase5_3_summary(path: Path, checkpoint: Path, **overrides):
    payload = {
        "checkpoint_found": True,
        "checkpoint_path": str(checkpoint),
        "selected_checkpoint": str(checkpoint),
        "selected_rule": "latest_valid_after_phase5_3_cross_validator",
        "checkpoint_provenance": "phase5_3_cross_candidate",
        "result_bucket": "retrained_ppo_koopman_mpc",
        "ppo_evidence_level": "phase5_3_cross_candidate",
        "controller_path": "koopman_mpc/direct_state",
        "adapter_mode": "heuristic_reference_delta_v0",
        "koopman_backend": "direct_state",
        "profile_id": "cross_reward_v1_adapter_soft",
        "reward_profile": "koopman_mpc_stability_v1",
        "adapter_profile": "adapter_scale_soft_v1",
        "mpc_profile": "mpc_default_v0",
        "changed_axis": "reward_adapter",
        "risk_level": "medium",
        "sentinel_required": True,
        "training_ladder_stage": "candidate",
        "comparison_baseline": "reward_v1_only",
        "health_floor": "baseline_rerun",
        "source_phase5_2_summary_path": "/root/EASYkoopman/source/results/koopman_phase5_2/phase5_2_experiment_summary.json",
        "observation_dim": 9,
        "action_dim": 4,
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


def test_validate_phase5_3_checkpoint_provenance_accepts_cross_candidate(tmp_path):
    checkpoint = tmp_path / "model_200.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = write_phase5_3_summary(tmp_path / "summary.json", checkpoint)

    result = validate_phase5_3_checkpoint_provenance(
        checkpoint,
        summary_path,
        expected_evidence_level="phase5_3_cross_matched_eval",
    )

    assert result["checkpoint_provenance_valid"] is True
    assert result["checkpoint_provenance"] == "phase5_3_cross_candidate"
    assert result["source_profile_id"] == "cross_reward_v1_adapter_soft"
    assert result["source_reward_profile"] == "koopman_mpc_stability_v1"
    assert result["source_adapter_profile"] == "adapter_scale_soft_v1"
    assert result["source_mpc_profile"] == "mpc_default_v0"


def test_validate_phase5_3_checkpoint_provenance_rejects_phase5_2_candidate(tmp_path):
    checkpoint = tmp_path / "model_200.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = write_phase5_3_summary(
        tmp_path / "summary.json",
        checkpoint,
        checkpoint_provenance="phase5_2_health_candidate",
        ppo_evidence_level="phase5_2_health_candidate",
    )

    with pytest.raises(ValueError, match="checkpoint_provenance"):
        validate_phase5_3_checkpoint_provenance(
            checkpoint,
            summary_path,
            expected_evidence_level="phase5_3_cross_matched_eval",
        )


def test_validate_phase5_3_checkpoint_provenance_requires_phase5_2_source_summary(tmp_path):
    checkpoint = tmp_path / "model_200.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = write_phase5_3_summary(
        tmp_path / "summary.json",
        checkpoint,
        source_phase5_2_summary_path="",
    )

    with pytest.raises(ValueError, match="source_phase5_2_summary_path"):
        validate_phase5_3_checkpoint_provenance(
            checkpoint,
            summary_path,
            expected_evidence_level="phase5_3_cross_candidate",
        )

import json
from pathlib import Path

import pytest

from workflows.validate_phase5_1_checkpoint_provenance import validate_phase5_1_checkpoint_provenance


def write_phase5_1_summary(path: Path, checkpoint: Path, **overrides):
    payload = {
        "checkpoint_found": True,
        "checkpoint_path": str(checkpoint),
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


def test_validate_phase5_1_checkpoint_provenance_accepts_stability_candidate(tmp_path):
    checkpoint = tmp_path / "model_25.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = write_phase5_1_summary(tmp_path / "summary.json", checkpoint)

    result = validate_phase5_1_checkpoint_provenance(
        checkpoint,
        summary_path,
        expected_evidence_level="stability_candidate",
    )

    assert result["checkpoint_provenance_valid"] is True
    assert result["checkpoint_provenance"] == "phase5_1_stability_candidate"
    assert result["source_ppo_evidence_level"] == "stability_candidate"


def test_validate_phase5_1_checkpoint_provenance_rejects_phase5_smoke_summary(tmp_path):
    checkpoint = tmp_path / "model_0.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = write_phase5_1_summary(
        tmp_path / "summary.json",
        checkpoint,
        checkpoint_provenance="phase5_train_koopman_mpc",
        ppo_evidence_level="retrained_policy_smoke",
    )

    with pytest.raises(ValueError, match="checkpoint_provenance"):
        validate_phase5_1_checkpoint_provenance(
            checkpoint,
            summary_path,
            expected_evidence_level="stability_candidate",
        )


def test_validate_phase5_1_checkpoint_provenance_rejects_sentinel_as_candidate(tmp_path):
    checkpoint = tmp_path / "model_10.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = write_phase5_1_summary(
        tmp_path / "summary.json",
        checkpoint,
        checkpoint_provenance="phase5_1_stability_sentinel",
        ppo_evidence_level="stability_sentinel",
    )

    with pytest.raises(ValueError, match="checkpoint_provenance"):
        validate_phase5_1_checkpoint_provenance(
            checkpoint,
            summary_path,
            expected_evidence_level="stability_candidate",
        )

import json
from pathlib import Path

import pytest

from workflows.validate_phase5_checkpoint_provenance import validate_phase5_checkpoint_provenance


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def write_summary(path: Path, checkpoint: Path, **overrides):
    payload = {
        "checkpoint_found": True,
        "checkpoint_path": str(checkpoint),
        "selected_checkpoint": str(checkpoint),
        "selected_rule": "latest_mtime_model_pt",
        "checkpoint_provenance": "phase5_train_koopman_mpc",
        "result_bucket": "retrained_ppo_koopman_mpc",
        "ppo_evidence_level": "retrained_policy_smoke",
        "controller_path": "koopman_mpc/direct_state",
        "adapter_mode": "heuristic_reference_delta_v0",
        "koopman_backend": "direct_state",
        "reward_profile": "legacy_easyuuv_v0",
        "observation_dim": 9,
        "action_dim": 4,
        "source_git_commit": "abc123",
        "source_git_dirty": False,
        "source_checkpoint_mtime": checkpoint.stat().st_mtime,
        "adapter_refresh_count": 3,
        "adapter_refresh_before_env_step": True,
        "base_reference_source": "env_goal_quat_plus_zero_depth",
        "depth_reference_source": "zero_depth_default",
        "base_reference_goal_match_max_error": 0.0,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_validate_phase5_checkpoint_provenance_accepts_valid_summary(tmp_path):
    checkpoint = tmp_path / "model_0.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = write_summary(tmp_path / "summary.json", checkpoint)

    result = validate_phase5_checkpoint_provenance(checkpoint, summary_path)

    assert result["checkpoint_provenance_valid"] is True
    assert result["source_result_bucket"] == "retrained_ppo_koopman_mpc"
    assert result["source_controller_path"] == "koopman_mpc/direct_state"
    assert result["source_adapter_mode"] == "heuristic_reference_delta_v0"


def test_validate_phase5_checkpoint_provenance_rejects_legacy_summary(tmp_path):
    checkpoint = tmp_path / "model_0.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = write_summary(
        tmp_path / "summary.json",
        checkpoint,
        result_bucket="legacy_ppo_baseline",
        controller_path="legacy/Ssurface",
        checkpoint_provenance="phase46_legacy_train",
    )

    with pytest.raises(ValueError, match="result_bucket"):
        validate_phase5_checkpoint_provenance(checkpoint, summary_path)


def test_validate_phase5_checkpoint_provenance_rejects_checkpoint_mismatch(tmp_path):
    checkpoint = tmp_path / "model_0.pt"
    other_checkpoint = tmp_path / "model_1.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    other_checkpoint.write_text("other", encoding="utf-8")
    summary_path = write_summary(tmp_path / "summary.json", other_checkpoint)

    with pytest.raises(ValueError, match="selected_checkpoint"):
        validate_phase5_checkpoint_provenance(checkpoint, summary_path)


def test_play_ppo_koopman_source_requires_provenance_for_retrained_bucket():
    source = (PROJECT_ROOT / "workflows" / "play_ppo_koopman.py").read_text(encoding="utf-8")

    assert "--source_training_summary_path" in source
    assert "--ppo_evidence_level" in source
    assert "validate_phase5_checkpoint_provenance" in source
    assert "preflight_phase5_provenance" in source
    assert source.index("preflight_phase5_provenance(") < source.index("app_launcher = AppLauncher(args_cli)")

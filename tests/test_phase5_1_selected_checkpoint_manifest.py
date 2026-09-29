import json
from pathlib import Path

import pytest

from workflows.write_phase5_1_selected_checkpoint_manifest import write_selected_checkpoint_manifest


def test_write_selected_checkpoint_manifest_from_valid_stability_summary(tmp_path):
    checkpoint = tmp_path / "model_25.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = tmp_path / "stability_candidate_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "checkpoint_found": True,
                "selected_checkpoint": str(checkpoint),
                "selected_rule": "latest_valid_after_stability_validator",
                "checkpoint_provenance": "phase5_1_stability_candidate",
                "ppo_evidence_level": "stability_candidate",
                "reward_profile": "legacy_easyuuv_v0",
                "adapter_mode": "heuristic_reference_delta_v0",
                "koopman_backend": "direct_state",
                "observation_dim": 9,
                "action_dim": 4,
                "selected_weight_status": "candidate_only",
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "selected_ppo_checkpoint_manifest.json"

    manifest = write_selected_checkpoint_manifest(summary_path, output_path)

    assert manifest["phase"] == "05.1"
    assert manifest["selected_checkpoint"] == str(checkpoint)
    assert manifest["matched_eval_status"] == "pending"
    assert json.loads(output_path.read_text(encoding="utf-8")) == manifest


def test_write_selected_checkpoint_manifest_rejects_phase5_smoke(tmp_path):
    checkpoint = tmp_path / "model_0.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "checkpoint_found": True,
                "selected_checkpoint": str(checkpoint),
                "selected_rule": "latest_mtime_model_pt",
                "checkpoint_provenance": "phase5_train_koopman_mpc",
                "ppo_evidence_level": "retrained_policy_smoke",
                "reward_profile": "legacy_easyuuv_v0",
                "adapter_mode": "heuristic_reference_delta_v0",
                "koopman_backend": "direct_state",
                "observation_dim": 9,
                "action_dim": 4,
                "selected_weight_status": "candidate_only",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="phase5_1_stability_candidate"):
        write_selected_checkpoint_manifest(summary_path, tmp_path / "manifest.json")

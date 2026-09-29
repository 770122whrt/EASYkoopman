import json
from pathlib import Path

import pytest

from koopman_data import KoopmanDataLogger, build_koopman_sample
from tests.test_koopman_data import valid_sample_kwargs
from workflows.validate_ppo_koopman_log import main, validate_ppo_koopman_sample


def valid_ppo_sample() -> dict:
    sample = build_koopman_sample(**valid_sample_kwargs(controller_mode="koopman_mpc/Ssurface"))
    sample.update(
        {
            "policy_mode": "stub",
            "policy_output": [0.0, 0.0, 0.0, 0.0],
            "policy_output_clipped": [0.0, 0.0, 0.0, 0.0],
            "base_reference": [0.0, 1.0, 0.0, 0.0, 0.0],
            "adapted_reference": [0.0, 1.0, 0.0, 0.0, 0.0],
            "adapter_mode": "heuristic_reference_delta_v0",
            "action_semantics": "heuristic_reference_delta_v0_legacy_4d_as_reference_delta",
            "ppo_evidence_level": "stub_only",
            "adapter_quat_convention": "reference_frame_right_multiply",
            "base_reference_goal_match_max_error": 0.0,
            "adapter_diagnostics": {
                "adapter_mode": "heuristic_reference_delta_v0",
                "policy_action_clip_rate": 0.0,
            },
            "policy_action_clip_rate": 0.0,
            "backend_used": "direct_state",
            "solver_diagnostics": {"fallback_used": False, "latency_ms": 1.0},
        }
    )
    return sample


def test_validate_ppo_koopman_sample_accepts_required_adapter_fields():
    sample = valid_ppo_sample()

    validate_ppo_koopman_sample(sample)

    assert sample["adapter_mode"] == "heuristic_reference_delta_v0"


@pytest.mark.parametrize(
    "missing_field",
    [
        "policy_output",
        "adapted_reference",
        "ppo_evidence_level",
        "action_semantics",
        "adapter_quat_convention",
        "base_reference_goal_match_max_error",
    ],
)
def test_validate_ppo_koopman_sample_rejects_missing_required_fields(missing_field: str):
    sample = valid_ppo_sample()
    sample.pop(missing_field)

    with pytest.raises(ValueError, match=missing_field):
        validate_ppo_koopman_sample(sample)


def test_validate_ppo_koopman_log_cli_reports_adapter_summary(tmp_path: Path, capsys):
    log_path = tmp_path / "ppo_koopman.jsonl"

    with KoopmanDataLogger(log_path) as logger:
        logger.write(valid_ppo_sample())

    assert main([str(log_path)]) == 0

    output = capsys.readouterr().out
    assert "OK: 1 PPO/Koopman samples" in output
    assert "adapter_modes=heuristic_reference_delta_v0" in output
    assert "ppo_evidence_levels=stub_only" in output
    assert "policy_modes=stub" in output


def test_validate_ppo_koopman_log_cli_rejects_bad_record(tmp_path: Path, capsys):
    log_path = tmp_path / "bad_ppo_koopman.jsonl"
    sample = valid_ppo_sample()
    sample["ppo_evidence_level"] = "performance_claim"
    log_path.write_text(json.dumps(sample) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main([str(log_path)])

    assert exc_info.value.code == 1
    assert "ppo_evidence_level" in capsys.readouterr().err


def test_retrained_policy_smoke_requires_phase5_provenance_fields():
    sample = valid_ppo_sample()
    sample["result_bucket"] = "retrained_ppo_koopman_mpc"
    sample["ppo_evidence_level"] = "retrained_policy_smoke"

    with pytest.raises(ValueError, match="checkpoint_provenance"):
        validate_ppo_koopman_sample(sample)


def test_matched_stability_eval_requires_phase5_1_provenance_fields():
    sample = valid_ppo_sample()
    sample["result_bucket"] = "retrained_ppo_koopman_mpc"
    sample["ppo_evidence_level"] = "matched_stability_eval"

    with pytest.raises(ValueError, match="checkpoint_provenance"):
        validate_ppo_koopman_sample(sample)


def test_matched_stability_eval_accepts_phase5_1_provenance_fields():
    sample = valid_ppo_sample()
    sample.update(
        {
            "result_bucket": "retrained_ppo_koopman_mpc",
            "ppo_evidence_level": "matched_stability_eval",
            "checkpoint_provenance": "phase5_1_stability_candidate",
            "checkpoint_provenance_valid": True,
            "source_training_summary_path": "/tmp/stability_candidate_summary.json",
            "controller_path": "koopman_mpc/direct_state",
            "reward_profile": "legacy_easyuuv_v0",
        }
    )

    validate_ppo_koopman_sample(sample)


def test_phase5_2_matched_eval_accepts_profile_provenance_fields():
    sample = valid_ppo_sample()
    sample.update(
        {
            "result_bucket": "retrained_ppo_koopman_mpc",
            "ppo_evidence_level": "phase5_2_matched_eval",
            "checkpoint_provenance": "phase5_2_health_candidate",
            "checkpoint_provenance_valid": True,
            "source_training_summary_path": "/tmp/phase5_2_reward_summary.json",
            "controller_path": "koopman_mpc/direct_state",
            "profile_id": "reward_v1_only",
            "reward_profile": "koopman_mpc_stability_v1",
            "adapter_profile": "heuristic_reference_delta_v0_default",
            "mpc_profile": "mpc_default_v0",
            "changed_axis": "reward",
        }
    )

    validate_ppo_koopman_sample(sample)


def test_phase5_3_matched_eval_accepts_cross_profile_provenance_fields():
    sample = valid_ppo_sample()
    sample.update(
        {
            "result_bucket": "retrained_ppo_koopman_mpc",
            "ppo_evidence_level": "phase5_3_cross_matched_eval",
            "checkpoint_provenance": "phase5_3_cross_candidate",
            "checkpoint_provenance_valid": True,
            "source_training_summary_path": "/tmp/phase5_3_cross_reward_adapter_summary.json",
            "controller_path": "koopman_mpc/direct_state",
            "profile_id": "cross_reward_v1_adapter_soft",
            "reward_profile": "koopman_mpc_stability_v1",
            "adapter_profile": "adapter_scale_soft_v1",
            "mpc_profile": "mpc_default_v0",
            "changed_axis": "reward_adapter",
        }
    )

    validate_ppo_koopman_sample(sample)

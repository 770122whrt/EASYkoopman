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

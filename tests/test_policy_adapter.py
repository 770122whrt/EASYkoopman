import math

import pytest

from koopman.policy_adapter import (
    ACTION_SEMANTICS,
    ADAPTER_MODE,
    ADAPTER_QUAT_CONVENTION,
    PolicyAdapterConfig,
    adapt_policy_reference,
)


def test_zero_policy_output_returns_base_reference_and_diagnostics():
    base_reference = [1.25, 1.0, 0.0, 0.0, 0.0]

    output = adapt_policy_reference(
        [0.0, 0.0, 0.0, 0.0],
        base_reference,
        observation_goal_quat=[1.0, 0.0, 0.0, 0.0],
        ppo_evidence_level="stub_only",
    )

    assert output.adapter_mode == ADAPTER_MODE == "heuristic_reference_delta_v0"
    assert output.adapted_reference_5d == pytest.approx(base_reference)
    assert output.policy_output_4d_clipped == pytest.approx([0.0, 0.0, 0.0, 0.0])
    assert output.diagnostics["action_semantics"] == ACTION_SEMANTICS
    assert output.diagnostics["adapter_quat_convention"] == ADAPTER_QUAT_CONVENTION
    assert output.diagnostics["ppo_evidence_level"] == "stub_only"
    assert output.diagnostics["base_reference_goal_match_max_error"] == pytest.approx(0.0)
    assert output.diagnostics["policy_action_clip_rate"] == pytest.approx(0.0)


def test_policy_output_is_clipped_and_depth_stays_bounded():
    config = PolicyAdapterConfig(
        policy_action_limit=0.5,
        rpy_delta_scale=(0.1, 0.2, 0.3),
        depth_delta_scale=2.0,
        depth_bounds=(-0.25, 1.0),
    )

    output = adapt_policy_reference(
        [4.0, -3.0, 2.0, 5.0],
        [0.5, 1.0, 0.0, 0.0, 0.0],
        observation_goal_quat=[1.0, 0.0, 0.0, 0.0],
        config=config,
        ppo_evidence_level="checkpoint_smoke",
    )

    assert output.policy_output_4d_clipped == pytest.approx([0.5, -0.5, 0.5, 0.5])
    assert output.adapted_reference_5d[0] == pytest.approx(1.0)
    quat_norm = math.sqrt(sum(value * value for value in output.adapted_reference_5d[1:5]))
    assert quat_norm == pytest.approx(1.0)
    assert output.diagnostics["policy_action_clip_rate"] == pytest.approx(1.0)
    assert output.diagnostics["ppo_evidence_level"] == "checkpoint_smoke"


def test_non_finite_policy_output_is_rejected():
    with pytest.raises(ValueError, match="finite"):
        adapt_policy_reference(
            [0.0, float("nan"), 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0, 0.0],
            observation_goal_quat=[1.0, 0.0, 0.0, 0.0],
        )


def test_base_reference_goal_match_accepts_quaternion_sign_equivalence():
    output = adapt_policy_reference(
        [0.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0, 0.0],
        observation_goal_quat=[-1.0, -0.0, -0.0, -0.0],
    )

    assert output.diagnostics["base_reference_goal_match_max_error"] == pytest.approx(0.0)


def test_invalid_ppo_evidence_level_is_rejected():
    with pytest.raises(ValueError, match="ppo_evidence_level"):
        adapt_policy_reference(
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0, 0.0],
            ppo_evidence_level="performance_claim",
        )

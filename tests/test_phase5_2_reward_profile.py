import pytest
import torch

from koopman.phase5_2_reward import Phase52RewardConfig, compute_phase52_reward_components


def test_phase5_2_reward_defaults_match_review_contract():
    config = Phase52RewardConfig()

    assert config.w_fallback == pytest.approx(0.30)
    assert config.w_pwm_sat == pytest.approx(0.20)
    assert config.w_latency == pytest.approx(0.05)
    assert config.latency_ref_ms == pytest.approx(20.0)
    assert config.pwm_soft_limit == pytest.approx(0.90)


def test_phase5_2_reward_has_zero_health_penalty_when_controller_is_healthy():
    legacy_reward = torch.tensor([0.65])

    components = compute_phase52_reward_components(
        legacy_reward=legacy_reward,
        actions=torch.zeros((1, 4)),
        action_delta=torch.zeros((1, 4)),
        pwm=torch.zeros((1, 8)),
        fallback_used=torch.tensor([False]),
        latency_ms=torch.tensor([12.0]),
    )

    assert components["health_penalty"].item() == pytest.approx(0.0)
    assert components["total_reward"].item() == pytest.approx(0.65)


def test_phase5_2_reward_penalizes_fallback_saturation_latency_and_motion():
    legacy_reward = torch.tensor([1.0])

    components = compute_phase52_reward_components(
        legacy_reward=legacy_reward,
        actions=torch.ones((1, 4)),
        action_delta=torch.full((1, 4), 0.5),
        pwm=torch.ones((1, 8)),
        fallback_used=torch.tensor([True]),
        latency_ms=torch.tensor([40.0]),
    )

    assert components["fallback_penalty"].item() == pytest.approx(0.30)
    assert components["pwm_saturation_penalty"].item() == pytest.approx(0.20)
    assert components["latency_penalty"].item() == pytest.approx(0.05)
    assert components["action_penalty"].item() == pytest.approx(0.04)
    assert components["delta_action_penalty"].item() == pytest.approx(0.02)
    assert components["health_penalty"].item() == pytest.approx(0.61)
    assert components["total_reward"].item() == pytest.approx(0.39)

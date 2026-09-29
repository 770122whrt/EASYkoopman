import pytest

from koopman.phase5_2_profiles import (
    PHASE5_2_REWARD_PROFILE,
    adapter_profile_values,
    get_phase52_profile,
    mpc_profile_values,
    resolve_phase52_profile,
)


def test_phase5_2_reward_profile_is_one_factor_change():
    profile = get_phase52_profile("reward_v1_only")

    assert profile.reward_profile == PHASE5_2_REWARD_PROFILE
    assert profile.adapter_profile == "heuristic_reference_delta_v0_default"
    assert profile.mpc_profile == "mpc_default_v0"
    assert profile.changed_axis == "reward"


def test_phase5_2_adapter_soft_v1_matches_review_scales():
    values = adapter_profile_values("adapter_scale_soft_v1")

    assert values.rpy_delta_scale == pytest.approx(0.30)
    assert values.depth_delta_scale == pytest.approx(0.40)
    assert values.policy_action_limit == pytest.approx(1.0)


def test_phase5_2_mpc_health_v1_keeps_delta_limit_and_only_changes_weights():
    values = mpc_profile_values("mpc_health_v1")

    assert values.delta_pwm_limit == pytest.approx(0.35)
    assert values.control_weight == pytest.approx(0.03)
    assert values.smoothness_weight == pytest.approx(0.10)


def test_phase5_2_profile_rejects_conflicting_cli_contract():
    with pytest.raises(ValueError, match="adapter_profile"):
        resolve_phase52_profile(
            profile_id="reward_v1_only",
            reward_profile=PHASE5_2_REWARD_PROFILE,
            adapter_profile="adapter_scale_soft_v1",
            mpc_profile="mpc_default_v0",
            changed_axis="reward",
        )

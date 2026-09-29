import pytest

from koopman.phase5_2_profiles import (
    ADAPTER_PROFILE_DEFAULT,
    ADAPTER_PROFILE_SOFT_V1,
    LEGACY_REWARD_PROFILE,
    MPC_PROFILE_DEFAULT,
    MPC_PROFILE_HEALTH_V1,
    PHASE5_2_REWARD_PROFILE,
)
from koopman.phase5_3_profiles import (
    PHASE53_PROFILE_IDS,
    PHASE5_3_CANDIDATE_CHECKPOINT_PROVENANCE,
    PHASE5_3_CANDIDATE_EVIDENCE_LEVEL,
    PHASE5_3_MATCHED_EVIDENCE_LEVEL,
    checkpoint_provenance_for_phase53_evidence,
    resolve_phase53_profile,
)


def test_phase5_3_includes_user_requested_reward_adapter_cross():
    profile = resolve_phase53_profile(profile_id="cross_reward_v1_adapter_soft")

    assert "cross_reward_v1_adapter_soft" in PHASE53_PROFILE_IDS
    assert profile.reward_profile == PHASE5_2_REWARD_PROFILE
    assert profile.adapter_profile == ADAPTER_PROFILE_SOFT_V1
    assert profile.mpc_profile == MPC_PROFILE_DEFAULT
    assert profile.changed_axis == "reward_adapter"
    assert profile.risk_level == "medium"
    assert profile.sentinel_required is True


@pytest.mark.parametrize(
    "profile_id,expected_reward,expected_adapter",
    [
        ("cross_reward_v1_mpc_health", PHASE5_2_REWARD_PROFILE, ADAPTER_PROFILE_DEFAULT),
        ("cross_adapter_soft_mpc_health", LEGACY_REWARD_PROFILE, ADAPTER_PROFILE_SOFT_V1),
        ("cross_reward_v1_adapter_soft_mpc_health", PHASE5_2_REWARD_PROFILE, ADAPTER_PROFILE_SOFT_V1),
    ],
)
def test_phase5_3_mpc_crosses_are_sentinel_first(profile_id, expected_reward, expected_adapter):
    profile = resolve_phase53_profile(profile_id=profile_id)

    assert profile.reward_profile == expected_reward
    assert profile.adapter_profile == expected_adapter
    assert profile.mpc_profile == MPC_PROFILE_HEALTH_V1
    assert profile.sentinel_required is True
    assert profile.risk_level in {"high", "very_high"}


def test_phase5_3_profile_rejects_conflicting_cli_contract():
    with pytest.raises(ValueError, match="mpc_profile"):
        resolve_phase53_profile(
            profile_id="cross_reward_v1_adapter_soft",
            reward_profile=PHASE5_2_REWARD_PROFILE,
            adapter_profile=ADAPTER_PROFILE_SOFT_V1,
            mpc_profile=MPC_PROFILE_HEALTH_V1,
            changed_axis="reward_adapter",
        )


def test_phase5_3_matched_eval_uses_candidate_checkpoint_provenance():
    assert (
        checkpoint_provenance_for_phase53_evidence(PHASE5_3_MATCHED_EVIDENCE_LEVEL)
        == PHASE5_3_CANDIDATE_CHECKPOINT_PROVENANCE
    )
    assert (
        checkpoint_provenance_for_phase53_evidence(PHASE5_3_CANDIDATE_EVIDENCE_LEVEL)
        == PHASE5_3_CANDIDATE_CHECKPOINT_PROVENANCE
    )

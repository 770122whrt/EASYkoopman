import pytest

from koopman.phase5_2_profiles import ADAPTER_PROFILE_DEFAULT, MPC_PROFILE_DEFAULT, PHASE5_2_REWARD_PROFILE
from koopman.phase5_4_profiles import (
    PHASE54_PROFILE_IDS,
    PHASE5_4_CANDIDATE_CHECKPOINT_PROVENANCE,
    PHASE5_4_CANDIDATE_EVIDENCE_LEVEL,
    PHASE5_4_MATCHED_EVIDENCE_LEVEL,
    PHASE5_4_SENTINEL_EVIDENCE_LEVEL,
    checkpoint_provenance_for_phase54_evidence,
    effective_mpc_values,
    effective_reward_config,
    resolve_phase54_profile,
)


def test_phase5_4_round1_keeps_adapter_fixed_and_covers_both_tracks():
    track_r = []
    track_rm = []
    for profile_id in PHASE54_PROFILE_IDS:
        profile = resolve_phase54_profile(profile_id=profile_id)
        if profile.sweep_round == "round1":
            assert profile.adapter_profile == ADAPTER_PROFILE_DEFAULT
            if profile.track == "R":
                track_r.append(profile_id)
            elif profile.track == "RM":
                track_rm.append(profile_id)

    assert len(track_r) >= 4
    assert len(track_rm) >= 5


def test_phase5_4_parameter_distance_is_computable_from_step_sizes():
    profile = resolve_phase54_profile(profile_id="r_pwm030_action_smooth")

    assert profile.reward_profile == PHASE5_2_REWARD_PROFILE
    assert profile.mpc_profile == MPC_PROFILE_DEFAULT
    assert profile.changed_parameter_count == 3
    assert profile.parameter_distance_from_parent == pytest.approx(4.0)
    assert profile.parameter_step_count["phase5_2_w_pwm_sat"] == pytest.approx(2.0)
    assert profile.parameter_step_count["phase5_2_w_action"] == pytest.approx(1.0)
    assert profile.parameter_step_count["phase5_2_w_delta_action"] == pytest.approx(1.0)


def test_phase5_4_effective_reward_and_mpc_values_apply_overrides_only():
    reward = effective_reward_config(resolve_phase54_profile(profile_id="r_pwm025"))
    assert reward.w_fallback == pytest.approx(0.30)
    assert reward.w_pwm_sat == pytest.approx(0.25)
    assert reward.w_action == pytest.approx(0.01)

    mpc = effective_mpc_values(resolve_phase54_profile(profile_id="rm_midweights_timeout14"))
    assert mpc.control_weight == pytest.approx(0.02)
    assert mpc.smoothness_weight == pytest.approx(0.075)
    assert mpc.timeout_ms == pytest.approx(14.0)
    assert mpc.horizon == 5


def test_phase5_4_rejects_conflicting_profile_contract():
    with pytest.raises(ValueError, match="adapter_profile"):
        resolve_phase54_profile(profile_id="r_pwm025", adapter_profile="adapter_scale_soft_v1")


def test_phase5_4_matched_eval_uses_candidate_checkpoint_provenance():
    assert (
        checkpoint_provenance_for_phase54_evidence(PHASE5_4_MATCHED_EVIDENCE_LEVEL)
        == PHASE5_4_CANDIDATE_CHECKPOINT_PROVENANCE
    )
    assert (
        checkpoint_provenance_for_phase54_evidence(PHASE5_4_CANDIDATE_EVIDENCE_LEVEL)
        == PHASE5_4_CANDIDATE_CHECKPOINT_PROVENANCE
    )
    assert checkpoint_provenance_for_phase54_evidence(PHASE5_4_SENTINEL_EVIDENCE_LEVEL) == "phase5_4_pareto_sentinel"

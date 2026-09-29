from __future__ import annotations

from dataclasses import dataclass

from koopman.phase5_2_profiles import (
    ADAPTER_PROFILE_DEFAULT,
    ADAPTER_PROFILE_SOFT_V1,
    LEGACY_REWARD_PROFILE,
    MPC_PROFILE_DEFAULT,
    MPC_PROFILE_HEALTH_V1,
    PHASE5_2_REWARD_PROFILE,
    _coalesce,
)


PHASE5_3_SENTINEL_EVIDENCE_LEVEL = "phase5_3_cross_sentinel"
PHASE5_3_CANDIDATE_EVIDENCE_LEVEL = "phase5_3_cross_candidate"
PHASE5_3_EXTENDED_EVIDENCE_LEVEL = "phase5_3_cross_extended"
PHASE5_3_MATCHED_EVIDENCE_LEVEL = "phase5_3_cross_matched_eval"

PHASE5_3_TRAINING_EVIDENCE_LEVELS = (
    PHASE5_3_SENTINEL_EVIDENCE_LEVEL,
    PHASE5_3_CANDIDATE_EVIDENCE_LEVEL,
    PHASE5_3_EXTENDED_EVIDENCE_LEVEL,
)
PHASE5_3_EVIDENCE_LEVELS = PHASE5_3_TRAINING_EVIDENCE_LEVELS + (PHASE5_3_MATCHED_EVIDENCE_LEVEL,)

PHASE5_3_SENTINEL_CHECKPOINT_PROVENANCE = "phase5_3_cross_sentinel"
PHASE5_3_CANDIDATE_CHECKPOINT_PROVENANCE = "phase5_3_cross_candidate"
PHASE5_3_EXTENDED_CHECKPOINT_PROVENANCE = "phase5_3_cross_extended"
PHASE5_3_PROVENANCE_BY_EVIDENCE_LEVEL = {
    PHASE5_3_SENTINEL_EVIDENCE_LEVEL: PHASE5_3_SENTINEL_CHECKPOINT_PROVENANCE,
    PHASE5_3_CANDIDATE_EVIDENCE_LEVEL: PHASE5_3_CANDIDATE_CHECKPOINT_PROVENANCE,
    PHASE5_3_EXTENDED_EVIDENCE_LEVEL: PHASE5_3_EXTENDED_CHECKPOINT_PROVENANCE,
}

PHASE5_3_COMPARISON_BASELINE = "reward_v1_only"
PHASE5_3_HEALTH_FLOOR = "baseline_rerun"
PHASE5_3_TRAINING_LADDER_STAGES = ("sentinel", "candidate", "extended")
PHASE5_3_CHANGED_AXIS_IDS = (
    "reward_adapter",
    "reward_mpc",
    "adapter_mpc",
    "reward_adapter_mpc",
)


@dataclass(frozen=True)
class Phase53CrossProfile:
    profile_id: str
    reward_profile: str
    adapter_profile: str
    mpc_profile: str
    changed_axis: str
    risk_level: str
    sentinel_required: bool = True
    candidate_requires_review: bool = False
    next_tuning_axis: str = ""


PHASE53_PROFILE_TABLE = {
    "cross_reward_v1_adapter_soft": Phase53CrossProfile(
        profile_id="cross_reward_v1_adapter_soft",
        reward_profile=PHASE5_2_REWARD_PROFILE,
        adapter_profile=ADAPTER_PROFILE_SOFT_V1,
        mpc_profile=MPC_PROFILE_DEFAULT,
        changed_axis="reward_adapter",
        risk_level="medium",
        candidate_requires_review=False,
        next_tuning_axis="adapter_scale_and_saturation_reward_sweep",
    ),
    "cross_reward_v1_mpc_health": Phase53CrossProfile(
        profile_id="cross_reward_v1_mpc_health",
        reward_profile=PHASE5_2_REWARD_PROFILE,
        adapter_profile=ADAPTER_PROFILE_DEFAULT,
        mpc_profile=MPC_PROFILE_HEALTH_V1,
        changed_axis="reward_mpc",
        risk_level="high",
        candidate_requires_review=True,
        next_tuning_axis="mpc_weight_sweep_with_clip_guard",
    ),
    "cross_adapter_soft_mpc_health": Phase53CrossProfile(
        profile_id="cross_adapter_soft_mpc_health",
        reward_profile=LEGACY_REWARD_PROFILE,
        adapter_profile=ADAPTER_PROFILE_SOFT_V1,
        mpc_profile=MPC_PROFILE_HEALTH_V1,
        changed_axis="adapter_mpc",
        risk_level="high",
        candidate_requires_review=True,
        next_tuning_axis="mpc_weight_sweep_with_clip_guard",
    ),
    "cross_reward_v1_adapter_soft_mpc_health": Phase53CrossProfile(
        profile_id="cross_reward_v1_adapter_soft_mpc_health",
        reward_profile=PHASE5_2_REWARD_PROFILE,
        adapter_profile=ADAPTER_PROFILE_SOFT_V1,
        mpc_profile=MPC_PROFILE_HEALTH_V1,
        changed_axis="reward_adapter_mpc",
        risk_level="very_high",
        candidate_requires_review=True,
        next_tuning_axis="defer_until_pairwise_review",
    ),
}
PHASE53_PROFILE_IDS = tuple(PHASE53_PROFILE_TABLE)


def get_phase53_profile(profile_id: str) -> Phase53CrossProfile:
    try:
        return PHASE53_PROFILE_TABLE[profile_id]
    except KeyError as exc:
        raise ValueError(f"profile_id must be one of {list(PHASE53_PROFILE_IDS)}, got {profile_id!r}") from exc


def resolve_phase53_profile(
    *,
    profile_id: str,
    reward_profile: str | None = None,
    adapter_profile: str | None = None,
    mpc_profile: str | None = None,
    changed_axis: str | None = None,
) -> Phase53CrossProfile:
    profile = get_phase53_profile(profile_id)
    return Phase53CrossProfile(
        profile_id=profile.profile_id,
        reward_profile=_coalesce(profile.reward_profile, reward_profile, "reward_profile"),
        adapter_profile=_coalesce(profile.adapter_profile, adapter_profile, "adapter_profile"),
        mpc_profile=_coalesce(profile.mpc_profile, mpc_profile, "mpc_profile"),
        changed_axis=_coalesce(profile.changed_axis, changed_axis, "changed_axis"),
        risk_level=profile.risk_level,
        sentinel_required=profile.sentinel_required,
        candidate_requires_review=profile.candidate_requires_review,
        next_tuning_axis=profile.next_tuning_axis,
    )


def checkpoint_provenance_for_phase53_evidence(evidence_level: str) -> str:
    if evidence_level == PHASE5_3_MATCHED_EVIDENCE_LEVEL:
        evidence_level = PHASE5_3_CANDIDATE_EVIDENCE_LEVEL
    try:
        return PHASE5_3_PROVENANCE_BY_EVIDENCE_LEVEL[evidence_level]
    except KeyError as exc:
        raise ValueError(f"Unsupported Phase 5.3 evidence level: {evidence_level!r}") from exc

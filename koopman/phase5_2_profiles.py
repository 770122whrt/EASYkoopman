from __future__ import annotations

from dataclasses import dataclass


LEGACY_REWARD_PROFILE = "legacy_easyuuv_v0"
PHASE5_2_REWARD_PROFILE = "koopman_mpc_stability_v1"

PHASE5_2_SENTINEL_EVIDENCE_LEVEL = "phase5_2_health_sentinel"
PHASE5_2_CANDIDATE_EVIDENCE_LEVEL = "phase5_2_health_candidate"
PHASE5_2_MATCHED_EVIDENCE_LEVEL = "phase5_2_matched_eval"
PHASE5_2_TRAINING_EVIDENCE_LEVELS = (
    PHASE5_2_SENTINEL_EVIDENCE_LEVEL,
    PHASE5_2_CANDIDATE_EVIDENCE_LEVEL,
)
PHASE5_2_EVIDENCE_LEVELS = PHASE5_2_TRAINING_EVIDENCE_LEVELS + (PHASE5_2_MATCHED_EVIDENCE_LEVEL,)

PHASE5_2_SENTINEL_CHECKPOINT_PROVENANCE = "phase5_2_health_sentinel"
PHASE5_2_CANDIDATE_CHECKPOINT_PROVENANCE = "phase5_2_health_candidate"
PHASE5_2_PROVENANCE_BY_EVIDENCE_LEVEL = {
    PHASE5_2_SENTINEL_EVIDENCE_LEVEL: PHASE5_2_SENTINEL_CHECKPOINT_PROVENANCE,
    PHASE5_2_CANDIDATE_EVIDENCE_LEVEL: PHASE5_2_CANDIDATE_CHECKPOINT_PROVENANCE,
}

ADAPTER_PROFILE_DEFAULT = "heuristic_reference_delta_v0_default"
ADAPTER_PROFILE_SOFT_V1 = "adapter_scale_soft_v1"
ADAPTER_PROFILE_SOFT_V2 = "adapter_scale_soft_v2"
ADAPTER_PROFILE_IDS = (
    ADAPTER_PROFILE_DEFAULT,
    ADAPTER_PROFILE_SOFT_V1,
    ADAPTER_PROFILE_SOFT_V2,
)

MPC_PROFILE_DEFAULT = "mpc_default_v0"
MPC_PROFILE_HEALTH_V1 = "mpc_health_v1"
MPC_PROFILE_DELTA_LIMIT_PROBE_V1 = "mpc_delta_limit_probe_v1"
MPC_PROFILE_IDS = (
    MPC_PROFILE_DEFAULT,
    MPC_PROFILE_HEALTH_V1,
    MPC_PROFILE_DELTA_LIMIT_PROBE_V1,
)

CHANGED_AXIS_IDS = ("baseline", "reward", "adapter", "mpc")


@dataclass(frozen=True)
class AdapterProfileValues:
    policy_action_limit: float
    rpy_delta_scale: float
    depth_delta_scale: float
    depth_min: float = -3.0
    depth_max: float = 3.0


@dataclass(frozen=True)
class MPCProfileValues:
    delta_pwm_limit: float
    depth_weight: float
    attitude_weight: float
    control_weight: float
    smoothness_weight: float


@dataclass(frozen=True)
class Phase52Profile:
    profile_id: str
    reward_profile: str
    adapter_profile: str
    mpc_profile: str
    changed_axis: str
    initial_ablation: bool = True


ADAPTER_PROFILE_TABLE = {
    ADAPTER_PROFILE_DEFAULT: AdapterProfileValues(
        policy_action_limit=1.0,
        rpy_delta_scale=0.35,
        depth_delta_scale=0.50,
    ),
    ADAPTER_PROFILE_SOFT_V1: AdapterProfileValues(
        policy_action_limit=1.0,
        rpy_delta_scale=0.30,
        depth_delta_scale=0.40,
    ),
    ADAPTER_PROFILE_SOFT_V2: AdapterProfileValues(
        policy_action_limit=1.0,
        rpy_delta_scale=0.25,
        depth_delta_scale=0.30,
    ),
}

MPC_PROFILE_TABLE = {
    MPC_PROFILE_DEFAULT: MPCProfileValues(
        delta_pwm_limit=0.35,
        depth_weight=1.0,
        attitude_weight=1.0,
        control_weight=0.01,
        smoothness_weight=0.05,
    ),
    MPC_PROFILE_HEALTH_V1: MPCProfileValues(
        delta_pwm_limit=0.35,
        depth_weight=1.0,
        attitude_weight=1.0,
        control_weight=0.03,
        smoothness_weight=0.10,
    ),
    MPC_PROFILE_DELTA_LIMIT_PROBE_V1: MPCProfileValues(
        delta_pwm_limit=0.25,
        depth_weight=1.0,
        attitude_weight=1.0,
        control_weight=0.03,
        smoothness_weight=0.10,
    ),
}

PHASE52_PROFILE_TABLE = {
    "baseline_rerun": Phase52Profile(
        profile_id="baseline_rerun",
        reward_profile=LEGACY_REWARD_PROFILE,
        adapter_profile=ADAPTER_PROFILE_DEFAULT,
        mpc_profile=MPC_PROFILE_DEFAULT,
        changed_axis="baseline",
    ),
    "reward_v1_only": Phase52Profile(
        profile_id="reward_v1_only",
        reward_profile=PHASE5_2_REWARD_PROFILE,
        adapter_profile=ADAPTER_PROFILE_DEFAULT,
        mpc_profile=MPC_PROFILE_DEFAULT,
        changed_axis="reward",
    ),
    "adapter_soft_v1_only": Phase52Profile(
        profile_id="adapter_soft_v1_only",
        reward_profile=LEGACY_REWARD_PROFILE,
        adapter_profile=ADAPTER_PROFILE_SOFT_V1,
        mpc_profile=MPC_PROFILE_DEFAULT,
        changed_axis="adapter",
    ),
    "mpc_health_v1_only": Phase52Profile(
        profile_id="mpc_health_v1_only",
        reward_profile=LEGACY_REWARD_PROFILE,
        adapter_profile=ADAPTER_PROFILE_DEFAULT,
        mpc_profile=MPC_PROFILE_HEALTH_V1,
        changed_axis="mpc",
    ),
    "mpc_delta_limit_probe_v1": Phase52Profile(
        profile_id="mpc_delta_limit_probe_v1",
        reward_profile=LEGACY_REWARD_PROFILE,
        adapter_profile=ADAPTER_PROFILE_DEFAULT,
        mpc_profile=MPC_PROFILE_DELTA_LIMIT_PROBE_V1,
        changed_axis="mpc",
        initial_ablation=False,
    ),
}
PHASE52_PROFILE_IDS = tuple(PHASE52_PROFILE_TABLE)


def adapter_profile_values(profile_id: str) -> AdapterProfileValues:
    try:
        return ADAPTER_PROFILE_TABLE[profile_id]
    except KeyError as exc:
        raise ValueError(f"adapter_profile must be one of {list(ADAPTER_PROFILE_IDS)}, got {profile_id!r}") from exc


def mpc_profile_values(profile_id: str) -> MPCProfileValues:
    try:
        return MPC_PROFILE_TABLE[profile_id]
    except KeyError as exc:
        raise ValueError(f"mpc_profile must be one of {list(MPC_PROFILE_IDS)}, got {profile_id!r}") from exc


def get_phase52_profile(profile_id: str) -> Phase52Profile:
    try:
        return PHASE52_PROFILE_TABLE[profile_id]
    except KeyError as exc:
        raise ValueError(f"profile_id must be one of {list(PHASE52_PROFILE_IDS)}, got {profile_id!r}") from exc


def _coalesce(expected: str, provided: str | None, field_name: str) -> str:
    if provided is None:
        return expected
    if provided != expected:
        raise ValueError(f"{field_name} must be {expected!r} for this profile, got {provided!r}")
    return provided


def resolve_phase52_profile(
    *,
    profile_id: str,
    reward_profile: str | None = None,
    adapter_profile: str | None = None,
    mpc_profile: str | None = None,
    changed_axis: str | None = None,
) -> Phase52Profile:
    profile = get_phase52_profile(profile_id)
    return Phase52Profile(
        profile_id=profile.profile_id,
        reward_profile=_coalesce(profile.reward_profile, reward_profile, "reward_profile"),
        adapter_profile=_coalesce(profile.adapter_profile, adapter_profile, "adapter_profile"),
        mpc_profile=_coalesce(profile.mpc_profile, mpc_profile, "mpc_profile"),
        changed_axis=_coalesce(profile.changed_axis, changed_axis, "changed_axis"),
        initial_ablation=profile.initial_ablation,
    )


def checkpoint_provenance_for_phase52_evidence(evidence_level: str) -> str:
    if evidence_level == PHASE5_2_MATCHED_EVIDENCE_LEVEL:
        evidence_level = PHASE5_2_CANDIDATE_EVIDENCE_LEVEL
    try:
        return PHASE5_2_PROVENANCE_BY_EVIDENCE_LEVEL[evidence_level]
    except KeyError as exc:
        raise ValueError(f"Unsupported Phase 5.2 evidence level: {evidence_level!r}") from exc

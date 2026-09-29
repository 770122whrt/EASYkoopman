from __future__ import annotations

from dataclasses import dataclass, field

from koopman.phase5_2_profiles import (
    ADAPTER_PROFILE_DEFAULT,
    LEGACY_REWARD_PROFILE,
    MPC_PROFILE_DEFAULT,
    MPC_PROFILE_HEALTH_V1,
    PHASE5_2_REWARD_PROFILE,
    _coalesce,
    mpc_profile_values,
)
from koopman.phase5_2_reward import Phase52RewardConfig
from koopman.phase5_3_profiles import PHASE5_3_COMPARISON_BASELINE, PHASE5_3_HEALTH_FLOOR


PHASE5_4_SENTINEL_EVIDENCE_LEVEL = "phase5_4_pareto_sentinel"
PHASE5_4_CANDIDATE_EVIDENCE_LEVEL = "phase5_4_pareto_candidate"
PHASE5_4_REFINEMENT_EVIDENCE_LEVEL = "phase5_4_pareto_refinement"
PHASE5_4_MATCHED_EVIDENCE_LEVEL = "phase5_4_pareto_matched_eval"

PHASE5_4_TRAINING_EVIDENCE_LEVELS = (
    PHASE5_4_SENTINEL_EVIDENCE_LEVEL,
    PHASE5_4_CANDIDATE_EVIDENCE_LEVEL,
    PHASE5_4_REFINEMENT_EVIDENCE_LEVEL,
)
PHASE5_4_EVIDENCE_LEVELS = PHASE5_4_TRAINING_EVIDENCE_LEVELS + (PHASE5_4_MATCHED_EVIDENCE_LEVEL,)

PHASE5_4_SENTINEL_CHECKPOINT_PROVENANCE = "phase5_4_pareto_sentinel"
PHASE5_4_CANDIDATE_CHECKPOINT_PROVENANCE = "phase5_4_pareto_candidate"
PHASE5_4_REFINEMENT_CHECKPOINT_PROVENANCE = "phase5_4_pareto_refinement"
PHASE5_4_PROVENANCE_BY_EVIDENCE_LEVEL = {
    PHASE5_4_SENTINEL_EVIDENCE_LEVEL: PHASE5_4_SENTINEL_CHECKPOINT_PROVENANCE,
    PHASE5_4_CANDIDATE_EVIDENCE_LEVEL: PHASE5_4_CANDIDATE_CHECKPOINT_PROVENANCE,
    PHASE5_4_REFINEMENT_EVIDENCE_LEVEL: PHASE5_4_REFINEMENT_CHECKPOINT_PROVENANCE,
}

PHASE5_4_TRACK_IDS = ("R", "RM")
PHASE5_4_SWEEP_ROUNDS = ("round1", "round2")
PHASE5_4_TRAINING_LADDER_STAGES = ("sentinel", "candidate", "refinement")
PHASE5_4_CHANGED_AXIS_IDS = ("reward", "reward_mpc")
PHASE5_4_COMPARISON_BASELINE = PHASE5_3_COMPARISON_BASELINE
PHASE5_4_HEALTH_FLOOR = PHASE5_3_HEALTH_FLOOR
PHASE5_4_CROSS_REFERENCE = "cross_reward_v1_mpc_health"

PARAMETER_STEP_SIZES = {
    "phase5_2_w_pwm_sat": 0.05,
    "phase5_2_w_fallback": 0.05,
    "phase5_2_w_action": 0.005,
    "phase5_2_w_delta_action": 0.01,
    "mpc_timeout_ms": 2.0,
    "mpc_control_weight": 0.005,
    "mpc_smoothness_weight": 0.015,
    "mpc_horizon": 1.0,
}

TRACK_R_PARENT_REWARD = Phase52RewardConfig(
    w_fallback=0.30,
    w_pwm_sat=0.20,
    w_action=0.01,
    w_delta_action=0.02,
)
TRACK_RM_PARENT_MPC = {
    "mpc_horizon": 5,
    "mpc_timeout_ms": 12.0,
    "mpc_control_weight": 0.03,
    "mpc_smoothness_weight": 0.10,
}


@dataclass(frozen=True)
class Phase54MPCValues:
    horizon: int
    timeout_ms: float
    delta_pwm_limit: float
    depth_weight: float
    attitude_weight: float
    control_weight: float
    smoothness_weight: float


@dataclass(frozen=True)
class Phase54Profile:
    profile_id: str
    track: str
    parent_profile_id: str
    reward_profile: str
    adapter_profile: str
    mpc_profile: str
    changed_axis: str
    sweep_round: str
    reward_overrides: dict[str, float] = field(default_factory=dict)
    mpc_overrides: dict[str, float | int] = field(default_factory=dict)
    protected_strengths: tuple[str, ...] = ()
    nearest_smaller_candidate_id: str | None = None

    @property
    def parameter_step_count(self) -> dict[str, float]:
        parent_values = _parent_parameter_values(self.track)
        overrides = {**self.reward_overrides, **self.mpc_overrides}
        step_counts: dict[str, float] = {}
        for parameter_name, candidate_value in overrides.items():
            parent_value = parent_values[parameter_name]
            step_size = PARAMETER_STEP_SIZES[parameter_name]
            step_counts[parameter_name] = abs(float(candidate_value) - float(parent_value)) / step_size
        return step_counts

    @property
    def parameter_distance_from_parent(self) -> float:
        return float(sum(self.parameter_step_count.values()))

    @property
    def changed_parameter_count(self) -> int:
        return len(self.parameter_step_count)


def _parent_parameter_values(track: str) -> dict[str, float]:
    if track == "R":
        return {
            "phase5_2_w_fallback": TRACK_R_PARENT_REWARD.w_fallback,
            "phase5_2_w_pwm_sat": TRACK_R_PARENT_REWARD.w_pwm_sat,
            "phase5_2_w_action": TRACK_R_PARENT_REWARD.w_action,
            "phase5_2_w_delta_action": TRACK_R_PARENT_REWARD.w_delta_action,
        }
    if track == "RM":
        return dict(TRACK_RM_PARENT_MPC)
    raise ValueError(f"track must be one of {list(PHASE5_4_TRACK_IDS)}, got {track!r}")


def _profile(
    *,
    profile_id: str,
    track: str,
    parent_profile_id: str,
    reward_overrides: dict[str, float] | None = None,
    mpc_overrides: dict[str, float | int] | None = None,
    sweep_round: str = "round1",
    nearest_smaller_candidate_id: str | None = None,
) -> Phase54Profile:
    if track == "R":
        reward_profile = PHASE5_2_REWARD_PROFILE
        mpc_profile = MPC_PROFILE_DEFAULT
        changed_axis = "reward"
        protected_strengths = ("reward_v1_fallback",)
    elif track == "RM":
        reward_profile = PHASE5_2_REWARD_PROFILE
        mpc_profile = MPC_PROFILE_HEALTH_V1
        changed_axis = "reward_mpc"
        protected_strengths = ("mpc_pwm", "mpc_clip", "mpc_depth", "mpc_attitude")
    else:
        raise ValueError(f"Unsupported Phase 5.4 track: {track!r}")

    return Phase54Profile(
        profile_id=profile_id,
        track=track,
        parent_profile_id=parent_profile_id,
        reward_profile=reward_profile,
        adapter_profile=ADAPTER_PROFILE_DEFAULT,
        mpc_profile=mpc_profile,
        changed_axis=changed_axis,
        sweep_round=sweep_round,
        reward_overrides=reward_overrides or {},
        mpc_overrides=mpc_overrides or {},
        protected_strengths=protected_strengths,
        nearest_smaller_candidate_id=nearest_smaller_candidate_id,
    )


PHASE54_PROFILE_TABLE = {
    "r_pwm025": _profile(
        profile_id="r_pwm025",
        track="R",
        parent_profile_id="reward_v1_only",
        reward_overrides={"phase5_2_w_pwm_sat": 0.25},
    ),
    "r_pwm030": _profile(
        profile_id="r_pwm030",
        track="R",
        parent_profile_id="reward_v1_only",
        reward_overrides={"phase5_2_w_pwm_sat": 0.30},
        nearest_smaller_candidate_id="r_pwm025",
    ),
    "r_pwm035": _profile(
        profile_id="r_pwm035",
        track="R",
        parent_profile_id="reward_v1_only",
        reward_overrides={"phase5_2_w_pwm_sat": 0.35},
        nearest_smaller_candidate_id="r_pwm030",
    ),
    "r_pwm030_action_smooth": _profile(
        profile_id="r_pwm030_action_smooth",
        track="R",
        parent_profile_id="reward_v1_only",
        reward_overrides={
            "phase5_2_w_pwm_sat": 0.30,
            "phase5_2_w_action": 0.015,
            "phase5_2_w_delta_action": 0.03,
        },
        nearest_smaller_candidate_id="r_pwm030",
    ),
    "r_pwm030_fallback025": _profile(
        profile_id="r_pwm030_fallback025",
        track="R",
        parent_profile_id="reward_v1_only",
        reward_overrides={"phase5_2_w_pwm_sat": 0.30, "phase5_2_w_fallback": 0.25},
        nearest_smaller_candidate_id="r_pwm025",
    ),
    "rm_timeout14": _profile(
        profile_id="rm_timeout14",
        track="RM",
        parent_profile_id="cross_reward_v1_mpc_health",
        mpc_overrides={"mpc_timeout_ms": 14.0},
    ),
    "rm_timeout16": _profile(
        profile_id="rm_timeout16",
        track="RM",
        parent_profile_id="cross_reward_v1_mpc_health",
        mpc_overrides={"mpc_timeout_ms": 16.0},
        nearest_smaller_candidate_id="rm_timeout14",
    ),
    "rm_midweights": _profile(
        profile_id="rm_midweights",
        track="RM",
        parent_profile_id="cross_reward_v1_mpc_health",
        mpc_overrides={"mpc_control_weight": 0.02, "mpc_smoothness_weight": 0.075},
    ),
    "rm_midweights_timeout14": _profile(
        profile_id="rm_midweights_timeout14",
        track="RM",
        parent_profile_id="cross_reward_v1_mpc_health",
        mpc_overrides={"mpc_control_weight": 0.02, "mpc_smoothness_weight": 0.075, "mpc_timeout_ms": 14.0},
        nearest_smaller_candidate_id="rm_midweights",
    ),
    "rm_lightweights_timeout14": _profile(
        profile_id="rm_lightweights_timeout14",
        track="RM",
        parent_profile_id="cross_reward_v1_mpc_health",
        mpc_overrides={"mpc_control_weight": 0.015, "mpc_smoothness_weight": 0.06, "mpc_timeout_ms": 14.0},
        nearest_smaller_candidate_id="rm_midweights_timeout14",
    ),
    "rm_horizon4_timeout14": _profile(
        profile_id="rm_horizon4_timeout14",
        track="RM",
        parent_profile_id="cross_reward_v1_mpc_health",
        mpc_overrides={
            "mpc_horizon": 4,
            "mpc_control_weight": 0.02,
            "mpc_smoothness_weight": 0.075,
            "mpc_timeout_ms": 14.0,
        },
        nearest_smaller_candidate_id="rm_midweights_timeout14",
    ),
    "rm_timeout15": _profile(
        profile_id="rm_timeout15",
        track="RM",
        parent_profile_id="cross_reward_v1_mpc_health",
        mpc_overrides={"mpc_timeout_ms": 15.0},
        sweep_round="round2",
        nearest_smaller_candidate_id="rm_timeout14",
    ),
    "rm_interpolate_weights_timeout14": _profile(
        profile_id="rm_interpolate_weights_timeout14",
        track="RM",
        parent_profile_id="cross_reward_v1_mpc_health",
        mpc_overrides={"mpc_control_weight": 0.0175, "mpc_smoothness_weight": 0.0675, "mpc_timeout_ms": 14.0},
        sweep_round="round2",
        nearest_smaller_candidate_id="rm_lightweights_timeout14",
    ),
    "r_pwm0325": _profile(
        profile_id="r_pwm0325",
        track="R",
        parent_profile_id="reward_v1_only",
        reward_overrides={"phase5_2_w_pwm_sat": 0.325},
        sweep_round="round2",
        nearest_smaller_candidate_id="r_pwm030",
    ),
}

PHASE54_PROFILE_IDS = tuple(PHASE54_PROFILE_TABLE)


def get_phase54_profile(profile_id: str) -> Phase54Profile:
    try:
        return PHASE54_PROFILE_TABLE[profile_id]
    except KeyError as exc:
        raise ValueError(f"profile_id must be one of {list(PHASE54_PROFILE_IDS)}, got {profile_id!r}") from exc


def resolve_phase54_profile(
    *,
    profile_id: str,
    reward_profile: str | None = None,
    adapter_profile: str | None = None,
    mpc_profile: str | None = None,
    changed_axis: str | None = None,
) -> Phase54Profile:
    profile = get_phase54_profile(profile_id)
    return Phase54Profile(
        profile_id=profile.profile_id,
        track=profile.track,
        parent_profile_id=profile.parent_profile_id,
        reward_profile=_coalesce(profile.reward_profile, reward_profile, "reward_profile"),
        adapter_profile=_coalesce(profile.adapter_profile, adapter_profile, "adapter_profile"),
        mpc_profile=_coalesce(profile.mpc_profile, mpc_profile, "mpc_profile"),
        changed_axis=_coalesce(profile.changed_axis, changed_axis, "changed_axis"),
        sweep_round=profile.sweep_round,
        reward_overrides=dict(profile.reward_overrides),
        mpc_overrides=dict(profile.mpc_overrides),
        protected_strengths=profile.protected_strengths,
        nearest_smaller_candidate_id=profile.nearest_smaller_candidate_id,
    )


def effective_reward_config(profile: Phase54Profile) -> Phase52RewardConfig:
    base = TRACK_R_PARENT_REWARD
    values = {
        "pwm_soft_limit": base.pwm_soft_limit,
        "latency_ref_ms": base.latency_ref_ms,
        "latency_clip": base.latency_clip,
        "w_fallback": base.w_fallback,
        "w_pwm_sat": base.w_pwm_sat,
        "w_latency": base.w_latency,
        "w_action": base.w_action,
        "w_delta_action": base.w_delta_action,
    }
    mapping = {
        "phase5_2_w_fallback": "w_fallback",
        "phase5_2_w_pwm_sat": "w_pwm_sat",
        "phase5_2_w_action": "w_action",
        "phase5_2_w_delta_action": "w_delta_action",
    }
    for key, value in profile.reward_overrides.items():
        values[mapping[key]] = float(value)
    return Phase52RewardConfig(**values)


def effective_mpc_values(profile: Phase54Profile) -> Phase54MPCValues:
    base = mpc_profile_values(profile.mpc_profile)
    values: dict[str, float | int] = {
        "horizon": 5,
        "timeout_ms": 12.0,
        "delta_pwm_limit": base.delta_pwm_limit,
        "depth_weight": base.depth_weight,
        "attitude_weight": base.attitude_weight,
        "control_weight": base.control_weight,
        "smoothness_weight": base.smoothness_weight,
    }
    mapping = {
        "mpc_horizon": "horizon",
        "mpc_timeout_ms": "timeout_ms",
        "mpc_control_weight": "control_weight",
        "mpc_smoothness_weight": "smoothness_weight",
    }
    for key, value in profile.mpc_overrides.items():
        values[mapping[key]] = value
    return Phase54MPCValues(
        horizon=int(values["horizon"]),
        timeout_ms=float(values["timeout_ms"]),
        delta_pwm_limit=float(values["delta_pwm_limit"]),
        depth_weight=float(values["depth_weight"]),
        attitude_weight=float(values["attitude_weight"]),
        control_weight=float(values["control_weight"]),
        smoothness_weight=float(values["smoothness_weight"]),
    )


def checkpoint_provenance_for_phase54_evidence(evidence_level: str) -> str:
    if evidence_level == PHASE5_4_MATCHED_EVIDENCE_LEVEL:
        evidence_level = PHASE5_4_CANDIDATE_EVIDENCE_LEVEL
    try:
        return PHASE5_4_PROVENANCE_BY_EVIDENCE_LEVEL[evidence_level]
    except KeyError as exc:
        raise ValueError(f"Unsupported Phase 5.4 evidence level: {evidence_level!r}") from exc

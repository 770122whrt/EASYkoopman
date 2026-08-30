"""Shared semantic identifiers for additive Phase 8.1 contracts."""

from __future__ import annotations


CONDITIONING_STRUCTURED_PCA2_V21 = "structured_pca2"
LOCO_SOURCE7_SCOPE_V21 = "loco_source7"
FINAL_REFIT_ALL8_SCOPE_V21 = "final_refit_all8"
CONDITIONAL_NOT_APPLICABLE_SCOPE_V21 = "not_applicable"
SERVER_ARTIFACT_ORIGIN_V21 = "server_isaac_smoke"
ROLLOUT_POLICY_VERSION_V21 = "phase8.1-rollout-analysis-policy-v1"
OFFICIAL_ROLLOUT_HORIZONS_V21 = (5, 20, 60, "full")
OFFICIAL_DEPTH_ABS_MAX_V21 = 100.0
OFFICIAL_LINEAR_VELOCITY_ABS_MAX_V21 = 100.0
OFFICIAL_ANGULAR_VELOCITY_ABS_MAX_V21 = 100.0


def official_rollout_policy_payload_v21() -> dict[str, object]:
    """Return the inherited Phase 8 divergence policy without SO(3) projection fields."""

    return {
        "angular_velocity_abs_max": OFFICIAL_ANGULAR_VELOCITY_ABS_MAX_V21,
        "depth_abs_max": OFFICIAL_DEPTH_ABS_MAX_V21,
        "horizons": list(OFFICIAL_ROLLOUT_HORIZONS_V21),
        "linear_velocity_abs_max": OFFICIAL_LINEAR_VELOCITY_ABS_MAX_V21,
        "version": ROLLOUT_POLICY_VERSION_V21,
    }

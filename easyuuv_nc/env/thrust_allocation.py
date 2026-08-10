"""Compatibility re-exports for the moved pure thrust-allocation API."""

from ..thrust_allocation import (
    CONTROL_CHANNEL_NAMES,
    LEGACY_CONTROL_TO_MOTOR,
    ThrusterLayout,
    allocate,
    build_wrench_matrix,
    control_channels_to_wrench,
    declared_control_rank,
    dof_weight_vector,
    quat_apply,
    quat_from_rpy,
)

__all__ = (
    "CONTROL_CHANNEL_NAMES",
    "LEGACY_CONTROL_TO_MOTOR",
    "ThrusterLayout",
    "allocate",
    "build_wrench_matrix",
    "control_channels_to_wrench",
    "declared_control_rank",
    "dof_weight_vector",
    "quat_apply",
    "quat_from_rpy",
)

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import torch


DEPTH_BARRIER_CONTRACT_VERSION = "v1_depth_barrier"
DEFAULT_DEPTH_REFERENCE_FRAME = "surface_relative_depth"
DEFAULT_DEPTH_SURFACE_Z = 3.0
DEFAULT_DEPTH_UPPER_LIMIT = -0.5
DEFAULT_DEPTH_LOWER_LIMIT = -1.5
DEFAULT_DEPTH_TRANSITION_WIDTH = 0.2
VALID_DEPTH_REFERENCE_FRAMES = ("raw_world_z", "surface_relative_depth")


def angle_remap(angle: torch.Tensor) -> torch.Tensor:
    return (angle + torch.pi) % (2 * torch.pi) - torch.pi


def calculate_compound_error(
    des_roll: float,
    des_pitch: float,
    des_yaw: float,
    true_roll: float,
    true_pitch: float,
    true_yaw: float,
    des_depth: float,
    true_depth: float,
) -> float:
    roll_error = float(angle_remap(torch.tensor(true_roll - des_roll)).item())
    pitch_error = float(angle_remap(torch.tensor(true_pitch - des_pitch)).item())
    yaw_error = float(angle_remap(torch.tensor(true_yaw - des_yaw)).item())
    depth_error = true_depth - des_depth
    return float(roll_error**2 + pitch_error**2 + yaw_error**2 + depth_error**2)


def calculate_attitude_tracking_mse(
    des_roll: float,
    des_pitch: float,
    des_yaw: float,
    true_roll: float,
    true_pitch: float,
    true_yaw: float,
) -> float:
    """Legacy RPY attitude-only squared error, excluding depth."""
    roll_error = float(angle_remap(torch.tensor(true_roll - des_roll)).item())
    pitch_error = float(angle_remap(torch.tensor(true_pitch - des_pitch)).item())
    yaw_error = float(angle_remap(torch.tensor(true_yaw - des_yaw)).item())
    return float(roll_error**2 + pitch_error**2 + yaw_error**2)


def _rpy_to_matrix_np(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr = math.cos(float(roll)), math.sin(float(roll))
    cp, sp = math.cos(float(pitch)), math.sin(float(pitch))
    cy, sy = math.cos(float(yaw)), math.sin(float(yaw))
    return np.asarray(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ],
        dtype=float,
    )


def calculate_attitude_error_so3(
    des_roll: float,
    des_pitch: float,
    des_yaw: float,
    true_roll: float,
    true_pitch: float,
    true_yaw: float,
) -> float:
    """SO(3) geodesic attitude error in radians from RPY targets/readouts."""
    r_des = _rpy_to_matrix_np(des_roll, des_pitch, des_yaw)
    r_true = _rpy_to_matrix_np(true_roll, true_pitch, true_yaw)
    r_err = r_des.T @ r_true
    cos_angle = np.clip((float(np.trace(r_err)) - 1.0) * 0.5, -1.0, 1.0)
    return float(math.acos(cos_angle))


def _nanmean(values: np.ndarray, default: float = 0.0) -> float:
    finite = values[np.isfinite(values)]
    return float(np.mean(finite)) if finite.size else float(default)


def _nanmax(values: np.ndarray, default: float = 0.0) -> float:
    finite = values[np.isfinite(values)]
    return float(np.max(finite)) if finite.size else float(default)


def _scalar_or_array(values: np.ndarray, scalar: bool):
    return float(values.reshape(-1)[0]) if scalar and values.size else values


def convert_depth_to_v1(
    depth,
    *,
    reference_frame: str = DEFAULT_DEPTH_REFERENCE_FRAME,
    surface_z: float = DEFAULT_DEPTH_SURFACE_Z,
):
    """Convert logged depth/z into the V1 real-world depth convention.

    V1 uses negative underwater depth relative to the water surface. The default
    simulator convention logs world ``z`` around ``+1.5`` while the water surface
    is around ``+3.0``. Therefore the default conversion is:

    ``depth_v1 = z_world - surface_z``.

    ``raw_world_z`` is kept as an opt-in compatibility path for old diagnostics.
    """
    frame = str(reference_frame)
    if frame not in VALID_DEPTH_REFERENCE_FRAMES:
        raise ValueError(
            f"Unsupported depth reference frame {frame!r}; "
            f"expected one of {VALID_DEPTH_REFERENCE_FRAMES}."
        )
    arr = np.asarray(depth, dtype=float)
    scalar = arr.ndim == 0
    arr = np.atleast_1d(arr)
    if frame == "surface_relative_depth":
        converted = arr - float(surface_z)
    else:
        converted = arr
    return _scalar_or_array(converted, scalar)


def resolve_depth_barrier_limits(
    *,
    upper_limit: float = DEFAULT_DEPTH_UPPER_LIMIT,
    lower_limit: float = DEFAULT_DEPTH_LOWER_LIMIT,
    transition_width: float = DEFAULT_DEPTH_TRANSITION_WIDTH,
) -> dict[str, float]:
    """Resolve hard depth bounds and their inner transition bands.

    The default hard tube is 1 m wide: ``[-1.5, -0.5]`` in V1 coordinates. The
    transition width can be tightened/relaxed without changing the hard bounds.
    """
    upper_limit = float(upper_limit)
    lower_limit = float(lower_limit)
    transition_width = max(float(transition_width), 0.0)
    if lower_limit >= upper_limit:
        raise ValueError(f"Depth lower_limit must be < upper_limit, got {lower_limit} >= {upper_limit}.")
    max_transition = 0.5 * (upper_limit - lower_limit)
    transition_width = min(transition_width, max_transition)
    return {
        "depth_upper_limit": upper_limit,
        "depth_upper_safe": upper_limit - transition_width,
        "depth_lower_safe": lower_limit + transition_width,
        "depth_lower_limit": lower_limit,
        "depth_tube_width": upper_limit - lower_limit,
        "depth_transition_width": transition_width,
    }


def calculate_depth_barrier_penalty_v1(
    true_depth_or_z,
    *,
    dt: float = 1.0,
    reference_frame: str = DEFAULT_DEPTH_REFERENCE_FRAME,
    surface_z: float = DEFAULT_DEPTH_SURFACE_Z,
    upper_limit: float = DEFAULT_DEPTH_UPPER_LIMIT,
    lower_limit: float = DEFAULT_DEPTH_LOWER_LIMIT,
    transition_width: float = DEFAULT_DEPTH_TRANSITION_WIDTH,
) -> dict:
    """Convert to V1 coordinates, then calculate depth safety-barrier metrics."""
    limits = resolve_depth_barrier_limits(
        upper_limit=upper_limit,
        lower_limit=lower_limit,
        transition_width=transition_width,
    )
    depth_v1 = convert_depth_to_v1(
        true_depth_or_z,
        reference_frame=reference_frame,
        surface_z=surface_z,
    )
    barrier = calculate_depth_barrier_penalty(
        depth_v1,
        dt=dt,
        upper_limit=limits["depth_upper_limit"],
        upper_safe=limits["depth_upper_safe"],
        lower_safe=limits["depth_lower_safe"],
        lower_limit=limits["depth_lower_limit"],
    )
    barrier.update(
        {
            "depth_reference_frame": str(reference_frame),
            "depth_surface_z": float(surface_z),
            "depth_tube_width": float(limits["depth_tube_width"]),
            "depth_transition_width": float(limits["depth_transition_width"]),
        }
    )
    return barrier


def calculate_depth_barrier_penalty(
    true_depth,
    *,
    dt: float = 1.0,
    upper_limit: float = -0.5,
    upper_safe: float = -0.7,
    lower_safe: float = -1.3,
    lower_limit: float = -1.5,
) -> dict:
    """Depth safety-barrier metrics for the V1 benchmark contract.

    Input must already be in the V1 negative-underwater depth coordinate. Use
    :func:`convert_depth_to_v1` or :func:`calculate_depth_barrier_penalty_v1`
    when consuming simulator world-z logs. The hard tube is [lower_limit, upper_limit], while
    [upper_safe, upper_limit] and [lower_limit, lower_safe] are soft transition
    bands. The returned per-step penalty is zero in the safe core, ramps to one
    at the hard boundary, and grows linearly outside the hard tube.
    """
    depth = np.asarray(true_depth, dtype=float)
    scalar = depth.ndim == 0
    depth = np.atleast_1d(depth)

    upper_band = max(float(upper_limit) - float(upper_safe), 1.0e-9)
    lower_band = max(float(lower_safe) - float(lower_limit), 1.0e-9)

    upper_transition = np.clip((depth - float(upper_safe)) / upper_band, 0.0, 1.0)
    lower_transition = np.clip((float(lower_safe) - depth) / lower_band, 0.0, 1.0)
    upper_outside = np.clip(depth - float(upper_limit), 0.0, None)
    lower_outside = np.clip(float(lower_limit) - depth, 0.0, None)
    hard_violation = upper_outside + lower_outside
    penalty = np.maximum(upper_transition, lower_transition)
    penalty = penalty + upper_outside / upper_band + lower_outside / lower_band

    finite_n = max(int(np.isfinite(depth).sum()), 1)
    dt = float(dt)
    return {
        "metric_contract_version": DEPTH_BARRIER_CONTRACT_VERSION,
        "depth_barrier_penalty": _scalar_or_array(penalty, scalar),
        "depth_violation": _scalar_or_array(hard_violation, scalar),
        "depth_upper_transition_penalty": _scalar_or_array(upper_transition, scalar),
        "depth_lower_transition_penalty": _scalar_or_array(lower_transition, scalar),
        "depth_violation_integral": float(np.nansum(hard_violation) * dt),
        "depth_violation_time_fraction": float(np.nansum(hard_violation > 0.0) / finite_n),
        "depth_upper_transition_integral": float(np.nansum(upper_transition) * dt),
        "depth_lower_transition_integral": float(np.nansum(lower_transition) * dt),
        "depth_barrier_penalty_mean": _nanmean(penalty),
        "depth_barrier_penalty_max": _nanmax(penalty),
        "depth_barrier_penalty_integral": float(np.nansum(penalty) * dt),
        "depth_upper_limit": float(upper_limit),
        "depth_upper_safe": float(upper_safe),
        "depth_lower_safe": float(lower_safe),
        "depth_lower_limit": float(lower_limit),
    }


def calculate_actuator_saturation_stats(saturation_ratio, *, threshold: float = 1.0e-6) -> dict[str, float]:
    """Aggregate allocator saturation telemetry into V1 summary fields.

    ``attitude_control_authority_ratio`` is a scalar proxy until per-axis
    allocator authority accounting is available: 1.0 means no logged saturation,
    0.0 means every actuator was saturated at every logged step.
    """
    arr = np.asarray(saturation_ratio, dtype=float)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {
            "actuator_saturation_time_fraction": 0.0,
            "actuator_saturation_p95": 0.0,
            "actuator_saturation_mean": 0.0,
            "actuator_saturation_max": 0.0,
            "attitude_control_authority_ratio": 1.0,
        }
    clipped = np.clip(finite, 0.0, 1.0)
    return {
        "actuator_saturation_time_fraction": float(np.mean(clipped > float(threshold))),
        "actuator_saturation_p95": float(np.percentile(clipped, 95.0)),
        "actuator_saturation_mean": float(np.mean(clipped)),
        "actuator_saturation_max": float(np.max(clipped)),
        "attitude_control_authority_ratio": float(np.mean(1.0 - clipped)),
    }


def calculate_control_effort(actions: torch.Tensor) -> float:
    if actions.ndim == 1:
        actions = actions.unsqueeze(0)
    return float(torch.linalg.norm(actions, dim=-1).mean().item())


def calculate_domain_bias(volume_scale: float, flow_velocity: Iterable[float]) -> float:
    flow_mag = float(np.linalg.norm(np.asarray(list(flow_velocity), dtype=np.float32)))
    return abs(volume_scale - 1.0) + flow_mag

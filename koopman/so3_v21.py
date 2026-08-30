"""Deterministic SO(3) numerics for the additive Phase 8.1 model stack.

Quaternions are binary64 ``[w, x, y, z]`` Hamilton quaternions that rotate
body-frame vectors into the world frame.  Model rollouts use body-right
increments; quaternion projection is deliberately not a recovery mechanism.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


STATE_DIM_V21 = 11
INCREMENT_TARGET_DIM_V21 = 10
DEPTH_INDEX_V21 = 0
QUATERNION_SLICE_V21 = slice(1, 5)
LINEAR_VELOCITY_SLICE_V21 = slice(5, 8)
ANGULAR_VELOCITY_SLICE_V21 = slice(8, 11)

QUATERNION_NORM_MIN_V21 = 1.0e-10
QUATERNION_INPUT_NORM_TOLERANCE_V21 = 1.0e-6
QUATERNION_COMPOSITION_DRIFT_LIMIT_V21 = 1.0e-10
_SERIES_THRESHOLD = math.sqrt(np.finfo(np.float64).eps)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _vector(value: Any, width: int, reason: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (width,) or not np.isfinite(result).all():
        _fail(reason)
    return np.array(result, dtype=np.float64, copy=True)


def normalize_quaternion_v21(value: Any) -> np.ndarray:
    """Validate a unit quaternion and remove only binary64 input roundoff."""

    quaternion = _vector(value, 4, "quaternion_invalid")
    norm = float(np.linalg.norm(quaternion))
    if (
        not math.isfinite(norm)
        or norm < QUATERNION_NORM_MIN_V21
        or abs(norm - 1.0) > QUATERNION_INPUT_NORM_TOLERANCE_V21
    ):
        _fail("quaternion_invalid")
    return quaternion / norm


def canonicalize_quaternion_v21(value: Any) -> np.ndarray:
    """Return the unique sign representative required by the v2.1 contract."""

    quaternion = normalize_quaternion_v21(value)
    if quaternion[0] < 0.0:
        quaternion = -quaternion
    elif quaternion[0] == 0.0:
        vector = quaternion[1:]
        pivot = int(np.flatnonzero(np.abs(vector) == np.max(np.abs(vector)))[0])
        if vector[pivot] < 0.0:
            quaternion = -quaternion
    return quaternion


def hamilton_product_v21(left: Any, right: Any) -> np.ndarray:
    """Hamilton product without implicit normalization or projection."""

    lhs = _vector(left, 4, "quaternion_invalid")
    rhs = _vector(right, 4, "quaternion_invalid")
    lw, lx, ly, lz = lhs
    rw, rx, ry, rz = rhs
    return np.asarray(
        [
            lw * rw - lx * rx - ly * ry - lz * rz,
            lw * rx + lx * rw + ly * rz - lz * ry,
            lw * ry - lx * rz + ly * rw + lz * rx,
            lw * rz + lx * ry - ly * rx + lz * rw,
        ],
        dtype=np.float64,
    )


def quaternion_inverse_v21(value: Any) -> np.ndarray:
    quaternion = normalize_quaternion_v21(value)
    return quaternion * np.asarray([1.0, -1.0, -1.0, -1.0], dtype=np.float64)


def quaternion_to_rotation_matrix_v21(value: Any) -> np.ndarray:
    w, x, y, z = normalize_quaternion_v21(value)
    return np.asarray(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y)],
            [2.0 * (x * y + w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - w * x)],
            [2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def quaternion_to_r6_v21(value: Any) -> np.ndarray:
    rotation = quaternion_to_rotation_matrix_v21(value)
    return np.concatenate((rotation[:, 0], rotation[:, 1]))


def so3_log_v21(value: Any) -> np.ndarray:
    """Principal quaternion logarithm as a body-frame rotation vector."""

    quaternion = canonicalize_quaternion_v21(value)
    w = float(quaternion[0])
    vector = quaternion[1:]
    vector_norm = float(np.linalg.norm(vector))
    if vector_norm == 0.0:
        return np.zeros(3, dtype=np.float64)
    if vector_norm < _SERIES_THRESHOLD:
        scale = 2.0 / w - 2.0 * vector_norm**2 / (3.0 * w**3)
    else:
        theta = 2.0 * math.atan2(vector_norm, w)
        scale = theta / vector_norm
    return np.asarray(scale * vector, dtype=np.float64)


def so3_exp_v21(value: Any) -> np.ndarray:
    """Quaternion exponential of a body-frame rotation vector."""

    vector = _vector(value, 3, "rotation_vector_invalid")
    theta = float(np.linalg.norm(vector))
    half = 0.5 * theta
    if theta < _SERIES_THRESHOLD:
        vector_scale = 0.5 - theta**2 / 48.0 + theta**4 / 3840.0
    else:
        vector_scale = math.sin(half) / theta
    # ``cos(pi/2)`` is a positive binary64 residual, not mathematical zero.
    # Pin the exact principal-branch boundary so the approved 180-degree axis
    # tie-break is actually reachable and opposite axes canonicalize alike.
    scalar = 0.0 if theta == math.pi else math.cos(half)
    quaternion = np.concatenate(([scalar], vector_scale * vector))
    norm = float(np.linalg.norm(quaternion))
    if not math.isfinite(norm) or abs(norm - 1.0) > QUATERNION_COMPOSITION_DRIFT_LIMIT_V21:
        _fail("quaternion_unit_norm_drift")
    return canonicalize_quaternion_v21(quaternion / norm)


def body_right_increment_v21(current: Any, next_value: Any) -> np.ndarray:
    current_quaternion = normalize_quaternion_v21(current)
    next_quaternion = normalize_quaternion_v21(next_value)
    delta = hamilton_product_v21(
        quaternion_inverse_v21(current_quaternion), next_quaternion
    )
    return so3_log_v21(delta)


def apply_body_right_increment_v21(current: Any, delta_theta_body: Any) -> np.ndarray:
    current_quaternion = normalize_quaternion_v21(current)
    delta_quaternion = so3_exp_v21(delta_theta_body)
    composed = hamilton_product_v21(current_quaternion, delta_quaternion)
    norm = float(np.linalg.norm(composed))
    if (
        not math.isfinite(norm)
        or norm < QUATERNION_NORM_MIN_V21
        or abs(norm - 1.0) > QUATERNION_COMPOSITION_DRIFT_LIMIT_V21
    ):
        _fail("quaternion_unit_norm_drift")
    return canonicalize_quaternion_v21(composed / norm)


def _state(value: Any) -> np.ndarray:
    state = _vector(value, STATE_DIM_V21, "state_invalid")
    state[QUATERNION_SLICE_V21] = normalize_quaternion_v21(
        state[QUATERNION_SLICE_V21]
    )
    return state


def build_increment_target_v21(current_state: Any, next_state: Any) -> np.ndarray:
    """Build the frozen 10D delta target from two 11D states."""

    current = _state(current_state)
    next_value = _state(next_state)
    return np.concatenate(
        (
            [next_value[DEPTH_INDEX_V21] - current[DEPTH_INDEX_V21]],
            next_value[LINEAR_VELOCITY_SLICE_V21]
            - current[LINEAR_VELOCITY_SLICE_V21],
            next_value[ANGULAR_VELOCITY_SLICE_V21]
            - current[ANGULAR_VELOCITY_SLICE_V21],
            body_right_increment_v21(
                current[QUATERNION_SLICE_V21], next_value[QUATERNION_SLICE_V21]
            ),
        )
    )


def apply_increment_target_v21(current_state: Any, increment_target: Any) -> np.ndarray:
    """Apply a 10D delta prediction to an 11D state."""

    current = _state(current_state)
    increment = _vector(
        increment_target, INCREMENT_TARGET_DIM_V21, "increment_target_invalid"
    )
    result = np.array(current, copy=True)
    result[DEPTH_INDEX_V21] += increment[0]
    result[LINEAR_VELOCITY_SLICE_V21] += increment[1:4]
    result[ANGULAR_VELOCITY_SLICE_V21] += increment[4:7]
    result[QUATERNION_SLICE_V21] = apply_body_right_increment_v21(
        current[QUATERNION_SLICE_V21], increment[7:10]
    )
    return result


def so3_geodesic_radians_v21(reference: Any, prediction: Any) -> float | np.ndarray:
    """Sign-invariant geodesic angle for one quaternion or equal-shaped batches."""

    first = np.asarray(reference, dtype=np.float64)
    second = np.asarray(prediction, dtype=np.float64)
    if first.shape != second.shape or first.shape[-1:] != (4,):
        _fail("quaternion_invalid")
    flat_first = first.reshape(-1, 4)
    flat_second = second.reshape(-1, 4)
    angles = np.empty(flat_first.shape[0], dtype=np.float64)
    for index, (left, right) in enumerate(zip(flat_first, flat_second, strict=True)):
        normalized_left = normalize_quaternion_v21(left)
        normalized_right = normalize_quaternion_v21(right)
        dot = float(abs(np.dot(normalized_left, normalized_right)))
        angles[index] = 2.0 * math.acos(min(1.0, max(0.0, dot)))
    shaped = angles.reshape(first.shape[:-1])
    return float(shaped) if shaped.ndim == 0 else shaped

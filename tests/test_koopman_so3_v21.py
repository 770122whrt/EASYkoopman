"""Frozen SO(3) contracts for the additive Phase 8.1 backend."""

from __future__ import annotations

import math

import numpy as np
import pytest

from koopman.so3_v21 import (
    apply_body_right_increment_v21,
    apply_increment_target_v21,
    body_right_increment_v21,
    build_increment_target_v21,
    canonicalize_quaternion_v21,
    hamilton_product_v21,
    quaternion_to_r6_v21,
    so3_exp_v21,
    so3_geodesic_radians_v21,
    so3_log_v21,
)


def _axis_angle(axis: tuple[float, float, float], angle: float) -> np.ndarray:
    unit = np.asarray(axis, dtype=np.float64)
    unit /= np.linalg.norm(unit)
    return np.concatenate(([math.cos(angle / 2.0)], math.sin(angle / 2.0) * unit))


def _state(quaternion: np.ndarray, *, depth: float = 2.0) -> np.ndarray:
    return np.concatenate(
        (
            [depth],
            quaternion,
            [0.1, -0.2, 0.3],
            [-0.4, 0.5, -0.6],
        )
    ).astype(np.float64)


def test_r6_is_body_to_world_first_two_columns_in_column_major_order() -> None:
    quaternion = _axis_angle((0.0, 0.0, 1.0), math.pi / 2.0)

    r6 = quaternion_to_r6_v21(quaternion)

    assert np.allclose(r6, [0.0, 1.0, 0.0, -1.0, 0.0, 0.0], atol=1e-15)


@pytest.mark.parametrize(
    "quaternion",
    (
        np.asarray([0.5, -0.5, 0.5, -0.5]),
        np.asarray([0.0, -1.0, 1.0, 0.0]) / math.sqrt(2.0),
    ),
)
def test_quaternion_canonicalization_is_sign_invariant(quaternion: np.ndarray) -> None:
    first = canonicalize_quaternion_v21(quaternion)
    second = canonicalize_quaternion_v21(-quaternion)

    assert np.array_equal(first, second)
    assert first[0] >= 0.0
    if first[0] == 0.0:
        tied = np.flatnonzero(np.abs(first[1:]) == np.max(np.abs(first[1:])))
        assert first[1 + int(tied[0])] > 0.0


@pytest.mark.parametrize(
    ("axis", "angle"),
    (
        ((1.0, 0.0, 0.0), 0.0),
        ((0.0, 1.0, 0.0), math.pi / 2.0),
        ((1.0, 1.0, 0.0), math.pi),
    ),
)
def test_log_exp_round_trip_is_deterministic_at_zero_ninety_and_pi(
    axis: tuple[float, float, float], angle: float
) -> None:
    vector = np.asarray(axis, dtype=np.float64)
    if angle:
        vector = vector / np.linalg.norm(vector) * angle
    else:
        vector[:] = 0.0

    quaternion = so3_exp_v21(vector)
    recovered = so3_log_v21(quaternion)

    assert np.all(np.isfinite(quaternion))
    assert np.all(np.isfinite(recovered))
    assert np.allclose(recovered, vector, atol=2e-15, rtol=2e-15)


def test_near_zero_log_and_exp_use_continuous_finite_series() -> None:
    vector = np.asarray([1.0e-12, -2.0e-12, 3.0e-12], dtype=np.float64)

    recovered = so3_log_v21(so3_exp_v21(vector))

    assert np.all(np.isfinite(recovered))
    assert np.allclose(recovered, vector, atol=1e-27, rtol=1e-14)


def test_exact_pi_axis_tie_uses_lowest_index_and_positive_sign() -> None:
    quaternion = np.asarray([0.0, -1.0, 1.0, 0.0], dtype=np.float64)
    quaternion /= np.linalg.norm(quaternion)

    vector = so3_log_v21(quaternion)

    assert vector[0] > 0.0
    assert vector[1] < 0.0
    assert np.isclose(np.linalg.norm(vector), math.pi)


def test_exact_pi_exp_canonicalizes_opposite_tied_axes_identically() -> None:
    axis = np.asarray([1.0, -1.0, 0.0], dtype=np.float64) / math.sqrt(2.0)

    positive = so3_exp_v21(math.pi * axis)
    negative = so3_exp_v21(-math.pi * axis)

    assert np.array_equal(positive, negative)
    assert positive[0] == 0.0
    assert positive[1] > 0.0


def test_body_right_increment_is_not_world_left_increment() -> None:
    current = _axis_angle((0.0, 0.0, 1.0), math.pi / 2.0)
    body_increment = np.asarray([math.pi / 2.0, 0.0, 0.0])
    expected = hamilton_product_v21(current, so3_exp_v21(body_increment))
    world_left = hamilton_product_v21(so3_exp_v21(body_increment), current)

    predicted = apply_body_right_increment_v21(current, body_increment)
    recovered = body_right_increment_v21(current, predicted)

    assert so3_geodesic_radians_v21(predicted, expected) < 1e-14
    assert so3_geodesic_radians_v21(predicted, world_left) > 1.0
    assert np.allclose(recovered, body_increment, atol=2e-15)


def test_nonzero_noncommutative_multi_step_body_right_rollout_preserves_norm() -> None:
    increments = (
        np.asarray([0.31, 0.0, 0.0], dtype=np.float64),
        np.asarray([0.0, -0.27, 0.0], dtype=np.float64),
        np.asarray([0.0, 0.0, 0.19], dtype=np.float64),
    )
    predicted = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    expected = predicted.copy()
    for increment in increments:
        predicted = apply_body_right_increment_v21(predicted, increment)
        expected = hamilton_product_v21(expected, so3_exp_v21(increment))
        assert np.linalg.norm(predicted) == pytest.approx(1.0, abs=2e-15)

    reversed_order = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    for increment in reversed(increments):
        reversed_order = apply_body_right_increment_v21(reversed_order, increment)

    assert so3_geodesic_radians_v21(predicted, expected) < 1e-14
    assert so3_geodesic_radians_v21(predicted, reversed_order) > 0.05


def test_increment_target_is_10d_and_reconstructs_next_state() -> None:
    current = _state(_axis_angle((0.0, 1.0, 0.0), 0.2))
    increment = np.asarray([0.05, -0.01, 0.02, 0.03, 0.04, -0.05, 0.06, 0.01, -0.02, 0.03])
    expected_next = apply_increment_target_v21(current, increment)

    target = build_increment_target_v21(current, expected_next)
    reconstructed = apply_increment_target_v21(current, target)

    assert target.shape == (10,)
    assert np.allclose(target[:7], increment[:7], atol=1e-15)
    assert np.allclose(target[7:], increment[7:], atol=2e-15)
    assert np.allclose(reconstructed[[0, 5, 6, 7, 8, 9, 10]], expected_next[[0, 5, 6, 7, 8, 9, 10]])
    assert so3_geodesic_radians_v21(reconstructed[1:5], expected_next[1:5]) < 1e-14


@pytest.mark.parametrize(
    "bad",
    (
        np.zeros(3),
        np.asarray([float("nan"), 0.0, 0.0, 1.0]),
        np.zeros(4),
        np.asarray([2.0, 0.0, 0.0, 0.0]),
    ),
)
def test_invalid_quaternion_fails_closed(bad: np.ndarray) -> None:
    with pytest.raises(ValueError, match="^quaternion_invalid"):
        canonicalize_quaternion_v21(bad)


def test_body_right_composition_rejects_unit_norm_drift(monkeypatch) -> None:
    import koopman.so3_v21 as module

    original = module.hamilton_product_v21

    def drifted(left, right):
        return original(left, right) * (1.0 + 2.0e-10)

    monkeypatch.setattr(module, "hamilton_product_v21", drifted)

    with pytest.raises(ValueError, match="^quaternion_unit_norm_drift"):
        module.apply_body_right_increment_v21(
            np.asarray([1.0, 0.0, 0.0, 0.0]), np.asarray([0.1, 0.0, 0.0])
        )


def test_geodesic_metric_is_sign_invariant() -> None:
    quaternion = _axis_angle((1.0, 2.0, 3.0), 1.2)
    assert so3_geodesic_radians_v21(quaternion, -quaternion) == pytest.approx(0.0)

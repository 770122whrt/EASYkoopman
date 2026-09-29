"""Focused contracts for the one-shot Phase 8 OOD evaluator."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from koopman.evaluation_v2 import (
    OFFICIAL_ROLLOUT_POLICY_V2,
    BoundPlatformModelV2,
    family_repetition_v2,
)


def test_official_rollout_policy_is_fixed_before_test_access() -> None:
    assert OFFICIAL_ROLLOUT_POLICY_V2.horizons == (5, 20, 60, "full")
    assert OFFICIAL_ROLLOUT_POLICY_V2.quaternion_epsilon == pytest.approx(1.0e-10)
    assert OFFICIAL_ROLLOUT_POLICY_V2.quaternion_projection_limit == pytest.approx(0.25)
    assert OFFICIAL_ROLLOUT_POLICY_V2.depth_abs_max == pytest.approx(100.0)
    assert OFFICIAL_ROLLOUT_POLICY_V2.linear_velocity_abs_max == pytest.approx(100.0)
    assert OFFICIAL_ROLLOUT_POLICY_V2.angular_velocity_abs_max == pytest.approx(100.0)


def test_conditional_wrapper_binds_physical_descriptor_only() -> None:
    calls = []
    model = SimpleNamespace(
        predict_next=lambda state, control, **kwargs: calls.append(kwargs) or state
    )
    descriptor = object()
    wrapped = BoundPlatformModelV2(model=model, platform_descriptor=descriptor)

    assert wrapped.predict_next([0.0] * 11, [0.0] * 4) == [0.0] * 11
    assert calls == [{"platform_descriptor": descriptor}]


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("phase8-main-independent-prbs", "independent_prbs"),
        ("phase8-main-bounded-multisine", "bounded_multisine"),
        ("phase8-main-coupled-chirp", "coupled_chirp"),
    ],
)
def test_test_episode_pairing_key_is_excitation_family(
    scenario: str, expected: str
) -> None:
    assert family_repetition_v2(scenario) == expected


def test_unknown_test_family_fails_closed() -> None:
    with pytest.raises(ValueError, match="test_family_unknown"):
        family_repetition_v2("phase8-main-unknown")

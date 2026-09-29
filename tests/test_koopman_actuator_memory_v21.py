"""Contracts for the Phase 8.1 causal actuator-memory proxy."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from koopman.actuator_memory_v21 import ActuatorMemoryProxyV21


def test_reset_is_exact_binary64_zero_and_current_is_defensive() -> None:
    proxy = ActuatorMemoryProxyV21(
        tau_s=0.2,
        control_dt_s=0.02,
        control_mask_4=[1, 1, 1, 1],
    )
    current = proxy.current()

    assert current.dtype == np.float64
    assert current.tobytes() == np.zeros(4, dtype=np.float64).tobytes()
    current.setflags(write=True)
    current[0] = 9.0
    assert proxy.current().tobytes() == np.zeros(4, dtype=np.float64).tobytes()

    proxy.advance([0.5, -0.25, 0.125, -0.75])
    proxy.reset()
    assert proxy.current().tobytes() == np.zeros(4, dtype=np.float64).tobytes()


def test_advance_matches_independent_binary64_closed_form() -> None:
    tau_s = 0.2
    control_dt_s = 0.05
    control = np.array([0.8, -0.4, 0.2, -0.1], dtype=np.float64)
    proxy = ActuatorMemoryProxyV21(tau_s, control_dt_s, [1, 1, 1, 1])

    first = proxy.advance(control)
    second = proxy.advance(control)

    expected_first = (1.0 - math.exp(-control_dt_s / tau_s)) * control
    expected_second = (1.0 - math.exp(-(2.0 * control_dt_s) / tau_s)) * control
    np.testing.assert_allclose(first, expected_first, atol=1e-12, rtol=1e-12)
    np.testing.assert_allclose(second, expected_second, atol=1e-12, rtol=1e-12)


def test_disabled_channel_must_already_be_masked_and_remains_exact_zero() -> None:
    proxy = ActuatorMemoryProxyV21(0.1, 0.02, [1, 1, 0, 1])

    with pytest.raises(ValueError, match="actuator_memory_disabled_channel_nonzero"):
        proxy.advance([0.1, -0.2, 1e-15, 0.3])

    updated = proxy.advance([0.1, -0.2, 0.0, 0.3])
    assert updated[2] == 0.0
    assert proxy.current()[2] == 0.0


def test_binary64_json_roundtrip_preserves_memory_bytes() -> None:
    proxy = ActuatorMemoryProxyV21(0.07, 1.0 / 60.0, [1, 1, 1, 1])
    memory = proxy.advance([0.12345678901234566, -0.2, 0.3, -0.4])

    decoded = np.asarray(json.loads(json.dumps(memory.tolist())), dtype=np.float64)

    assert decoded.tobytes() == memory.tobytes()


def test_rollout_factory_accepts_only_a_validated_window_start_state() -> None:
    state = np.array([0.12, -0.25, 0.0, 0.5], dtype=np.float64)
    proxy = ActuatorMemoryProxyV21.from_validated_state(
        0.1, 0.02, [1, 1, 0, 1], state
    )

    assert proxy.current().tobytes() == state.tobytes()
    state[0] = 99.0
    assert proxy.current()[0] == 0.12

    with pytest.raises(ValueError, match="actuator_memory_state_invalid"):
        ActuatorMemoryProxyV21.from_validated_state(
            0.1, 0.02, [1, 1, 0, 1], [0.0, 0.0, 1e-15, 0.0]
        )


@pytest.mark.parametrize(
    ("tau_s", "control_dt_s", "control_mask_4", "reason"),
    (
        (0.0, 0.1, [1, 1, 1, 1], "actuator_memory_tau_invalid"),
        (float("nan"), 0.1, [1, 1, 1, 1], "actuator_memory_tau_invalid"),
        (0.1, 0.0, [1, 1, 1, 1], "actuator_memory_control_dt_invalid"),
        (0.1, 0.1, [1, 1, 1], "actuator_memory_control_mask_invalid"),
        (0.1, 0.1, [1, 1, 2, 1], "actuator_memory_control_mask_invalid"),
    ),
)
def test_constructor_fails_closed_on_invalid_contract(
    tau_s, control_dt_s, control_mask_4, reason: str
) -> None:
    with pytest.raises(ValueError, match=reason):
        ActuatorMemoryProxyV21(tau_s, control_dt_s, control_mask_4)


@pytest.mark.parametrize(
    "control",
    ([0.0, 0.0, 0.0], [0.0, 0.0, 0.0, float("nan")], "not-a-vector"),
)
def test_advance_fails_closed_on_invalid_control(control) -> None:
    proxy = ActuatorMemoryProxyV21(0.1, 0.02, [1, 1, 1, 1])

    with pytest.raises(ValueError, match="actuator_memory_control_invalid"):
        proxy.advance(control)

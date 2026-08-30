"""Causal actuator-memory proxy for the additive Koopman schema v2.1.

The proxy is a filtered-virtual-control state that can be maintained at
deployment time.  It is not motor thrust, PWM, applied wrench, simulator
actuator truth, or proof that the complete plant is strictly Markov.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _positive_binary64(value: Any, *, reason: str) -> np.float64:
    if isinstance(value, (bool, np.bool_)):
        _fail(reason)
    try:
        result = np.float64(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(reason) from exc
    if result.ndim != 0 or not np.isfinite(result) or result <= 0.0:
        _fail(reason)
    return result


class ActuatorMemoryProxyV21:
    """Maintain one topology-neutral, causal filtered-control state."""

    def __init__(
        self,
        tau_s: Any,
        control_dt_s: Any,
        control_mask_4: Any,
    ) -> None:
        self._tau_s = _positive_binary64(
            tau_s, reason="actuator_memory_tau_invalid"
        )
        self._control_dt_s = _positive_binary64(
            control_dt_s, reason="actuator_memory_control_dt_invalid"
        )
        try:
            raw_mask = np.asarray(control_mask_4)
        except (TypeError, ValueError) as exc:
            raise ValueError("actuator_memory_control_mask_invalid") from exc
        if raw_mask.shape != (4,) or any(
            not isinstance(item, (int, np.integer)) or isinstance(item, (bool, np.bool_))
            for item in raw_mask.tolist()
        ):
            _fail("actuator_memory_control_mask_invalid")
        if not np.isin(raw_mask, (0, 1)).all():
            _fail("actuator_memory_control_mask_invalid")
        self._control_mask_4 = raw_mask.astype(np.float64, copy=True)
        self._alpha = np.float64(
            math.exp(-float(self._control_dt_s / self._tau_s))
        )
        self._state = np.zeros(4, dtype=np.float64)

    @classmethod
    def from_validated_state(
        cls,
        tau_s: Any,
        control_dt_s: Any,
        control_mask_4: Any,
        state_4: Any,
    ) -> "ActuatorMemoryProxyV21":
        """Create a rollout chain from one already validated window start.

        This intentionally is a construction seam rather than a mutable state
        setter: collectors and episode Bridges always start through ``reset``.
        """
        proxy = cls(tau_s, control_dt_s, control_mask_4)
        try:
            state = np.asarray(state_4, dtype=np.float64)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("actuator_memory_state_invalid") from exc
        if state.shape != (4,) or not np.isfinite(state).all():
            _fail("actuator_memory_state_invalid")
        disabled = proxy._control_mask_4 == 0.0
        if np.any(state[disabled] != 0.0):
            _fail("actuator_memory_state_invalid")
        proxy._state = state.copy()
        proxy._state[disabled] = 0.0
        return proxy

    @property
    def tau_s(self) -> float:
        return float(self._tau_s)

    @property
    def control_dt_s(self) -> float:
        return float(self._control_dt_s)

    @property
    def control_mask_4(self) -> np.ndarray:
        return self._control_mask_4.copy()

    def reset(self) -> None:
        """Reset the episode-local proxy to exact binary64 zeros."""
        self._state.fill(0.0)

    def current(self) -> np.ndarray:
        """Return a defensive binary64 copy of ``m[t]``."""
        return self._state.copy()

    def advance(self, masked_virtual_control_t: Any) -> np.ndarray:
        """Advance once after validating that disabled channels are zero."""
        try:
            control = np.asarray(masked_virtual_control_t, dtype=np.float64)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("actuator_memory_control_invalid") from exc
        if control.shape != (4,) or not np.isfinite(control).all():
            _fail("actuator_memory_control_invalid")
        disabled = self._control_mask_4 == 0.0
        if np.any(control[disabled] != 0.0):
            _fail("actuator_memory_disabled_channel_nonzero")

        masked = control * self._control_mask_4
        self._state = self._alpha * self._state + (1.0 - self._alpha) * masked
        # Preserve exact-zero disabled channels instead of relying on arithmetic.
        self._state[disabled] = 0.0
        return self.current()

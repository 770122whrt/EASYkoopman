from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from koopman_data import PWM_DIM, REFERENCE_DIM, STATE_DIM

from .mpc import MPCConfig, solve_mpc


DEFAULT_KNOWN_LIMITATIONS = (
    "selected backend is direct_state, not paper_lifted_edmd",
    "Phase 2.5 is an offline model gate, not closed-loop control evidence",
    "Phase 4 must compare closed-loop performance before superiority claims",
)


@dataclass(frozen=True)
class MPCControllerOutput:
    pwm: np.ndarray
    diagnostics: dict[str, Any]
    fallback_used: bool


class KoopmanMPCController:
    def __init__(self, runtime: Any, config: MPCConfig | None = None):
        self.runtime = runtime
        self.config = config or MPCConfig()

    def command(
        self,
        state: np.ndarray,
        reference: np.ndarray,
        *,
        previous_pwm: np.ndarray,
        legacy_pwm: np.ndarray,
    ) -> MPCControllerOutput:
        fallback = np.clip(np.asarray(legacy_pwm, dtype=float).reshape(PWM_DIM), -1.0, 1.0)
        try:
            x = np.asarray(state, dtype=float).reshape(STATE_DIM)
            r = np.asarray(reference, dtype=float).reshape(REFERENCE_DIM)
            prev = np.clip(np.asarray(previous_pwm, dtype=float).reshape(PWM_DIM), -1.0, 1.0)
        except Exception as exc:
            return self._fallback(fallback, f"bad_input:{type(exc).__name__}")

        if not np.isfinite(x).all() or not np.isfinite(r).all() or not np.isfinite(prev).all():
            return self._fallback(fallback, "nonfinite_input")

        result = solve_mpc(self.runtime, x, r, previous_pwm=prev, fallback_pwm=fallback, config=self.config)
        diagnostics = result.diagnostics(backend_used=getattr(self.runtime, "backend_used", None))
        latency_ms = float(diagnostics.get("latency_ms") or 0.0)
        diagnostics.update(
            {
                "model_class": getattr(self.runtime, "model_class", None),
                "backend_is_paper_style_lifted_edmd": bool(
                    getattr(self.runtime, "backend_is_paper_style_lifted_edmd", False)
                ),
                "latency_budget_ms": float(self.config.timeout_ms),
                "latency_budget_met": latency_ms <= float(self.config.timeout_ms),
                "known_limitations": self._known_limitations(),
            }
        )
        return MPCControllerOutput(
            pwm=np.clip(np.asarray(result.pwm, dtype=float), -1.0, 1.0),
            diagnostics=diagnostics,
            fallback_used=result.fallback_used,
        )

    def _fallback(self, fallback_pwm: np.ndarray, reason: str) -> MPCControllerOutput:
        return MPCControllerOutput(
            pwm=np.clip(np.asarray(fallback_pwm, dtype=float).reshape(PWM_DIM), -1.0, 1.0),
            diagnostics={
                "backend_used": getattr(self.runtime, "backend_used", None),
                "model_class": getattr(self.runtime, "model_class", None),
                "status": "fallback",
                "fallback_used": True,
                "fallback_reason": reason,
                "latency_ms": 0.0,
                "latency_budget_ms": float(self.config.timeout_ms),
                "latency_budget_met": True,
                "cost": None,
                "baseline_cost": None,
                "candidate_count": 0,
                "known_limitations": self._known_limitations(),
            },
            fallback_used=True,
        )

    def _known_limitations(self) -> list[str]:
        limitations = [str(item) for item in getattr(self.runtime, "known_limitations", ()) if str(item).strip()]
        return limitations or list(DEFAULT_KNOWN_LIMITATIONS)

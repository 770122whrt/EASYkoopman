from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from koopman_data import PWM_DIM, REFERENCE_DIM, STATE_DIM


class PredictionRuntime(Protocol):
    def predict_next(self, state: np.ndarray, pwm: np.ndarray, reference: np.ndarray) -> np.ndarray:
        ...


@dataclass(frozen=True)
class MPCWeights:
    depth: float = 1.0
    attitude: float = 1.0
    control: float = 0.01
    smoothness: float = 0.05


@dataclass(frozen=True)
class MPCBounds:
    pwm_min: float = -1.0
    pwm_max: float = 1.0
    delta_pwm_limit: float | None = 0.35


@dataclass(frozen=True)
class MPCConfig:
    horizon: int = 5
    weights: MPCWeights = field(default_factory=MPCWeights)
    bounds: MPCBounds = field(default_factory=MPCBounds)
    timeout_ms: float = 12.0


@dataclass(frozen=True)
class MPCResult:
    pwm: np.ndarray
    status: str
    cost: float
    baseline_cost: float
    latency_ms: float
    candidate_count: int
    fallback_used: bool = False
    fallback_reason: str | None = None
    predicted_quaternion_norms: tuple[float, ...] = ()

    def diagnostics(self, *, backend_used: str | None = None) -> dict[str, Any]:
        return {
            "backend_used": backend_used,
            "status": self.status,
            "cost": float(self.cost),
            "baseline_cost": float(self.baseline_cost),
            "latency_ms": float(self.latency_ms),
            "candidate_count": int(self.candidate_count),
            "fallback_used": bool(self.fallback_used),
            "fallback_reason": self.fallback_reason,
            "predicted_quaternion_norms": list(self.predicted_quaternion_norms),
        }


def _as_vector(values: Any, dim: int, name: str) -> np.ndarray:
    vector = np.asarray(values, dtype=float).reshape(-1)
    if vector.shape != (dim,):
        raise ValueError(f"{name} must have shape ({dim},), got {vector.shape}")
    return vector


def _align_reference_quaternion(state_quat: np.ndarray, reference_quat: np.ndarray) -> np.ndarray:
    aligned = reference_quat.copy()
    if float(np.dot(state_quat, aligned)) < 0.0:
        aligned *= -1.0
    return aligned


def tracking_cost(state: np.ndarray, reference: np.ndarray, weights: MPCWeights) -> float:
    x = _as_vector(state, STATE_DIM, "state")
    r = _as_vector(reference, REFERENCE_DIM, "reference")
    depth_error = float(x[0] - r[0])
    quat = x[1:5]
    reference_quat = _align_reference_quaternion(quat, r[1:5])
    quat_error = quat - reference_quat
    return float(weights.depth * depth_error * depth_error + weights.attitude * np.dot(quat_error, quat_error))


def stage_cost(
    state: np.ndarray,
    reference: np.ndarray,
    pwm: np.ndarray,
    previous_pwm: np.ndarray,
    weights: MPCWeights,
) -> float:
    u = _as_vector(pwm, PWM_DIM, "pwm")
    u_prev = _as_vector(previous_pwm, PWM_DIM, "previous_pwm")
    return float(
        tracking_cost(state, reference, weights)
        + weights.control * np.dot(u, u)
        + weights.smoothness * np.dot(u - u_prev, u - u_prev)
    )


def project_pwm(pwm: np.ndarray, previous_pwm: np.ndarray, bounds: MPCBounds) -> np.ndarray:
    projected = np.clip(_as_vector(pwm, PWM_DIM, "pwm"), bounds.pwm_min, bounds.pwm_max)
    if bounds.delta_pwm_limit is not None:
        delta = abs(float(bounds.delta_pwm_limit))
        previous = _as_vector(previous_pwm, PWM_DIM, "previous_pwm")
        projected = np.minimum(np.maximum(projected, previous - delta), previous + delta)
    return np.clip(projected, bounds.pwm_min, bounds.pwm_max)


def rollout_cost(
    runtime: PredictionRuntime,
    state: np.ndarray,
    reference: np.ndarray,
    sequence: np.ndarray,
    previous_pwm: np.ndarray,
    weights: MPCWeights,
) -> tuple[float, tuple[float, ...]]:
    current_state = _as_vector(state, STATE_DIM, "state").copy()
    r = _as_vector(reference, REFERENCE_DIM, "reference")
    previous = _as_vector(previous_pwm, PWM_DIM, "previous_pwm")
    total = 0.0
    quat_norms: list[float] = []
    for pwm in np.asarray(sequence, dtype=float):
        u = _as_vector(pwm, PWM_DIM, "pwm")
        total += stage_cost(current_state, r, u, previous, weights)
        current_state = _as_vector(runtime.predict_next(current_state, u, r), STATE_DIM, "prediction")
        if not np.isfinite(current_state).all():
            return float("inf"), tuple(quat_norms)
        quat_norms.append(float(np.linalg.norm(current_state[1:5])))
        previous = u
    total += tracking_cost(current_state, r, weights)
    return float(total), tuple(quat_norms)


def _constant_sequence(pwm: np.ndarray, horizon: int) -> np.ndarray:
    return np.repeat(_as_vector(pwm, PWM_DIM, "pwm").reshape(1, PWM_DIM), horizon, axis=0)


def _candidate_sequences(previous_pwm: np.ndarray, fallback_pwm: np.ndarray, config: MPCConfig) -> list[np.ndarray]:
    previous = _as_vector(previous_pwm, PWM_DIM, "previous_pwm")
    fallback = _as_vector(fallback_pwm, PWM_DIM, "fallback_pwm")
    horizon = int(config.horizon)
    candidates = [
        _constant_sequence(previous, horizon),
        _constant_sequence(fallback, horizon),
        _constant_sequence(np.zeros(PWM_DIM), horizon),
    ]
    for amplitude in (-1.0, -0.5, -0.25, 0.25, 0.5, 1.0):
        candidates.append(_constant_sequence(project_pwm(np.full(PWM_DIM, amplitude), previous, config.bounds), horizon))
    for index in range(PWM_DIM):
        for amplitude in (-1.0, -0.5, 0.5, 1.0):
            command = previous.copy()
            command[index] = amplitude
            candidates.append(_constant_sequence(project_pwm(command, previous, config.bounds), horizon))
    return candidates


def _fallback_result(
    *,
    start_time: float,
    pwm: np.ndarray,
    status: str,
    reason: str,
    cost: float = float("inf"),
    baseline_cost: float = float("inf"),
    candidate_count: int = 0,
    quat_norms: tuple[float, ...] = (),
) -> MPCResult:
    return MPCResult(
        pwm=_as_vector(pwm, PWM_DIM, "fallback_pwm"),
        status=status,
        cost=float(cost),
        baseline_cost=float(baseline_cost),
        latency_ms=(time.perf_counter() - start_time) * 1000.0,
        candidate_count=candidate_count,
        fallback_used=True,
        fallback_reason=reason,
        predicted_quaternion_norms=quat_norms,
    )


def solve_mpc(
    runtime: PredictionRuntime,
    state: np.ndarray,
    reference: np.ndarray,
    *,
    previous_pwm: np.ndarray | None = None,
    fallback_pwm: np.ndarray | None = None,
    config: MPCConfig | None = None,
) -> MPCResult:
    cfg = config or MPCConfig()
    if cfg.horizon <= 0:
        raise ValueError("MPC horizon must be positive")
    start = time.perf_counter()
    previous = np.zeros(PWM_DIM) if previous_pwm is None else _as_vector(previous_pwm, PWM_DIM, "previous_pwm")
    fallback = previous if fallback_pwm is None else _as_vector(fallback_pwm, PWM_DIM, "fallback_pwm")
    fallback = project_pwm(fallback, previous, cfg.bounds)

    try:
        x = _as_vector(state, STATE_DIM, "state")
        r = _as_vector(reference, REFERENCE_DIM, "reference")
        if not np.isfinite(x).all() or not np.isfinite(r).all() or not np.isfinite(previous).all():
            return _fallback_result(start_time=start, pwm=fallback, status="fallback", reason="nonfinite_input")

        hold_sequence = _constant_sequence(project_pwm(previous, previous, cfg.bounds), cfg.horizon)
        baseline_cost, baseline_quat_norms = rollout_cost(runtime, x, r, hold_sequence, previous, cfg.weights)
        if not np.isfinite(baseline_cost):
            return _fallback_result(start_time=start, pwm=fallback, status="fallback", reason="nonfinite_baseline")

        best_cost = baseline_cost
        best_sequence = hold_sequence
        best_quat_norms = baseline_quat_norms
        candidate_count = 0
        for sequence in _candidate_sequences(previous, fallback, cfg):
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if elapsed_ms > cfg.timeout_ms:
                return _fallback_result(
                    start_time=start,
                    pwm=fallback,
                    status="fallback",
                    reason="timeout",
                    cost=best_cost,
                    baseline_cost=baseline_cost,
                    candidate_count=candidate_count,
                    quat_norms=best_quat_norms,
                )
            sequence = np.asarray([project_pwm(command, previous, cfg.bounds) for command in sequence], dtype=float)
            cost, quat_norms = rollout_cost(runtime, x, r, sequence, previous, cfg.weights)
            candidate_count += 1
            if np.isfinite(cost) and cost < best_cost:
                best_cost = cost
                best_sequence = sequence
                best_quat_norms = quat_norms

        if not best_cost < baseline_cost:
            return _fallback_result(
                start_time=start,
                pwm=fallback,
                status="fallback",
                reason="no_cost_improvement",
                cost=best_cost,
                baseline_cost=baseline_cost,
                candidate_count=candidate_count,
                quat_norms=best_quat_norms,
            )

        return MPCResult(
            pwm=project_pwm(best_sequence[0], previous, cfg.bounds),
            status="ok",
            cost=float(best_cost),
            baseline_cost=float(baseline_cost),
            latency_ms=(time.perf_counter() - start) * 1000.0,
            candidate_count=candidate_count,
            fallback_used=False,
            fallback_reason=None,
            predicted_quaternion_norms=best_quat_norms,
        )
    except Exception as exc:
        return _fallback_result(start_time=start, pwm=fallback, status="fallback", reason=f"exception:{type(exc).__name__}")

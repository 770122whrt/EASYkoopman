import numpy as np

from koopman.mpc import MPCBounds, MPCConfig, MPCWeights, solve_mpc, stage_cost, tracking_cost


class DepthControlRuntime:
    backend_used = "fixture"
    model_class = "fixture"

    def predict_next(self, state, pwm, reference):
        next_state = np.asarray(state, dtype=float).copy()
        next_state[0] = next_state[0] + 0.5 * float(np.asarray(pwm)[0])
        return next_state


class FrozenRuntime:
    backend_used = "fixture"
    model_class = "fixture"

    def predict_next(self, state, pwm, reference):
        return np.asarray(state, dtype=float).copy()


def _state(z=1.0, quat=None):
    state = np.zeros(11, dtype=float)
    state[0] = z
    state[1:5] = np.asarray(quat if quat is not None else [1.0, 0.0, 0.0, 0.0], dtype=float)
    return state


def _reference(z=0.0, quat=None):
    reference = np.zeros(5, dtype=float)
    reference[0] = z
    reference[1:5] = np.asarray(quat if quat is not None else [1.0, 0.0, 0.0, 0.0], dtype=float)
    return reference


def test_tracking_cost_handles_quaternion_sign_equivalence_without_mutating_inputs():
    state = _state(quat=[1.0, 0.0, 0.0, 0.0])
    reference = _reference(quat=[-1.0, 0.0, 0.0, 0.0])
    original_reference = reference.copy()

    cost = tracking_cost(state, reference, MPCWeights(depth=1.0, attitude=1.0))

    assert cost == 0.0
    np.testing.assert_allclose(reference, original_reference)


def test_stage_cost_penalizes_tracking_energy_and_smoothness():
    weights = MPCWeights(depth=2.0, attitude=1.0, control=0.5, smoothness=1.5)
    previous_pwm = np.zeros(8)
    reference = _reference(z=0.0)

    near = stage_cost(_state(z=0.1), reference, np.zeros(8), previous_pwm, weights)
    far = stage_cost(_state(z=2.0), reference, np.zeros(8), previous_pwm, weights)
    energetic = stage_cost(_state(z=0.1), reference, np.ones(8), previous_pwm, weights)
    abrupt = stage_cost(_state(z=0.1), reference, np.ones(8), -np.ones(8), weights)

    assert near < far
    assert near < energetic
    assert energetic < abrupt


def test_solve_mpc_returns_bounded_pwm_and_latency_metadata():
    result = solve_mpc(
        DepthControlRuntime(),
        _state(z=1.0),
        _reference(z=0.0),
        previous_pwm=np.zeros(8),
        fallback_pwm=np.full(8, 0.2),
        config=MPCConfig(horizon=3, bounds=MPCBounds(delta_pwm_limit=1.0), timeout_ms=50),
    )

    assert result.pwm.shape == (8,)
    assert np.all(result.pwm >= -1.0)
    assert np.all(result.pwm <= 1.0)
    assert result.status == "ok"
    assert result.fallback_used is False
    assert result.cost < result.baseline_cost
    assert result.latency_ms >= 0.0
    assert result.candidate_count > 0
    assert result.predicted_quaternion_norms


def test_solve_mpc_prefers_fallback_when_it_cannot_improve_hold_previous_cost():
    result = solve_mpc(
        FrozenRuntime(),
        _state(z=1.0),
        _reference(z=0.0),
        previous_pwm=np.zeros(8),
        fallback_pwm=np.full(8, 0.25),
        config=MPCConfig(horizon=2, bounds=MPCBounds(delta_pwm_limit=0.5), timeout_ms=50),
    )

    assert result.fallback_used is True
    assert result.status == "fallback"
    assert result.fallback_reason == "no_cost_improvement"
    np.testing.assert_allclose(result.pwm, np.full(8, 0.25))

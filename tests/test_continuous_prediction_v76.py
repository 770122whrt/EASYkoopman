"""Independent frozen-rollout and derivative checks for the optimizer's model."""
import numpy as np
import pytest
pytest.importorskip('casadi', reason='v76 optimizer tests run in the isolated server CasADi environment')

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from test_prepared_projected_v40 import context, model, states


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
@pytest.mark.parametrize('family', ['linear', 'nonlinear'])
def test_symbolic_step_matches_frozen_predictor(name, family):
    from koopman.prepared_projected_v40 import prepare_projected
    from koopman.continuous_prediction_v76 import SymbolicPlant
    c = context(name)
    original = prepare_projected(model(family), c)
    plant = SymbolicPlant(original, name)
    x = states(3)
    acceleration = np.random.default_rng(760).uniform(-.3, .3, (3, 6))
    for state, applied in zip(x, acceleration):
        actual = np.asarray(plant.step(state, applied)).ravel()
        np.testing.assert_allclose(actual, original(state[None], applied[None], c)[0],
                                   rtol=1e-11, atol=1e-11)


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
def test_full_rollout_preserves_causal_memory_and_four_substep_hold(name):
    from koopman.prepared_projected_v40 import prepare_projected
    from koopman.command_state_v39 import CausalCommandState
    from koopman.continuous_prediction_v76 import SymbolicPlant
    c = context(name)
    predictor = prepare_projected(model(), c)
    live = CausalCommandState(name, c, episode_id='v76', zero_rotor_reset_verified=True)
    command = np.array([.023, -.037, 0., .33], dtype=np.float32)
    for index in range(12):
        live.record_issued(command, physics_index=index, episode_id='v76')
    origin = live.snapshot(configuration=name, context=c, origin_control=6, episode_id='v76')
    x = np.array([5.5, 1., 0, 0, 0, .02, -.01, .03, .01, -.02, .01])
    controls = np.tile(command, (5, 1))
    before = origin._actuator.current().copy()
    expected = origin.forecast(x, np.repeat(controls, 2, axis=0), predictor)
    assert expected['complete']
    actual = SymbolicPlant(predictor, name).forecast(origin, x, controls)
    # The optimizer uses real-valued commands; execution quantizes PWM/commands
    # to float32. This is an explicit numerical proxy, not bitwise equivalence.
    np.testing.assert_allclose(actual['predictions'], expected['predictions'], rtol=1e-7, atol=3e-6)
    np.testing.assert_allclose(actual['rotor_speed'], expected['rotor_speed'], rtol=1e-7, atol=3e-4)
    assert actual['predictions'].shape == (20, 11)
    np.testing.assert_array_equal(origin._actuator.current(), before)
    assert live.physics_index == 12


def test_automatic_derivative_matches_independent_difference_and_is_finite_at_rest():
    import casadi as ca
    from koopman.prepared_projected_v40 import prepare_projected
    from koopman.continuous_prediction_v76 import SymbolicPlant
    plant = SymbolicPlant(prepare_projected(model(), context()), 'base')
    x = ca.SX.sym('x', 11); u = ca.SX.sym('u', 6)
    derivative = ca.Function('derivative', [x, u], [ca.jacobian(plant.step(x, u), u)])
    state = np.array([5.5, 1., 0, 0, 0, 0, 0, 0, 0, 0, 0])
    input_ = np.array([.1, -.2, .3, .04, -.05, .06])
    analytic = np.asarray(derivative(state, input_))
    eps = 1e-5
    numeric = np.column_stack([(np.asarray(plant.step(state, input_ + eps*np.eye(6)[i])) -
                                np.asarray(plant.step(state, input_ - eps*np.eye(6)[i]))).ravel()/(2*eps)
                               for i in range(6)])
    np.testing.assert_allclose(analytic, numeric, rtol=1e-6, atol=1e-9)
    assert np.isfinite(np.asarray(derivative(state, np.zeros(6)))).all()

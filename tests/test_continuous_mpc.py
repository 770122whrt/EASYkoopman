"""Consolidation equivalence, not new Isaac or closed-loop evidence."""
import importlib
import inspect

import numpy as np
import pytest

pytest.importorskip('casadi')
from control_fixtures import context, model, oracle, assert_frozen


def solver_pair(configuration='base', horizon=2):
    from koopman.prepared_physics import prepare_projected
    from koopman.command_state import CausalCommandState
    from koopman.support_domain import SupportDomain
    current = importlib.import_module('koopman.continuous_mpc').ContinuousMPC
    physical_context = context(configuration)
    predictor = prepare_projected(model(), physical_context)
    domain = SupportDomain.diagnostic(configuration, physical_context, model_id='7'*64)
    solvers = [cls(domain, predictor, horizon=horizon, allow_diagnostic=True)
               for cls in (current,)]
    live = CausalCommandState(configuration, physical_context, episode_id='current-equivalence',
                              zero_rotor_reset_verified=True)
    previous = np.array([0., 0., 0., .3])
    for i in range(16):
        live.record_issued(previous, physics_index=i, episode_id='current-equivalence')
    origin = live.snapshot(configuration=configuration, context=physical_context, origin_control=8,
                           episode_id='current-equivalence')
    state = np.array([5.5, 1., 0., 0., 0., 0., 0., 0., 0., 0., 0.])
    args = dict(origin=origin, initial_state=state, baseline=np.tile(previous, (horizon, 1)),
                previous=previous, reference=np.array([5.55, 1., 0., 0., 0.]))
    return solvers, live, args


def test_current_solver_owns_implementation_without_old_solver_inheritance():
    module = importlib.import_module('koopman.continuous_mpc')
    assert module.ContinuousMPC.__bases__ == (object,)
    source = inspect.getsource(module)
    for obsolete in ('continuous_mpc_v76', 'continuous_mpc_v80', 'preview_solver_v80'):
        assert obsolete not in source


@pytest.mark.parametrize('configuration', ['base', 'uuv4', 'uuv6'])
def test_nlp_bounds_structure_prediction_and_checker_are_unchanged(configuration):
    (current,), live, args = solver_pair(configuration)
    frozen = oracle()["mpc"][configuration]
    np.testing.assert_array_equal(np.asarray(frozen['lower'], dtype=float), current._lower_g)
    np.testing.assert_array_equal(np.asarray(frozen['upper'], dtype=float), current._upper_g)
    assert list(current._solver.size_in('x0')) == frozen['x_shape']
    assert list(current._solver.size_in('p')) == frozen['p_shape']
    baseline, x, origin = args['baseline'], args['initial_state'], args['origin']
    speed, alpha = current.plant.actuator_inputs(origin, current.horizon)
    for index, previous_offset in enumerate((0., .005)):
        commands = baseline.copy()
        commands[:, 1] += previous_offset
        params = np.r_[x, speed, alpha, args['previous'], args['reference']]
        sample = frozen['samples'][index]
        for actual, expected in zip(current._evaluate(commands[:, current.axes].T, params), sample['evaluate']):
            np.testing.assert_allclose(actual, np.asarray(expected), rtol=1e-12, atol=1e-12)
        assert_frozen(current.check(origin, x, commands, args['previous'], args['reference']), sample['check'])
    assert live.physics_index == 16


@pytest.mark.parametrize('status', ['Maximum_CpuTime_Exceeded', 'Maximum_WallTime_Exceeded'])
@pytest.mark.parametrize('candidate_kind', ['finite', 'infeasible', 'nonfinite', 'missing'])
def test_timeout_candidate_is_retained_and_independently_checked(status, candidate_kind):
    solvers, live, args = solver_pair()
    answer = args['baseline'].copy()
    if candidate_kind == 'infeasible':
        answer[0, 3] = .8
    elif candidate_kind == 'nonfinite':
        answer[0, 3] = np.nan
    results = []
    for solver in solvers:
        class TimedOut:
            def __call__(self, **kwargs):
                value = [] if candidate_kind == 'missing' else answer[:, solver.axes].T.reshape(-1, order='F')
                # Falsely reported constraint values must not replace independent evaluation.
                return {'x': value, 'g': np.zeros_like(solver._lower_g)}

            def stats(self):
                return dict(return_status=status, success=False, iter_count=4)

        solver._solver = TimedOut()
        results.append(solver.solve(**args))
    result = results[0]
    assert result['solver']['timed_out'] and not result['solver']['success']
    assert result['selected_source'] == 'baseline' and result['exact_feasible']
    if candidate_kind in ('nonfinite', 'missing'):
        assert result['candidate_commands'] is None
        assert result['candidate_failure'] == 'nonfinite_or_invalid_shape'
    else:
        np.testing.assert_array_equal(result['candidate_commands'], answer)
        assert result['solution_check']['feasible'] == (candidate_kind == 'finite')
        if candidate_kind == 'infeasible':
            assert result['constraint_violation'] > 0
    assert live.physics_index == 16


def test_actual_ipopt_timeout_preserves_finite_candidate():
    (current,), live, args = solver_pair()
    current.solve_seconds = 1e-9
    current._build()
    result = current.solve(**args)
    assert result['solver']['return_status'] == 'Maximum_CpuTime_Exceeded'
    assert not result['solver']['success']
    assert np.isfinite(result['candidate_commands']).all()
    assert 'solution_check' in result and result['exact_feasible']
    assert live.physics_index == 16


@pytest.mark.parametrize('scenario', ['optimized', 'recovered', 'committed_prefix', 'invalid_prefix'])
def test_actual_solver_improves_or_recovers_and_respects_committed_prefix(scenario):
    solvers, live, args = solver_pair(horizon=6)
    if scenario in ('recovered', 'invalid_prefix'):
        args['baseline'][:, 3] = .5
    if scenario in ('committed_prefix', 'invalid_prefix'):
        args['committed_prefix'] = 2
    results = [solver.solve(**args) for solver in solvers]
    result = results[0]
    if scenario == 'invalid_prefix':
        assert result['reason'] == 'committed_prefix_infeasible'
        assert result['commands'] is None and not result['exact_feasible']
    else:
        assert result['exact_feasible']
        if scenario == 'recovered':
            assert result['status'] == 'recovered'
            assert result['baseline_check']['reason'] == 'command_slew'
        else:
            assert result['cost'] < result['baseline_cost']
        if scenario == 'committed_prefix':
            np.testing.assert_array_equal(result['commands'][:2], args['baseline'][:2].astype(np.float32))
    assert live.physics_index == 16


@pytest.mark.parametrize('offset,feasible', [(2.5e-6, False), (3.5e-6, True)])
def test_exact_checker_keeps_stricter_planning_margin(offset, feasible):
    (current,), _, args = solver_pair()
    command = np.array([0., 0., 0., float(np.float32(.02))+offset])
    checks = [solver.check(args['origin'], args['initial_state'], np.tile(command, (2, 1)),
                           command, args['reference']) for solver in (current,)]
    assert checks[0]['feasible'] == feasible
    if not feasible:
        assert checks[0]['reason'] == 'planning_pwm_interior'


def test_margin_layout_rejects_drift_without_mutating_input():
    margin = importlib.import_module('koopman.planning_margin')
    h, n = 2, 4
    lower = np.full(60*h+h*(4+2*n), -1.)
    for k in range(h):
        lower[60*h+k*(4+2*n)+4+n:60*h+(k+1)*(4+2*n)] = 2e-6
    before = lower.copy()
    expected = lower.copy()
    expected[expected == 2e-6] = 4e-6
    np.testing.assert_array_equal(margin.tighten_deadzone_bounds(lower, h, n), expected)
    np.testing.assert_array_equal(lower, before)
    with pytest.raises(ValueError, match='constraint_layout'):
        margin.tighten_deadzone_bounds(lower[:-1], h, n)
    lower[-1] = 0.
    with pytest.raises(ValueError, match='constraint_layout'):
        margin.tighten_deadzone_bounds(lower, h, n)

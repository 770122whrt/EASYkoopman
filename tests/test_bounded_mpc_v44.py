"""Control contracts, including counterexamples that can reject an optimizer."""
from dataclasses import replace
import time

import numpy as np
import pytest

from test_prepared_projected_v40 import context
from test_command_batch_v41 import setup


def world_yaw(q, angle):
    a, z = np.cos(angle/2), np.sin(angle/2)
    w, x, y, v = q
    return np.array([a*w-z*v, a*x-z*y, a*y+z*x, a*v+z*w])


@pytest.mark.parametrize('name', ['uuv4', 'uuv4_angled'])
@pytest.mark.parametrize('yaw', [-2.8, -.4, .7, 2.9])
def test_uncontrollable_world_yaw_is_absent_from_objective_and_domain_features(name, yaw):
    from koopman.control_objective_v44 import tracking_terms, state_features, control_mask, trajectory_cost, ObjectiveWeights
    x = np.array([5.4, .97, .12, -.09, .05, .01, .02, .03, .04, .05, .7])
    x[1:5] /= np.linalg.norm(x[1:5]); changed = x.copy()
    changed[1:5] = world_yaw(x[1:5], yaw)
    ref = np.array([5.5, 1., 0, 0, 0]); mask = control_mask(name)
    for key, value in tracking_terms(x[None], ref, mask).items():
        np.testing.assert_allclose(value, tracking_terms(changed[None], ref, mask)[key], rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(state_features(x[None], mask), state_features(changed[None], mask), rtol=1e-12, atol=1e-12)
    commands = np.array([[.01, -.02, .4, .12]])
    altered = commands.copy(); altered[:, 2] = -.8
    a = trajectory_cost(np.repeat(x[None], 2, axis=0), commands, np.zeros(4), ref, mask, ObjectiveWeights())
    b = trajectory_cost(np.repeat(changed[None], 2, axis=0), altered, np.zeros(4), ref, mask, ObjectiveWeights())
    assert a == pytest.approx(b, rel=1e-12, abs=1e-12)


def test_controllable_yaw_remains_a_target_and_quaternion_sign_is_irrelevant():
    from koopman.control_objective_v44 import tracking_terms, control_mask
    x = np.array([[5.5, 1., 0, 0, 0, 0, 0, 0, 0, 0, 0]])
    ref = x[0, :5].copy(); changed = x.copy(); changed[0, 1:5] = world_yaw(x[0, 1:5], .7)
    terms = tracking_terms(changed, ref, control_mask('base'))
    assert terms['attitude'][0] == pytest.approx(.7**2)
    changed[:, 1:5] *= -1
    np.testing.assert_allclose(terms['attitude'], tracking_terms(changed, ref, control_mask('base'))['attitude'])


@pytest.mark.parametrize('bad', ['zero_quaternion', 'nan', 'reference', 'mask'])
def test_objective_rejects_malformed_state_reference_or_mask(bad):
    from koopman.control_objective_v44 import tracking_terms
    x = np.array([[5.5, 1., 0, 0, 0, 0, 0, 0, 0, 0, 0]])
    ref, mask = x[0, :5].copy(), np.ones(4)
    if bad == 'zero_quaternion': x[0, 1:5] = 0
    if bad == 'nan': x[0, 0] = np.nan
    if bad == 'reference': ref[1:5] = 0
    if bad == 'mask': mask = [1, 0, 1, 1]
    with pytest.raises(ValueError): tracking_terms(x, ref, mask)


def fixtures(name='base', **config):
    from koopman.bounded_mpc_v44 import SupportDomain, BoundedMPC, SearchConfig
    from koopman.control_objective_v44 import ObjectiveWeights
    live, origin, x, _ = setup(name, 0)
    x[5:] = 0
    domain = SupportDomain.diagnostic(name, context(name), 'a'*64)
    def predict(states, acceleration, c):
        # Small monotonic test response: avoid making the heave candidates hit
        # the physical height limit before their direction can be compared.
        y = states.copy(); y[:, 0] += .01*acceleration[:, 2]
        return y
    cfg = SearchConfig(horizon=8, perturbation=(.04, .04, .04, .04), slew=(.1,)*4, timeout_ms=2000., **config)
    weights = ObjectiveWeights(effort=0., slew=0.)
    solver = BoundedMPC(domain, predict, model_id='a'*64, config=cfg, weights=weights, allow_diagnostic=True)
    args = dict(origin=origin, initial_state=x, baseline=np.zeros((8, 4)), previous=np.zeros(4),
                reference=np.array([6., 1., 0, 0, 0]), episode_id='batch-test', reference_id='ref', request_id='request')
    return live, domain, solver, args


def test_known_vertical_response_selects_improving_depth_without_committing():
    live, domain, solver, args = fixtures()
    result = solver.solve(**args)
    assert result['status'] == 'selected' and result['cost'] < result['baseline_cost']
    assert np.all(result['commands'][:, 3] > 0)
    assert result['candidate_count'] == 9 and live.physics_index == 0
    assert result['runtime_eligible'] is False and result['data_source_verified'] is False
    with pytest.raises(ValueError): result['commands'][:] = 99


def test_baseline_wins_when_already_at_target():
    _, _, solver, args = fixtures()
    args['reference'][0] = args['initial_state'][0]
    result = solver.solve(**args)
    assert result['status'] == 'baseline' and result['selected_index'] == 0
    assert result['cost'] == 0


@pytest.mark.parametrize('name', ['uuv4', 'uuv4_angled'])
def test_yaw_only_reference_change_does_not_change_candidates_or_selection(name):
    _, _, solver, args = fixtures(name)
    first = solver.solve(**args)
    args['reference'][1:5] = world_yaw(args['reference'][1:5], 1.2)
    second = solver.solve(**args)
    assert first['candidate_count'] == second['candidate_count'] == 7
    np.testing.assert_array_equal(first['commands'], second['commands'])
    assert np.all(first['commands'][:, 2] == 0)
    assert first['cost'] == pytest.approx(second['cost'], abs=1e-12)


def test_committed_prefix_is_unchanged_and_future_slew_is_bounded():
    _, _, solver, args = fixtures()
    args['committed_prefix'] = 3
    result = solver.solve(**args)
    np.testing.assert_array_equal(result['commands'][:3], args['baseline'][:3])
    assert np.all(np.abs(np.diff(np.vstack([args['previous'], result['commands']]), axis=0)) <= .1+1e-7)


@pytest.mark.parametrize('kind', ['state', 'command', 'slew', 'saturation', 'prediction'])
def test_inadmissible_baseline_and_predictions_never_return_usable_plan(kind):
    _, domain, solver, args = fixtures()
    if kind == 'state': args['initial_state'][0] = 1.5
    if kind == 'command': args['baseline'][:, 3] = .96
    if kind == 'slew': args['baseline'][:, 3] = .2
    if kind == 'saturation':
        args['baseline'][:] = [.4, .4, 0, .4]; args['previous'][:] = [.4, .4, 0, .4]
    if kind == 'prediction': solver.predictor = lambda x,u,c: np.full_like(x, np.nan)
    result = solver.solve(**args)
    assert result['status'] == 'no_plan' and result['reason']
    assert result['commands'] is None and result['selected_index'] is None


def test_expired_or_blocking_computation_returns_timeout_never_issued_history():
    live, _, solver, args = fixtures()
    solver.config = replace(solver.config, timeout_ms=.1)
    result = solver.solve(**args)
    assert result['status'] == 'no_plan' and result['reason'] == 'timeout'
    solver.config = replace(solver.config, timeout_ms=20.)
    def slow(x,u,c): time.sleep(.03); return x.copy()
    solver.predictor = slow
    result = solver.solve(**args)
    assert result['reason'] == 'timeout' and live.physics_index == 0


def test_context_model_and_missing_fit_provenance_fail_closed():
    from koopman.bounded_mpc_v44 import BoundedMPC
    _, domain, solver, args = fixtures()
    with pytest.raises(ValueError, match='provenance'):
        BoundedMPC(domain, solver.predictor, model_id='a'*64)
    with pytest.raises(ValueError, match='model'):
        BoundedMPC(domain, solver.predictor, model_id='b'*64, allow_diagnostic=True)
    _, other, _, _ = setup('uuv6', 0)
    args['origin'] = other
    assert solver.solve(**args)['reason'] == 'origin_context_mismatch'


def test_diagnostic_domain_is_owned_and_yaw_rate_remains_a_physical_bound():
    from koopman.bounded_mpc_v44 import SupportDomain
    d = SupportDomain.diagnostic('uuv4', context('uuv4'), 'a'*64)
    x = np.array([[5.5, 1., 0, 0, 0, 0, 0, 0, 0, 0, 0]])
    assert d.check_states(x) is None
    x[:, 10] = 3.1
    assert d.check_states(x)['reason'] == 'angular_speed_limit'
    with pytest.raises(ValueError): d.state_lower[:] = -1


@pytest.mark.parametrize('field,value', [('horizon', 0), ('timeout_ms', np.nan),
    ('perturbation', (0, 0, 0, 0)), ('slew', (-1,)*4), ('raw_pwm_limit', 1.01)])
def test_invalid_search_configuration_is_rejected(field, value):
    from koopman.bounded_mpc_v44 import SearchConfig
    with pytest.raises(ValueError): SearchConfig(**{field:value})


def test_coarse_monotonic_clock_cannot_hide_a_real_solver_timeout(monkeypatch):
    """Windows GetTickCount64 may stay unchanged throughout a short deadline."""
    import koopman.bounded_mpc_v44 as core
    live, _, solver, args = fixtures()
    solver.config = replace(solver.config, timeout_ms=20.)
    def slow(x, u, c): time.sleep(.03); return x.copy()
    solver.predictor = slow
    monkeypatch.setattr(core.time, 'monotonic', lambda: 12345.)
    before = time.perf_counter()
    result = solver.solve(**args)
    assert result['status'] == 'no_plan' and result['reason'] == 'timeout'
    assert result['elapsed_ms'] > 0 and time.perf_counter()-before < .25
    assert live.physics_index == 0

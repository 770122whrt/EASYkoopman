"""Behavioral tests of continuous sequence optimization and exact admission."""
import numpy as np
import pytest
pytest.importorskip('casadi', reason='v76 optimizer tests run in the isolated server CasADi environment')

from test_prepared_projected_v40 import context, model


def setup():
    from koopman.prepared_projected_v40 import prepare_projected
    from koopman.command_state_v39 import CausalCommandState
    from koopman.bounded_mpc_v44 import SupportDomain
    from koopman.control_objective_v44 import ObjectiveWeights
    from koopman.continuous_mpc_v76 import ContinuousMPC
    c = context('base')
    predictor = prepare_projected(model(), c)
    domain = SupportDomain.diagnostic('base', c, model_id='7'*64)
    solver = ContinuousMPC(domain, predictor, horizon=6, allow_diagnostic=True,
                           weights=ObjectiveWeights(effort=0., slew=0.), max_iterations=120)
    live = CausalCommandState('base', c, episode_id='v76-solve', zero_rotor_reset_verified=True)
    for i in range(16):
        live.record_issued([0, 0, 0, .3], physics_index=i, episode_id='v76-solve')
    origin = live.snapshot(configuration='base', context=c, origin_control=8, episode_id='v76-solve')
    x = np.array([5.5, 1., 0, 0, 0, 0, 0, 0, 0, 0, 0])
    return solver, live, dict(origin=origin, initial_state=x,
        baseline=np.tile([0., 0, 0, .3], (6, 1)), previous=np.array([0., 0, 0, .3]),
        reference=np.array([5.55, 1., 0, 0, 0]))


def test_continuous_solution_improves_exact_cost_without_trial_history_writes():
    solver, live, args = setup()
    result = solver.solve(**args)
    assert result['status'] == 'optimized', result
    assert result['exact_feasible']
    assert result['cost'] < result['baseline_cost'] - 1e-8
    assert result['solver']['iterations'] > 0
    assert result['search_kind'] == 'continuous_nonlinear_program'
    assert result['commands'].shape == (6, 4)
    assert live.physics_index == 16
    assert np.max(np.abs(result['commands'][:, 3] - .3)) > .0021


def test_committed_prefix_is_fixed_and_all_axes_are_joint_variables():
    solver, live, args = setup()
    args['reference'] = np.array([5.55, np.cos(.02), 0., np.sin(.02), 0.])
    result = solver.solve(**args, committed_prefix=2)
    assert result['exact_feasible'], result
    np.testing.assert_array_equal(result['commands'][:2], args['baseline'][:2].astype(np.float32))
    assert result['decision_variables'] == 4*6
    assert np.max(np.abs(result['commands'][2:, 1])) > 1e-5
    assert live.physics_index == 16


def test_feasible_restoration_is_not_rejected_by_an_infeasible_baseline():
    solver, _, args = setup()
    # Baseline violates the first command slew; a nearby lawful sequence exists.
    args['baseline'] = np.tile([0., 0, 0, .5], (6, 1))
    result = solver.solve(**args)
    assert result['status'] == 'recovered', result
    assert result['baseline_cost'] is None and result['exact_feasible']
    assert result['baseline_check']['reason'] == 'command_slew'
    assert abs(float(result['commands'][0, 3])-.3) <= .0200001


def test_invalid_fixed_prefix_cannot_be_rewritten_to_make_a_solution():
    solver, _, args = setup()
    args['baseline'][0, 3] = .5
    result = solver.solve(**args, committed_prefix=1)
    assert result['status'] == 'no_plan'
    assert result['reason'] == 'committed_prefix_infeasible'
    assert result['commands'] is None


@pytest.mark.parametrize('name', ['base', 'uuv4'])
def test_symbolic_objective_preserves_original_tracking_and_cost_weights(name):
    from koopman.prepared_projected_v40 import prepare_projected
    from koopman.command_state_v39 import CausalCommandState
    from koopman.bounded_mpc_v44 import SupportDomain
    from koopman.control_objective_v44 import trajectory_cost
    from koopman.continuous_mpc_v76 import ContinuousMPC
    c=context(name);predictor=prepare_projected(model(),c)
    solver=ContinuousMPC(SupportDomain.diagnostic(name,c,'8'*64),predictor,horizon=3,allow_diagnostic=True)
    live=CausalCommandState(name,c,episode_id='objective',zero_rotor_reset_verified=True)
    previous=np.array([.01,.037,0.,.3])
    for i in range(8):live.record_issued(previous,physics_index=i,episode_id='objective')
    origin=live.snapshot(configuration=name,context=c,origin_control=4,episode_id='objective')
    x=np.array([5.5,np.cos(.01),np.sin(.01),0.,0.,.02,-.01,.03,.01,-.02,.01])
    ref=np.array([5.55,np.cos(.02),0.,np.sin(.02),0.])
    commands=np.tile(previous,(3,1));commands[:,1]+=[.001,.002,.003]
    speed,alphas=solver.plant.actuator_inputs(origin,3)
    symbolic=float(solver._evaluate(commands[:,solver.axes].T,np.r_[x,speed,alphas,previous,ref])[0])
    exact=origin.forecast(x,np.repeat(commands.astype(np.float32),2,axis=0),predictor)
    cost=trajectory_cost(exact['predictions'],np.repeat(commands.astype(np.float32),2,axis=0),previous,ref,solver.mask,solver.weights)
    assert symbolic==pytest.approx(cost,rel=1e-6,abs=1e-9)

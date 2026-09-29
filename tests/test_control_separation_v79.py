"""Causal preview and model identity regressions; not closed-loop benefit tests."""
import importlib
from dataclasses import replace
import numpy as np
import pytest
from test_prepared_projected_v40 import context, model, states
from koopman.command_state_v39 import CausalCommandState
from koopman.bounded_mpc_v44 import SupportDomain
from test_isaac_execution_v67 import routed_control, bridge30


def api(name):
    assert importlib.util.find_spec(name), 'v79 separation implementation missing'
    return importlib.import_module(name)


def setup():
    c = context('base'); m = model()
    domain = SupportDomain.diagnostic('base', c, '0'*64)
    live = CausalCommandState('base', c, episode_id='test', zero_rotor_reset_verified=True)
    for i in range(4): live.record_issued(np.zeros(4), physics_index=i, episode_id='test')
    origin = live.snapshot(configuration='base', context=c, origin_control=2, episode_id='test')
    x = np.array([5.5, 1., 0, 0, 0, 0, 0, 0, 0, 0, 0])
    return c, m, domain, live, origin, x


def test_model_names_do_not_silently_alias_koopman_to_identified_physics():
    mod = api('koopman.model_separation_v79'); c, m = context(), model()
    with pytest.raises(ValueError, match='ambiguous'):
        mod.make_predictor('koopman', m, c)
    identified = mod.make_predictor('identified_physics', m, c)
    projected = mod.make_predictor('structured_projected', m, c)
    x = states(8); u = np.zeros((8, 6))
    np.testing.assert_allclose(identified(x,u,c), projected(x,u,c), atol=1e-11,rtol=1e-11)
    with pytest.raises(ValueError, match='not_admitted'):
        mod.make_predictor('frozen_full_lift_probe', m, c)


def test_full_lift_probe_reads_learned_columns_and_never_claims_control_admission():
    mod = api('koopman.model_separation_v79'); c, m = context(), model()
    x=np.array([5.5,1.,0,0,0,0,0,0,0,0,0]); u=np.zeros((3,6))
    changed=m.matrix.copy();changed[-1,0]+=.01
    alternative=replace(m,matrix=changed)
    first=mod.full_lift_probe(m,c,x,u); second=mod.full_lift_probe(alternative,c,x,u)
    assert first['runtime_eligible'] is False and second['runtime_eligible'] is False
    assert second['complete']
    np.testing.assert_allclose(second['predictions'][:,0]-first['predictions'][:,0],[.01,.02,.03],atol=1e-10)
    projected=mod.make_predictor('structured_projected',m,c)
    same=mod.make_predictor('structured_projected',alternative,c)
    np.testing.assert_allclose(projected(x[None],u[:1],c),same(x[None],u[:1],c),atol=1e-12)


def test_full_lift_rejects_nonrotation_instead_of_replacing_with_physics():
    mod=api('koopman.model_separation_v79'); c,m=context(),model()
    bad=m.matrix.copy();bad[:,1:10]=0
    x=np.array([5.5,1.,0,0,0,0,0,0,0,0,0])
    result=mod.full_lift_probe(replace(m,matrix=bad),c,x,np.zeros((2,6)))
    assert not result['complete'] and result['reason']=='rotation_rank_deficient'
    assert len(result['predictions'])==0


def test_feedback_preview_uses_predicted_state_and_preserves_origin():
    mod=api('koopman.feedback_preview_v79'); models=api('koopman.model_separation_v79')
    c,m,d,live,origin,x=setup(); speed=origin._actuator.current().copy(); clock=origin._actuator.elapsed_time
    predictor=models.make_predictor('structured_projected',m,c)
    checker=mod.ExactChecker(d,predictor,horizon=3)
    seen=[]
    class Feedback:
        def decide(self,state,reference,*,previous):
            seen.append(np.array(state));return dict(status='ready',command=np.zeros(4),reason=None)
    r=mod.feedback_preview(origin,x,np.zeros(4),x[:5],Feedback(),checker,timeout_s=10)
    assert r['status']=='ready' and r['commands'].shape==(3,4)
    np.testing.assert_allclose(seen[1],r['predictions'][3])
    np.testing.assert_allclose(seen[2],r['predictions'][7])
    assert not np.array_equal(seen[1],x)
    assert live.physics_index==4 and origin._actuator.elapsed_time==clock
    np.testing.assert_array_equal(origin._actuator.current(),speed)


def test_preview_failure_never_returns_a_partial_plan_as_ready():
    mod=api('koopman.feedback_preview_v79'); models=api('koopman.model_separation_v79')
    c,m,d,_,origin,x=setup(); checker=mod.ExactChecker(d,models.make_predictor('nominal_physics',m,c),horizon=3)
    class Feedback:
        def decide(self,*args,**kwargs):return dict(status='no_command',reason='timeout',command=None)
    r=mod.feedback_preview(origin,x,np.zeros(4),x[:5],Feedback(),checker)
    assert r['status']=='no_preview' and r['commands'] is None and r['reason']=='feedback_timeout'


def test_independent_selection_rejects_a_feasible_but_worse_winner_and_missing_reference():
    mod=api('koopman.feedback_preview_v79'); models=api('koopman.model_separation_v79')
    c,m,d,_,origin,x=setup(); checker=mod.ExactChecker(d,models.make_predictor('nominal_physics',m,c),horizon=2)
    plans={'held':np.zeros((2,4)),'preview':np.tile([0,0,0,.01],(2,1))}
    checks={k:checker.check(origin,x,p,np.zeros(4),x[:5]) for k,p in plans.items()}
    assert all(v['feasible'] for v in checks.values())
    ordered=sorted(checks,key=lambda k:checks[k]['cost']);assert checks[ordered[0]]['cost']<checks[ordered[1]]['cost']
    ok=mod.audit_selection(checker,origin,x,np.zeros(4),x[:5],plans,plans[ordered[0]],required=('held','preview'))
    assert ok['accepted']
    bad=mod.audit_selection(checker,origin,x,np.zeros(4),x[:5],plans,plans[ordered[1]],required=('held','preview'))
    assert not bad['accepted'] and bad['reason']=='dominated_selection'
    with pytest.raises(ValueError,match='missing_reference'):
        mod.audit_selection(checker,origin,x,np.zeros(4),x[:5],{'held':plans['held']},plans['held'],required=('held','preview'))


def test_preview_mpc_keeps_original_hold_and_audits_all_references():
    mod=api('koopman.preview_mpc_v79'); helpers=api('koopman.feedback_preview_v79')
    models=api('koopman.model_separation_v79'); c,m,d,_,origin,x=setup()
    checker=helpers.ExactChecker(d,models.make_predictor('nominal_physics',m,c),horizon=2)
    class Feedback:
        def decide(self,*args,**kwargs):return dict(status='ready',command=np.zeros(4))
    class Worker:
        def call(self,request):
            return dict(status='baseline_retained',commands=request['initial_guess'],reason=None)
        def close(self):return {}
    solver=mod.PreviewMPC(checker,Worker(),Feedback)
    held=np.tile([0,0,0,.01],(2,1))
    r=solver.solve(origin=origin,initial_state=x,baseline=held,previous=np.zeros(4),reference=x[:5])
    assert r['exact_feasible'] and r['selection_audit']['accepted']
    assert set(r['selection_plans'])=={'held','preview','worker'}
    np.testing.assert_array_equal(r['selection_plans']['held'],held)
    assert r['preview']['actual_history_advanced'] is False


def test_full_lift_pose_decoder_matches_known_quaternions():
    mod=api('koopman.model_separation_v79');c,m=context(),model()
    for q in ([1,0,0,0],[0,1,0,0],[.5,.5,.5,.5]):
        x=np.r_[5.5,q,np.zeros(6)]
        r=mod.full_lift_probe(m,c,x,np.zeros((1,6)))
        assert r['complete']
        assert abs(abs(np.dot(r['predictions'][0,1:5],q))-1)<1e-12


def test_preview_timeout_does_not_discard_safe_hold_but_worker_failures_are_bounded():
    mod=api('koopman.preview_mpc_v79'); helpers=api('koopman.feedback_preview_v79')
    models=api('koopman.model_separation_v79'); c,m,d,_,origin,x=setup()
    checker=helpers.ExactChecker(d,models.make_predictor('nominal_physics',m,c),horizon=2)
    class Feedback:
        def decide(self,*args,**kwargs):return dict(status='no_command',reason='timeout')
    class Worker:
        def call(self,request):return dict(status='no_plan',commands=None,reason='solver_timeout')
        def close(self):return {}
    solver=mod.PreviewMPC(checker,Worker(),Feedback)
    for _ in range(3):
        r=solver.solve(origin=origin,initial_state=x,baseline=np.zeros((2,4)),previous=np.zeros(4),reference=x[:5])
        assert r['status']=='timeout_retained' and r['selection_audit']['accepted']
        assert r['preview']['reason']=='feedback_timeout'
    r=solver.solve(origin=origin,initial_state=x,baseline=np.zeros((2,4)),previous=np.zeros(4),reference=x[:5])
    assert r['reason']=='consecutive_solver_failures' and not r['exact_feasible']


def test_invalid_worker_output_still_fails_closed():
    mod=api('koopman.preview_mpc_v79'); helpers=api('koopman.feedback_preview_v79')
    models=api('koopman.model_separation_v79'); c,m,d,_,origin,x=setup()
    checker=helpers.ExactChecker(d,models.make_predictor('nominal_physics',m,c),horizon=2)
    class Feedback:
        def decide(self,*args,**kwargs):return dict(status='ready',command=np.zeros(4))
    class Worker:
        def call(self,request):return dict(status='optimized',commands=np.full((2,4),.8),reason=None)
        def close(self):return {}
    solver=mod.PreviewMPC(checker,Worker(),Feedback)
    r=solver.solve(origin=origin,initial_state=x,baseline=np.zeros((2,4)),previous=np.zeros(4),reference=x[:5])
    assert not r['exact_feasible'] and r['reason']=='worker_plan_failed_exact_check'
    assert solver._last is None


def test_new_solver_runs_through_existing_execution_ledger_fixture(bridge30):
    from koopman.reliable_runtime_v77 import ReliableCoordinator
    mod=api('koopman.preview_mpc_v79'); helpers=api('koopman.feedback_preview_v79')
    models=api('koopman.model_separation_v79')
    env,session,old=bridge30();domain=old.ledger._domain;c=old.ledger._context
    checker=helpers.ExactChecker(domain,models.make_predictor('nominal_physics',model(),c),horizon=2)
    class Feedback:
        def decide(self,*args,**kwargs):return dict(status='no_command',reason='timeout')
    class Worker:
        def call(self,r):return dict(status='baseline_retained',commands=r['initial_guess'],reason=None)
        def close(self):return {}
    solver=mod.PreviewMPC(checker,Worker(),Feedback)
    runtime=ReliableCoordinator(old.ledger,old.feedback,solver);session.runtime=runtime
    ref=env.x[0,:5]
    session.run_interval(env.step,ref,reference_id='ref')
    session.run_interval(env.step,ref,reference_id='ref')
    assert env.physics_steps==8 and runtime.ledger.physics_index==8
    assert runtime.solve_audit[-1]['selection_audit']['accepted']
    assert runtime.stats['mpc_activations']==0


def test_unavailable_preview_preserves_legacy_warm_initialization():
    from test_reliable_mpc_v77 import Checker,Worker
    from types import SimpleNamespace
    mod=api('koopman.preview_mpc_v79')
    class Feedback:
        def decide(self,*a,**kw):return dict(status='no_command',reason='timeout')
    class QuantizedChecker(Checker):
        def check(self,origin,state,commands,previous,reference):
            return super().check(origin,state,np.asarray(commands,dtype=np.float32).astype(float),previous,reference)
    worker=Worker();solver=mod.PreviewMPC(QuantizedChecker(),worker,Feedback)
    ref=np.array([5.5,1,0,0,0]);state=np.zeros(11)
    first=solver.solve(origin=SimpleNamespace(origin_control=2),initial_state=state,
        baseline=np.full((3,4),.1),previous=np.full(4,.1),reference=ref)
    second=solver.solve(origin=SimpleNamespace(origin_control=4),initial_state=state,
        baseline=np.full((3,4),.01),previous=first['commands'][0],reference=ref)
    assert second['exact_feasible']
    np.testing.assert_allclose(worker.requests[-1]['initial_guess'],first['commands'])


def test_actual_pwm_margin_is_checked_even_when_cpu_replay_is_close():
    mod=api('koopman.feedback_preview_v79')
    assert hasattr(mod,'audit_observed_pwm'), 'actual PWM margin check missing'
    threshold=float(np.float32(.02))
    # A 1e-8 backend difference passes the old 1e-6 replay comparison, but
    # the observed signal itself must satisfy the original 2e-6 margin.
    observed=np.array([threshold-1.99e-6,-.04,.04,0.])
    assert np.max(abs(observed-(observed-1e-8)))<1e-6
    bad=mod.audit_observed_pwm(observed,observed)
    assert not bad['accepted'] and bad['reason']=='observed_pwm_deadzone_margin'
    good=np.array([threshold-2.01e-6,-.04,.04,0.])
    assert mod.audit_observed_pwm(good,good)['accepted']


@pytest.mark.parametrize('selected', [np.zeros((1,4)), np.zeros(4), np.full((2,4),np.nan)])
def test_selection_audit_rejects_short_broadcast_or_nonfinite_plan(selected):
    mod=api('koopman.feedback_preview_v79');models=api('koopman.model_separation_v79')
    c,m,d,_,origin,x=setup()
    checker=mod.ExactChecker(d,models.make_predictor('nominal_physics',m,c),horizon=2)
    with pytest.raises(ValueError,match='selected_plan'):
        mod.audit_selection(checker,origin,x,np.zeros(4),x[:5],
            {'held':np.zeros((2,4))},selected,required=('held',))


def test_preview_off_is_an_explicit_paired_experiment_switch():
    mod=api('koopman.preview_mpc_v79');helpers=api('koopman.feedback_preview_v79')
    models=api('koopman.model_separation_v79');c,m,d,_,origin,x=setup()
    checker=helpers.ExactChecker(d,models.make_predictor('nominal_physics',m,c),horizon=2)
    def forbidden():raise AssertionError('disabled preview was called')
    class Worker:
        def call(self,r):return dict(status='baseline_retained',commands=r['initial_guess'],reason=None)
        def close(self):return {}
    solver=mod.PreviewMPC(checker,Worker(),forbidden,preview_enabled=False)
    r=solver.solve(origin=origin,initial_state=x,baseline=np.zeros((2,4)),previous=np.zeros(4),reference=x[:5])
    assert r['exact_feasible'] and r['preview']['reason']=='disabled_by_protocol'
    assert r['required_references']==['held','worker']
    assert r['preview_enabled'] is False

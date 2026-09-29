import importlib
from test_isaac_execution_v67 import routed_control,bridge30
from test_continuous_runtime_v76 import Solver


def test_retained_plan_is_dispatched_but_not_counted_as_new_optimization(bridge30):
    assert importlib.util.find_spec('koopman.reliable_runtime_v77'), 'v77 runtime missing'
    from koopman.reliable_runtime_v77 import ReliableCoordinator
    env,s,old=bridge30()
    class Retained(Solver):
        def solve(self,**request):
            r=super().solve(**request);r['status']='warm_retained';return r
    r=ReliableCoordinator(old.ledger,old.feedback,Retained());s.runtime=r;ref=env.x[0,:5]
    s.run_interval(env.step,ref,reference_id='ref');s.run_interval(env.step,ref,reference_id='ref')
    assert env.physics_steps==8 and r.stats['mpc_activations']==0
    assert s.interval_records[-1]['decision']['solver_status']=='warm_retained'


def test_feedback_search_failure_does_not_veto_continuous_optimizer(bridge30):
    from koopman.reliable_runtime_v77 import ReliableCoordinator
    env,s,old=bridge30();solver=Solver()
    r=ReliableCoordinator(old.ledger,old.feedback,solver);s.runtime=r;ref=env.x[0,:5]
    s.run_interval(env.step,ref,reference_id='ref')
    r.feedback.decide=lambda *a,**kw:dict(status='no_command',reason='no_admissible_limited_command')
    s.run_interval(env.step,ref,reference_id='ref')
    assert env.physics_steps==8 and len(solver.calls)==1
    assert r.solve_audit[-1]['baseline_reference']=='previous_hold_feedback_unavailable'


def test_feedback_integrity_failure_still_stops(bridge30):
    import pytest
    from koopman.reliable_runtime_v77 import ReliableCoordinator
    env,s,old=bridge30();solver=Solver()
    r=ReliableCoordinator(old.ledger,old.feedback,solver);s.runtime=r;ref=env.x[0,:5]
    s.run_interval(env.step,ref,reference_id='ref')
    r.feedback.decide=lambda *a,**kw:dict(status='no_command',reason='policy_binding_changed')
    with pytest.raises(ValueError,match='policy_binding_changed'):
        s.run_interval(env.step,ref,reference_id='ref')
    assert env.physics_steps==4 and not solver.calls

"""Receipt/safety fixtures, explicitly not Isaac closed-loop evidence."""
import numpy as np
from test_isaac_execution_v67 import routed_control, bridge30


class Solver:
    horizon = 10
    def __init__(self, failure=False): self.calls=[]; self.failure=failure
    def solve(self, **request):
        self.calls.append(request)
        return dict(status='no_plan' if self.failure else 'recovered', reason='test_failure' if self.failure else None,
                    exact_feasible=not self.failure, commands=None if self.failure else request['baseline'],
                    predictions=None, cost=0., elapsed_seconds=.01)


def wire(bridge30, failure=False):
    from koopman.continuous_runtime_v76 import ContinuousCoordinator
    env, session, old = bridge30()
    solver=Solver(failure)
    runtime=ContinuousCoordinator(old.ledger,old.feedback,solver)
    session.runtime=runtime
    return env,session,runtime,solver


def test_synchronous_recovery_dispatches_only_after_solve_and_receipts(bridge30):
    env,s,r,solver=wire(bridge30)
    ref=env.x[0,:5]
    s.run_interval(env.step,ref,reference_id='ref')
    assert not solver.calls and r.ledger.physics_index==4
    s.run_interval(env.step,ref,reference_id='ref')
    assert len(solver.calls)==1 and r.ledger.physics_index==8
    assert solver.calls[0]['origin'].origin_control==2
    assert r.stats['mpc_activations']==1
    assert s.interval_records[-1]['decision']['solver_status']=='recovered'


def test_no_exact_sequence_stops_before_another_physics_step(bridge30):
    import pytest
    env,s,r,_=wire(bridge30,True);ref=env.x[0,:5]
    s.run_interval(env.step,ref,reference_id='ref')
    with pytest.raises(ValueError,match='continuous_no_exact_plan'):
        s.run_interval(env.step,ref,reference_id='ref')
    assert env.physics_steps==4 and r.ledger.stopped

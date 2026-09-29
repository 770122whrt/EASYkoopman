"""Integrated issuance with explicit synthetic receipts, not a physics pilot."""
from dataclasses import replace
import numpy as np
import pytest

from test_bounded_feedback_v46 import initial
from test_prepared_projected_v40 import context
from test_plan_arbiter_v52 import Clock
from koopman.bounded_feedback_v46 import FeedbackConfig
from koopman.bounded_feedback_v47 import TrackingFeedback
from koopman.bounded_mpc_v44 import SupportDomain
from koopman.execution_ledger_v48 import BoundaryObservation,ResetObservation
from koopman.prepared_execution_v49 import PreparedExecutionLedger
from koopman.recovery_solver_v50 import request_binding


class Worker:
    def __init__(self):self.state='ready';self.generation='fixture-A';self.request=None;self.event=None;self.calls=0
    def submit(self,rid,payload):
        assert self.state=='ready';self.calls+=1;self.request=payload;self.state='busy'
        return dict(status='accepted',generation=self.generation,key=str(self.calls),request_id=rid)
    def poll(self):
        event=self.event;self.event=None
        if event is not None:self.state='ready' if event['status']=='result' else 'failed'
        return event
    def complete(self):
        req=self.request;c=req.capture;commands=np.repeat(req.prefix[-1][None],20,axis=0)
        commands[:8]=req.prefix;commands[8:,0]=.003
        packet=dict(status='selected',commands=commands,predictions=np.repeat(c.state[None],40,axis=0),
            runtime_eligible=False,actual_history_advanced=False,binding=request_binding(req),
            metadata=dict(episode_id=c.episode_id,reference_id=c.reference_id,request_id=req.request_id,
                configuration=c.configuration,context_key=list(c.context_key),model_id=c.model_id,support_id=c.support_id,
                origin_control=c.physics_index//2,history_physics_index=c.physics_index,committed_prefix=8,
                previous_command=c.previous.tolist(),reference=c.reference.tolist()))
        self.event=dict(status='result',generation=self.generation,key=str(self.calls),request_id=req.request_id,
                        elapsed_ms=20.,payload=packet)


def setup(worker=True):
    from koopman.runtime_coordinator_v52 import RuntimeCoordinator
    c=context('base');d=SupportDomain.diagnostic('base',c,'a'*64);x=initial();ref=x[:5].copy()
    policy=TrackingFeedback(d,c,config=FeedbackConfig(timeout_ms=2000),allow_diagnostic=True)
    seed=policy.prepare_startup(x,ref);assert seed['status']=='prepared'
    ledger=PreparedExecutionLedger(d,c,ResetObservation('episode','reset',0,x,np.zeros(8)),
        reference=ref,reference_id='ref',startup_command=seed['command'],allow_diagnostic=True)
    clock=Clock();worker=Worker() if worker else None
    run=RuntimeCoordinator(ledger,policy,worker,clock=clock)
    return run,clock,worker


def safety(index=0,**kw):
    from koopman.runtime_coordinator_v52 import SafetyObservation
    return SafetyObservation('episode','reset',index,np.zeros(2),4.,False,**kw)


def step(run,state=None,reference=None,reference_id='ref',safe=None):
    x=initial() if state is None else state
    i=run.ledger.physics_index
    return run.step(BoundaryObservation('episode','reset',i,x),initial()[:5] if reference is None else reference,
        reference_id=reference_id,safety=safety(i) if safe is None else safe)


def ack(run,decision):
    p=decision['packet'];start=p['physics_index']
    for i in (start,start+1):
        got=run.acknowledge(p['ticket'],p['command'],physics_index=i,episode_id='episode',reset_id='reset',safety=safety(i+1))
        assert got['status']=='acknowledged',got


def test_coordinator_startup_prefix_plan_activation_and_ack_form_one_chain():
    run,clock,worker=setup();d=step(run)
    assert d['status']=='dispatch' and d['packet']['startup_exception']
    assert worker.calls==0 and run.ledger.physics_index==0
    ack(run,d);assert run.ledger.startup_consumed
    clock.now=1/60;d=step(run);assert worker.calls==1
    assert d['packet']['source']=='committed_prefix';ack(run,d);worker.complete()
    for control in range(2,10):
        clock.now=control/60;d=step(run)
        assert d['status']=='dispatch',d
        if control==9:
            assert d['packet']['source']=='mpc'
            assert d['packet']['command'][0]==pytest.approx(.003)
            assert worker.calls==2  # Explicit active-plan prefix for the next request.
        ack(run,d)
    assert run.ledger.physics_index==20
    assert run.stats['mpc_activations']==1 and run.stats['confirmed_controls']==10


def test_worker_failure_keeps_qualified_feedback_without_wait_or_restart():
    run,clock,worker=setup();ack(run,step(run));clock.now=1/60;ack(run,step(run))
    worker.event=dict(status='failed',reason='fixture_crash',generation=worker.generation,
        key='1',request_id=worker.request.request_id)
    clock.now=2/60;d=step(run)
    assert d['status']=='dispatch' and d['packet']['source']=='fallback'
    assert worker.calls==1 and worker.state=='failed'


@pytest.mark.parametrize('bad',['contact','clearance','xy','identity','missing'])
def test_runtime_safety_rejects_before_any_dispatch_or_model_request(bad):
    run,_,worker=setup();s=safety()
    if bad=='contact':s=replace(s,contact_observed=True)
    if bad=='clearance':s=replace(s,minimum_clearance_m=.09)
    if bad=='xy':s=replace(s,xy_displacement_m=np.array([2.01,0]))
    if bad=='identity':s=replace(s,reset_id='wrong')
    if bad=='missing':s=None
    got=run.step(BoundaryObservation('episode','reset',0,initial()),initial()[:5],reference_id='ref',safety=s)
    assert got['status']=='stop' and got['packet'] is None
    assert run.ledger.physics_index==0 and not run.ledger.pending and worker.calls==0


def test_unsafe_first_substep_preserves_actual_partial_history_and_stops():
    run,_,_=setup();p=step(run)['packet']
    got=run.acknowledge(p['ticket'],p['command'],physics_index=0,episode_id='episode',reset_id='reset',
        safety=replace(safety(1),contact_observed=True))
    assert got['status']=='stop' and run.ledger.physics_index==1 and run.ledger.startup_consumed
    assert got['actual_history_advanced'] is True
    assert run.ledger.pending and run.ledger.stopped


def test_feedback_failure_never_falls_back_to_zero_or_last_command(monkeypatch):
    run,_,_=setup();monkeypatch.setattr(run.feedback,'decide',lambda *a,**k:dict(status='no_command',reason='timeout'))
    got=step(run);assert got['status']=='stop' and got['packet'] is None
    assert run.ledger.physics_index==0


def test_unacknowledged_dispatch_is_not_sent_again():
    run,_,worker=setup();d=step(run);got=step(run)
    assert d['status']=='dispatch' and got['status']=='stop'
    assert run.ledger.physics_index==0 and worker.calls==0


def test_control_decision_deadline_does_not_return_a_late_dispatch(monkeypatch):
    run,clock,_=setup();original=run.feedback.decide
    def slow(*a,**k):
        answer=original(*a,**k);clock.now+=.02;return answer
    monkeypatch.setattr(run.feedback,'decide',slow)
    got=step(run);assert got['status']=='stop' and got['packet'] is None
    assert run.ledger.physics_index==0


def test_worker_replacement_preserves_startup_and_causal_history():
    run,clock,worker=setup();ack(run,step(run));old=run.ledger.physics_index
    worker.state='failed';fresh=Worker();fresh.generation='fixture-B';run.replace_worker(fresh)
    assert run.ledger.physics_index==old and run.ledger.startup_consumed
    clock.now=1/60;d=step(run)
    assert not d['packet']['startup_exception'] and fresh.request.capture.worker_generation==1


def test_replacement_cannot_discard_an_already_dispatched_startup():
    run,_,worker=setup();d=step(run);worker.state='failed'
    fresh=Worker();fresh.generation='fixture-B';run.replace_worker(fresh)
    assert run.ledger.pending and not run.ledger.startup_consumed
    ack(run,d)
    assert run.ledger.physics_index==2 and run.ledger.startup_consumed


def test_ack_computation_timeout_keeps_confirmed_actual_history(monkeypatch):
    run,clock,_=setup();p=step(run)['packet'];original=run.ledger.acknowledge
    def delayed(*args,**kwargs):
        answer=original(*args,**kwargs);clock.now+=.009;return answer
    monkeypatch.setattr(run.ledger,'acknowledge',delayed)
    first=run.acknowledge(p['ticket'],p['command'],physics_index=0,episode_id='episode',reset_id='reset',safety=safety(1))
    assert first['status']=='acknowledged'
    second=run.acknowledge(p['ticket'],p['command'],physics_index=1,episode_id='episode',reset_id='reset',safety=safety(2))
    assert second['status']=='stop' and second['reason']=='control_compute_timeout'
    assert second['actual_history_advanced'] is True and run.ledger.physics_index==2


def test_progress_guard_stops_persistent_measured_error_on_confirmed_intervals():
    from koopman.runtime_coordinator_v52 import ProgressGuard,RuntimeConfig
    cfg=RuntimeConfig(no_improvement_controls=3,zero_progress_controls=2)
    g=ProgressGuard('base',config=cfg);x=initial();ref=x[:5].copy();ref[0]+=.1
    for i in range(3):assert g.observe(i,x,ref,reference_id='ref')['status']=='continue'
    got=g.observe(3,x,ref,reference_id='changed')
    assert got['status']=='stop' and got['reason']=='persistent_tracking_no_improvement'
    assert g.observe(4,initial(),initial()[:5],reference_id='ref')['status']=='stop'


def test_progress_guard_recognizes_measured_improvement_not_static_wrench_label():
    from koopman.runtime_coordinator_v52 import ProgressGuard,RuntimeConfig
    g=ProgressGuard('base',config=RuntimeConfig(no_improvement_controls=3,zero_progress_controls=2))
    x=initial();ref=x[:5].copy();ref[0]+=.1
    for i in range(8):
        x[0]=5.5+.01*i
        got=g.observe(i,x,ref,reference_id='ref',last_tracking=dict(tracking_status='target_attained'))
        assert got['status']=='continue'


def test_zero_progress_limit_and_duplicate_observation_fail_closed():
    from koopman.runtime_coordinator_v52 import ProgressGuard,RuntimeConfig
    g=ProgressGuard('base',config=RuntimeConfig(no_improvement_controls=5,zero_progress_controls=2))
    x=initial();ref=x[:5].copy();ref[0]+=.1
    assert g.observe(0,x,ref,reference_id='ref')['status']=='continue'
    flag=dict(tracking_status='tracking_limited',zero_progress=True)
    assert g.observe(1,x,ref,reference_id='ref',last_tracking=flag)['status']=='continue'
    assert g.observe(2,x,ref,reference_id='ref',last_tracking=flag)['reason']=='persistent_zero_progress'
    other=ProgressGuard('base');other.observe(0,x,ref,reference_id='ref')
    assert other.observe(0,x,ref,reference_id='ref')['status']=='stop'

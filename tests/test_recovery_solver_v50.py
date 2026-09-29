"""Causal recovery proposals and real-worker binding; no Isaac qualification."""
from dataclasses import replace
import pickle
import time

import numpy as np
import pytest

from test_prepared_projected_v40 import context
from test_bounded_feedback_v46 import initial
from test_execution_ledger_v48 import setup, execute, capture
from koopman.bounded_feedback_v46 import FeedbackConfig
from koopman.bounded_mpc_v44 import SearchConfig, SupportDomain


def builder(name='base'):
    from koopman.recovery_solver_v50 import RecoveryBaseline
    c=context(name); d=SupportDomain.diagnostic(name,c,'a'*64)
    return RecoveryBaseline(d,c,config=FeedbackConfig(timeout_ms=2000),allow_diagnostic=True)


def build(b, *, prefix=None, old=None, deadline=None):
    ref=initial()[:5].copy();ref[0]+=.05
    return b.build(initial(),ref,np.zeros(4) if old is None else old,
        np.zeros((8,4)) if prefix is None else prefix,horizon=20,
        deadline=time.perf_counter()+2 if deadline is None else deadline)


def test_recovery_crosses_source_deadzone_after_exact_committed_prefix():
    from workflows.control_seam_v23 import ControlKernel
    from workflows.workpoint_v27 import _steady
    b=builder(); p=np.zeros((8,4)); got=build(b,prefix=p)
    assert got['status']=='ready', got
    np.testing.assert_array_equal(got['commands'][:8],p)
    assert np.max(np.abs(np.diff(np.vstack([np.zeros(4),got['commands']]),axis=0)))<=.01+1e-7
    kernel=ControlKernel('base')
    wrenches=np.array([_steady(kernel,u.copy())[0] for u in got['commands']])
    assert np.max(np.abs(wrenches[:8]))==0
    assert np.linalg.norm(wrenches[-1])>0
    assert got['future_feedback_assumed'] is False and got['actual_history_advanced'] is False
    assert got['target_rewritten'] is False
    with pytest.raises(ValueError):got['commands'][0,0]=1


def test_static_target_can_be_outside_fit_but_entire_recovery_stays_inside():
    b=builder();upper=b.domain.command_upper.copy();upper[3]=.003
    b.domain=replace(b.domain,command_upper=upper)
    got=build(b)
    assert got['status']=='ready'
    assert np.max(got['commands'][:,3])<=.003+1e-7
    assert got['static_command'][3]>.003
    assert got['tracking'][-1]['zero_progress']
    assert got['tracking'][-1]['status']=='tracking_limited'


@pytest.mark.parametrize('bad',['slew','mask','nan','prefix_shape','prefix_long','previous','deadline','state'])
def test_invalid_or_expired_baseline_cannot_yield_commands(bad):
    b=builder('uuv4');x=initial();p=np.zeros((8,4));old=np.zeros(4);deadline=time.perf_counter()+2
    if bad=='slew':p[3,0]=.1
    if bad=='mask':p[:,2]=.001
    if bad=='nan':p[0,0]=np.nan
    if bad=='prefix_shape':p=np.zeros((8,3))
    if bad=='prefix_long':p=np.zeros((20,4))
    if bad=='previous':old=np.ones(3)
    if bad=='deadline':deadline=time.perf_counter()-1
    if bad=='state':x[0]=1
    result=b.build(x,x[:5],old,p,horizon=20,deadline=deadline)
    assert result['status']=='no_baseline' and result['commands'] is None


def request_and_solver():
    from koopman.recovery_solver_v50 import PlanningRequest, RecoverySolver
    ledger,u,ref=setup();execute(ledger,u,startup=True);cap=capture(ledger)
    req=PlanningRequest('request-1',cap,np.repeat(u[None],8,axis=0))
    c=context('base');d=SupportDomain.diagnostic('base',c,'a'*64)
    solver=RecoverySolver(d,c,lambda x,a,c:x.copy(),config=SearchConfig(timeout_ms=2000),
        feedback_config=FeedbackConfig(timeout_ms=2000),allow_diagnostic=True)
    return ledger,req,solver


def test_plan_request_roundtrip_owns_prefix_and_binds_actual_origin():
    ledger,req,solver=request_and_solver(); before=capture(ledger)
    got=solver(pickle.loads(pickle.dumps(req)))
    assert got['status'] in ('selected','baseline'),got
    np.testing.assert_array_equal(got['commands'][:8],req.prefix)
    assert got['metadata']['committed_prefix']==8
    assert got['binding']['history_digest']==before.history_digest
    assert got['binding']['execution_id']==before.execution_id
    assert got['binding']['activation_control']==9
    assert got['runtime_eligible'] is False and got['actual_history_advanced'] is False
    assert ledger.physics_index==2
    np.testing.assert_array_equal(capture(ledger).origin._actuator.current(),before.origin._actuator.current())
    with pytest.raises(ValueError):req.prefix[0,0]=1


@pytest.mark.parametrize('field,value',[
    ('configuration','uuv4'),('model_id','b'*64),('support_id','bad'),
    ('context_key',(1.,)*12),('physics_index',4),('previous',None),
    ('history_digest','bad'),('reference_revision',-1),('worker_generation',True)])
def test_changed_request_binding_is_rejected(field,value):
    from koopman.recovery_solver_v50 import PlanningRequest
    _,req,solver=request_and_solver()
    try:changed=PlanningRequest(req.request_id,replace(req.capture,**{field:value}),req.prefix)
    except ValueError:return
    result=solver(changed)
    assert result['status']=='no_plan' and result['commands'] is None


def test_complete_recovery_and_solve_share_one_budget(monkeypatch):
    _,req,solver=request_and_solver();solver.config=SearchConfig(timeout_ms=5)
    original=solver.baseline.build
    def slow(*a,**kw):time.sleep(.012);return original(*a,**kw)
    monkeypatch.setattr(solver.baseline,'build',slow)
    got=solver(req)
    assert got['status']=='no_plan' and got['reason']=='timeout'


def test_no_request_is_allowed_before_once_only_startup_ack():
    from koopman.recovery_solver_v50 import PlanningRequest
    ledger,u,_=setup()
    with pytest.raises(ValueError):PlanningRequest('request',capture(ledger),np.repeat(u[None],8,axis=0))


def test_frozen_factory_fails_before_model_load_when_handoff_hash_wrong(tmp_path):
    from koopman.recovery_solver_v50 import FrozenWorkerSpec, frozen_model_factory
    p=tmp_path/'docs/evidence/phase8_4/server-projected-formal-v38-r23'
    p.mkdir(parents=True);(p/'prediction-control-handoff-v2.json').write_text('{}')
    spec=FrozenWorkerSpec(str(tmp_path),'base',context('base'),'nonlinear__pooled','a'*64,'b'*64,'c'*64,None)
    with pytest.raises(ValueError,match='handoff_hash'):frozen_model_factory(spec)

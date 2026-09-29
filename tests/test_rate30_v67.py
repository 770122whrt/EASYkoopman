import time
from dataclasses import replace
import numpy as np
import pytest
from test_prepared_projected_v40 import context
from test_bounded_feedback_v46 import initial

def setup():
    from koopman.rate30_v67 import ExecutionLedger, FEEDBACK_CONFIG
    from koopman.bounded_mpc_v44 import SupportDomain
    from koopman.inexact_tracking_v66 import InexactTrackingFeedback
    from koopman.execution_ledger_v48 import ResetObservation
    c=context('base');d=SupportDomain.diagnostic('base',c,'a'*64)
    cfg=replace(FEEDBACK_CONFIG,timeout_ms=2000)
    f=InexactTrackingFeedback(d,c,config=cfg,allow_diagnostic=True)
    x=initial();r=x[:5];seed=f.prepare_startup(x,r)
    reset=ResetObservation('e','r',0,x,np.zeros(f.steady.allocator.wrench_matrix.shape[1]))
    ledger=ExecutionLedger(d,c,reset,reference=r,reference_id='ref',startup_command=seed['command'],
        feedback_config=cfg,steady=f.steady,allow_diagnostic=True)
    return ledger,seed['command'],r

def capture(l,r):
    from koopman.execution_ledger_v48 import BoundaryObservation
    return l.capture(BoundaryObservation('e','r',l.physics_index,initial()),r,reference_id='ref')

def ack(l,t,u,i):
    return l.acknowledge(t,u,physics_index=i,episode_id='e',reset_id='r')

def test_four_receipts_hold_and_two_micro_history_entries():
    from koopman.command_state_v39 import CausalCommandState
    l,u,r=setup();t=l.reserve(capture(l,r),u,source='fallback',startup=True);l.dispatch(t)
    old=CausalCommandState('base',context('base'),episode_id='e',zero_rotor_reset_verified=True)
    for i in range(4):
        got=ack(l,t,u,i);old.record_issued(u,physics_index=i,episode_id='e')
        assert got['interval_complete']==(i==3)
        if i<3:
            with pytest.raises(ValueError):capture(l,r)
        if i==1:np.testing.assert_array_equal(l.acknowledged_commands(0,1),u[None])
    cap=capture(l,r);assert cap.origin.origin_control==2
    np.testing.assert_array_equal(l.acknowledged_commands(0,2),np.repeat(u[None],2,axis=0))
    snap=old.snapshot(configuration='base',context=context('base'),origin_control=2,episode_id='e')
    np.testing.assert_allclose(cap.origin._actuator.current(),snap._actuator.current(),atol=1e-12,rtol=1e-12)
    assert cap.origin._actuator.elapsed_time==snap._actuator.elapsed_time

@pytest.mark.parametrize('bad',['duplicate','third_changed','fifth'])
def test_invalid_receipt_stops_without_guessing(bad):
    l,u,r=setup();t=l.reserve(capture(l,r),u,source='fallback',startup=True);l.dispatch(t)
    for i in range(2 if bad!='fifth' else 4):ack(l,t,u,i)
    v=u.copy();index=2
    if bad=='duplicate':index=1
    if bad=='third_changed':v[3]=np.nextafter(v[3],np.float32(1))
    if bad=='fifth':index=4
    with pytest.raises(ValueError):ack(l,t,v,index)
    assert l.stopped and l.physics_index==(4 if bad=='fifth' else 2)

def test_progress_uses_macro_count_and_keeps_time_limits():
    from koopman.rate30_v67 import Progress30,RUNTIME_CONFIG
    p=Progress30('base');x=initial();r=x[:5].copy();r[0]+=.1
    for i in range(30):assert p.observe(2*i,x,r,reference_id='ref')['status']=='continue'
    assert p.observe(60,x,r,reference_id='ref')['reason']=='persistent_tracking_no_improvement'
    assert RUNTIME_CONFIG.control_compute_budget_s==1/30
    assert Progress30('base').observe(1,x,r,reference_id='ref')['status']=='stop'

@pytest.mark.parametrize('bad',[None,'pair','horizon'])
def test_baseline_pairing_prefix_preservation_and_macro_slew(bad):
    from koopman.rate30_v67 import RecoveryBaseline,FEEDBACK_CONFIG
    from koopman.bounded_mpc_v44 import SupportDomain
    c=context('base');d=SupportDomain.diagnostic('base',c,'a'*64)
    b=RecoveryBaseline(d,c,config=replace(FEEDBACK_CONFIG,timeout_ms=2000),allow_diagnostic=True)
    p=np.zeros((8,4));h=20
    if bad=='pair':p[1,3]=.001
    if bad=='horizon':h=19
    result=b.build(initial(),[5.48,1,0,0,0],np.zeros(4),p,horizon=h,deadline=time.perf_counter()+2)
    if bad:assert result['status']=='no_baseline'
    else:
        assert result['status']=='ready';u=result['commands']
        np.testing.assert_array_equal(u[:8],p);np.testing.assert_array_equal(u[::2],u[1::2])
        assert np.max(np.abs(np.diff(u[::2],axis=0)))<=.02+1e-7

@pytest.mark.parametrize('bad',[None,'baseline','prefix','origin','float_origin'])
def test_solver_pairing_and_causal_origin(bad):
    from koopman.bounded_mpc_v67 import BoundedMPC
    from test_bounded_mpc_v44 import fixtures
    _,d,old,args=fixtures();cfg=replace(old.config,slew=(.02,)*4)
    s=BoundedMPC(d,old.predictor,model_id=d.model_id,config=cfg,weights=old.weights,allow_diagnostic=True)
    args['committed_prefix']=2
    if bad=='baseline':args['baseline'][1,3]=.001
    if bad=='prefix':args['committed_prefix']=1
    if bad=='origin':args['origin']=replace(args['origin'],origin_control=1)
    if bad=='float_origin':args['origin']=replace(args['origin'],origin_control=2.)
    result=s.solve(**args)
    if bad:assert result['status']=='no_plan' and result['reason']=='rate30_pairing_or_origin'
    else:
        assert result['status'] in ('selected','baseline')
        np.testing.assert_array_equal(result['commands'][::2],result['commands'][1::2])
        assert result['predictions'].shape==(16,11)
        assert result['metadata']['control_rate_hz']==30


def macro_execute(l,u,r,startup=False):
    cap=capture(l,r);t=l.reserve(cap,u,source='fallback',startup=startup);l.dispatch(t)
    start=l.physics_index
    for i in range(4):ack(l,t,u,start+i)

def arbiter_fixture():
    from koopman.rate30_v67 import Rate30Arbiter
    from koopman.recovery_solver_v50 import PlanningRequest,request_binding
    from test_plan_arbiter_v52 import Clock
    l,u,r=setup();macro_execute(l,u,r,startup=True);cap=capture(l,r)
    clock=Clock();arb=Rate30Arbiter(l,clock=clock)
    req=PlanningRequest('request',cap,np.repeat(u[None],8,axis=0))
    receipt=dict(status='accepted',generation='g',key='k',request_id='request')
    arb.register(req,receipt)
    packet=dict(status='selected',commands=np.repeat(u[None],20,axis=0),
        predictions=np.repeat(initial()[None],40,axis=0),runtime_eligible=False,
        actual_history_advanced=False,binding=request_binding(req),
        metadata=dict(episode_id='e',reference_id='ref',request_id='request',configuration='base',
            context_key=list(cap.context_key),model_id=cap.model_id,support_id=cap.support_id,
            origin_control=2,history_physics_index=4,committed_prefix=8,
            previous_command=cap.previous.tolist(),reference=cap.reference.tolist(),
            control_rate_hz=30,prediction_grid_hz=60))
    event=dict(status='result',generation='g',key='k',request_id='request',elapsed_ms=10.,payload=packet)
    return l,u,r,clock,arb,req,receipt,event

@pytest.mark.parametrize('bad',[None,'pair','odd_origin','missing_rate','late','history','state'])
def test_parent_arbiter_rechecks_pairs_and_real_micro_history(bad):
    l,u,r,clock,a,req,receipt,event=arbiter_fixture()
    if bad=='pair':event['payload']['commands'][9,0]+=.001
    if bad=='odd_origin':event['payload']['metadata']['origin_control']=3
    if bad=='missing_rate':del event['payload']['metadata']['control_rate_hz']
    if bad=='late':event['elapsed_ms']=101
    result=a.ingest(event)
    if bad in ('pair','odd_origin','missing_rate','late'):
        assert result['status']=='rejected' and not a.pending
        return
    assert result['status']=='staged'
    for _ in range(4):
        chosen=a.choose(capture(l,r));assert chosen['source']=='committed_prefix'
        actual=chosen['command'].copy()
        if bad=='history':actual[0]+=.001
        macro_execute(l,actual,r)
        if bad=='history':break
    clock.now=.133
    cap=capture(l,r)
    if bad=='state':
        from koopman.execution_ledger_v48 import BoundaryObservation
        x=initial();x[5]=.03
        cap=l.capture(BoundaryObservation('e','r',l.physics_index,x),r,reference_id='ref')
    result=a.choose(cap)
    if bad in ('history','state'):assert result['status']=='fallback'
    else:
        assert result['source']=='mpc' and result['plan_index']==8 and l.physics_index==20
        np.testing.assert_array_equal(a.following_prefix(cap),event['payload']['commands'][8:16])

@pytest.mark.parametrize('bad',['prefix','origin'])
def test_parent_register_rejects_nonmacro_contract(bad):
    from koopman.recovery_solver_v50 import PlanningRequest
    l,u,r,clock,a,req,receipt,event=arbiter_fixture();a.invalidate('test')
    cap=capture(l,r);prefix=np.array(req.prefix)
    if bad=='prefix':prefix[1,0]+=.001
    else:cap=replace(cap,physics_index=6,origin=replace(cap.origin,origin_control=3))
    badreq=PlanningRequest('request',cap,prefix)
    with pytest.raises(ValueError,match='rate30_request_pairing'):a.register(badreq,receipt)

@pytest.mark.parametrize('name',['base','asymmetric','uuv4'])
def test_compiled_forecast_preserves_all_four_substeps(name):
    pytest.importorskip('numba')
    from koopman.bounded_mpc_v67 import BoundedMPC
    from koopman.compiled_projected_v43 import prepare_compiled
    from koopman.prepared_commands_v45 import PreparedCommands
    from koopman.command_batch_v45 import forecast_prepared
    from test_bounded_mpc_v44 import fixtures
    from test_prepared_projected_v40 import model
    live,d,old,args=fixtures(name);cfg=replace(old.config,horizon=4,slew=(.02,)*4)
    # A short legal forecast checks the compiled recurrence, not zero-input stability.
    args['baseline']=args['baseline'][:4]
    predictor=prepare_compiled(model(),args['origin']._context)
    s=BoundedMPC(d,predictor,model_id=d.model_id,config=cfg,weights=old.weights,allow_diagnostic=True)
    args['committed_prefix']=2
    got=s.solve(**args);assert got['status'] in ('selected','baseline')
    prepared=PreparedCommands(args['origin'],got['commands'][None])
    reference=forecast_prepared(args['origin'],args['initial_state'],prepared,predictor)[0]
    np.testing.assert_allclose(got['predictions'],reference['predictions'],rtol=1e-12,atol=1e-12)
    assert live.physics_index==0

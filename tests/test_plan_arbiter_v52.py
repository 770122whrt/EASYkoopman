"""Late plans must align to acknowledged history, not an old first command."""
from copy import deepcopy
from dataclasses import replace
import numpy as np
import pytest

from test_execution_ledger_v48 import setup,execute,capture
from test_bounded_feedback_v46 import initial
from test_bounded_mpc_v44 import world_yaw
from koopman.execution_ledger_v48 import BoundaryObservation
from koopman.recovery_solver_v50 import PlanningRequest,request_binding


class Clock:
    def __init__(self):self.now=0.
    def __call__(self):return self.now


def fixture(name='base',history_limit=256):
    from koopman.plan_arbiter_v52 import PlanArbiter
    ledger,u,ref=setup(name,history_limit);execute(ledger,u,startup=True);cap=capture(ledger)
    clock=Clock();arb=PlanArbiter(ledger,clock=clock)
    req=PlanningRequest('request',cap,np.repeat(u[None],8,axis=0))
    receipt=dict(status='accepted',generation='transport-A',key='key-A',request_id='request')
    arb.register(req,receipt)
    commands=np.repeat(u[None],20,axis=0);commands[8:,0]=.003
    predictions=np.repeat(initial()[None],40,axis=0)
    # Predicted boundary before activation is row15, not row0 or row16.
    predictions[15,0]+=.01
    packet=dict(status='selected',commands=commands,predictions=predictions,runtime_eligible=False,
        actual_history_advanced=False,binding=request_binding(req),
        metadata=dict(episode_id=cap.episode_id,reference_id=cap.reference_id,request_id=req.request_id,
            configuration=cap.configuration,context_key=list(cap.context_key),model_id=cap.model_id,
            support_id=cap.support_id,origin_control=1,history_physics_index=2,committed_prefix=8,
            previous_command=cap.previous.tolist(),reference=cap.reference.tolist()))
    event=dict(status='result',generation='transport-A',key='key-A',request_id='request',elapsed_ms=30.,payload=packet)
    return ledger,u,ref,clock,arb,req,event


def advance(ledger,u,count=8):
    for _ in range(count):execute(ledger,u)


def observed(ledger,state=None,ref=None,rid='reference-1'):
    return ledger.capture(BoundaryObservation('episode','reset-1',ledger.physics_index,
        initial() if state is None else state),initial()[:5] if ref is None else ref,reference_id=rid)


def test_early_result_waits_and_activates_correct_index_without_advancing_history():
    ledger,u,_,clock,arb,req,event=fixture()
    assert arb.ingest(event)['status']=='staged'
    first=arb.choose(capture(ledger));assert first['source']=='committed_prefix'
    np.testing.assert_array_equal(first['command'],u);assert ledger.physics_index==2
    advance(ledger,u);clock.now=.133
    cap=capture(ledger);result=arb.choose(cap)
    assert result['source']=='mpc' and result['plan_index']==8
    np.testing.assert_array_equal(result['command'],event['payload']['commands'][8].astype(np.float32))
    assert ledger.physics_index==18 and not ledger.pending
    assert result['actual_history_advanced'] is False
    with pytest.raises(ValueError):result['command'][0]=99


def test_current_state_compared_with_last_predicted_physics_step_at_activation():
    ledger,u,_,clock,arb,_,event=fixture();event['payload']['predictions'][15,0]+=.04
    assert arb.ingest(event)['status']=='staged';advance(ledger,u);clock.now=.133
    result=arb.choose(capture(ledger))
    assert result['status']=='fallback' and 'state_deviation' in result['reason']


def test_only_real_acknowledged_prefix_is_accepted_with_small_command_tolerance():
    ledger,u,_,clock,arb,_,event=fixture();arb.ingest(event)
    changed=u.copy();changed[0]+=5e-8
    advance(ledger,changed);clock.now=.133
    assert arb.choose(capture(ledger))['source']=='mpc'


@pytest.mark.parametrize('why',['different_prefix','expired_history','missing_reply','missed_activation','wall_age'])
def test_prefix_age_and_activation_rejections(why):
    ledger,u,_,clock,arb,_,event=fixture(history_limit=2 if why=='expired_history' else 256)
    if why!='missing_reply':arb.ingest(event)
    changed=u.copy()
    if why=='different_prefix':changed[0]+=.001
    advance(ledger,changed,9 if why=='missed_activation' else 8)
    clock.now=.5 if why=='wall_age' else .133
    got=arb.choose(capture(ledger));assert got['status']=='fallback' and got['command'] is None


@pytest.mark.parametrize('field,value', [('generation','wrong'),('key','wrong'),('request_id','wrong'),('elapsed_ms',101.)])
def test_transport_mismatch_or_late_result_cannot_be_staged(field,value):
    _,_,_,clock,arb,_,event=fixture();event[field]=value
    assert arb.ingest(event)['status']=='rejected'


@pytest.mark.parametrize('field,value',[('reset_id','another-reset'),('history_digest','a'*64),
    ('worker_generation',99),('reference_revision',99),('model_id','b'*64),('support_id','bad')])
def test_worker_cannot_relabel_a_plan_as_another_request(field,value):
    _,_,_,_,arb,_,event=fixture();event['payload']['binding'][field]=value
    assert arb.ingest(event)['status']=='rejected'


@pytest.mark.parametrize('bad',['prefix','shape','nan','deadzone','slew','masked_axis','support','metadata'])
def test_malformed_or_physically_inadmissible_worker_plan_rejected(bad):
    _,_,_,_,arb,_,event=fixture('uuv4');p=event['payload']
    if bad=='prefix':p['commands'][0,0]=.001
    if bad=='shape':p['predictions']=np.zeros((20,11))
    if bad=='nan':p['predictions'][0,0]=np.nan
    if bad=='deadzone':p['commands'][8:,0]=0;p['commands'][8:,3]=.02
    if bad=='slew':p['commands'][8:,0]=.04
    if bad=='masked_axis':p['commands'][8:,2]=.001
    if bad=='support':p['predictions'][10,0]=1.
    if bad=='metadata':p['metadata']['origin_control']=0
    assert arb.ingest(event)['status']=='rejected'


def test_change_of_reference_invalidates_pending_and_active_without_rearming_startup():
    ledger,u,ref,clock,arb,_,event=fixture();arb.ingest(event);advance(ledger,u)
    ref[0]+=.01;clock.now=.133
    got=arb.choose(observed(ledger,ref=ref,rid='reference-2'))
    assert got['status']=='fallback' and 'binding' in got['reason']
    assert ledger.startup_consumed


def test_worker_restart_and_explicit_fallback_invalidate_old_plans():
    ledger,u,_,clock,arb,_,event=fixture();arb.ingest(event);ledger.restart_worker_generation()
    assert arb.choose(capture(ledger))['status']=='fallback'
    arb.invalidate('fallback_replaced_prefix')
    assert arb.ingest(event)['status']=='rejected'


@pytest.mark.parametrize('name',['uuv4','uuv4_angled','base'])
def test_current_attitude_gate_retains_controllability_and_quaternion_sign(name):
    ledger,u,_,clock,arb,_,event=fixture(name);arb.ingest(event);advance(ledger,u);clock.now=.133
    x=initial();x[1:5]=world_yaw(x[1:5],.4)
    got=arb.choose(observed(ledger,x))
    assert got['status']==('fallback' if name=='base' else 'proposal')


def test_no_reply_prefix_still_has_measured_drift_guard():
    ledger,_,_,_,arb,_,_=fixture();x=initial();x[5]=.03
    got=arb.choose(observed(ledger,x))
    assert got['status']=='fallback' and 'state_deviation' in got['reason']


def test_staged_result_owns_arrays_and_an_active_plan_cannot_replay_after_fallback():
    ledger,u,_,clock,arb,_,event=fixture();arb.ingest(event)
    event['payload']['commands'][:]=.9;event['payload']['predictions'][:]=np.nan
    advance(ledger,u);clock.now=.133;chosen=arb.choose(capture(ledger))
    assert chosen['command'][0]==pytest.approx(.003)
    execute(ledger,chosen['command']);different=chosen['command'].copy();different[0]+=.001
    execute(ledger,different);clock.now=.17
    assert arb.choose(capture(ledger))['status']=='fallback'


def test_second_request_cannot_overwrite_pending_slot():
    _,_,_,_,arb,req,_=fixture()
    with pytest.raises(ValueError,match='pending'):arb.register(req,dict(status='accepted'))


def test_reply_validation_itself_cannot_cross_admission_deadline(monkeypatch):
    ledger,_,_,clock,arb,_,event=fixture();original=ledger._checked_command
    def delayed(*args,**kwargs):
        clock.now+=.01
        return original(*args,**kwargs)
    monkeypatch.setattr(ledger,'_checked_command',delayed)
    assert arb.ingest(event)['status']=='rejected'


def test_quaternion_sign_and_nonactuated_angular_velocity_are_checked_separately():
    ledger,u,_,clock,arb,_,event=fixture('uuv4');arb.ingest(event);advance(ledger,u);clock.now=.133
    x=initial();x[1:5]*=-1
    assert arb.choose(observed(ledger,x))['source']=='mpc'
    x[10]=.06
    assert arb.choose(observed(ledger,x))['status']=='fallback'

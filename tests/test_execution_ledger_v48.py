"""Acknowledged execution and once-only startup, with no Isaac claim."""
from dataclasses import replace

import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from test_bounded_feedback_v46 import initial
from test_prepared_projected_v40 import context
from koopman.bounded_feedback_v46 import FeedbackConfig
from koopman.bounded_feedback_v47 import TrackingFeedback
from koopman.bounded_mpc_v44 import SupportDomain
from koopman.command_state_v39 import CausalCommandState


def setup(name='base', history_limit=256):
    from koopman.execution_ledger_v48 import ExecutionLedger, ResetObservation
    c=context(name);d=SupportDomain.diagnostic(name,c,'a'*64)
    cfg=FeedbackConfig(timeout_ms=2000)
    p=TrackingFeedback(d,c,config=cfg,allow_diagnostic=True)
    x=initial();ref=x[:5].copy();seed=p.prepare_startup(x,ref)
    assert seed['status']=='prepared'
    reset=ResetObservation('episode', 'reset-1', 0, x, np.zeros(len(p.steady.allocator.wrench_matrix.T)))
    ledger=ExecutionLedger(d,c,reset,reference=ref,reference_id='reference-1',
        startup_command=seed['command'],feedback_config=cfg,history_limit=history_limit,allow_diagnostic=True)
    return ledger,seed['command'].copy(),ref


def capture(ledger,ref=None,reference_id='reference-1'):
    from koopman.execution_ledger_v48 import BoundaryObservation
    return ledger.capture(BoundaryObservation('episode','reset-1',ledger.physics_index,initial()),
                          initial()[:5] if ref is None else ref, reference_id=reference_id)


def reserve(ledger,command,*,startup=False,cap=None):
    return ledger.reserve(capture(ledger) if cap is None else cap,command,source='fallback',startup=startup)


def ack(ledger,ticket,index,command):
    return ledger.acknowledge(ticket,command,physics_index=index,episode_id='episode',reset_id='reset-1')


def execute(ledger,command,*,startup=False,cap=None):
    token=reserve(ledger,command,startup=startup,cap=cap)
    packet=ledger.dispatch(token);index=ledger.physics_index
    ack(ledger,token,index,packet['command']);ack(ledger,token,index+1,packet['command'])
    return token


@pytest.mark.parametrize('name',SUPPORTED_EMBODIMENTS)
def test_startup_permission_is_consumed_only_by_first_ack_and_history_matches_original(name):
    ledger,command,ref=setup(name)
    start=capture(ledger);assert start.previous is None and start.origin.origin_control==0
    token=reserve(ledger,command,startup=True,cap=start)
    assert ledger.physics_index==0 and not ledger.startup_consumed
    packet=ledger.dispatch(token)
    assert ledger.physics_index==0 and not ledger.startup_consumed
    assert packet['startup_exception'] and packet['actual_execution_confirmed'] is False
    ack(ledger,token,0,packet['command'])
    assert ledger.physics_index==1 and ledger.startup_consumed
    with pytest.raises(ValueError,match='pending|boundary'):capture(ledger)
    ack(ledger,token,1,packet['command'])
    end=capture(ledger);assert end.origin.origin_control==1
    np.testing.assert_array_equal(end.previous,command)
    assert start.history_digest!=end.history_digest
    original=CausalCommandState(name,context(name),episode_id='episode',zero_rotor_reset_verified=True)
    for i in range(2):original.record_issued(command,physics_index=i,episode_id='episode')
    old=original.snapshot(configuration=name,context=context(name),origin_control=1,episode_id='episode')
    np.testing.assert_allclose(end.origin._actuator.current(),old._actuator.current(),rtol=1e-12,atol=1e-12)
    assert end.origin._actuator.elapsed_time==old._actuator.elapsed_time
    assert ledger.pending is False


def test_an_outstanding_dispatch_cannot_be_reissued_or_replaced():
    ledger,u,_=setup();cap=capture(ledger);token=reserve(ledger,u,startup=True,cap=cap)
    with pytest.raises(ValueError,match='pending'):reserve(ledger,u,startup=True,cap=cap)
    ledger.dispatch(token)
    with pytest.raises(ValueError,match='dispatch'):ledger.dispatch(token)
    assert ledger.physics_index==0
    assert ledger.stopped


@pytest.mark.parametrize('bad',['not_dispatched','skip','wrong_episode','wrong_reset','wrong_ticket','changed_command','nan_command'])
def test_untrusted_ack_stops_without_committing_a_guess(bad):
    ledger,u,_=setup();token=reserve(ledger,u,startup=True)
    if bad!='not_dispatched':ledger.dispatch(token)
    kwargs=dict(physics_index=0,episode_id='episode',reset_id='reset-1')
    if bad=='skip':kwargs['physics_index']=1
    if bad=='wrong_episode':kwargs['episode_id']='another'
    if bad=='wrong_reset':kwargs['reset_id']='another'
    if bad=='wrong_ticket':token='unknown'
    if bad=='changed_command':u[3]+=.01
    if bad=='nan_command':u[3]=np.nan
    with pytest.raises(ValueError):ledger.acknowledge(token,u,**kwargs)
    assert ledger.physics_index==0 and ledger.stopped and not ledger.startup_consumed
    with pytest.raises(ValueError,match='stopped'):capture(ledger)


def test_duplicate_or_changed_second_hold_ack_preserves_only_confirmed_first_substep():
    for duplicate in (True,False):
        ledger,u,_=setup();token=reserve(ledger,u,startup=True);ledger.dispatch(token);ack(ledger,token,0,u)
        changed=u.copy();changed[3]=np.nextafter(changed[3],np.float32(1))
        with pytest.raises(ValueError):ack(ledger,token,0 if duplicate else 1,u if duplicate else changed)
        assert ledger.physics_index==1 and ledger.stopped and ledger.startup_consumed


def test_uncertain_execution_aborts_and_cannot_be_rearmed_by_worker_restart():
    ledger,u,_=setup();token=reserve(ledger,u,startup=True);ledger.dispatch(token)
    ledger.abort('lost_ack')
    with pytest.raises(ValueError,match='stopped'):ledger.restart_worker_generation()
    assert ledger.stopped and ledger.physics_index==0


def test_worker_generation_and_reference_changes_do_not_rearm_startup():
    ledger,u,ref=setup('heavy_moderate');cap=capture(ledger)
    ledger.restart_worker_generation()
    with pytest.raises(ValueError,match='capture'):reserve(ledger,u,startup=True,cap=cap)
    execute(ledger,u,startup=True)
    ledger.restart_worker_generation();ref[0]+=.05
    cap=capture(ledger,ref,'reference-2')
    with pytest.raises(ValueError,match='startup'):reserve(ledger,u,startup=True,cap=cap)
    token=reserve(ledger,u,cap=cap)
    assert not ledger.dispatch(token)['startup_exception']
    assert ledger.startup_consumed and ledger.physics_index==2


def test_worker_restart_does_not_discard_in_flight_execution_confirmation():
    ledger,u,_=setup();token=reserve(ledger,u,startup=True);ledger.dispatch(token)
    ledger.restart_worker_generation()
    ack(ledger,token,0,u);ack(ledger,token,1,u)
    assert ledger.physics_index==2 and ledger.startup_consumed


def test_startup_command_cannot_be_borrowed_for_a_different_reference_or_changed_command():
    ledger,u,ref=setup('heavy_moderate');ref[0]+=.05
    with pytest.raises(ValueError,match='startup_reference'):capture(ledger,ref,'reference-2')
    changed=u.copy();changed[3]+=.005
    with pytest.raises(ValueError,match='startup'):reserve(ledger,changed,startup=True)
    with pytest.raises(ValueError,match='startup'):reserve(ledger,u,startup=False)
    assert ledger.physics_index==0 and not ledger.startup_consumed


@pytest.mark.parametrize('bad',['state','rotors','rotor_count','index','episode','startup_command','unverified'])
def test_bad_reset_or_unqualified_startup_cannot_construct_live_ledger(bad):
    from koopman.execution_ledger_v48 import ExecutionLedger,ResetObservation
    c=context('base');d=SupportDomain.diagnostic('base',c,'a'*64);x=initial();rotors=np.zeros(8);index=0;episode='episode';u=np.zeros(4)
    if bad=='state':x[7]=.01
    if bad=='rotors':rotors[0]=1e-4
    if bad=='rotor_count':rotors=np.zeros(4)
    if bad=='index':index=2
    if bad=='episode':episode=''
    if bad=='startup_command':u[3]=.1
    with pytest.raises(ValueError):
        reset=ResetObservation(episode,'reset-1',index,x,rotors)
        ExecutionLedger(d,c,reset,reference=initial()[:5],reference_id='reference-1',startup_command=u,allow_diagnostic=bad!='unverified')


@pytest.mark.parametrize('bad',['slew','mask','support','pwm','deadzone'])
def test_normal_command_rechecks_constraints_at_unique_issue_boundary(bad):
    name='uuv4' if bad=='mask' else 'base';ledger,u,_=setup(name);execute(ledger,u,startup=True)
    command=u.copy()
    if bad=='slew':command[3]+=.011
    if bad=='mask':command[2]=.001
    if bad=='support':command[3]=.951
    if bad=='pwm':command[:]=[.5,.5,0,.5]
    if bad=='deadzone':
        command[3]=.01;execute(ledger,command);command[3]=.02
    with pytest.raises(ValueError,match='command'):reserve(ledger,command)
    assert ledger.pending is False and not ledger.stopped


def test_recorded_actual_rounding_not_planned_value_advances_estimator():
    ledger,u,_=setup('heavy_moderate');actual=u.copy();actual[3]=np.nextafter(actual[3],np.float32(1))
    assert 0<np.max(np.abs(actual-u))<=1e-7
    token=reserve(ledger,u,startup=True);ledger.dispatch(token)
    ack(ledger,token,0,actual);ack(ledger,token,1,actual)
    cap=capture(ledger);np.testing.assert_array_equal(cap.previous,actual)
    np.testing.assert_array_equal(ledger.acknowledged_commands(0,1),actual[None])
    old=CausalCommandState('heavy_moderate',context('heavy_moderate'),episode_id='episode',zero_rotor_reset_verified=True)
    for i in range(2):old.record_issued(actual,physics_index=i,episode_id='episode')
    snap=old.snapshot(configuration='heavy_moderate',context=context('heavy_moderate'),origin_control=1,episode_id='episode')
    np.testing.assert_allclose(cap.origin._actuator.current(),snap._actuator.current(),rtol=1e-12,atol=1e-12)


def test_snapshots_inputs_and_ticket_outputs_do_not_alias_committed_history():
    from koopman.execution_ledger_v48 import BoundaryObservation
    ledger,u,ref=setup();state=initial();observation=BoundaryObservation('episode','reset-1',0,state)
    cap=ledger.capture(observation,ref,reference_id='reference-1');state[0]=2;ref[0]=2
    assert cap.state[0]==5.5 and cap.reference[0]==5.5
    for a in (cap.state,cap.reference):
        with pytest.raises(ValueError):a.setflags(write=True)
    token=reserve(ledger,u,startup=True,cap=cap);packet=ledger.dispatch(token)
    with pytest.raises(ValueError):packet['command'].setflags(write=True)
    u[3]=.3
    ack(ledger,token,0,packet['command']);ack(ledger,token,1,packet['command'])
    out=ledger.acknowledged_commands(0,1);out[0,3]=.9
    assert ledger.acknowledged_commands(0,1)[0,3]==0
    cap.origin._actuator._speed[:]=99
    assert not np.any(capture(ledger).origin._actuator.current()==99)


def test_history_is_bounded_and_stale_capture_does_not_reserve():
    ledger,u,_=setup(history_limit=2);old=capture(ledger)
    execute(ledger,u,startup=True)
    for _ in range(3):execute(ledger,u)
    assert ledger.physics_index==8
    with pytest.raises(ValueError,match='history'):ledger.acknowledged_commands(0,1)
    assert ledger.acknowledged_commands(2,4).shape==(2,4)
    with pytest.raises(ValueError,match='capture'):reserve(ledger,u,cap=old)


def test_lock_busy_returns_without_waiting_or_advancing():
    ledger,u,_=setup()
    assert ledger._lock.acquire(blocking=False)
    try:
        with pytest.raises(RuntimeError,match='busy'):capture(ledger)
    finally:ledger._lock.release()
    assert ledger.physics_index==0


@pytest.mark.parametrize('bad',['episode','reset','index','state','reference'])
def test_boundary_capture_rejects_wrong_measurement_or_reference_binding(bad):
    from koopman.execution_ledger_v48 import BoundaryObservation
    ledger,u,ref=setup();execute(ledger,u,startup=True)
    episode,reset,index,x='episode','reset-1',2,initial()
    if bad=='episode':episode='old-episode'
    if bad=='reset':reset='old-reset'
    if bad=='index':index=0
    if bad=='state':x[0]=1
    if bad=='reference':ref[0]=6
    with pytest.raises(ValueError):
        ledger.capture(BoundaryObservation(episode,reset,index,x),ref,reference_id='reference-1')
    assert ledger.physics_index==2 and ledger.startup_consumed


def test_capture_from_another_ledger_or_modified_copy_cannot_reserve():
    first,u,_=setup();second,_,_=setup();cap=capture(first)
    for forged in (capture(second),replace(cap,history_digest='b'*64)):
        with pytest.raises(ValueError,match='capture'):reserve(first,u,startup=True,cap=forged)
    assert first.physics_index==0 and not first.pending

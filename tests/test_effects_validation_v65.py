import copy
import pytest
from test_runtime_audit_v57 import recorded_run


def test_original_activation_replay_remains_required_for_mpc():
    from workflows.runtime_audit_v65 import replay_audit
    report,reset,domain,context=recorded_run()
    got=replay_audit(report,reset,domain,context,reference=reset.state[:5],reference_id='ref',allow_diagnostic=True)
    assert got['activations']==1
    bad=copy.deepcopy(report);bad['activations']=0
    with pytest.raises(ValueError):
        replay_audit(bad,reset,domain,context,reference=reset.state[:5],reference_id='ref',allow_diagnostic=True,require_mpc=False)


def test_feedback_zero_activation_is_explicit_and_physics_replayed():
    from test_runtime_coordinator_v52 import setup,step,ack
    from workflows.runtime_audit_v57 import RecordingArbiter
    from workflows.runtime_audit_v65 import replay_audit
    run,clock,worker=setup();run.worker=None
    run.arbiter=RecordingArbiter(run.ledger,clock=clock)
    intervals=[];receipts=[]
    reset=run.ledger._reset
    for i in range(10):
        clock.now=i/60;d=step(run);assert d['status']=='dispatch'
        intervals.append(dict(physics_index=2*i,decision=d,state=reset.state.copy()))
        ack(run,d);receipts.append(run.ledger._digest)
    report=dict(audit=run.arbiter.export(),intervals=intervals,receipts=receipts,
                execution_id=run.ledger._execution_id,startup=run.ledger._startup,activations=0)
    args=(report,reset,run.ledger._domain,run.ledger._context)
    kwargs=dict(reference=reset.state[:5],reference_id='ref',allow_diagnostic=True)
    assert replay_audit(*args,**kwargs,require_mpc=False)['activations']==0
    with pytest.raises(ValueError):replay_audit(*args,**kwargs)


@pytest.mark.parametrize('mode,index,dt,passes',[
    ('startup_then_realtime',0,28,True),('startup_then_realtime',0,101,False),
    ('startup_then_realtime',1,28,False),('simulation_effect',1,28,True),
    ('simulation_effect',1,1001,False)])
def test_timing_validator_separates_new_protocols(mode,index,dt,passes):
    from workflows.validate_effects_v65 import validate_timing
    row=dict(external_cycle_wall_ms=dt,whole_cycle_wall_ms=dt-.1,
             scheduled_start_lateness_ms=0,timing_mode=mode,
             timing_phase='startup' if index==0 else 'steady',wall_deadline_missed=dt>1000/60)
    if passes:validate_timing(row,index,mode)
    else:
        with pytest.raises(ValueError):validate_timing(row,index,mode)


@pytest.mark.parametrize('bad',['requests','activations','source','clock'])
def test_feedback_arm_and_simulation_clock_cannot_be_mislabeled(bad):
    from workflows.validate_effects_v65 import validate_protocol_flags
    data=dict(runtime_final=dict(stats=dict(requests=0,mpc_activations=0)),
        intervals=[dict(decision=dict(packet=dict(source='fallback')))],
        arbitration_audit=[dict(physics_index=2,started=1/60,finished=1/60,clock_reads=[1/60])])
    case=dict(controller='feedback',mode='simulation_effect')
    validate_protocol_flags(data,case)
    if bad=='requests':data['runtime_final']['stats']['requests']=1
    if bad=='activations':data['runtime_final']['stats']['mpc_activations']=1
    if bad=='source':data['intervals'][0]['decision']['packet']['source']='committed_prefix'
    if bad=='clock':data['arbitration_audit'][0]['clock_reads']=[.1]
    with pytest.raises(ValueError):validate_protocol_flags(data,case)

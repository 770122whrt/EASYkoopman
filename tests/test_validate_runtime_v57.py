"""Mutation coverage using a deliberately synthetic stationary physics fixture."""
import copy
import numpy as np
import pytest

from test_isaac_execution_v55 import bridge, advance
from test_runtime_episode_v57 import snapshot
from test_runtime_coordinator_v52 import Worker


@pytest.fixture
def execution(bridge):
    from workflows.runtime_audit_v57 import RecordingArbiter
    from workflows.control_trace_v23 import _copy
    from koopman.diagnostics_v23 import json_safe
    env,s,run,clock=bridge(bind=False)
    original_backend=env.backend;original_telemetry=env.get_koopman_telemetry_snapshot
    mechanics=snapshot();c=run.ledger._context
    def backend():
        result=original_backend();result.update(copy.deepcopy(mechanics['backend']))
        result.update(_external_force_b=[[[0.,0.,c.mass*c.gravity]]],has_external_wrench=True)
        return result
    def telemetry():
        result=original_telemetry();result.update(copy.deepcopy(mechanics['telemetry']))
        speed=env.thruster_dynamics.state.cpu().numpy()[0]
        result['applied_wrench_6']=[(env.kernel.B.numpy()@(env.cfg.rotor_constant*np.abs(speed)*speed)).tolist()]
        return result
    env.backend=backend;env.get_koopman_telemetry_snapshot=telemetry
    s.reset_observation();s.bind(run)
    worker=Worker();run.worker=worker;run._worker_generation=worker.generation
    run.arbiter=RecordingArbiter(run.ledger,clock=clock)
    try:
        for i in range(10):
            clock.now=i/60;row=advance(env,s)
            # Explicit synthetic timing, not a benchmark of the fixture.
            row.update(whole_cycle_wall_ms=2.,external_cycle_wall_ms=3.,scheduled_start_lateness_ms=0.)
            if i==1:worker.complete()
        data=json_safe(dict(substeps=s.substeps,intervals=s.interval_records,reset_record=s.reset_record,
            geometry=s.geometry,arbitration_audit=run.arbiter.export(),
            runtime_binding=dict(startup=dict(command=run.ledger._startup),execution_id=run.ledger._execution_id),
            runtime_final=dict(stats=run.stats,physics_index=run.ledger.physics_index,stopped=False,pending=False),
            cycle_summary=dict(completed_controls=10,maximum_cycle_ms=3.,maximum_start_lateness_ms=0.,
                               seconds=10/60,simulated_seconds=10/60)))
        q=dict(configuration='base',controls=10,reference=[5.5,1.,0.,0.,0.],reference_id='ref')
        yield data,q,run.ledger._domain,c
    finally:s.__exit__(None,None,None)


def test_synthetic_raw_actuator_and_arbitration_chain_replayed(execution):
    from workflows.validate_runtime_v57 import validate_execution
    data,q,domain,context=execution
    result=validate_execution(data,q,domain,context,allow_diagnostic=True)
    assert result['physics_steps']==20 and result['arbitration']['activations']==1
    assert max(result['maximum_control_pwm_speed_wrench_errors'])<1e-3


@pytest.mark.parametrize('bad',['missing_substep','missing_ack','ack_index','hold','command','rotor','wrench',
    'time','mass','initial_speed','contact','clearance','domain','cycle','lateness','summary','fake_activation','state_seam'])
def test_raw_or_execution_mutations_are_rejected(execution,bad):
    from workflows.validate_runtime_v57 import validate_execution
    data,q,domain,context=execution;data=copy.deepcopy(data);row=data['substeps'][1]
    if bad=='missing_substep':data['substeps'].pop()
    if bad=='missing_ack':row.pop('execution_ack_v55')
    if bad=='ack_index':row['execution_ack_v55']['receipt']['physics_index']=1
    if bad=='hold':row['execution_command_v55']['command'][0]+=.001
    if bad=='command':row['command']['telemetry']['virtual_control_4'][0][0]+=.001
    if bad=='rotor':row['command']['actuator_speed_n'][0][0]+=1.
    if bad=='wrench':row['command']['telemetry']['applied_wrench_6'][0][0]+=1.
    if bad=='time':row['backend_after_physics']['cache_sim_timestamp_s']+=.01
    if bad=='mass':row['before']['backend']['mass_kg'][0][0]+=1.
    if bad=='initial_speed':data['reset_record']['snapshot']['actuator_speed_n'][0][0]=1.
    if bad=='contact':row['contact_after_physics_v26']['normal_force_world_n'][0][2]=1.
    if bad=='clearance':data['geometry']['minimum_clearance_m']=0.
    if bad=='domain':row['state_after_physics_11'][0][8]=9.
    if bad=='cycle':data['intervals'][0]['external_cycle_wall_ms']=17.
    if bad=='lateness':data['intervals'][0]['scheduled_start_lateness_ms']=15.
    if bad=='summary':data['cycle_summary']['maximum_cycle_ms']=1.
    if bad=='fake_activation':data['runtime_final']['stats']['mpc_activations']+=1
    if bad=='state_seam':row['before']['state_11'][0][0]+=.01
    with pytest.raises((ValueError,AssertionError,KeyError)):
        validate_execution(data,q,domain,context,allow_diagnostic=True)


def test_raw_validator_does_not_admit_diagnostic_support_domain(execution):
    from workflows.validate_runtime_v57 import validate_execution
    data,q,domain,context=execution
    with pytest.raises(ValueError):validate_execution(data,q,domain,context)

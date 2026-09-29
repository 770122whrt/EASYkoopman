"""Reconstruct a feedback-only support failure; never promote a failed run."""
import hashlib
import json
import numpy as np
from workflows.validate_effects_v67 import (same, validate_geometry, check_runtime_context,
    check_state_backend, validate_protocol_flags, validate_timing, contact_screen, domain_screen,
    compare_values, validate_clock_step)
from workflows.validate_tracking_v67 import validate_tracking_audit
from workflows.control_seam_v23 import ControlKernel
from workflows.actuator_replay_v28 import Float32PWMActuatorState
from koopman.execution_ledger_v48 import ResetObservation, BoundaryObservation
from koopman.rate30_v67 import ExecutionLedger


def validate_failure(data, case, domain, context):
    if (data['case'] != case or case['controller'] != 'feedback'
            or data.get('exception') != 'RuntimeError:execution_bridge:actual_state_outside_support'
            or data.get('status') != 'diagnostic_exception' or data['cleanup_errors']
            or not data['cleanup_completed']['environment'] or not data['cleanup_completed']['simulation_app']):
        raise ValueError('failure_not_isolatable')
    validate_protocol_flags(data,case)
    rows, intervals = data['substeps'], data['intervals']
    if not rows or len(rows)>4*case['controls'] or len(intervals)!=(len(rows)+3)//4:
        raise ValueError('failure_counts')
    final=data['runtime_final'];stats=final['stats']
    if (final['physics_index']!=len(rows) or final['stopped'] is not True
            or stats['dispatches']!=len(intervals) or stats['confirmed_controls']!=(len(rows)-1)//4):
        raise ValueError('failure_final_state')
    geometry=data['geometry'];validate_geometry(geometry)
    reset=data['reset_record'];start=reset['snapshot'];check_runtime_context(start,case['configuration'],context)
    same(start['state_11'],[[5.5,1.,0.,0.,0.,0.,0.,0.,0.,0.,0.]],label='reset')
    kernel=ControlKernel(case['configuration']);count=kernel.env._num_thrusters
    same(start['actuator_speed_n'],np.zeros((1,count)),atol=1e-8,label='reset_rotor')
    same(start['_thruster_dynamics_time_s'],[0.],atol=0,label='reset_clock')
    check_state_backend(start['state_11'],start['backend'])
    estimator=Float32PWMActuatorState(count,tau=kernel.tau,dt=1/120,clock='float32_accumulated_v1')
    first=intervals[0]['decision']['packet'];binding=data['runtime_binding']
    observed=ResetObservation(first['episode_id'],first['reset_id'],0,
        np.asarray(start['state_11'])[0],np.asarray(start['actuator_speed_n'])[0])
    ledger=ExecutionLedger(domain,context,observed,reference=case['reference'],reference_id=case['reference_id'],
        startup_command=binding['startup']['command'])
    ledger._execution_id=binding['execution_id']
    ledger._digest=hashlib.sha256(json.dumps(dict(execution_id=ledger._execution_id,
        episode=observed.episode_id,reset=observed.reset_id,binding=ledger._binding),sort_keys=True).encode()).hexdigest()
    maximum=np.zeros(4)
    for j,row in enumerate(rows):
        i=j//4;interval=intervals[i];packet=interval['decision']['packet'];u=np.asarray(packet['command'],dtype=np.float32)
        if j%4==0:
            if interval['physics_index']!=j or packet['source']!='fallback':raise ValueError('failure_interval_binding')
            if i<len(intervals)-1:
                if interval['status']!='completed_interval':raise ValueError('failure_earlier_interval')
                validate_timing(interval,i,case['mode'])
            elif interval['status']!='stopped':raise ValueError('failure_terminal_interval')
            cap=ledger.capture(BoundaryObservation(observed.episode_id,observed.reset_id,j,
                np.asarray(row['before']['state_11'])[0]),case['reference'],reference_id=case['reference_id'])
            ticket=ledger.reserve(cap,u,source='fallback',startup=i==0);ledger.dispatch(ticket)
        before=row['before'];cmd=row['command'];backend=before['backend'];after=row['backend_after_physics']
        issued=row['execution_command_v55'];ack=row['execution_ack_v55']
        if (row['control_index']!=i or row['substep_index']!=j%4 or row['reset_generation']!=[1]
                or issued['physics_index']!=j or issued['backend_step_before']!=reset['backend_step_index']+j+1):
            raise ValueError('failure_physics_sequence')
        same(issued['command'],u,atol=1e-7,label='failure_hold')
        previous=start if j==0 else rows[j-1]['command']
        same(before['state_11'],start['state_11'] if j==0 else rows[j-1]['state_after_physics_11'],label='failure_state_seam')
        same(before['actuator_speed_n'],previous['actuator_speed_n'],label='failure_rotor_seam')
        if j and before['telemetry']['step_token']!=previous['telemetry']['step_token']:raise ValueError('failure_token_seam')
        validate_clock_step([0.] if j==0 else rows[j-1]['actuator_update']['end_time_s'],row['actuator_update']['end_time_s'])
        same(backend['cache_sim_timestamp_s'],start['backend']['cache_sim_timestamp_s'] if j==0 else rows[j-1]['backend_after_physics']['cache_sim_timestamp_s'],atol=1e-7,label='failure_time_seam')
        same(issued['timestamp_before'],backend['cache_sim_timestamp_s'],atol=1e-7,label='failure_issue_time')
        same(after['cache_sim_timestamp_s']-backend['cache_sim_timestamp_s'],1/120,atol=1e-7,label='failure_physics_dt')
        for snapshot in (before,cmd,dict(telemetry=cmd['telemetry'],backend=after)):
            check_runtime_context(snapshot,case['configuration'],context)
        if domain.check_states(np.asarray(before['state_11'])):raise ValueError('failure_earlier_support_violation')
        for x,b in ((before['state_11'],backend),(row['state_after_physics_11'],after)):check_state_backend(x,b)
        rejection=domain.check_states(np.asarray(row['state_after_physics_11']))
        if j<len(rows)-1:
            if rejection or row.get('execution_observation_error_v55') is not None:raise ValueError('failure_earlier_rejection')
        elif rejection!={'reason':'state_out_of_support','index':0} or row.get('execution_observation_error_v55')!='actual_state_outside_support':
            raise ValueError('failure_not_support_only')
        sent=kernel.command(u,pre_tam=True);speed=estimator.advance_pwm(sent['pwm'])
        wrench=kernel.B.numpy()@(kernel.env.cfg.rotor_constant*np.abs(speed)*speed);telemetry=cmd['telemetry']
        errors=[np.max(np.abs(sent['virtual_control']-np.asarray(telemetry['virtual_control_4'])[0])),
            np.max(np.abs(sent['pwm']-np.asarray(telemetry['motor_pwm_n'])[0])),
            np.max(np.abs(speed-np.asarray(cmd['actuator_speed_n'])[0])),
            np.max(np.abs(wrench-np.asarray(telemetry['applied_wrench_6'])[0]))]
        maximum=np.maximum(maximum,errors)
        contact=contact_screen(row,geometry);compare_values(contact,row['free_water_screen_v26'])
        screen=domain_screen(row,geometry,5.5);compare_values(screen,row['calibration_screen_v27'])
        if not contact['screen_pass'] or not screen['screen_pass']:raise ValueError('failure_unsafe_physics')
        receipt=ledger.acknowledge(ticket,u,physics_index=j,episode_id=observed.episode_id,reset_id=observed.reset_id)
        if ack.get('actual_history_advanced') is not True:raise ValueError('failure_missing_actual_history')
        if j<len(rows)-1:
            if ack['status']!='acknowledged' or ack['receipt']!=receipt or not 0<=ack['control_compute_ms']<1000/30:
                raise ValueError('failure_receipt_mismatch')
        elif ack['status']!='stop' or ack['reason']!='runtime_ack_failed:runtime_safety_binding':
            raise ValueError('failure_terminal_ack')
    if not np.isfinite(maximum).all() or np.any(maximum>[1e-6,1e-6,1e-3,1e-3]):raise ValueError('failure_causal_reconstruction')
    feedback=validate_tracking_audit(data,domain,context)
    return dict(status='configuration_support_no_go',physical_steps=len(rows),
        feedback_validation=feedback,maximum_control_pwm_speed_wrench_errors=maximum.tolist(),
        reconstructed_final_history_digest=ledger._digest,control_benefit_claim=False,
        physical_safety_violation=False,complete_episode=False,optimizer_recomputed=False)

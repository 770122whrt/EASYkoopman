"""Raw execution and offline arbitration verification, separate from native exit.

The actuator recurrence is reconstructed independently from actual commands.
Arbitration replay reuses the frozen admission mathematics; it does not claim
an independent optimizer, control improvement, or a hard real-time guarantee.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np

from workflows.collect_runtime_v59 import HANDOFF_SHA, classify_exit, check_simulator_binding
from workflows.phase9_preflight_v59 import authorize_case, cases, proposal, verify_release
from workflows.runtime_assets_v56 import AssetLocation, load_assets
from workflows.runtime_episode_v59 import check_runtime_context
from workflows.runtime_audit_v57 import replay_audit
from workflows.validate_control_trace_v23 import compare_values, validate_clock_step
from workflows.collect_formal_v25 import validate_interval
from workflows.calibration_trace_v27 import domain_screen
from workflows.validate_free_water_v26 import contact_screen


def same(a,b,*,atol=1e-6,label='values'):
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
    if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all() or not np.allclose(a,b,rtol=0,atol=atol):
        raise ValueError('runtime_validation_'+label)


def validate_geometry(geometry):
    same(geometry['body_local_corners_m'],list(itertools.product((-.5,.5),(-.5,.5),(-.25,.25))),atol=1e-7,label='geometry')
    if geometry['minimum_clearance_m']!=.1 or geometry['ground_world_z_m']!=0:
        raise ValueError('runtime_geometry_threshold')


def check_state_backend(state,backend):
    from koopman.projected_edmd_v24 import rotation
    x=np.asarray(state,dtype=float)[0];pose=np.asarray(backend['transform_actor_world_xyzw'],dtype=float)
    velocity=np.asarray(backend['velocity_com_world_6'],dtype=float)
    if pose.shape!=(1,7) or velocity.shape!=(1,6):raise ValueError('runtime_backend_shape')
    same(x[0],pose[0,2],label='backend_depth')
    q=pose[0,[6,3,4,5]]
    if np.dot(x[1:5],q)<0:q=-q
    same(x[1:5],q,label='backend_attitude')
    r=rotation(x[1:5])
    same(x[5:8],r.T@velocity[0,:3],label='backend_body_velocity')
    same(x[8:],r.T@velocity[0,3:],label='backend_body_omega')


def validate_execution(data,q,domain,context,*,allow_diagnostic=False):
    from workflows.control_seam_v23 import ControlKernel
    from workflows.actuator_replay_v28 import Float32PWMActuatorState
    from koopman.execution_ledger_v48 import ResetObservation
    n=q['controls'];rows=data['substeps'];intervals=data['intervals'];reset=data['reset_record']
    if len(rows)!=2*n or len(intervals)!=n:raise ValueError('runtime_execution_count')
    final=data['runtime_final'];stats=final['stats']
    if (final['physics_index']!=2*n or final['stopped'] is not False or final['pending'] is not False
            or stats['dispatches']!=n or stats['confirmed_controls']!=n):raise ValueError('runtime_final_state')
    geom=data['geometry'];validate_geometry(geom);start=reset['snapshot']
    check_runtime_context(start,q['configuration'],context)
    same(start['state_11'],[[5.5,1.,0.,0.,0.,0.,0.,0.,0.,0.,0.]],label='initial_state')
    kernel=ControlKernel(q['configuration']);count=kernel.env._num_thrusters
    same(start['actuator_speed_n'],np.zeros((1,count)),atol=1e-8,label='initial_rotor')
    same(start['_thruster_dynamics_time_s'],[0.],atol=0,label='initial_clock')
    check_state_backend(start['state_11'],start['backend'])
    estimator=Float32PWMActuatorState(count,tau=kernel.tau,dt=1/120,clock='float32_accumulated_v1')
    maximum=np.zeros(4);screens=[];times=[];latenesses=[];records=[];receipts=[]
    for i,interval in enumerate(intervals):
        if interval['status']!='completed_interval' or interval['physics_index']!=2*i:
            raise ValueError('runtime_interval_completion')
        dt=interval['external_cycle_wall_ms'];late=interval['scheduled_start_lateness_ms'];inner=interval['whole_cycle_wall_ms']
        if (not np.isfinite([dt,late,inner]).all() or min(dt,late,inner)<0
                or inner>dt+1e-6 or dt+late>1000/60):raise ValueError('runtime_full_cycle_deadline')
        times.append(dt);latenesses.append(late)
        decision=interval['decision'];p=decision['packet']
        if not 0<=decision['decision_compute_ms']<1000/60:raise ValueError('runtime_decision_time')
        u=np.asarray(p['command'],dtype=np.float32)
        if u.shape!=(4,) or not np.isfinite(u).all():raise ValueError('runtime_packet_command')
        pair=rows[2*i:2*i+2];validate_interval(pair,configuration=q['configuration'])
        records.append(dict(physics_index=2*i,decision=decision,state=pair[0]['before']['state_11'][0]))
        for j,row in enumerate(pair,start=2*i):
            before=row['before'];cmd=row['command'];b=before['backend'];after=row['backend_after_physics']
            issued=row['execution_command_v55'];ack=row['execution_ack_v55'];r=ack['receipt']
            if (row['control_index']!=i or row['reset_generation']!=[1] or issued['physics_index']!=j
                    or issued['backend_step_before']!=reset['backend_step_index']+j+1
                    or ack['status']!='acknowledged' or ack['actual_history_advanced'] is not True
                    or r['physics_index']!=j+1 or r['interval_complete'] is not (j%2==1)
                    or r['startup_consumed'] is not True or row.get('execution_observation_error_v55') is not None):
                raise ValueError('runtime_substep_receipt')
            if not 0<=ack['control_compute_ms']<1000/60:raise ValueError('runtime_ack_time')
            same(issued['command'],u,atol=1e-7,label='actual_hold')
            previous=start if j==0 else rows[j-1]['command']
            old_state=start['state_11'] if j==0 else rows[j-1]['state_after_physics_11']
            same(before['state_11'],old_state,label='state_seam')
            same(before['actuator_speed_n'],previous['actuator_speed_n'],label='rotor_seam')
            if j and before['telemetry']['step_token']!=previous['telemetry']['step_token']:
                raise ValueError('runtime_token_seam')
            old_time=[0.] if j==0 else rows[j-1]['actuator_update']['end_time_s']
            validate_clock_step(old_time,row['actuator_update']['end_time_s'])
            previous_stamp=start['backend']['cache_sim_timestamp_s'] if j==0 else rows[j-1]['backend_after_physics']['cache_sim_timestamp_s']
            same(b['cache_sim_timestamp_s'],previous_stamp,atol=1e-7,label='physics_time_seam')
            same(issued['timestamp_before'],b['cache_sim_timestamp_s'],atol=1e-7,label='issue_time')
            same(after['cache_sim_timestamp_s']-b['cache_sim_timestamp_s'],1/120,atol=1e-7,label='physics_tick')
            for snap in (before,cmd,dict(telemetry=cmd['telemetry'],backend=after)):
                check_runtime_context(snap,q['configuration'],context)
            for x,backend in ((before['state_11'],b),(row['state_after_physics_11'],after)):
                if domain.check_states(np.asarray(x)):raise ValueError('runtime_actual_state_support')
                check_state_backend(x,backend)
            sent=kernel.command(u,pre_tam=True);speed=estimator.advance_pwm(sent['pwm'])
            wrench=kernel.B.numpy()@(kernel.env.cfg.rotor_constant*np.abs(speed)*speed)
            t=cmd['telemetry']
            errors=[np.max(np.abs(sent['virtual_control']-np.asarray(t['virtual_control_4'])[0])),
                np.max(np.abs(sent['pwm']-np.asarray(t['motor_pwm_n'])[0])),
                np.max(np.abs(speed-np.asarray(cmd['actuator_speed_n'])[0])),
                np.max(np.abs(wrench-np.asarray(t['applied_wrench_6'])[0]))]
            maximum=np.maximum(maximum,errors)
            base=contact_screen(row,geom);compare_values(base,row['free_water_screen_v26'])
            screen=domain_screen(row,geom,5.5);compare_values(screen,row['calibration_screen_v27'])
            if not screen['screen_pass']:raise ValueError('runtime_unsafe_actual_physics')
            screens.append(screen)
        receipts.append(pair[-1]['execution_ack_v55']['receipt']['history_digest'])
    if not np.isfinite(maximum).all() or np.any(maximum>[1e-6,1e-6,1e-3,1e-3]):
        raise ValueError('runtime_causal_input_reconstruction')
    summary=data['cycle_summary']
    if summary['completed_controls']!=n:raise ValueError('runtime_summary_count')
    same(summary['maximum_cycle_ms'],max(times),atol=1e-9,label='cycle_summary')
    same(summary['maximum_start_lateness_ms'],max(latenesses),atol=1e-9,label='lateness_summary')
    same(summary['simulated_seconds'],n/60,atol=1e-12,label='simulated_time')
    if not np.isfinite(summary['seconds']) or not (n-1)/60<=summary['seconds']<=180:
        raise ValueError('runtime_episode_time')
    p=intervals[0]['decision']['packet']
    observed=ResetObservation(p['episode_id'],p['reset_id'],0,np.asarray(start['state_11'])[0],np.asarray(start['actuator_speed_n'])[0])
    binding=data['runtime_binding']
    audit=replay_audit(dict(audit=data['arbitration_audit'],intervals=records,receipts=receipts,
        execution_id=binding['execution_id'],startup=binding['startup']['command'],activations=stats['mpc_activations']),
        observed,domain,context,reference=q['reference'],reference_id=q['reference_id'],allow_diagnostic=allow_diagnostic)
    for row,digest in zip(rows,audit['physics_history_digests']):
        if row['execution_ack_v55']['receipt']['history_digest']!=digest:raise ValueError('runtime_substep_history_digest')
    return dict(physics_steps=len(rows),maximum_control_pwm_speed_wrench_errors=maximum.tolist(),arbitration=audit,
        maximum_cycle_ms=max(times),minimum_clearance_m=min(s['minimum_hull_clearance_m'] for s in screens),
        measured_run_only=True,control_benefit_claim=False,training_eligible=False)


def validate_trace(data,q,release_root,approval,*,native_exit):
    binding=authorize_case(release_root,q,approval);release=verify_release(release_root)
    if classify_exit(native_exit,data,q,binding['release_sha256']):raise ValueError('runtime_native_or_report_rejected')
    if (data['schema']!='phase9-runtime-trace-v59' or data['protocol']!=proposal()
            or data['protocol_sha256']!=binding['protocol_sha256']):raise ValueError('runtime_protocol')
    check_simulator_binding(data,release)
    loaded=data['loaded_project_sources']
    required=('workflows.collect_runtime_v59','workflows.runtime_episode_v59','workflows.runtime_audit_v57',
              'workflows.isaac_execution_v55','koopman.plan_continuity_v54','koopman.runtime_coordinator_v52')
    if not set(required)<=loaded.keys():raise ValueError('runtime_loaded_sources_missing')
    for item in loaded.values():
        if release['manifest']['files_sha256'].get(item['relative_path'])!=item['sha256']:
            raise ValueError('runtime_loaded_source_hash')
    expected=dict(starting_depth=5.5,ground_plane_mode='grid',control_input_mode='direct_pre_tam_v24',
        control_history_reset_mode='episode_local_v1',inertia_sync_mode='declared_v1',
        physics_initialization_mode='authored_static_v1',initial_embodiment_type=q['configuration'])
    if data['effective_cfg']!=expected:raise ValueError('runtime_effective_configuration')
    geom=data['geometry']
    if geom['meters_per_unit']!=1 or geom['initial_clearance_m']<.1:raise ValueError('runtime_geometry_units')
    authored=data['contact_authoring']
    if len(authored)!=1 or authored[0]['body_path']!=geom['body_path']:raise ValueError('runtime_contact_authoring')
    non_report=lambda d:{k:v for k,v in d.items() if not k.startswith('physxContactReport:')}
    if non_report(authored[0]['before'])!=non_report(authored[0]['after']):raise ValueError('runtime_contact_changed_physics')
    resets=[e for e in data['events'] if e['kind']=='reset'];dones=[e for e in data['events'] if e['kind']=='dones']
    if len(resets)!=1 or resets[0]['reset_generation']!=[1] or len(dones)!=q['controls']:
        raise ValueError('runtime_reset_or_done_count')
    for i,d in enumerate(dones):
        if d['control_index']!=i or d['reset_generation']!=[1] or d['result']!=[[False],[False]]:
            raise ValueError('runtime_unexpected_done')
    assets=load_assets(AssetLocation(str(Path(release_root).resolve()),'.','assets/v38/inputs',HANDOFF_SHA),model_key=q['model_key'])
    domain=assets.domains[q['configuration']];context=assets.context(q['configuration'])
    if data['assets']!=dict(model_key=q['model_key'],model_sha256=assets.model_sha256,handoff_sha256=HANDOFF_SHA,support_id=domain.identity):
        raise ValueError('runtime_assets_binding')
    b=data['runtime_binding']
    if b['model_id']!=domain.model_id or b['support_id']!=domain.identity:raise ValueError('runtime_model_binding')
    compare_values(check_runtime_context(data['reset_record']['snapshot'],q['configuration'],context),b['context_audit'],atol=1e-12)
    p=data['intervals'][0]['decision']['packet']
    if p['episode_id']!=q['case_id'] or p['reset_id']!=q['case_id']+':reset1':raise ValueError('runtime_episode_binding')
    result=validate_execution(data,q,domain,context)
    return dict(status='runtime_interface_preflight_passed',request=q,**binding,**result)


def main():
    p=argparse.ArgumentParser();p.add_argument('--release-root',type=Path,required=True)
    p.add_argument('--approval',type=Path,required=True);p.add_argument('--case',required=True)
    p.add_argument('--native-exit',type=int,required=True);args=p.parse_args()
    q=next(q for q in cases() if q['case_id']==args.case)
    folder=args.release_root/'results'/q['case_id'];path=folder/'trace.json'
    result=validate_trace(json.loads(path.read_text(encoding='utf8')),q,args.release_root,
        json.loads(args.approval.read_text(encoding='utf8')),native_exit=args.native_exit)
    result['trace_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    with (folder/'acceptance.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2,allow_nan=False)
    return 0


if __name__=='__main__':raise SystemExit(main())

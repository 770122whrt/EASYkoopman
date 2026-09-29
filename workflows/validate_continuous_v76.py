"""Independent raw-physics and planned-sequence replay; never rerun optimization."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from workflows.runtime_assets_v56 import AssetLocation,load_assets,read
from workflows.runtime_episode_v59 import check_runtime_context
from workflows.validate_effects_v67 import same,validate_interval,check_state_backend
from workflows.validate_control_trace_v23 import validate_clock_step
from workflows.calibration_trace_v27 import domain_screen
from workflows.geometry_v76 import ground_top
from workflows.control_seam_v23 import ControlKernel
from workflows.actuator_replay_v28 import Float32PWMActuatorState
from koopman.command_state_v39 import CausalCommandState
from koopman.control_objective_v44 import tracking_terms,control_mask,trajectory_cost,ObjectiveWeights
from koopman.prepared_projected_v40 import prepare_projected
from koopman.physical_control_v76 import PhysicalPredictor
from workflows.identify_sparse_world_v30 import from_record
from workflows.feedback_inverse_v28 import MINIMUM_DEADZONE_DISTANCE


def validate(data,assets,native_exit):
    if native_exit!=0 or data['status']!='completed_pending_independent_acceptance':raise ValueError('native_or_status')
    if (data['cleanup_errors'] or not data['cleanup_completed']['environment'] or
            not data['cleanup_completed']['simulation_app'] or not data['native_alias_release']['robot_released']):
        raise ValueError('native_cleanup')
    if data['model_fits']!=0 or data['real_time_qualified'] is not False:raise ValueError('scope')
    q=data['case'];cfg=q['configuration'];c=assets.context(cfg);d=assets.domains[cfg]
    if data['model']['frozen_parameter_source_sha256']!=assets.model_sha256 or data['model']['common_support_id']!=d.identity:
        raise ValueError('model_binding')
    rows=data['substeps'];intervals=data['intervals'];start=data['reset_record']['snapshot'];n=60
    if len(rows)!=4*n or len(intervals)!=n or q['controls']!=n:raise ValueError('count')
    if data['stats']['confirmed_controls']!=n or data['stats']['dispatches']!=n:raise ValueError('receipt_count')
    same(start['state_11'],[[5.5,1,0,0,0,0,0,0,0,0,0]],label='reset')
    same(start['actuator_speed_n'],np.zeros_like(start['actuator_speed_n']),atol=1e-8,label='rotor_reset')
    same(start['_thruster_dynamics_time_s'],[0.],atol=0,label='clock_reset')
    geom=data['geometry'];same(ground_top(geom['ground_world_corners_m']),geom['ground_world_z_m'],atol=1e-8)
    if geom['minimum_clearance_m']!=.1:raise ValueError('clearance_threshold')
    first=intervals[0]['decision']['packet'];episode=first['episode_id'];reset=first['reset_id']
    binding=(cfg,d.context_key,d.model_id,d.identity)
    digest=hashlib.sha256(json.dumps(dict(execution_id=first['execution_id'],episode=episode,reset=reset,binding=binding),sort_keys=True).encode()).hexdigest()
    kernel=ControlKernel(cfg);est=Float32PWMActuatorState(kernel.env._num_thrusters,tau=kernel.tau,dt=1/120,clock='float32_accumulated_v1')
    live=CausalCommandState(cfg,c,episode_id=episode,zero_rotor_reset_verified=True)
    fitted=from_record(read(assets.model_path))
    predictor=(PhysicalPredictor(fitted,c) if q['controller']=='nominal_physics' else prepare_projected(fitted,c))
    audits={r['physics_index']:r for r in data['solve_audit']}
    if q['controller']=='feedback':
        if audits or data['stats']['requests'] or data['stats']['mpc_activations']:raise ValueError('feedback_contaminated')
    elif set(audits)!=set(range(4,240,4)):raise ValueError('solve_count')
    maximum=np.zeros(4);clearances=[];planned_max=0.;previous=None
    for i,interval in enumerate(intervals):
        if interval['status']!='completed_interval' or interval['physics_index']!=4*i:raise ValueError('interval')
        packet=interval['decision']['packet'];u=np.asarray(packet['command'],dtype=np.float32)
        expected_source='fallback' if i==0 or q['controller']=='feedback' else 'mpc'
        if packet['source']!=expected_source:raise ValueError('controller_arm_source')
        if packet['episode_id']!=episode or packet['reset_id']!=reset or packet['execution_id']!=first['execution_id']:
            raise ValueError('packet_binding')
        if (np.any(u<d.command_lower-1e-7) or np.any(u>d.command_upper+1e-7)
                or np.any(np.abs(u*(1-control_mask(cfg)))>1e-7)
                or previous is not None and np.max(np.abs(u-previous))>.0200001):raise ValueError('command_constraints')
        if i==0 and not packet['startup_exception']:raise ValueError('startup')
        if i>0 and packet['startup_exception']:raise ValueError('startup_reuse')
        if i and q['controller']!='feedback':
            audit=audits[4*i];seq=np.asarray(audit['commands'],dtype=np.float32)
            if not audit['exact_feasible'] or seq.shape!=(10,4):raise ValueError('planned_sequence')
            same(seq[0],u,atol=1e-7,label='first_plan_action')
            if (np.any(seq<d.command_lower-1e-7) or np.any(seq>d.command_upper+1e-7)
                    or np.any(np.abs(seq*(1-control_mask(cfg)))>1e-7)
                    or np.max(np.abs(np.diff(np.vstack([previous,seq]),axis=0)))>.0200001):raise ValueError('planned_bounds')
            for v in seq:
                raw=kernel.command(v,pre_tam=True)['pwm_raw']
                if np.max(np.abs(raw))>.9500001 or np.min(np.abs(np.abs(raw)-float(np.float32(.02))))<=MINIMUM_DEADZONE_DISTANCE:
                    raise ValueError('planned_pwm')
            origin=live.snapshot(configuration=cfg,context=c,origin_control=2*i,episode_id=episode)
            initial=np.asarray(rows[4*i]['before']['state_11'][0]);micro=np.repeat(seq,2,axis=0)
            forecast=origin.forecast(initial,micro,predictor)
            if not forecast['complete'] or d.check_states(forecast['predictions']):raise ValueError('plan_prediction_support')
            same(forecast['predictions'],audit['predictions'],atol=1e-10,label='independent_plan_replay')
            cost=trajectory_cost(forecast['predictions'],micro,previous,q['reference'],control_mask(cfg),ObjectiveWeights())
            same(cost,audit['cost'],atol=1e-10,label='plan_cost')
            planned_max=max(planned_max,float(np.max(np.abs(forecast['predictions']-audit['predictions']))))
        pair=rows[4*i:4*i+4];validate_interval(pair,configuration=cfg)
        for j,row in enumerate(pair,start=4*i):
            before=row['before'];cmd=row['command'];b=before['backend'];after=row['backend_after_physics']
            ack=row['execution_ack_v55'];receipt=ack['receipt'];issued=row['execution_command_v55']
            if (ack['status']!='acknowledged' or not ack['actual_history_advanced'] or receipt['physics_index']!=j+1
                or receipt['interval_complete']!=(j%4==3) or issued['physics_index']!=j
                or row['reset_generation']!=[1] or row.get('execution_observation_error_v55')):raise ValueError('receipt')
            same(issued['command'],u,atol=1e-7,label='issued')
            oldstate=start['state_11'] if j==0 else rows[j-1]['state_after_physics_11']
            oldspeed=start['actuator_speed_n'] if j==0 else rows[j-1]['command']['actuator_speed_n']
            same(before['state_11'],oldstate,label='state_seam');same(before['actuator_speed_n'],oldspeed,label='rotor_seam')
            validate_clock_step([0.] if j==0 else rows[j-1]['actuator_update']['end_time_s'],row['actuator_update']['end_time_s'])
            same(after['cache_sim_timestamp_s']-b['cache_sim_timestamp_s'],1/120,atol=1e-7,label='clock')
            for snap in (before,cmd,dict(telemetry=cmd['telemetry'],backend=after)):check_runtime_context(snap,cfg,c)
            for x,backend in ((before['state_11'],b),(row['state_after_physics_11'],after)):
                if d.check_states(np.asarray(x)):raise ValueError('actual_support')
                check_state_backend(x,backend)
            sent=kernel.command(u,pre_tam=True);speed=est.advance_pwm(sent['pwm'])
            wrench=kernel.B.numpy()@(kernel.env.cfg.rotor_constant*np.abs(speed)*speed);t=cmd['telemetry']
            maximum=np.maximum(maximum,[np.max(np.abs(sent['virtual_control']-np.asarray(t['virtual_control_4'])[0])),
                np.max(np.abs(sent['pwm']-np.asarray(t['motor_pwm_n'])[0])),np.max(np.abs(speed-np.asarray(cmd['actuator_speed_n'])[0])),
                np.max(np.abs(wrench-np.asarray(t['applied_wrench_6'])[0]))])
            screen=domain_screen(row,geom,5.5)
            if not screen['screen_pass']:raise ValueError('actual_safety')
            clearances.append(screen['minimum_hull_clearance_m'])
            live.record_issued(u,physics_index=j,episode_id=episode)
            digest=hashlib.sha256(bytes.fromhex(digest)+j.to_bytes(8,'little')+u.tobytes()).hexdigest()
            if receipt['history_digest']!=digest:raise ValueError('history_digest')
        previous=u
    if np.any(maximum>[1e-6,1e-6,1e-3,1e-3]):raise ValueError('causal_input_reconstruction')
    x=np.asarray([r['state_after_physics_11'][0] for r in rows]);terms=tracking_terms(x,q['reference'],control_mask(cfg))
    score=float(np.mean(terms['depth']/.02**2+terms['attitude']/.04**2))
    same(score,data['metrics']['normalized_tracking_score'],atol=1e-12,label='metric')
    return dict(status='accepted_bounded_simulation_time_closed_loop',physics_steps=240,
        replay_max_errors=maximum.tolist(),plan_replay_max_error=planned_max,
        min_clearance_m=min(clearances),normalized_tracking_score=score,case=q,
        real_time_qualified=False,training_eligible=False)


def main():
    p=argparse.ArgumentParser();p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--assets',required=True);p.add_argument('--native-exit',type=int,required=True)
    a=p.parse_args();assets=load_assets(AssetLocation(a.assets,'.','assets/v38/inputs',
        '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    result=validate(json.loads(gzip.decompress(a.trace.read_bytes())),assets,a.native_exit)
    result['trace_sha256']=hashlib.sha256(a.trace.read_bytes()).hexdigest()
    with a.trace.with_name('acceptance.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result))


if __name__=='__main__':main()

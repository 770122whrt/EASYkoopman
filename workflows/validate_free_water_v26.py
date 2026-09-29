"""Offline/online semantic acceptance, kept separate from collector exit codes."""
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
from workflows.free_water_microtrace_v26 import cases,validate_case,EXPERIMENT
from workflows.free_water_v26 import screen_step
from workflows.free_water_runtime_v26 import step_clearance
from workflows.validate_control_trace_v23 import compare_values,validate_clock_step
from workflows.collect_formal_v25 import validate_interval
from workflows.validate_formal_trace_v25 import DIRECT_RL_SHA

ASSET_SHA='40148fbe201b993448d2dfbac118ef48acdb71641c1ed88caa2b6168b9ae146d'


def contact_screen(row,geometry):
    c=row['contact_after_physics_v26'];f=np.asarray(c['normal_force_world_n'],dtype=float)
    if (c['body_paths']!=[geometry['body_path']] or f.shape!=(1,3) or not np.isfinite(f).all()
            or c['physics_dt_s']!=row['physics_dt_s']
            or c['sample_timestamp_s']!=row['backend_after_physics']['cache_sim_timestamp_s']):
        raise ValueError('free_water_contact_binding')
    result=screen_step(row);margin=step_clearance(row,geometry)
    result['minimum_hull_clearance_m']=margin
    if margin<geometry['minimum_clearance_m']:
        result['reasons'].append('hull_clearance_below_minimum');result['screen_pass']=False
    result['direct_contact_observed']=bool(np.any(f))
    if np.any(f):result['reasons'].append('measured_normal_contact');result['screen_pass']=False
    return result


def validate_trace(data,q,source,root):
    validate_case(q);root=Path(root)
    if data.get('status')!='completed_free_water_diagnostic_pending_acceptance':raise ValueError('free_water_trace_status')
    if (data['request']!=q or data['experiment']!=EXPERIMENT or data['source_commit']!=source
            or data['training_eligible'] is not False or data['model_fits']!=0):raise ValueError('free_water_trace_identity')
    rows=data['substeps'];boundaries=data['boundary_states'];n=q['intervals']
    if len(rows)!=2*n or len(boundaries)!=n:raise ValueError('free_water_trace_count')
    cfg=data['effective_cfg']
    expected={'starting_depth':q['starting_z_m'],'ground_plane_mode':'grid',
        'control_input_mode':'direct_pre_tam_v24','control_history_reset_mode':'episode_local_v1',
        'inertia_sync_mode':'declared_v1','physics_initialization_mode':'authored_static_v1',
        'initial_embodiment_type':q['configuration']}
    if cfg!=expected:raise ValueError('free_water_cfg')
    src=data['loaded_sources']
    if (src['EasyUUVEnv']['sha256']!=hashlib.sha256((root/'easyuuv_nc/env/easyuuv_env.py').read_bytes()).hexdigest()
            or src['DirectRLEnv']['sha256']!=DIRECT_RL_SHA or data['asset_sha256']!=ASSET_SHA):raise ValueError('free_water_source_binding')
    provenance=data['runtime_provenance']
    if provenance['actual_isaac_sim']!='5.0' or provenance['actual_isaac_lab']!='2.2.1':raise ValueError('free_water_runtime_version')
    provenance=provenance['runtime_provenance']
    if (provenance['isaac_lab_repo_commit']!='c91a125c73c8b574878419a9583afc0b63b99f0a'
            or provenance['isaac_lab_repo_patch_sha256']!='d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079'):
        raise ValueError('free_water_runtime_source')
    geom=data['geometry'];expected_points=list(itertools.product((-.5,.5),(-.5,.5),(-.25,.25)))
    np.testing.assert_allclose(geom['body_local_corners_m'],expected_points,rtol=0,atol=1e-7)
    if geom['ground_world_z_m']!=0 or geom['minimum_clearance_m']!=.1 or geom['meters_per_unit']!=1:
        raise ValueError('free_water_geometry')
    start=data['observed_start_boundary'];compare_values(start['state_11'][0],[q['starting_z_m'],1,0,0,0,0,0,0,0,0,0])
    if np.any(start['actuator_speed_n']):raise ValueError('free_water_actuator_initialization')
    from workflows.control_seam_v23 import ControlKernel
    from workflows.pilot_control_v24 import commands
    from easyuuv_nc.control import ActuatorState
    from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS
    kernel=ControlKernel(q['configuration']);estimator=ActuatorState(kernel.env._num_thrusters,tau=kernel.tau,dt=1/120,clock='float32_accumulated_v1')
    actions=commands(q)
    if data['commands_sha256']!=hashlib.sha256(actions.tobytes()).hexdigest():raise ValueError('free_water_commands')
    maximum=np.zeros(4);screens=[]
    for i in range(n):
        pair=rows[2*i:2*i+2];validate_interval(pair,configuration=q['configuration'])
        compare_values(pair[-1]['state_after_physics_11'],boundaries[i]['state_11'])
    for j,row in enumerate(rows):
        if row['reset_generation']!=[1] or row['control_index']!=j//2:raise ValueError('free_water_reset_index')
        previous=start if j==0 else rows[j-1]['command']
        prior_state=start['state_11'] if j==0 else rows[j-1]['state_after_physics_11']
        compare_values(prior_state,row['before']['state_11']);compare_values(previous['actuator_speed_n'],row['before']['actuator_speed_n'])
        validate_clock_step([0] if j==0 else rows[j-1]['actuator_update']['end_time_s'],row['actuator_update']['end_time_s'])
        backend=row['before']['backend'];declared=np.asarray(row['before']['telemetry']['mass_kg'],dtype=np.float32)
        inverse=np.asarray(backend['inverse_mass_per_kg'],dtype=np.float32)
        if not np.array_equal(inverse,np.float32(1)/declared):raise ValueError('free_water_mass')
        mass=EMBODIMENT_CONFIGS[q['configuration']]['mass']
        np.testing.assert_allclose(declared,mass,rtol=0,atol=1e-5)
        np.testing.assert_allclose(np.asarray(backend['inertia_9']).reshape(3,3).diagonal(),EMBODIMENT_CONFIGS[q['configuration']]['inertia_tensors'],rtol=0,atol=1e-6)
        sent=kernel.command(actions[j//2],pre_tam=True);speed=estimator.advance_pwm(sent['pwm'])
        wrench=kernel.B.numpy()@(kernel.env.cfg.rotor_constant*np.abs(speed)*speed)
        command=row['command'];t=command['telemetry']
        maximum=np.maximum(maximum,[np.max(np.abs(sent['virtual_control']-np.asarray(t['virtual_control_4'])[0])),
            np.max(np.abs(sent['pwm']-np.asarray(t['motor_pwm_n'])[0])),
            np.max(np.abs(speed-np.asarray(command['actuator_speed_n'])[0])),
            np.max(np.abs(wrench-np.asarray(t['applied_wrench_6'])[0]))])
        before_time=backend['cache_sim_timestamp_s'];after_time=row['backend_after_physics']['cache_sim_timestamp_s']
        if not np.isclose(after_time-before_time,1/120,rtol=0,atol=1e-12):raise ValueError('free_water_physics_sample_time')
        if q['contact_observer']:
            result=contact_screen(row,geom);compare_values(result,row['free_water_screen_v26'])
        else:
            if 'contact_after_physics_v26' in row:raise ValueError('free_water_off_observer')
            result=screen_step(row);result['minimum_hull_clearance_m']=step_clearance(row,geom)
        screens.append(result)
    if np.any(maximum>[1e-6,1e-6,1e-3,1e-3]):raise ValueError('free_water_causal_input')
    rejected=[j for j,s in enumerate(screens) if not s['screen_pass']]
    if q['stop_on_rejection'] and rejected:raise ValueError('free_water_high_altitude_rejected')
    contacts=[j for j,s in enumerate(screens) if s['direct_contact_observed'] is True]
    impulses=[j for j,s in enumerate(screens) if 'unexplained_linear_impulse' in s['reasons']]
    return {'status':'diagnostic_semantics_passed_not_training_data','run_id':q['run_id'],'source_commit':source,
        'physics_ticks':len(rows),'contact_ticks':len(contacts),'first_contact_index':contacts[0] if contacts else None,
        'impulse_ticks':len(impulses),'first_impulse_index':impulses[0] if impulses else None,
        'rejected_ticks':len(rejected),'minimum_hull_clearance_m':min(s['minimum_hull_clearance_m'] for s in screens),
        'maximum_velocity_balance_residual_m_s':max(s['max_abs_velocity_residual_m_s'] for s in screens),
        'maximum_control_pwm_speed_wrench_errors':maximum.tolist(),'model_handoff':False,'training_eligible':False}


def compare_pair(low,high):
    q1=low['request'];q2=high['request']
    if (q1['configuration']!=q2['configuration'] or q1['seed']!=q2['seed'] or q1['intervals']!=q2['intervals']
            or low['commands_sha256']!=high['commands_sha256'] or low['asset_sha256']!=high['asset_sha256']):
        raise ValueError('free_water_pair_identity')
    contacts=[j for j,r in enumerate(low['substeps']) if r.get('free_water_screen_v26',{}).get('direct_contact_observed')]
    end=contacts[0] if contacts else len(low['substeps'])
    # A contact's first post-state is excluded from the precontact comparison.
    errors=[];height_errors=[];offset=q2['starting_z_m']-q1['starting_z_m']
    for a,b in zip(low['substeps'][:end],high['substeps'][:end]):
        x=np.asarray(a['state_after_physics_11'])[0];y=np.asarray(b['state_after_physics_11'])[0]
        errors.append(np.abs(x[1:]-y[1:]));height_errors.append(abs((y[0]-x[0])-offset))
        compare_values(a['command']['telemetry'],b['command']['telemetry'])
    if not errors:raise ValueError('free_water_pair_no_precontact_window')
    maximum=np.max(errors,axis=0);height=float(max(height_errors))
    equal=bool(np.max(maximum)<=1e-6 and height<=1e-5)
    if q1['configuration']=='base' and not equal:raise ValueError('free_water_observer_changes_trajectory')
    return {'configuration':q1['configuration'],'precontact_physics_ticks':end,
            'maximum_quaternion_body_velocity_difference':maximum.tolist(),'maximum_height_offset_error_m':height,
            'precontact_equivalent_within_fixed_tolerances':equal,'low_contact_observed':bool(contacts),
            'limits':'Matched measured states; no model comparison or prediction promotion.'}

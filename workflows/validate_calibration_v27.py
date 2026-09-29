"""Offline/online semantic acceptance, kept separate from collector exit codes."""
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
from workflows.workpoint_v27 import cases,validate_case,EXPERIMENT,commands,validate_calibration
from workflows.calibration_trace_v27 import domain_screen,tail_gate,LIMITS,TAIL_LIMITS
from workflows.free_water_v26 import screen_step
from workflows.free_water_runtime_v26 import step_clearance
from workflows.validate_control_trace_v23 import compare_values,validate_clock_step
from workflows.collect_formal_v25 import validate_interval
from workflows.validate_formal_trace_v25 import DIRECT_RL_SHA

ASSET_SHA='40148fbe201b993448d2dfbac118ef48acdb71641c1ed88caa2b6168b9ae146d'


from workflows.validate_free_water_v26 import contact_screen

def validate_trace(data,q,source,root):
    validate_case(q);root=Path(root)
    if data.get('status')!='completed_calibration_pending_acceptance':raise ValueError('calibration_trace_status')
    if (data['request']!=q or data['experiment']!=EXPERIMENT or data['source_commit']!=source
            or data['training_eligible'] is not False or data['model_fits']!=0):raise ValueError('free_water_trace_identity')
    rows=data['substeps'];boundaries=data['boundary_states'];n=q['intervals']
    if len(rows)!=2*n or len(boundaries)!=n:raise ValueError('free_water_trace_count')
    if data['motion_limits']!=LIMITS or data['tail_limits']!=TAIL_LIMITS:
        raise ValueError('calibration_limit_binding')
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
    from easyuuv_nc.control import ActuatorState
    from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS
    kernel=ControlKernel(q['configuration']);estimator=ActuatorState(kernel.env._num_thrusters,tau=kernel.tau,dt=1/120,clock='float32_accumulated_v1')
    validate_calibration(data['calibration'])
    mechanics=data['calibration']['mechanics']
    actions=commands(q,data['calibration'])
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
        for snapshot in (row['before'],row['command']):
            t=snapshot['telemetry']
            compare_values(t['volume_m3'],[[mechanics['volume_m3']]])
            compare_values(t['com_to_cob_offset_m'],[mechanics['cob_m']])
            compare_values(t['water_density_kg_m3'],mechanics['water_density_kg_m3'])
            compare_values(snapshot['backend']['gravity_world_m_s2'],[0,0,-mechanics['gravity_m_s2']])
        sent=kernel.command(actions[j//2],pre_tam=True);speed=estimator.advance_pwm(sent['pwm'])
        wrench=kernel.B.numpy()@(kernel.env.cfg.rotor_constant*np.abs(speed)*speed)
        command=row['command'];t=command['telemetry']
        maximum=np.maximum(maximum,[np.max(np.abs(sent['virtual_control']-np.asarray(t['virtual_control_4'])[0])),
            np.max(np.abs(sent['pwm']-np.asarray(t['motor_pwm_n'])[0])),
            np.max(np.abs(speed-np.asarray(command['actuator_speed_n'])[0])),
            np.max(np.abs(wrench-np.asarray(t['applied_wrench_6'])[0]))])
        before_time=backend['cache_sim_timestamp_s'];after_time=row['backend_after_physics']['cache_sim_timestamp_s']
        if not np.isclose(after_time-before_time,1/120,rtol=0,atol=1e-12):raise ValueError('free_water_physics_sample_time')
        base=contact_screen(row,geom);compare_values(base,row['free_water_screen_v26'])
        result=domain_screen(row,geom,q['starting_z_m']);compare_values(result,row['calibration_screen_v27'])
        screens.append(result)
    if np.any(maximum>[1e-6,1e-6,1e-3,1e-3]):raise ValueError('free_water_causal_input')
    rejected=[j for j,s in enumerate(screens) if not s['screen_pass']]
    if rejected:raise ValueError('free_water_high_altitude_rejected')
    contacts=[j for j,s in enumerate(screens) if s['direct_contact_observed'] is True]
    impulses=[j for j,s in enumerate(screens) if 'unexplained_linear_impulse' in s['reasons']]
    return {'status':'calibration_semantics_passed_not_training_data','run_id':q['run_id'],'source_commit':source,
        'physics_ticks':len(rows),'contact_ticks':len(contacts),'first_contact_index':contacts[0] if contacts else None,
        'impulse_ticks':len(impulses),'first_impulse_index':impulses[0] if impulses else None,
        'rejected_ticks':len(rejected),'minimum_hull_clearance_m':min(s['minimum_hull_clearance_m'] for s in screens),
        'maximum_velocity_balance_residual_m_s':max(s['max_abs_velocity_residual_m_s'] for s in screens),
        'maximum_control_pwm_speed_wrench_errors':maximum.tolist(),
        'maximum_motion':{k:max(s['motion_metrics'][k] for s in screens) for k in screens[0]['motion_metrics']},
        'tail':tail_gate(rows),'model_handoff':False,'training_eligible':False}


def rejected_trace(data,q,source):
    """A failed bounded run remains rejected; only verify its stop cause here.

    This does NOT validate a partial prefix as usable data or admit excitation.
    Unknown crashes abort the batch instead of silently skipping a configuration.
    """
    allowed=('ValueError:calibration_motion_rejected:', 'ValueError:free_water_screen_rejected:')
    if (data.get('status')!='failed_calibration'
            or not str(data.get('exception','')).startswith(allowed)
            or data.get('request')!=q or data.get('source_commit')!=source
            or data.get('training_eligible') is not False or data.get('model_fits')!=0):
        raise ValueError('calibration_rejection_unverified')
    rows=data.get('substeps',[])
    if not 1<=len(rows)<=2*q['intervals']:raise ValueError('calibration_rejection_unverified')
    screen=domain_screen(rows[-1],data['geometry'],q['starting_z_m'])
    if screen['screen_pass']:raise ValueError('calibration_rejection_unverified')
    return {'status':'rejected_calibration_stop_cause_verified_only','run_id':q['run_id'],
            'physics_ticks_recorded':len(rows),'reasons':screen['reasons'],
            'last_screen':screen,'eligible_for_excitation':False,
            'prefix_semantically_accepted':False,'training_eligible':False,'model_handoff':False}


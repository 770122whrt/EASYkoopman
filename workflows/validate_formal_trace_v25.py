"""Semantic acceptance of one new D-23 trace, never an evidence relabeller."""
import hashlib
from pathlib import Path
import numpy as np
from workflows.formal_contract_v25 import proposal,analysis_policy,authorize
from workflows.collect_formal_v25 import validate_interval
from workflows.validate_control_trace_v23 import compare_values,validate_clock_step
from workflows.control_seam_v23 import ControlKernel
from workflows.pilot_control_v24 import commands
from easyuuv_nc.control import ActuatorState

DIRECT_RL_SHA='8d4c64aef3a4b9e258fb069211c5cae1293d7b5b742ce3b5c523dceaa298317c'


def validate_trace(data,case,source_commit):
    if data.get('status')!='completed_formal_v25':raise ValueError('formal_trace_status')
    if data.get('source_commit')!=source_commit or data.get('request')!=case:
        raise ValueError('formal_trace_source_or_case')
    binding=data['authorization'];approval={k:v for k,v in binding.items() if k!='approval_sha256'}
    approved,expected=authorize(proposal(),analysis_policy(),approval,source_commit,case['run_id'])
    if approved!=case or expected!=binding:raise ValueError('formal_trace_approval')
    n=case['intervals'];rows=data['substeps'];boundaries=data['boundary_states']
    if len(rows)!=2*n or len(boundaries)!=n:raise ValueError('formal_trace_inventory')
    cfg=data['effective_cfg']
    for name,value in [('control_input_mode','direct_pre_tam_v24'),('control_history_reset_mode','episode_local_v1'),
                       ('inertia_sync_mode','declared_v1'),('physics_initialization_mode','authored_static_v1'),
                       ('initial_embodiment_type',case['configuration'])]:
        if cfg[name]!=value:raise ValueError('formal_trace_effective_cfg')
    sources=data['loaded_sources'];env=Path(__file__).resolve().parents[1]/'easyuuv_nc/env/easyuuv_env.py'
    if (sources['EasyUUVEnv']['sha256']!=hashlib.sha256(env.read_bytes()).hexdigest()
            or sources['EasyUUVEnv']['path']!=proposal()['remote_project_root']+'/easyuuv_nc/env/easyuuv_env.py'
            or sources['DirectRLEnv']['path']!='/root/IsaacLab/source/isaaclab/isaaclab/envs/direct_rl_env.py'
            or sources['DirectRLEnv']['sha256']!=DIRECT_RL_SHA):raise ValueError('formal_trace_loaded_sources')
    provenance=data['runtime_provenance']
    if provenance['actual_isaac_sim']!='5.0' or provenance['actual_isaac_lab']!='2.2.1':raise ValueError('formal_runtime')
    provenance=provenance['runtime_provenance']
    for key,value in [('isaac_lab_release_commit','0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20'),
                      ('isaac_lab_repo_commit','c91a125c73c8b574878419a9583afc0b63b99f0a'),
                      ('isaac_lab_repo_patch_sha256','d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079')]:
        if provenance[key]!=value:raise ValueError('formal_runtime_source')
    kernel=ControlKernel(case['configuration']);p=data['actuator_parameters']
    if (p['tau_s']!=kernel.tau or p['physics_dt_s']!=1/120 or p['count']!=kernel.env._num_thrusters
            or p['clock']!='float32_accumulated_v1' or not p['known_zero_initialization'] or p['truth_feedback']):
        raise ValueError('formal_actuator_contract')
    if np.any(data['observed_start_boundary']['actuator_speed_n']):raise ValueError('formal_actuator_initialization')
    estimator=ActuatorState(p['count'],tau=p['tau_s'],dt=1/120,clock=p['clock'])
    actions=np.repeat(commands(case),2,axis=0);maximum=np.zeros(4)
    for i in range(n):
        pair=rows[2*i:2*i+2];validate_interval(pair,configuration=case['configuration'])
        if any(r['control_index']!=i or r['reset_generation']!=[1] for r in pair):raise ValueError('formal_trace_reset_or_index')
        compare_values(pair[-1]['state_after_physics_11'],boundaries[i]['state_11'])
    for j,row in enumerate(rows):
        previous=data['observed_start_boundary'] if j==0 else rows[j-1]['command']
        prior_state=data['observed_start_boundary']['state_11'] if j==0 else rows[j-1]['state_after_physics_11']
        compare_values(prior_state,row['before']['state_11'])
        compare_values(previous['actuator_speed_n'],row['before']['actuator_speed_n'])
        compare_values(previous['telemetry']['step_token'],row['before']['telemetry']['step_token'],atol=0)
        validate_clock_step([0] if j==0 else rows[j-1]['actuator_update']['end_time_s'],row['actuator_update']['end_time_s'])
        before=row['before'];backend=before['backend'];declared=np.asarray(before['telemetry']['mass_kg'],dtype=np.float32)
        inverse=np.asarray(backend['inverse_mass_per_kg'],dtype=np.float32);actual=np.asarray(backend['mass_kg'],dtype=np.float32)
        if not np.array_equal(inverse,np.float32(1)/declared) or not np.array_equal(actual,np.float32(1)/inverse):raise ValueError('formal_mass_readback')
        np.testing.assert_allclose(np.asarray(before['telemetry']['inertia_diagonal_kg_m2'])[0],np.asarray(backend['inertia_9']).reshape(3,3).diagonal(),rtol=0,atol=1e-6)
        sent=kernel.command(actions[j],pre_tam=True);speed=estimator.advance_pwm(sent['pwm'])
        wrench=kernel.B.numpy()@(kernel.env.cfg.rotor_constant*np.abs(speed)*speed)
        command=row['command'];telemetry=command['telemetry']
        errors=[np.max(np.abs(sent['virtual_control']-np.asarray(telemetry['virtual_control_4'])[0])),
                np.max(np.abs(sent['pwm']-np.asarray(telemetry['motor_pwm_n'])[0])),
                np.max(np.abs(speed-np.asarray(command['actuator_speed_n'])[0])),
                np.max(np.abs(wrench-np.asarray(telemetry['applied_wrench_6'])[0]))]
        maximum=np.maximum(maximum,errors)
    if np.any(maximum>np.asarray([1e-6,1e-6,1e-3,1e-3])):raise ValueError('formal_input_reconstruction')
    return {'status':'formal_trace_semantic_checks_pass','run_id':case['run_id'],'intervals':n,
            'maximum_control_pwm_speed_wrench_errors':maximum.tolist(),'source_commit':source_commit,
            'limits':'raw semantic/source/request acceptance; native exits/inventory/pullback and model evaluation remain separate'}

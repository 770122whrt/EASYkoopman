"""New D-23 collector; unchanged plant mechanics, formal source/role binding.

Derived from the tested r7 loop. Private entry revalidates authorization before
any simulator import or output reservation. Canonical raw data still require
independent runtime/semantic/inventory acceptance; no model promotion here.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from easyuuv_nc.embodiments import qualification_record
from koopman.diagnostics_v23 import reserve_output,json_safe
from workflows.pilot_control_v24 import commands
from workflows.formal_contract_v25 import RESULT_RELATIVE


def validate_interval(rows,*,configuration):
    from workflows.validate_control_trace_v23 import validate_interval as original
    record=qualification_record(configuration)
    if not record['public']:raise ValueError('formal_configuration_not_public')
    for row in rows:
        if row['before']['telemetry']['configuration']!=configuration or row['command']['telemetry']['configuration']!=configuration:
            raise ValueError('formal_trace_configuration_mismatch')
    equivalent={8:'base',6:'uuv6',4:'uuv4'}[record['thruster_count']]
    original(rows,configuration=equivalent)


def run_authorized_case(q, authorization, stage_gate=None):
    from workflows.formal_contract_v25 import proposal,analysis_policy,authorize,validate_stage,verify_gate_artifacts,digest
    approval={k:v for k,v in authorization.items() if k!='approval_sha256'}
    expected_case,expected_binding=authorize(proposal(),analysis_policy(),approval,authorization['source_commit'],q['run_id'])
    if q!=expected_case or authorization!=expected_binding:raise ValueError('formal_d23_binding')
    validate_stage(q,stage_gate,authorization['source_commit'],digest(proposal()))
    verify_gate_artifacts(stage_gate,Path(__file__).resolve().parents[1])
    from workflows.collect_koopman_v21_identification import _repository_commit
    source_commit=_repository_commit(expected_source_commit=authorization['source_commit'])
    root=Path(__file__).resolve().parents[1]
    output=reserve_output(root/RESULT_RELATIVE/'collection',q['run_id'])
    report={'request':q,'source_commit':source_commit,'status':'started_formal_v25',
            'evidence_level':'source_bound_isaac_v25_pending_acceptance','authorization':authorization,'boundary_states':[],
            'frames':'world z; wxyz body-to-world; body v/omega; body wrench; dimensionless control; internal rotor rad/s convention'}
    from isaaclab_app import AppLauncher
    app=AppLauncher({'headless':True}).app
    env=None;trace=None
    try:
        import inspect
        import gymnasium as gym
        import torch
        import isaaclab
        from isaaclab_compat import DirectRLEnv
        from easyuuv_nc import register_gym_tasks
        from easyuuv_nc.env.easyuuv_env import EasyUUVEnvCfg,EasyUUVEnv
        from easyuuv_nc.control_v24 import ActuatorState
        from workflows.control_trace_v23 import ControlTraceSession,_copy,_states
        from workflows.control_seam_v23 import mechanical_readback
        from workflows.qualify_easyuuv_v2 import detect_runtime_provenance
        # validate_interval is the source-derived eight-configuration wrapper below
        register_gym_tasks();cfg=EasyUUVEnvCfg()
        cfg.scene.num_envs=1;cfg.eval_mode=True;cfg.cap_episode_length=False;cfg.reference_mode='step'
        cfg.disturbance_cfg.mode='none';cfg.noise_cfg.enable_noise=False
        cfg.domain_randomization.use_custom_randomization=False
        cfg.control_history_reset_mode='episode_local_v1';cfg.inertia_sync_mode='declared_v1'
        cfg.physics_initialization_mode='authored_static_v1';cfg.initial_embodiment_type=q['configuration']
        cfg.control_input_mode=q['mode'];cfg.seed=q['seed']
        env=gym.make('EasyUUV-Direct-v1',cfg=cfg);runtime=env.unwrapped
        if runtime.sim.cfg.dt!=1/120 or runtime.cfg.decimation!=2 or float(runtime.step_dt)!=1/60:
            raise ValueError('pilot_runtime_clock_invalid')
        report['runtime_provenance']=detect_runtime_provenance(isaaclab.__file__)
        report['loaded_sources']={c.__name__:{'path':inspect.getfile(c),'sha256':hashlib.sha256(Path(inspect.getfile(c)).read_bytes()).hexdigest()} for c in (EasyUUVEnv,DirectRLEnv)}
        report['initial_mechanics']=_copy(runtime._initial_mechanics_v23)
        report['mechanics']=mechanical_readback(runtime)
        report['effective_cfg']={k:_copy(getattr(cfg,k)) for k in ('control_input_mode','control_history_reset_mode','inertia_sync_mode','physics_initialization_mode','initial_embodiment_type','cascade_control','control_method','s_ratio','self_adapt','attitude_error_mode','d_use_ang_vel','d_filter_tau','depth_integral_gain')}
        report['topology']={k:_copy(getattr(runtime,k)) for k in ('_control_mask_4','thruster_com_offsets','thruster_quats','_alloc_B','_alloc_channel_sign','_use_config_alloc','_alloc_mode','PID_args','action_lim')}
        report['actuator_parameters']={'tau_s':float(runtime.cfg.dyn_time_constant),'physics_dt_s':1/120,'rotor_constant':float(runtime.cfg.rotor_constant),'count':runtime._num_thrusters,'known_zero_initialization':True,'truth_feedback':False,'clock':'float32_accumulated_v1'}
        trace=ControlTraceSession(runtime,enabled=q['trace'],max_substeps=2*q['intervals'],backend_readback_enabled=True)
        estimate=ActuatorState(runtime._num_thrusters,tau=float(runtime.cfg.dyn_time_constant),dt=1/120,clock='float32_accumulated_v1')
        with trace:
            env.reset(seed=q['seed']);report['observed_start_boundary']=trace._snapshot()
            for i,a in enumerate(commands(q)):
                before_count=len(trace.substeps)
                result=env.step(torch.as_tensor(a,device=runtime.device).reshape(1,4))
                if bool(torch.any(result[2])) or bool(torch.any(result[3])):
                    raise ValueError('pilot_unexpected_reset')
                if q['mode']!='legacy_action' and runtime._direct_index_v24!=2:
                    raise ValueError('pilot_direct_consume_count')
                x=np.asarray(_states(runtime))
                if not np.isfinite(x).all() or np.any(np.abs(x[:,0])>100) or np.any(np.abs(x[:,5:])>100):
                    raise ValueError('pilot_physical_state_bound')
                rows=trace.substeps[before_count:]
                if q['trace']:
                    if len(rows)!=2:raise ValueError('pilot_substep_count')
                    for row in rows:row.update(stage='observed',stage_interval=i)
                    validate_interval(rows,configuration=q['configuration'])
                    for row in rows:
                        speed=estimate.advance_pwm(row['command']['telemetry']['motor_pwm_n'][0])
                        row['command_driven_speed_n']=speed.tolist()
                        row['estimated_minus_actual_speed_n']=(speed-np.asarray(row['command']['actuator_speed_n'][0])).tolist()
                report['boundary_states'].append({'stage':'observed','interval':i,'state_11':x.tolist(),'telemetry':_copy(runtime.get_koopman_telemetry_snapshot())})
        report['status']='completed_formal_v25'
    except Exception as exc:
        report.update(status='failed_formal_v25',exception=f'{type(exc).__name__}:{exc}')
        raise
    finally:
        if trace is not None:report.update(substeps=trace.substeps,events=trace.events)
        (output/'trace.json').write_text(json.dumps(json_safe(report),indent=2,allow_nan=False)+'\n')
        try:
            if env is not None:env.close()
        finally:app.close()

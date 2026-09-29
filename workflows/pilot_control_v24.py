"""One explicit v2.4 runtime request. Collection is exploratory, never formal."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import numpy as np

from easyuuv_nc.embodiments import qualification_record
from koopman.diagnostics_v23 import reserve_output, json_safe


def validate_request(value):
    q = dict(value)
    required = {'run_id','configuration','seed','mode','intervals','excitation','amplitudes','hold_intervals','trace','replay_path'}
    if set(q) != required or not isinstance(q['run_id'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,95}',q['run_id']):
        raise ValueError('pilot_request_fields_invalid')
    if q['configuration'] not in ('base','uuv4','uuv6'):
        raise ValueError('pilot_configuration_invalid')
    if type(q['seed']) is not int or not 8400 <= q['seed'] <= 8499:
        raise ValueError('pilot_seed_invalid')
    if q['mode'] not in ('legacy_action','direct_pre_tam_v24','direct_sequence_replay_v24'):
        raise ValueError('pilot_mode_invalid')
    if type(q['intervals']) is not int or q['intervals'] not in (32,128):
        raise ValueError('pilot_intervals_invalid')
    if q['excitation'] not in ('prbs','multisine','chirp','zero') or type(q['trace']) is not bool:
        raise ValueError('pilot_excitation_invalid')
    a=np.asarray(q['amplitudes'],dtype=float)
    if a.shape!=(4,) or not np.isfinite(a).all() or np.any(a<0) or np.any(a>1):
        raise ValueError('pilot_amplitude_invalid')
    if type(q['hold_intervals']) is not int or not 1<=q['hold_intervals']<=32:
        raise ValueError('pilot_hold_invalid')
    if q['mode']=='direct_sequence_replay_v24':
        if not isinstance(q['replay_path'],str) or not q['replay_path']:
            raise ValueError('pilot_replay_path_required')
        if q['intervals']!=32 or not q['trace']:
            raise ValueError('pilot_replay_diagnostic_only')
    elif q['replay_path'] is not None:
        raise ValueError('pilot_replay_forbidden')
    return q


def commands(q):
    n=q['intervals'];rng=np.random.default_rng(q['seed']);amp=np.asarray(q['amplitudes'])
    if q['excitation']=='prbs':
        hold=q['hold_intervals'];a=np.repeat(rng.choice([-1.,1.],size=((n+hold-1)//hold,4)),hold,axis=0)[:n]*amp
    elif q['excitation']=='zero':
        a=np.zeros((n,4))
    else:
        t=np.arange(n)[:,None]/60;phase=rng.uniform(-np.pi,np.pi,size=(1,4))
        if q['excitation']=='multisine':
            a=amp*(.6*np.sin(2*np.pi*.7*t+phase)+.4*np.sin(2*np.pi*2.3*t-2*phase))
        else:
            a=amp*np.sin(2*np.pi*(.3*t+.5*(3.-.3)/(n/60)*t*t)+phase)
    return np.asarray(a*np.asarray(qualification_record(q['configuration'])['control_mask']),dtype=np.float32)


def execute(q):
    q=validate_request(q)
    from workflows.collect_koopman_v21_identification import _repository_commit
    source_commit=_repository_commit()
    root=Path(__file__).resolve().parents[1]
    output=reserve_output(root/'tmp/phase8_4',q['run_id'])
    report={'request':q,'source_commit':source_commit,'status':'started_exploratory_v24',
            'evidence_level':'exploratory_isaac_v24','boundary_states':[],
            'frames':'world z; wxyz body-to-world; body v/omega; body wrench; dimensionless control; internal rotor rad/s convention'}
    replay=None
    if q['replay_path']:
        p=(root/q['replay_path']).resolve()
        if not p.is_relative_to((root/'tmp/phase8_4').resolve()) or p.parent==output:
            raise ValueError('pilot_replay_path_escape')
        d=json.loads(p.read_text());source=d['request']
        if (d['status']!='completed_exploratory_v24' or d['source_commit']!=source_commit
                or source['mode']!='legacy_action' or any(source[k]!=q[k] for k in ('configuration','seed','intervals','excitation','amplitudes','hold_intervals'))):
            raise ValueError('pilot_replay_binding_invalid')
        if len(d['substeps'])!=64:
            raise ValueError('pilot_replay_count_invalid')
        replay=np.asarray([r['command']['telemetry']['virtual_control_4'][0] for r in d['substeps']],dtype=np.float32).reshape(32,2,4)
        report['diagnostic_replay']={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                                    'measured_sequence_for_seam_equivalence_only':True,'prediction_fit_permitted':False}
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
        from easyuuv_nc.control import queue_sequence,ActuatorState
        from workflows.control_trace_v23 import ControlTraceSession,_copy,_states
        from workflows.control_seam_v23 import mechanical_readback
        from workflows.qualify_easyuuv_v2 import detect_runtime_provenance
        from workflows.validate_control_trace_v23 import validate_interval
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
                if replay is not None:
                    sequence=torch.as_tensor(replay[i:i+1],device=runtime.device)
                    queue_sequence(runtime,sequence);a=replay[i,0]
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
        report['status']='completed_exploratory_v24'
    except Exception as exc:
        report.update(status='failed_exploratory_v24',exception=f'{type(exc).__name__}:{exc}')
        raise
    finally:
        if trace is not None:report.update(substeps=trace.substeps,events=trace.events)
        (output/'trace.json').write_text(json.dumps(json_safe(report),indent=2,allow_nan=False)+'\n')
        try:
            if env is not None:env.close()
        finally:app.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--request',type=Path,required=True);p.add_argument('--execute',action='store_true')
    args=p.parse_args();q=validate_request(json.loads(args.request.read_text(encoding='utf8')))
    if args.execute:execute(q)
    else:print(json.dumps(q,indent=2))


if __name__=='__main__':main()

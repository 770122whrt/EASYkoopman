"""Fixed six-case contact/altitude diagnostic. No model training or promotion."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

EXPERIMENT='phase8.4-free-water-microtrace-v26-20260913'


def cases():
    result=[]
    for cfg,seed,n,excitation in [('base',8500,32,'prbs'),('heavy_moderate',8501,128,'chirp'),
                                ('asymmetric',8502,256,'chirp')]:
        for variant in (0,1):
            high=(cfg=='base' or variant==1);observer=(cfg!='base' or variant==1)
            label=('on' if observer else 'off') if cfg=='base' else ('high' if high else 'low')
            result.append({'run_id':f'w26-{cfg}-{seed}-{label}','configuration':cfg,'seed':seed,
                'intervals':n,'role':'diagnostic','mode':'direct_pre_tam_v24','excitation':excitation,
                'amplitudes':[.04,.04,.08,.20],'hold_intervals':4,'trace':True,'replay_path':None,
                'starting_z_m':5.5 if high else 1.5,'contact_observer':observer,
                'stop_on_rejection':high})
    return result


def validate_case(q):
    if q not in cases():raise ValueError('free_water_fixed_case')
    return q


def run_case(q,output,expected_source):
    validate_case(q)
    from workflows.collect_koopman_v21_identification import _repository_commit
    source=_repository_commit(expected_source_commit=expected_source)
    output=Path(output);output.mkdir(exist_ok=False,parents=True)
    report={'experiment':EXPERIMENT,'request':q,'source_commit':source,'status':'started_free_water_diagnostic',
            'model_fits':0,'training_eligible':False,'boundary_states':[],'contact_authoring':[]}
    from isaaclab_app import AppLauncher
    app=AppLauncher({'headless':True}).app;env=None;trace=None
    try:
        import inspect
        import gymnasium as gym
        import torch
        import isaaclab
        from easyuuv_nc import register_gym_tasks
        from easyuuv_nc.env.easyuuv_env import EasyUUVEnvCfg,EasyUUVEnv
        from isaaclab_compat import DirectRLEnv
        from easyuuv_nc.package_paths import EMBODIMENT_USD_PATH
        from workflows.control_trace_v23 import ControlTraceSession,_copy,_states
        from workflows.free_water_trace_v26 import FreeWaterTraceSession
        from workflows.free_water_runtime_v26 import contact_report_spawner,read_geometry,bind_contact_getter
        from workflows.collect_formal_v25 import validate_interval
        from workflows.pilot_control_v24 import commands
        from workflows.qualify_easyuuv_v2 import detect_runtime_provenance
        register_gym_tasks();cfg=EasyUUVEnvCfg()
        cfg.scene.num_envs=1;cfg.eval_mode=True;cfg.cap_episode_length=False;cfg.reference_mode='step'
        cfg.disturbance_cfg.mode='none';cfg.noise_cfg.enable_noise=False
        cfg.domain_randomization.use_custom_randomization=False
        cfg.control_history_reset_mode='episode_local_v1';cfg.inertia_sync_mode='declared_v1'
        cfg.physics_initialization_mode='authored_static_v1';cfg.initial_embodiment_type=q['configuration']
        cfg.control_input_mode=q['mode'];cfg.seed=q['seed'];cfg.starting_depth=q['starting_z_m']
        if q['contact_observer']:
            cfg.robot_cfg.spawn.func=contact_report_spawner(cfg.robot_cfg.spawn.func,report['contact_authoring'])
        env=gym.make('EasyUUV-Direct-v1',cfg=cfg);runtime=env.unwrapped
        if runtime.sim.cfg.dt!=1/120 or runtime.cfg.decimation!=2 or float(runtime.step_dt)!=1/60:
            raise ValueError('free_water_runtime_clock')
        report['runtime_provenance']=detect_runtime_provenance(isaaclab.__file__)
        report['loaded_sources']={c.__name__:{'path':inspect.getfile(c),'sha256':hashlib.sha256(Path(inspect.getfile(c)).read_bytes()).hexdigest()} for c in (EasyUUVEnv,DirectRLEnv)}
        report['asset_sha256']=hashlib.sha256(EMBODIMENT_USD_PATH.read_bytes()).hexdigest()
        report['initial_mechanics']=_copy(runtime._initial_mechanics_v23)
        report['effective_cfg']={k:_copy(getattr(cfg,k)) for k in ('starting_depth','ground_plane_mode','control_input_mode','control_history_reset_mode','inertia_sync_mode','physics_initialization_mode','initial_embodiment_type')}
        geometry=read_geometry(runtime);report['geometry']=geometry
        if geometry['initial_clearance_m']<.1:raise ValueError('free_water_initial_geometry')
        if q['contact_observer']:
            getter=bind_contact_getter(runtime,geometry)
            trace=FreeWaterTraceSession(runtime,contact_getter=getter,geometry=geometry,
                stop_on_rejection=q['stop_on_rejection'],max_substeps=2*q['intervals'])
        else:trace=ControlTraceSession(runtime,max_substeps=2*q['intervals'],backend_readback_enabled=True)
        actions=commands(q);report['commands_sha256']=hashlib.sha256(actions.tobytes()).hexdigest()
        with trace:
            env.reset(seed=q['seed']);report['observed_start_boundary']=trace._snapshot()
            report['initial_backend_step_index']=int(runtime._sim_step_counter)
            for i,a in enumerate(actions):
                count=len(trace.substeps)
                result=env.step(torch.as_tensor(a,device=runtime.device).reshape(1,4))
                if bool(torch.any(result[2])) or bool(torch.any(result[3])):raise ValueError('free_water_unexpected_reset')
                x=np.asarray(_states(runtime));rows=trace.substeps[count:]
                if not np.isfinite(x).all() or np.any(np.abs(x[:,0])>100) or np.any(np.abs(x[:,5:])>100):
                    raise ValueError('free_water_state_bound')
                if runtime._direct_index_v24!=2:raise ValueError('free_water_direct_consume')
                validate_interval(rows,configuration=q['configuration'])
                report['boundary_states'].append({'interval':i,'state_11':x.tolist()})
        report['status']='completed_free_water_diagnostic_pending_acceptance'
    except Exception as exc:
        import traceback
        report.update(status='failed_free_water_diagnostic',exception=f'{type(exc).__name__}:{exc}')
        traceback.print_exc()
        raise
    finally:
        if trace is not None:report.update(substeps=trace.substeps,events=trace.events)
        from koopman.diagnostics_v23 import json_safe
        (output/'trace.json').write_text(json.dumps(json_safe(report),indent=2,allow_nan=False)+'\n',encoding='utf8')
        print('FREE_WATER_STATUS='+report['status'],flush=True)
        try:
            if env is not None:env.close()
        finally:app.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--source-commit',required=True);args=parser.parse_args()
    matches=[q for q in cases() if q['run_id']==args.case]
    if len(matches)!=1:raise ValueError('free_water_fixed_case')
    run_case(matches[0],args.output,args.source_commit)

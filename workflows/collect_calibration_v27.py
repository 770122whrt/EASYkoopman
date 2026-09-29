"""Cold-start static trim and physical-pulse calibration using the qualified v26 chain.

No environmental parameter writes, rotor prewarming, model fits, or training roles.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

from workflows.workpoint_v27 import cases,validate_case,EXPERIMENT,commands,validate_calibration

def run_case(q,output,expected_source,calibration):
    validate_case(q)
    validate_calibration(calibration)
    actions=commands(q,calibration)
    from workflows.collect_koopman_v21_identification import _repository_commit
    source=_repository_commit(expected_source_commit=expected_source)
    output=Path(output);output.mkdir(exist_ok=False,parents=True)
    report={'experiment':EXPERIMENT,'request':q,'source_commit':source,'status':'started_calibration','calibration':calibration,
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
        from workflows.calibration_trace_v27 import CalibrationTraceSession,LIMITS,TAIL_LIMITS
        from workflows.free_water_runtime_v26 import contact_report_spawner,read_geometry,bind_contact_getter
        from workflows.collect_formal_v25 import validate_interval
        from workflows.qualify_easyuuv_v2 import detect_runtime_provenance
        register_gym_tasks();cfg=EasyUUVEnvCfg()
        cfg.scene.num_envs=1;cfg.eval_mode=True;cfg.cap_episode_length=False;cfg.reference_mode='step'
        cfg.disturbance_cfg.mode='none';cfg.noise_cfg.enable_noise=False
        cfg.domain_randomization.use_custom_randomization=False
        cfg.control_history_reset_mode='episode_local_v1';cfg.inertia_sync_mode='declared_v1'
        cfg.physics_initialization_mode='authored_static_v1';cfg.initial_embodiment_type=q['configuration']
        cfg.control_input_mode=q['mode'];cfg.seed=q['seed'];cfg.starting_depth=q['starting_z_m']
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
        getter=bind_contact_getter(runtime,geometry)
        trace=CalibrationTraceSession(runtime,contact_getter=getter,geometry=geometry,
            starting_z=q['starting_z_m'],max_substeps=2*q['intervals'])
        report['motion_limits']=LIMITS;report['tail_limits']=TAIL_LIMITS
        report['commands_sha256']=hashlib.sha256(actions.tobytes()).hexdigest()
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
        report['status']='completed_calibration_pending_acceptance'
    except Exception as exc:
        import traceback
        report.update(status='failed_calibration',exception=f'{type(exc).__name__}:{exc}')
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
    parser.add_argument('--source-commit',required=True);parser.add_argument('--calibration',required=True);args=parser.parse_args()
    matches=[q for q in cases() if q['run_id']==args.case]
    if len(matches)!=1:raise ValueError('free_water_fixed_case')
    table=json.loads(Path(args.calibration).read_text())
    run_case(matches[0],args.output,args.source_commit,table[matches[0]['configuration']])

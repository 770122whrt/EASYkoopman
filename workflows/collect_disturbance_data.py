"""Fresh 30Hz data collection. Native exit and independent acceptance are separate."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from workflows.disturbance_protocol import get_protocol
from workflows.disturbance_data import verify_manifest,context


def child(q,output,manifest,*,spec=None):
    spec=get_protocol() if spec is None else spec
    manifest_sha=verify_manifest(manifest,spec=spec);output.mkdir(parents=True,exist_ok=False)
    version=spec.VERSION
    signal=spec.excitation(q)
    report=dict(schema='disturbance-data-'+version,case=q,status='started',cleanup_errors=[],
        source_manifest_sha256=manifest_sha,decisions=[],contact_authoring=[])
    resources={};env=runtime=trace=app=None;started=time.monotonic()
    os.environ['CUDA_MODULE_LOADING']='EAGER'
    try:
        from isaaclab_app import AppLauncher
        app=AppLauncher({'headless':True,'fast_shutdown':False,'kit_args':'--allow-root'}).app
        resources['app']=app
        import numpy as np
        import torch
        import gymnasium as gym
        from easyuuv_nc import register_gym_tasks
        from easyuuv_nc.env.easyuuv_env import EasyUUVEnvCfg
        from workflows.runtime_episode_v67 import configure_environment
        from workflows.runtime_episode_v59 import check_runtime_context
        from workflows.calibration_trace_v27 import CalibrationTraceSession
        from workflows.control_trace_v23 import _states
        from workflows.geometry_v76 import read_geometry
        from workflows.free_water_runtime_v26 import contact_report_spawner,bind_contact_getter
        from workflows.feedback_v31 import FeedbackPolicy,validate_decision
        torch.set_num_threads(1);register_gym_tasks();cfg=EasyUUVEnvCfg()
        configure_environment(cfg,'base',q['seed']);cfg.ground_plane_mode='local_cuboid'
        cfg.hidden_quadratic_drag_fraction_v86=q['hidden_drag_fraction']
        cfg.robot_cfg.spawn.func=contact_report_spawner(cfg.robot_cfg.spawn.func,report['contact_authoring'])
        env=gym.make('EasyUUV-Direct-v1',cfg=cfg);resources['env']=env;runtime=env.unwrapped
        if runtime.sim.cfg.dt!=1/120 or runtime.cfg.decimation!=4:raise ValueError('v86_clock')
        report['effective_hidden_drag_fraction']=runtime.cfg.hidden_quadratic_drag_fraction_v86
        report['geometry']=read_geometry(runtime)
        trace=CalibrationTraceSession(runtime,contact_getter=bind_contact_getter(runtime,report['geometry']),
            geometry=report['geometry'],starting_z=5.5,max_substeps=4*q['controls'])
        resources['trace']=trace;policy=FeedbackPolicy('base')
        with trace:
            env.reset(seed=q['seed']);report['observed_start_boundary']=trace._snapshot()
            check_runtime_context(report['observed_start_boundary'],'base',context())
            for i,demand in enumerate(signal):
                x=np.asarray(_states(runtime))[0];d=policy.decide(x,demand);d['interval']=i
                report['decisions'].append(d)
                if not validate_decision(d,x,demand,'base'):raise ValueError('v86_collection_command')
                result=env.step(torch.as_tensor(d['command_4'],dtype=torch.float32,device=runtime.device).reshape(1,4))
                if bool(torch.any(result[2])) or bool(torch.any(result[3])):raise ValueError('v86_unexpected_reset')
                if len(trace.substeps)!=4*(i+1):raise ValueError('v86_substep_count')
                if time.monotonic()-started>300:raise TimeoutError('v86_collection_budget')
                if (i+1)%40==0:print(f'{version.upper()}_DATA_PROGRESS={i+1}/{q["controls"]}',flush=True)
        report['status']='completed_pending_native_cleanup'
    except BaseException as exc:
        report.update(status='failed',exception=type(exc).__name__+':'+str(exc));traceback.print_exc()
    finally:
        if trace is not None:report.update(substeps=trace.substeps,events=trace.events)
        from koopman.diagnostics_v23 import json_safe
        with gzip.open(output/'before-cleanup.json.gz','xt',encoding='utf8') as f:json.dump(json_safe(report),f,allow_nan=False)
        from workflows.runtime_lifecycle_v70 import close_owned_resources
        env=runtime=trace=app=None
        close_owned_resources(resources,report,output)
        if report['status']=='completed_pending_native_cleanup' and not report['cleanup_errors']:
            report['status']='completed_pending_independent_acceptance'
        with gzip.open(output/'trace.json.gz','xt',encoding='utf8') as f:json.dump(json_safe(report),f,allow_nan=False)
    return 0 if report['status']=='completed_pending_independent_acceptance' else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--case',required=True)
    p.add_argument('--version',choices=('v86','v87','v88'),default='v88')
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--native-child',action='store_true');a=p.parse_args()
    spec=get_protocol(a.version)
    inventory=spec.cases()
    q=next((q for q in inventory if q['run_id']==a.case),None)
    if q is None:raise ValueError('v86_case')
    verify_manifest(a.manifest,spec=spec)
    if a.native_child:return child(q,a.output,a.manifest,spec=spec)
    if a.output.exists():raise FileExistsError(a.output)
    module=spec.COLLECTOR
    proc=subprocess.run([sys.executable,'-B','-m',module,
        '--native-child','--version',a.version,'--case',a.case,'--manifest',str(a.manifest),'--output',str(a.output)])
    path=a.output/'trace.json.gz'
    if a.output.is_dir():
        with (a.output/'native-exit.json').open('x',encoding='utf8') as f:
            json.dump(dict(native_exit=proc.returncode,trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
                if path.is_file() else None),f)
    return proc.returncode


if __name__=='__main__':sys.exit(main())

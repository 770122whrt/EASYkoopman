"""Bounded new-server simulation-time model/controller comparison, zero fitting."""
import argparse
import faulthandler
import gzip
import hashlib
import json
import os
from pathlib import Path
from dataclasses import asdict
import sys
import time
import traceback


def main():
    p=argparse.ArgumentParser();p.add_argument('--configuration',choices=('base','uuv4','long_body','uuv6'),required=True)
    p.add_argument('--controller',choices=('feedback','projected_koopman','nominal_physics'),required=True)
    p.add_argument('--assets',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--profile',choices=('repair','depth4','depth4_h20'),default='repair')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1];manifest=json.loads(a.manifest.read_text())
    for rel,digest in manifest['files'].items():
        if hashlib.sha256((root/rel).read_bytes()).hexdigest()!=digest:raise ValueError('source_changed:'+rel)
    from workflows.protocol_v77 import settings
    profile=settings(a.profile)
    case=dict(configuration=a.configuration,controller=a.controller,profile=a.profile,controls=60,seed=19760,
              reference=[5.5,0.9998000066665778,0.,0.01999866669333308,0.],task='pitch_0.04_rad')
    report=dict(schema='reliable-control-v77',collector_pid=os.getpid(),case=case,status='started',cleanup_errors=[],
        model_fits=0,real_time_qualified=False,timing_mode='synchronous_nonrealtime',contact_authoring=[],
        source_manifest_sha256=hashlib.sha256(a.manifest.read_bytes()).hexdigest(),
        physical_steps=0,completed_controls=0)
    resources={};env=runtime=trace=app=coordinator=None;started=time.monotonic()
    os.environ['CUDA_MODULE_LOADING']='EAGER';faulthandler.enable(all_threads=True)
    try:
        from isaaclab_app import AppLauncher
        app=AppLauncher({'headless':True,'fast_shutdown':False,'kit_args':'--allow-root'}).app
        resources['app']=app
        import numpy as np
        import torch
        torch.set_num_threads(1)
        import gymnasium as gym
        from easyuuv_nc import register_gym_tasks
        from easyuuv_nc.env.easyuuv_env import EasyUUVEnvCfg
        from easyuuv_nc.control_v67 import install_control_clock
        from workflows.runtime_episode_v67 import configure_environment
        from workflows.runtime_episode_v59 import check_runtime_context
        from workflows.free_water_runtime_v26 import contact_report_spawner,bind_contact_getter
        from workflows.geometry_v76 import read_geometry
        from workflows.isaac_execution_v67 import IsaacExecutionSession
        from workflows.runtime_assets_v56 import AssetLocation,load_assets,read
        from workflows.identify_sparse_world_v30 import from_record
        from koopman.prepared_projected_v40 import prepare_projected
        from koopman.physical_control_v76 import PhysicalPredictor
        from koopman.reliable_mpc_v77 import create_solver
        from koopman.reliable_runtime_v77 import ReliableCoordinator
        from koopman.inexact_tracking_v66 import InexactTrackingFeedback
        from koopman.bounded_feedback_v46 import FeedbackConfig
        from koopman.rate30_v67 import ExecutionLedger
        from workflows.runtime_prepare_v69 import prepare_math,assert_unchanged
        from koopman.control_objective_v44 import tracking_terms,control_mask
        assets=load_assets(AssetLocation(a.assets,'.','assets/v38/inputs',
            '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
        domain=assets.domains[a.configuration];context=assets.context(a.configuration)
        fitted=from_record(read(assets.model_path));solver=None
        if a.controller!='feedback':
            solver=create_solver(domain,fitted,context,a.controller,**profile)
            resources['worker']=solver
            report['solver_process_pid']=solver.worker.pid
        report['model']=dict(kind=a.controller,frozen_parameter_source_sha256=assets.model_sha256,
            common_support_id=domain.identity,horizon_macro_steps=profile['horizon'],weights=asdict(profile['weights']))
        install_control_clock();register_gym_tasks();cfg=EasyUUVEnvCfg()
        configure_environment(cfg,a.configuration,case['seed']);cfg.ground_plane_mode='local_cuboid'
        cfg.robot_cfg.spawn.func=contact_report_spawner(cfg.robot_cfg.spawn.func,report['contact_authoring'])
        env=gym.make('EasyUUV-Direct-v1',cfg=cfg);resources['env']=env;runtime=env.unwrapped
        assert runtime.sim.cfg.dt==1/120 and runtime.cfg.decimation==4 and runtime.step_dt==1/30
        report['gpu']=torch.cuda.get_device_name(0);report['geometry']=read_geometry(runtime)
        trace=IsaacExecutionSession(runtime,episode_id=a.output.name,reset_id=a.output.name+':reset1',
            geometry=report['geometry'],contact_getter=bind_contact_getter(runtime,report['geometry']),max_substeps=240)
        resources['trace']=trace
        with trace:
            env.reset(seed=case['seed']);before=trace._snapshot()
            report['math_preparation']=prepare_math(runtime);assert_unchanged(before,trace._snapshot())
            reset=trace.reset_observation()
            report['context_audit']=check_runtime_context(trace.reset_record['snapshot'],a.configuration,context)
            feedback_config=FeedbackConfig(slew=.02,timeout_ms=2000.)
            feedback=InexactTrackingFeedback(domain,context,config=feedback_config)
            seed=feedback.prepare_startup(reset.state,case['reference'])
            if seed['status']!='prepared':raise ValueError('startup:'+str(seed['reason']))
            ledger=ExecutionLedger(domain,context,reset,reference=case['reference'],reference_id='pitch-v76',
                startup_command=seed['command'],feedback_config=feedback_config,steady=feedback.steady)
            coordinator=ReliableCoordinator(ledger,feedback,solver);trace.bind(coordinator)
            feedback.physics_index=lambda:ledger.physics_index
            for i in range(case['controls']):
                trace.run_interval(env.step,case['reference'],reference_id='pitch-v76')
                report['completed_controls']=i+1
                if time.monotonic()-started>900:raise TimeoutError('case_wall_budget')
            assert len(trace.substeps)==240 and ledger.physics_index==240 and not ledger.pending
            x=np.asarray([r['state_after_physics_11'][0] for r in trace.substeps])
            terms=tracking_terms(x,case['reference'],control_mask(a.configuration))
            report['metrics']=dict(depth_rmse_m=float(np.sqrt(np.mean(terms['depth']))),
                attitude_rmse_rad=float(np.sqrt(np.mean(terms['attitude']))),
                normalized_tracking_score=float(np.mean(terms['depth']/.02**2+terms['attitude']/.04**2)),
                maximum_angular_speed=float(np.max(np.linalg.norm(x[:,8:],axis=1))),
                maximum_cycle_ms=max(r['whole_cycle_wall_ms'] for r in trace.interval_records))
        report['status']='completed_pending_native_cleanup'
    except BaseException as exc:
        report.update(status='failed',exception=type(exc).__name__+':'+str(exc));traceback.print_exc()
    finally:
        if trace is not None:
            report.update(substeps=trace.substeps,intervals=trace.interval_records,events=trace.events,
                reset_record=getattr(trace,'reset_record',None),physical_steps=len(trace.substeps))
        if coordinator is not None:
            report.update(solve_audit=coordinator.solve_audit,stats=coordinator.stats,feedback_audit=coordinator.feedback.audit)
        from koopman.diagnostics_v23 import json_safe
        with gzip.open(a.output/'before-cleanup.json.gz','xt') as f:json.dump(json_safe(report),f,allow_nan=False)
        from workflows.runtime_lifecycle_v70 import close_owned_resources
        env=runtime=trace=app=coordinator=None
        close_owned_resources(resources,report,a.output)
        report['wall_seconds']=time.monotonic()-started
        if report['status']=='completed_pending_native_cleanup' and not report['cleanup_errors']:
            report['status']='completed_pending_independent_acceptance'
        with gzip.open(a.output/'trace.json.gz','xt') as f:json.dump(json_safe(report),f,allow_nan=False)
        summary={k:v for k,v in report.items() if k not in ('substeps','intervals','events','solve_audit','feedback_audit','reset_record')}
        (a.output/'summary.json').write_text(json.dumps(json_safe(summary),indent=2,allow_nan=False))
        print('CONTINUOUS_RESULT='+json.dumps(json_safe(summary)),flush=True)
    return 0 if report['status']=='completed_pending_independent_acceptance' else 1


if __name__=='__main__':sys.exit(main())

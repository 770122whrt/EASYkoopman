"""Read-only v59 dependencies, separate bounded diagnostic output; no promotion.

Execute this file directly outside the frozen release. cProfile adds overhead,
so its measurements diagnose attribution, not uninstrumented realtime latency.
The original cycle deadline and all actual substep/safety checks remain active.
"""
import argparse
import cProfile
import faulthandler
import hashlib
import inspect
import os
import json
from pathlib import Path
import pstats
import sys
import time


def prepare_output(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output == root or output.is_relative_to(root):
        raise ValueError('diagnostic_output_must_be_outside_frozen_release')
    output.mkdir(parents=True, exist_ok=False)


def profile_call(function, output):
    profiler = cProfile.Profile()
    try:
        return profiler.runcall(function)
    finally:
        profiler.dump_stats(str(Path(output)/'profile.pstats'))
        stats = pstats.Stats(profiler)
        rows = [dict(file=k[0], line=k[1], function=k[2], primitive_calls=v[0],
                     calls=v[1], self_seconds=v[2], cumulative_seconds=v[3])
                for k,v in stats.stats.items()]
        rows.sort(key=lambda q:q['cumulative_seconds'], reverse=True)
        with (Path(output)/'profile.json').open('x', encoding='utf8') as f:
            json.dump(dict(diagnostic_only=True, runtime_qualified=False,
                           profiler_overhead_included=True, functions=rows), f, indent=2)


def write_report(path, report):
    import gzip
    from koopman.diagnostics_v23 import json_safe
    # Full traces retained losslessly; compression is outside control timing.
    with gzip.open(str(path)+'.gz','xt',encoding='utf8') as f:
        json.dump(json_safe(report),f,separators=(',',':'),allow_nan=False)


def diagnose(root, output, case):
    from workflows.collect_runtime_v59 import (HANDOFF_SHA, check_loaded_sources,
        check_simulator_binding, close_resources, launch_application)
    from workflows.phase9_preflight_v59 import verify_release, cases
    from workflows.runtime_assets_v56 import AssetLocation, load_assets, portable_model_factory
    from koopman.compiled_recovery_v64 import portable_compiled_factory
    portable_model_factory = portable_compiled_factory
    from runtime_episode_v65 import run_intervals, BoundaryWorker, bind_effect_clock
    release = verify_release(root)
    if release['release_sha256'] != 'aa1efbb4c57b3d01225a3d1604f9b39a2adbc4d04e6e359b249afbfbabb7e3a9':
        raise ValueError('diagnostic_frozen_v59_required')
    prepare_output(root, output)
    report=dict(schema='phase9-effects-v65', diagnostic_only=True, profiler_enabled=False,
        runtime_qualified=False, model_fits=0, training_eligible=False,
        release_sha256=release['release_sha256'], case=case,
        diagnostic_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        status='started_diagnostic', contact_authoring=[], cleanup_errors=[], worker_closed=None)
    app=env=trace=worker=runtime=None
    started=time.perf_counter()
    try:
        assets=load_assets(AssetLocation(str(root), '.', 'assets/v38/inputs', HANDOFF_SHA), model_key=case['model_key'])
        report['assets']=dict(model_sha256=assets.model_sha256)
        report['cuda_module_loading']=os.environ.get('CUDA_MODULE_LOADING')
        from koopman.solver_worker_v49 import IsolatedSolverWorker
        if case['controller']=='mpc':
            worker=IsolatedSolverWorker(portable_model_factory, assets.worker_spec(case['configuration']))
            worker.start()
            while worker.state=='starting':
                worker.poll()
                if time.perf_counter()-started>30: raise TimeoutError('diagnostic_worker_startup')
                if worker.state=='starting': time.sleep(.005)
            if worker.state!='ready':raise ValueError('diagnostic_worker_not_ready')
            if case['mode']=='simulation_effect': worker=BoundaryWorker(worker)
        from isaaclab_app import AppLauncher
        app=launch_application(AppLauncher)
        faulthandler.enable(all_threads=True)
        import gymnasium as gym
        import isaaclab
        import torch
        torch.set_num_threads(1)
        from easyuuv_nc import register_gym_tasks
        from easyuuv_nc.env.easyuuv_env import EasyUUVEnvCfg, EasyUUVEnv
        from isaaclab_compat import DirectRLEnv
        from easyuuv_nc.package_paths import EMBODIMENT_USD_PATH
        from workflows.control_trace_v23 import _copy
        from workflows.free_water_runtime_v26 import contact_report_spawner, read_geometry, bind_contact_getter
        from workflows.qualify_easyuuv_v2 import detect_runtime_provenance
        from workflows.isaac_execution_v55 import IsaacExecutionSession
        from workflows.runtime_episode_v59 import configure_environment, bind_runtime
        register_gym_tasks(); cfg=EasyUUVEnvCfg()
        configure_environment(cfg, case['configuration'], case['seed'])
        cfg.robot_cfg.spawn.func=contact_report_spawner(cfg.robot_cfg.spawn.func, report['contact_authoring'])
        report['runtime_provenance']=detect_runtime_provenance(isaaclab.__file__)
        report['loaded_sources']={c.__name__:dict(path=inspect.getfile(c),
            sha256=hashlib.sha256(Path(inspect.getfile(c)).read_bytes()).hexdigest()) for c in (EasyUUVEnv, DirectRLEnv)}
        report['asset_sha256']=hashlib.sha256(EMBODIMENT_USD_PATH.read_bytes()).hexdigest()
        check_simulator_binding(report, release)
        from runtime_addon_v64 import check_loaded_sources as check_addon_sources
        addon=Path(__file__).resolve().parents[1]
        addon_manifest=json.loads((addon/'ADDON_MANIFEST.json').read_text())
        report['loaded_project_sources']=check_addon_sources(root, release, addon, addon_manifest)
        env=gym.make('EasyUUV-Direct-v1',cfg=cfg); runtime=env.unwrapped
        if runtime.sim.cfg.dt!=1/120 or runtime.cfg.decimation!=2 or float(runtime.step_dt)!=1/60:
            raise ValueError('runtime_physics_clock')
        geometry=read_geometry(runtime)
        report['geometry']=geometry
        trace=IsaacExecutionSession(runtime, episode_id=case['case_id'], reset_id=case['case_id']+':reset1',
            geometry=geometry, contact_getter=bind_contact_getter(runtime,geometry),max_substeps=2*case['controls'])
        with trace:
            env.reset(seed=case['seed'])
            from runtime_prepare_v61 import prepare_math, assert_unchanged
            before_prepare=trace._snapshot()
            report['runtime_preparation']=prepare_math(runtime)
            assert_unchanged(before_prepare,trace._snapshot())
            report['runtime_preparation']['full_reset_snapshot_unchanged']=True
            report['preparation_source_sha256']=hashlib.sha256((Path(__file__).parent/'runtime_prepare_v61.py').read_bytes()).hexdigest()
            report['runtime_binding']=bind_runtime(trace,assets,case['configuration'],case['reference'],reference_id=case['reference_id'],worker=worker)
            if case['mode']=='simulation_effect': bind_effect_clock(trace)
            report['cycle_summary']=run_intervals(trace,env.step,case['reference'],
                reference_id=case['reference_id'],controls=case['controls'],mode=case['mode'],
                require_mpc=case['controller']=='mpc')
        report['status']='diagnostic_returned'
    except BaseException as exc:
        report.update(status='diagnostic_exception',exception=type(exc).__name__+':'+str(exc))
        import traceback
        traceback.print_exc()
    finally:
        if trace is not None:
            report.update(substeps=trace.substeps,intervals=trace.interval_records,events=trace.events,
                          reset_record=getattr(trace,'reset_record',None))
            if trace.runtime is not None:
                report['runtime_final']=dict(stats=dict(trace.runtime.stats),physics_index=trace.runtime.ledger.physics_index,
                    stopped=trace.runtime.ledger.stopped,pending=trace.runtime.ledger.pending)
                report['arbitration_audit']=trace.runtime.arbiter.export()
        report['outside_cycle_worker_wait_s']=getattr(worker,'wait_seconds',0.)
        write_report(output/'before-cleanup.json',report)
        from runtime_lifecycle_v62 import close_owned_resources
        report['lifecycle_source_sha256']=hashlib.sha256((Path(__file__).parent/'runtime_lifecycle_v62.py').read_bytes()).hexdigest()
        owned=dict(worker=worker,env=env,trace=trace,runtime=runtime,app=app)
        worker=env=trace=runtime=app=None
        close_owned_resources(owned,report,output)
        faulthandler.enable(all_threads=True)
        report['wall_seconds']=time.perf_counter()-started
        write_report(output/'diagnostic.json',report)
    return 1 if report.get('exception') or report['cleanup_errors'] else 0


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--release-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case',required=True)
    args=parser.parse_args()
    faulthandler.enable(all_threads=True)
    sys.path.insert(0,str(args.release_root.resolve()))
    if 'torch' in sys.modules:
        raise RuntimeError('eager_loading_must_precede_torch')
    os.environ['CUDA_MODULE_LOADING']='EAGER'
    import koopman
    koopman.__path__.insert(0,str(Path(__file__).resolve().parents[1]/'koopman'))
    protocol=json.loads((Path(__file__).resolve().parents[1]/'protocol.json').read_text())
    case=next(x for x in protocol['cases'] if x['case_id']==args.case)
    return diagnose(args.release_root.resolve(),args.output.resolve(),case)



if __name__ == '__mp_main__':
    sys.path.insert(0,sys.argv[sys.argv.index('--release-root')+1])
    import koopman
    koopman.__path__.insert(0,str(Path(__file__).resolve().parents[1]/'koopman'))

if __name__=='__main__':
    raise SystemExit(main())

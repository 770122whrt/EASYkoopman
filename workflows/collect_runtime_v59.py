"""Source-bound Isaac collector. Importing this module never launches Isaac.

Run only as a child of the bounded stage supervisor. A native zero exit is not
semantic acceptance; failed/partial traces remain diagnostic evidence only.
"""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys
import time

from workflows.phase9_preflight_v59 import authorize_case, cases, proposal, verify_release
from workflows.runtime_assets_v56 import AssetLocation, load_assets, portable_model_factory


HANDOFF_SHA = '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'


def classify_exit(native, report, case, release_sha):
    """Parent envelope only; actual execution still needs validate_runtime_v57."""
    if type(native) is not int:
        return 1
    if native:
        return native if native > 0 else 128-native
    if (not isinstance(report, dict)
            or report.get('status') != 'completed_runtime_pending_acceptance'
            or report.get('request') != case or report.get('release_sha256') != release_sha
            or report.get('training_eligible') is not False
            or type(report.get('model_fits')) is not int or report['model_fits'] != 0
            or report.get('cleanup_errors') != []
            or report.get('worker_closed') != {'process_stopped': True, 'io_threads_stopped': True}
            or report.get('app_launch') != {'headless': True, 'fast_shutdown': False}
            or report.get('cleanup_completed') != {'worker': True, 'environment': True, 'simulation_app': True}):
        return 1
    return 0


def check_loaded_sources(root, release):
    """Do not validate one tree and silently import another project checkout."""
    root = Path(root).resolve(); result = {}
    for name, module in tuple(sys.modules.items()):
        if name.split('.')[0] not in ('workflows', 'koopman', 'easyuuv_nc'):
            continue
        filename = getattr(module, '__file__', None)
        if filename is None:
            continue
        path = Path(filename).resolve()
        if not path.is_relative_to(root):
            raise ValueError('runtime_import_outside_release:' + name)
        rel = path.relative_to(root).as_posix()
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if release['manifest']['files_sha256'].get(rel) != actual:
            raise ValueError('runtime_import_not_frozen:' + name)
        result[name] = dict(relative_path=rel, sha256=actual)
    return result


def check_simulator_binding(report, release):
    from workflows.validate_formal_trace_v25 import DIRECT_RL_SHA
    from workflows.validate_feedback_v28 import ASSET_SHA
    source = report['loaded_sources']; p = report['runtime_provenance']
    if (source['EasyUUVEnv']['sha256'] != release['manifest']['files_sha256']['easyuuv_nc/env/easyuuv_env.py']
            or source['DirectRLEnv']['sha256'] != DIRECT_RL_SHA or report['asset_sha256'] != ASSET_SHA
            or p['actual_isaac_sim'] != '5.0' or p['actual_isaac_lab'] != '2.2.1'):
        raise ValueError('runtime_simulator_binding')
    p = p['runtime_provenance']
    if (p['isaac_lab_repo_commit'] != 'c91a125c73c8b574878419a9583afc0b63b99f0a'
            or p['isaac_lab_repo_patch_sha256'] != 'd056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079'):
        raise ValueError('runtime_simulator_patch')


def write_report(path, report):
    from koopman.diagnostics_v23 import json_safe
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(json_safe(report), stream, indent=2, allow_nan=False)
        stream.write('\n')


def launch_application(factory):
    """Require Python to regain control after native application shutdown."""
    return factory({'headless': True, 'fast_shutdown': False}).app


def close_resources(worker, env, app, report, *, output):
    """Persist each boundary before native code; never infer return from exit 0."""
    report['cleanup_completed'] = dict(worker=False, environment=False, simulation_app=False)
    def record(index, name, phase):
        write_report(Path(output)/f'cleanup-{index:02d}-{name}-{phase}.json', dict(
            resource=name, phase=phase, status=report['status'],
            exception=report.get('exception'), cleanup_errors=list(report['cleanup_errors']),
            cleanup_completed=dict(report['cleanup_completed']), worker_closed=report.get('worker_closed')))
    for index, (name, resource) in enumerate((('worker', worker), ('environment', env), ('simulation_app', app)), 1):
        record(index, name, 'begin')
        try:
            if resource is not None:
                result = resource.close()
                if name == 'worker':
                    report['worker_closed'] = result
                    if result != {'process_stopped': True, 'io_threads_stopped': True}:
                        raise RuntimeError('worker_not_fully_closed')
                report['cleanup_completed'][name] = True
        except BaseException as exc:
            report['cleanup_errors'].append(name + ':' + type(exc).__name__ + ':' + str(exc))
        record(index, name, 'end')


def collect_case(release_root, case, approval):
    binding = authorize_case(release_root, case, approval)  # Before mkdir/importing Isaac.
    root = Path(release_root).resolve()
    if Path(__file__).resolve().parents[1] != root:
        raise ValueError('runtime_collector_wrong_checkout')
    release = verify_release(root)
    output = root/'results'/case['case_id']; output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='phase9-runtime-trace-v59', **binding, request=case,
        status='started_runtime', protocol=proposal(), model_fits=0, training_eligible=False,
        contact_authoring=[], cleanup_errors=[], worker_closed=None)
    app = env = trace = worker = None
    started = time.perf_counter()
    try:
        assets = load_assets(AssetLocation(str(root), '.', 'assets/v38/inputs', HANDOFF_SHA), model_key=case['model_key'])
        report['assets'] = dict(model_key=assets.model_key, model_sha256=assets.model_sha256,
            handoff_sha256=HANDOFF_SHA, support_id=assets.domains[case['configuration']].identity)
        from koopman.solver_worker_v49 import IsolatedSolverWorker
        worker = IsolatedSolverWorker(portable_model_factory, assets.worker_spec(case['configuration']))
        worker.start(); events = []; warm_start = time.perf_counter()
        while worker.state == 'starting':
            event = worker.poll()
            if event is not None: events.append(event)
            if worker.state == 'starting': time.sleep(.005)
        report['worker_startup'] = dict(events=events, state=worker.state,
                                       seconds=time.perf_counter()-warm_start)
        if worker.state != 'ready': raise ValueError('runtime_worker_startup_failed')
        # The solver uses a spawned CPU process, prepared before GPU app launch.
        from isaaclab_app import AppLauncher
        report['app_launch'] = {'headless': True, 'fast_shutdown': False}
        app = launch_application(AppLauncher)
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
        from workflows.runtime_episode_v59 import configure_environment, bind_runtime, run_intervals
        register_gym_tasks(); cfg = EasyUUVEnvCfg()
        configure_environment(cfg, case['configuration'], case['seed'])
        cfg.robot_cfg.spawn.func = contact_report_spawner(cfg.robot_cfg.spawn.func, report['contact_authoring'])
        report['runtime_provenance'] = detect_runtime_provenance(isaaclab.__file__)
        report['loaded_sources'] = {c.__name__: dict(path=inspect.getfile(c),
            sha256=hashlib.sha256(Path(inspect.getfile(c)).read_bytes()).hexdigest()) for c in (EasyUUVEnv, DirectRLEnv)}
        report['asset_sha256'] = hashlib.sha256(EMBODIMENT_USD_PATH.read_bytes()).hexdigest()
        check_simulator_binding(report, release)
        report['loaded_project_sources'] = check_loaded_sources(root, release)
        env = gym.make('EasyUUV-Direct-v1', cfg=cfg); runtime = env.unwrapped
        if runtime.sim.cfg.dt != 1/120 or runtime.cfg.decimation != 2 or float(runtime.step_dt) != 1/60:
            raise ValueError('runtime_physics_clock')
        report['initial_mechanics'] = _copy(runtime._initial_mechanics_v23)
        report['effective_cfg'] = {k: _copy(getattr(cfg, k)) for k in (
            'starting_depth', 'ground_plane_mode', 'control_input_mode', 'control_history_reset_mode',
            'inertia_sync_mode', 'physics_initialization_mode', 'initial_embodiment_type')}
        geometry = read_geometry(runtime); report['geometry'] = geometry
        if geometry['initial_clearance_m'] < .1: raise ValueError('runtime_initial_geometry')
        trace = IsaacExecutionSession(runtime, episode_id=case['case_id'], reset_id=case['case_id']+':reset1',
            geometry=geometry, contact_getter=bind_contact_getter(runtime, geometry), max_substeps=2*case['controls'])
        with trace:
            env.reset(seed=case['seed'])
            report['runtime_binding'] = bind_runtime(trace, assets, case['configuration'], case['reference'],
                                                    reference_id=case['reference_id'], worker=worker)
            report['cycle_summary'] = run_intervals(trace, env.step, case['reference'],
                reference_id=case['reference_id'], controls=case['controls'])
        report['loaded_project_sources'] = check_loaded_sources(root, release)
        report['status'] = 'completed_runtime_pending_cleanup'
    except BaseException as exc:
        report.update(status='stopped_runtime_no_go', exception=type(exc).__name__+':'+str(exc))
        import traceback
        traceback.print_exc()
    finally:
        if trace is not None:
            from workflows.control_trace_v23 import _copy
            report.update(substeps=trace.substeps, events=trace.events, intervals=trace.interval_records,
                          reset_record=getattr(trace, 'reset_record', None))
            if trace.runtime is not None:
                ledger = trace.runtime.ledger
                report['runtime_final'] = dict(stats=_copy(trace.runtime.stats),
                    physics_index=ledger.physics_index, stopped=ledger.stopped, pending=bool(ledger.pending))
                report['arbitration_audit'] = trace.runtime.arbiter.export()
        # A native exit during cleanup leaves this file but never a completed trace.
        write_report(output/'trace-before-cleanup.json', report)
        close_resources(worker, env, app, report, output=output)
        if report['cleanup_errors']:
            report['status'] = 'stopped_runtime_no_go'
        elif report['status'] == 'completed_runtime_pending_cleanup':
            report['status'] = 'completed_runtime_pending_acceptance'
        report['wall_seconds'] = time.perf_counter()-started
        write_report(output/'trace.json', report)
    return classify_exit(0, report, case, binding['release_sha256'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release-root', type=Path, required=True)
    parser.add_argument('--approval', type=Path, required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--native-child', action='store_true', required=True)
    args = parser.parse_args()
    match = [q for q in cases() if q['case_id'] == args.case]
    if len(match) != 1: raise ValueError('runtime_fixed_case')
    return collect_case(args.release_root, match[0], json.loads(args.approval.read_text(encoding='utf8')))


if __name__ == '__main__':
    raise SystemExit(main())

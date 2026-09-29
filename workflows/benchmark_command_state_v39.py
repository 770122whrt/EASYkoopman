"""Bounded local equivalence/timing assay; existing fit episodes only.

Run this file directly. Prediction dependencies and the v37 reference are
imported from the immutable r23 source, with only the new v39 module loaded
from the working tree. This does not create Isaac or model-promotion evidence.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import time

FIELDS = ('predictions', 'pwm', 'rotor_speed', 'acceleration', 'physics_time_s',
          'origin_rotor_speed', 'requested_commands', 'applied_control',
          'issued_commands', 'control_mask', 'origin_actuator_time_s')
RTOL = ATOL = 1e-12


def compare_forecasts(reference, candidate):
    import numpy as np
    if reference['complete'] is not True or candidate['complete'] is not True:
        raise ValueError('assay_incomplete_prediction')
    if any(reference[k] != candidate[k] for k in
           ('failure', 'completed_control_intervals', 'origin_control')):
        raise ValueError('assay_equivalence_status')
    differences = {}
    for field in FIELDS:
        a, b = np.asarray(reference[field]), np.asarray(candidate[field])
        if (a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all()
                or not np.allclose(a, b, rtol=RTOL, atol=ATOL)):
            raise ValueError('assay_equivalence_'+field)
        differences[field] = float(np.max(np.abs(a-b))) if a.size else 0.
    return differences


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def dump(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def cpu_name():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            return winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
    except (ImportError, OSError):
        return platform.processor() or 'unavailable'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if 'workflows' in sys.modules or 'koopman' in sys.modules:
        raise RuntimeError('run_benchmark_file_directly_for_frozen_imports')
    project = Path(__file__).resolve().parents[1]
    directory = project/'docs/evidence/phase8_4/server-projected-formal-v38-r23'
    handoff_path = directory/'prediction-control-handoff-v2.json'
    handoff = read(handoff_path)
    frozen = Path(handoff['frozen_source_directory'])
    package = frozen.parent
    candidate_path = project/'koopman/command_state_v39.py'
    assert handoff['input']['channels'] == ['roll', 'pitch', 'yaw', 'depth']
    assert handoff['prediction_handoff'] is True and handoff['closed_loop_controller_promoted'] is False
    assert handoff['closeout_sha256'] == sha(directory/'formal-closeout.json')
    assert handoff['formal_freeze_sha256'] == sha(package/'inputs/freeze.json')
    if args.output.exists():
        raise FileExistsError('assay_output_already_exists')
    args.output.mkdir(parents=True)
    protocol = dict(schema='command-state-v39-local-assay-v1', evidence_level='local_fit_interface_only',
        origins=[0, 64, 128], horizons=[20, 60, 128], repetitions=3, warmups_per_path_per_cell=1,
        scopes=['pooled', 'heldout'], configurations=list(handoff['configurations']),
        maximum_seconds=600, output_limit_bytes=128*1024**2, new_fits=0, new_server_runs=0,
        formal_test_access=False, rtol=RTOL, atol=ATOL, handoff_sha256=sha(handoff_path),
        reference_source_commit=handoff['source_commit'], freeze_sha256=handoff['formal_freeze_sha256'],
        candidate_sha256=sha(candidate_path), runner_sha256=sha(__file__),
        fit_cache_inventory_sha256=sha(project/'docs/evidence/phase8_4/identification-fit-20260913-r17/cache-inventory.json'))
    dump(args.output/'protocol.json', protocol)
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[key] = '1'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sys.path.insert(0, str(frozen))
    started = time.monotonic(); deadline = started+protocol['maximum_seconds']
    rows, case_bindings, live_costs = [], [], []
    status, error = 'failed', None
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1); torch.set_num_interop_threads(1)
        from workflows.projected_release_v38 import verify_bundle
        from workflows.identify_sparse_world_v30 import load_fit_cache, from_record
        from koopman.command_prediction_v37 import forecast_commands
        verify_bundle(frozen, package/'inputs', handoff['source_commit'])
        spec = importlib.util.spec_from_file_location('phase9_candidate_v39', candidate_path)
        candidate = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = candidate; spec.loader.exec_module(candidate)
        episodes = [e for e in load_fit_cache(project) if e.case['excitation'] == 'prbs']
        assert {e.case['configuration'] for e in episodes} == set(protocol['configurations'])
        assert len(episodes) == 8 and all(e.case['role'] == 'fit' for e in episodes)
        models = {}
        for key, entry in handoff['eligible_models'].items():
            path = frozen/entry['path']; assert sha(path) == entry['sha256']
            models[key] = from_record(read(path))

        def checked_time():
            if time.monotonic() >= deadline:
                raise TimeoutError('local_interface_assay_budget')

        def stats(samples):
            return dict(p50_ms=float(np.percentile(samples, 50)),
                        p95_ms=float(np.percentile(samples, 95)), worst_ms=float(max(samples)))

        for e in episodes:
            name, episode_id = e.case['configuration'], e.case['run_id']
            case_bindings.append(dict(configuration=name, role='fit', episode_id=episode_id,
                                      trace_sha256=e.trace_sha256))
            t = time.perf_counter()
            live = candidate.CausalCommandState(name, e.context, episode_id=episode_id,
                                               zero_rotor_reset_verified=True)
            construction_ms = 1000*(time.perf_counter()-t)
            commit_samples, snapshot_samples = [], []
            for origin in protocol['origins']:
                for index in range(live.physics_index, 2*origin):
                    checked_time(); t = time.perf_counter()
                    live.record_issued(e.arrays['issued_control'][index], physics_index=index, episode_id=episode_id)
                    commit_samples.append(1000*(time.perf_counter()-t))
                t = time.perf_counter()
                snapshot = live.snapshot(configuration=name, context=e.context, origin_control=origin, episode_id=episode_id)
                snapshot_samples.append(1000*(time.perf_counter()-t))
                for horizon in protocol['horizons']:
                    history = e.arrays['issued_control'][:2*origin]
                    drive = e.arrays['issued_control'][2*origin:2*(origin+horizon):2]
                    assert len(drive) == horizon
                    state = e.states[2*origin]
                    for scope in protocol['scopes']:
                        model_key = 'nonlinear__'+('pooled' if scope == 'pooled' else 'heldout-'+name)
                        model = models[model_key]
                        def reference():
                            return forecast_commands(state, history, drive, name, e.context, model,
                                                     origin_control=origin, deadline=deadline)
                        def cached():
                            return snapshot.forecast(state, drive, model, deadline=deadline)
                        maximum = {k: 0. for k in FIELDS}
                        elapsed = {'replay': [], 'cached': []}
                        # Alternate order; the first pair is an unscored warmup.
                        for repeat in range(protocol['repetitions']+1):
                            results = {}
                            pairs = [('replay', reference), ('cached', cached)]
                            if (len(rows)+repeat) % 2: pairs.reverse()
                            for label, call in pairs:
                                checked_time(); t = time.perf_counter(); results[label] = call()
                                duration = 1000*(time.perf_counter()-t)
                                if repeat: elapsed[label].append(duration)
                            difference = compare_forecasts(results['replay'], results['cached'])
                            for k, value in difference.items(): maximum[k] = max(maximum[k], value)
                        assert live.physics_index == 2*origin
                        rows.append(dict(configuration=name, episode_id=episode_id, model_key=model_key,
                            origin_control=origin, horizon_control=horizon, maximum_absolute_difference=maximum,
                            milliseconds=elapsed, timing={k: stats(v) for k, v in elapsed.items()},
                            speedup_p50=float(np.median(elapsed['replay'])/np.median(elapsed['cached']))))
            live_costs.append(dict(configuration=name, construction_ms=construction_ms,
                recorded_physics_ticks=live.physics_index, record_issued=stats(commit_samples),
                snapshot=stats(snapshot_samples)))
            print(json.dumps(dict(configuration=name, completed_cells=len(rows), seconds=time.monotonic()-started)), flush=True)
        assert len(rows) == 144
        assert sha(candidate_path) == protocol['candidate_sha256'] and sha(__file__) == protocol['runner_sha256']
        verify_bundle(frozen, package/'inputs', handoff['source_commit'])
        checked_time()
        status = 'local_equivalence_and_timing_complete'
    except Exception as exc:
        error = f'{type(exc).__name__}:{exc}'
    finally:
        result = dict(status=status, error=error, evidence_level='local_fit_interface_only',
            created_at=datetime.datetime.now().astimezone().isoformat(), seconds=time.monotonic()-started,
            protocol_sha256=sha(args.output/'protocol.json'), cpu=cpu_name(),
            logical_cpu_count=os.cpu_count(), python=sys.version, platform=platform.platform(),
            torch_threads=1, torch_interop_threads=1, blas_environment_threads=1, processes=1,
            cases=case_bindings, cells=len(rows), rows=rows, live_update_costs=live_costs,
            new_fits=0, new_server_runs=0, formal_test_access=False, controller_promoted=False,
            limitations=['only8fit_PRBS_episodes_for_interface_checks', '3timing_repeats_per_cell_descriptive_only',
                         'cooperative_deadline_not_process_preemption', 'no_MPC_optimization_or_closed_loop_test'])
        dump(args.output/'result.json', result)
    print(json.dumps(dict(status=status, cells=len(rows), seconds=result['seconds'], error=error)), flush=True)
    if status != 'local_equivalence_and_timing_complete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()

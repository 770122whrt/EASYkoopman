"""One bounded fit-only CPU profile, retaining the immutable v37 reference.

This diagnoses local engineering costs; it neither fits nor qualifies a model.
Run the file directly so all prediction dependencies load from frozen r23.
"""
import argparse
import cProfile
import datetime
import importlib.util
import json
import os
from pathlib import Path
import pstats
import sys
import time


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if 'workflows' in sys.modules or 'koopman' in sys.modules:
        raise RuntimeError('run_file_directly_for_frozen_imports')
    project = Path(__file__).resolve().parents[1]
    helper = load_file('v39_profile_helpers', project/'workflows/benchmark_command_state_v39.py')
    handoff_path = project/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    handoff = helper.read(handoff_path)
    frozen = Path(handoff['frozen_source_directory'])
    package = frozen.parent
    candidate_path = project/'koopman/command_state_v39.py'
    baseline_dir = project/'docs/evidence/phase9/command-state-v39-20260920'
    original = helper.read(baseline_dir/'protocol.json')
    baseline = helper.read(baseline_dir/'result.json')
    assert baseline['protocol_sha256'] == helper.sha(baseline_dir/'protocol.json')
    assert baseline['status'] == 'local_equivalence_and_timing_complete'
    assert helper.sha(candidate_path) == original['candidate_sha256']
    assert helper.sha(handoff_path) == original['handoff_sha256']
    assert helper.sha(project/'workflows/benchmark_command_state_v39.py') == original['runner_sha256']
    if args.output.exists():
        raise FileExistsError('profile_output_already_exists')
    args.output.mkdir(parents=True)
    protocol = dict(schema='command-state-v39-profile-v1',
        evidence_level='local_fit_performance_diagnosis',
        origin=128, horizon=20, scope='nonlinear__pooled', configurations=original['configurations'],
        unprofiled_repetitions=3, profiled_calls_per_configuration=1, warmups=1,
        maximum_seconds=180, output_limit_bytes=16*1024**2, processes=1, threads=1,
        new_fits=0, new_server_runs=0, formal_test_access=False,
        candidate_sha256=helper.sha(candidate_path), runner_sha256=helper.sha(__file__),
        handoff_sha256=helper.sha(handoff_path), baseline_result_sha256=helper.sha(baseline_dir/'result.json'),
        helper_sha256=helper.sha(project/'workflows/benchmark_command_state_v39.py'))
    helper.dump(args.output/'protocol.json', protocol)
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[key] = '1'
    sys.path.insert(0, str(frozen))
    started = time.monotonic()
    deadline = started + protocol['maximum_seconds']
    status, error, rows = 'failed', None, []
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        from workflows.projected_release_v38 import verify_bundle
        from workflows.identify_sparse_world_v30 import load_fit_cache, from_record
        from koopman.command_prediction_v37 import forecast_commands
        verify_bundle(frozen, package/'inputs', handoff['source_commit'])
        candidate = load_file('v39_profile_candidate', candidate_path)
        entry = handoff['eligible_models'][protocol['scope']]
        model_path = frozen/entry['path']
        assert helper.sha(model_path) == entry['sha256']
        model = from_record(helper.read(model_path))
        episodes = [e for e in load_fit_cache(project) if e.case['excitation'] == 'prbs']
        assert len(episodes) == 8 and {e.case['configuration'] for e in episodes} == set(protocol['configurations'])
        assert all(e.case['role'] == 'fit' for e in episodes)
        for e in episodes:
            if time.monotonic() >= deadline:
                raise TimeoutError('profile_budget')
            name, episode_id = e.case['configuration'], e.case['run_id']
            origin, horizon = protocol['origin'], protocol['horizon']
            live = candidate.CausalCommandState(name, e.context, episode_id=episode_id,
                                               zero_rotor_reset_verified=True)
            for index in range(2*origin):
                live.record_issued(e.arrays['issued_control'][index], physics_index=index, episode_id=episode_id)
            snapshot = live.snapshot(configuration=name, context=e.context,
                                     origin_control=origin, episode_id=episode_id)
            state = e.states[2*origin]
            drive = e.arrays['issued_control'][2*origin:2*(origin+horizon):2]

            def call():
                return snapshot.forecast(state, drive, model, deadline=deadline)

            call()
            elapsed = []
            for _ in range(protocol['unprofiled_repetitions']):
                t = time.perf_counter()
                observed = call()
                elapsed.append(1000*(time.perf_counter()-t))
            profile = cProfile.Profile()
            profiled = profile.runcall(call)
            reference = forecast_commands(state, e.arrays['issued_control'][:2*origin], drive,
                name, e.context, model, origin_control=origin, deadline=deadline)
            difference = helper.compare_forecasts(reference, observed)
            helper.compare_forecasts(reference, profiled)
            assert live.physics_index == 2*origin
            functions = []
            stats = pstats.Stats(profile)
            for (filename, line, function), (primitive, calls, own, cumulative, callers) in stats.stats.items():
                try:
                    filename = Path(filename).relative_to(frozen).as_posix()
                except ValueError:
                    if filename == str(candidate_path):
                        filename = 'candidate/koopman/command_state_v39.py'
                functions.append(dict(file=filename, line=line, function=function, calls=calls,
                    primitive_calls=primitive, self_ms=1000*own, cumulative_ms=1000*cumulative))
            rows.append(dict(configuration=name, episode_id=episode_id, role='fit', trace_sha256=e.trace_sha256,
                unprofiled_ms=elapsed, p50_ms=float(np.median(elapsed)),
                maximum_absolute_difference=difference, profiled_total_ms=1000*stats.total_tt,
                by_cumulative=sorted(functions, key=lambda f: -f['cumulative_ms'])[:30],
                by_self=sorted(functions, key=lambda f: -f['self_ms'])[:30]))
            print(json.dumps(dict(configuration=name, p50_ms=rows[-1]['p50_ms']), ensure_ascii=False), flush=True)
        verify_bundle(frozen, package/'inputs', handoff['source_commit'])
        assert helper.sha(candidate_path) == protocol['candidate_sha256']
        assert helper.sha(__file__) == protocol['runner_sha256']
        if time.monotonic() >= deadline:
            raise TimeoutError('profile_budget')
        status = 'local_profile_complete'
    except Exception as exc:
        error = f'{type(exc).__name__}:{exc}'
    result = dict(status=status, error=error, rows=rows, seconds=time.monotonic()-started,
        created_at=datetime.datetime.now().astimezone().isoformat(), protocol_sha256=helper.sha(args.output/'protocol.json'),
        cpu=helper.cpu_name(), python=sys.version, controller_promoted=False,
        limitations=['fit_PRBS_only', 'cProfile_overhead_not_real_time_cost', 'three_repetitions_descriptive_only',
                     'no_new_model_fit_or_Isaac_run'])
    payload = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n'
    if len(payload.encode('utf8')) + (args.output/'protocol.json').stat().st_size > protocol['output_limit_bytes']:
        raise RuntimeError('profile_output_budget')
    with (args.output/'result.json').open('x', encoding='utf8') as stream:
        stream.write(payload)
    print(json.dumps(dict(status=status, seconds=result['seconds'], error=error)), flush=True)
    if status != 'local_profile_complete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()

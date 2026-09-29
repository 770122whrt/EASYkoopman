"""Bounded fit-only batch/scalar equivalence and end-to-end CPU timing."""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
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
    parser.add_argument('--stage', choices=('pilot', 'full'), required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--pilot', type=Path)
    args = parser.parse_args()
    if 'workflows' in sys.modules or 'koopman' in sys.modules:
        raise RuntimeError('run_benchmark_file_directly_for_frozen_imports')
    project = Path(__file__).resolve().parents[1]
    helper = load_file('batch_assay_helper', project/'workflows/benchmark_command_state_v39.py')
    handoff_path = project/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    handoff = helper.read(handoff_path)
    frozen = Path(handoff['frozen_source_directory'])
    package = frozen.parent
    previous_dir = project/'docs/evidence/phase9/prepared-v40-full-20260920'
    previous = helper.read(previous_dir/'protocol.json')
    assert helper.sha(handoff_path) == previous['handoff_sha256']
    sources = ['koopman/command_state_v39.py', 'koopman/prepared_projected_v40.py',
               'koopman/command_batch_v41.py', 'workflows/benchmark_command_state_v39.py',
               'workflows/benchmark_command_batch_v41.py']
    bindings = {name: helper.sha(project/name) for name in sources}
    assert bindings[sources[0]] == previous['branch_sha256']
    assert bindings[sources[1]] == previous['candidate_sha256']
    full = args.stage == 'full'
    pilot_binding = None
    if full:
        if args.pilot is None:
            raise ValueError('full_requires_batch_pilot')
        pilot = helper.read(args.pilot/'result.json')
        p = helper.read(args.pilot/'protocol.json')
        assert pilot['protocol_sha256'] == helper.sha(args.pilot/'protocol.json')
        assert pilot['status'] == 'local_batch_pilot_go' and len(pilot['rows']) == 8
        assert p['sources'] == bindings
        pilot_binding = helper.sha(args.pilot/'result.json')
    arms = [dict(origin=128, horizon=20, candidates=8, scope='pooled')]
    if full:
        arms = [dict(origin=128, horizon=60, candidates=16, scope='pooled'),
                dict(origin=0, horizon=128, candidates=8, scope='heldout')]
    if args.output.exists():
        raise FileExistsError('batch_assay_output_already_exists')
    args.output.mkdir(parents=True)
    protocol = dict(schema='command-batch-v41-assay-v1', stage=args.stage, arms=arms,
        configurations=handoff['configurations'], repetitions=3, warmups_per_path=1,
        maximum_seconds=600 if full else 180, output_limit_bytes=128*1024**2,
        candidate_recipe='recorded_fit_commands_plus_0.0005_sine_offsets_first_candidate_unchanged_clip_to_0.95',
        rtol=helper.RTOL, atol=helper.ATOL, sources=bindings,
        handoff_sha256=helper.sha(handoff_path), previous_full_result_sha256=helper.sha(previous_dir/'result.json'),
        pilot_result_sha256=pilot_binding, pilot_gate='median_speedup>=1.20_and_minimum_speedup>=1.0',
        processes=1, threads=1, new_fits=0, new_server_runs=0, formal_test_access=False)
    helper.dump(args.output/'protocol.json', protocol)
    # Archive the complete additive execution path, without copying research data.
    for name in sources+['tests/test_command_batch_v41.py', 'tests/test_prepared_projected_v40.py']:
        target = args.output/'source'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write((project/name).read_bytes())
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[key] = '1'
    sys.path.insert(0, str(frozen))
    started = time.monotonic()
    deadline = started+protocol['maximum_seconds']
    rows, status, error = [], 'failed', None
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1); torch.set_num_interop_threads(1)
        from workflows.projected_release_v38 import verify_bundle
        from workflows.identify_sparse_world_v30 import load_fit_cache, from_record
        verify_bundle(frozen, package/'inputs', handoff['source_commit'])
        branch = load_file('koopman.command_state_v39', project/sources[0])
        prepared = load_file('koopman.prepared_projected_v40', project/sources[1])
        batch = load_file('koopman.command_batch_v41', project/sources[2])
        episodes = [e for e in load_fit_cache(project) if e.case['excitation'] == 'prbs']
        assert len(episodes) == 8 and all(e.case['role'] == 'fit' for e in episodes)
        assert {e.case['configuration'] for e in episodes} == set(protocol['configurations'])
        models = {}
        for key, entry in handoff['eligible_models'].items():
            path = frozen/entry['path']
            assert helper.sha(path) == entry['sha256']
            models[key] = from_record(helper.read(path))
        for e in episodes:
            name, episode_id = e.case['configuration'], e.case['run_id']
            for arm in arms:
                origin, horizon, count = arm['origin'], arm['horizon'], arm['candidates']
                key = 'nonlinear__'+('pooled' if arm['scope'] == 'pooled' else 'heldout-'+name)
                predictor = prepared.prepare_projected(models[key], e.context)
                live = branch.CausalCommandState(name, e.context, episode_id=episode_id, zero_rotor_reset_verified=True)
                for i in range(2*origin):
                    if time.monotonic() >= deadline: raise TimeoutError('batch_assay_budget')
                    live.record_issued(e.arrays['issued_control'][i], physics_index=i, episode_id=episode_id)
                snapshot = live.snapshot(configuration=name, context=e.context, origin_control=origin, episode_id=episode_id)
                x = e.states[2*origin]
                recorded = e.arrays['issued_control'][2*origin:2*(origin+horizon):2]
                assert len(recorded) == horizon
                drive = np.repeat(recorded[None].astype(float), count, axis=0)
                offsets = np.arange(count)[:, None, None]+np.arange(horizon)[None, :, None]/7+np.arange(4)[None, None, :]
                drive[1:] += .0005*np.sin(offsets[1:])
                drive = np.clip(drive, -.95, .95)
                calls = dict(scalar=lambda: [snapshot.forecast(x, commands, predictor, deadline=deadline) for commands in drive],
                             batch=lambda: batch.forecast_batch(snapshot, x, drive, predictor, deadline=deadline))
                elapsed = {label: [] for label in calls}
                maximum = {field: 0. for field in helper.FIELDS}
                for repeat in range(protocol['repetitions']+1):
                    order = list(calls)
                    if (len(rows)+repeat) % 2: order.reverse()
                    results = {}
                    for label in order:
                        t = time.perf_counter(); results[label] = calls[label]()
                        duration = 1000*(time.perf_counter()-t)
                        if repeat: elapsed[label].append(duration)
                    for a, b in zip(results['scalar'], results['batch']):
                        diff = helper.compare_forecasts(a, b)
                        for field, value in diff.items(): maximum[field] = max(maximum[field], value)
                # Independently use the unchanged v30 model in the scalar origin API.
                for commands, result in zip(drive, results['batch']):
                    reference = snapshot.forecast(x, commands, models[key], deadline=deadline)
                    diff = helper.compare_forecasts(reference, result)
                    for field, value in diff.items(): maximum[field] = max(maximum[field], value)
                assert live.physics_index == 2*origin
                timing = {label: dict(p50_ms=float(np.median(samples)), worst_ms=float(max(samples)))
                          for label, samples in elapsed.items()}
                rows.append(dict(configuration=name, episode_id=episode_id, role='fit', trace_sha256=e.trace_sha256,
                    model_key=key, **arm, timing=timing, milliseconds=elapsed, maximum_absolute_difference=maximum,
                    speedup_p50=timing['scalar']['p50_ms']/timing['batch']['p50_ms']))
                print(json.dumps(dict(configuration=name, arm=arm, cells=len(rows), seconds=time.monotonic()-started)), flush=True)
        assert len(rows) == (16 if full else 8)
        verify_bundle(frozen, package/'inputs', handoff['source_commit'])
        assert all(helper.sha(project/name) == digest for name, digest in bindings.items())
        if time.monotonic() >= deadline: raise TimeoutError('batch_assay_budget')
        speedups = [row['speedup_p50'] for row in rows]
        go = np.median(speedups) >= 1.2 and min(speedups) >= 1.0
        status = 'local_batch_full_complete' if full else ('local_batch_pilot_go' if go else 'local_batch_pilot_no_go')
    except Exception as exc:
        error = f'{type(exc).__name__}:{exc}'
    result = dict(status=status, error=error, seconds=time.monotonic()-started, rows=rows,
        created_at=datetime.datetime.now().astimezone().isoformat(), protocol_sha256=helper.sha(args.output/'protocol.json'),
        cpu=helper.cpu_name(), python=sys.version, controller_promoted=False,
        evidence_level='local_fit_batch_equivalence_and_cost_only',
        limitations=['small_perturbations_for_numerical_interface_checks_not_model_accuracy',
                     'three_repeats_descriptive_only', 'batch_latency_is_for_entire_set_not_per_candidate',
                     'no_optimizer_or_real_time_or_closed_loop_qualification'])
    payload = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n'
    other_bytes = sum(path.stat().st_size for path in args.output.rglob('*') if path.is_file())
    if len(payload.encode('utf8'))+other_bytes > protocol['output_limit_bytes']:
        raise RuntimeError('batch_assay_output_budget')
    with (args.output/'result.json').open('x', encoding='utf8') as stream: stream.write(payload)
    print(json.dumps(dict(status=status, seconds=result['seconds'], error=error)), flush=True)
    if status not in ('local_batch_pilot_go', 'local_batch_full_complete'): raise SystemExit(1)


if __name__ == '__main__':
    main()

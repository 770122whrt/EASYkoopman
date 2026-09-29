"""Bounded fit-only, alternating original/compiled/shared solver comparison.

No model fit, simulator step or formal test access. Three base worker requests
add IPC/deadline evidence; all other timing is direct solver time on this host.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ[_key] = '1'


def bootstrap(root, addon, compiler=None):
    sys.path.insert(0, str(root))
    if compiler: sys.path.insert(0, str(compiler))
    import koopman
    koopman.__path__.insert(0, str(addon/'koopman'))


# A spawned worker executes this source as __mp_main__, before unpickling its
# factory. Resolve only the explicit new modules from the sibling addon.
if __name__ == '__mp_main__':
    def _arg(name): return Path(sys.argv[sys.argv.index(name)+1]).resolve()
    bootstrap(_arg('--release-root'), _arg('--addon-root'),
              _arg('--compiler-dir') if '--compiler-dir' in sys.argv else None)


def compare(actual, expected):
    import numpy as np
    for key in ('status', 'reason', 'selected_index', 'candidate_count', 'binding'):
        if actual.get(key) != expected.get(key): raise ValueError('changed_result:'+key)
    for a, b in zip(actual['candidates'], expected['candidates']):
        for key in ('index', 'feasible', 'rejection'):
            if a[key] != b[key]: raise ValueError('changed_candidate:'+key)
        if a['cost'] is not None:
            np.testing.assert_allclose(a['cost'], b['cost'], rtol=1e-12, atol=1e-12)
    differences = {}
    for key in ('commands', 'predictions', 'cost', 'baseline_cost'):
        np.testing.assert_allclose(actual[key], expected[key], rtol=1e-12, atol=1e-12)
        differences[key] = float(np.max(np.abs(np.asarray(actual[key])-np.asarray(expected[key]))))
    return differences


def verify_origin_replay(actual, reference, cached, clock, reference_clock, cached_clock):
    """Same-host source is the equivalence reference, never a telemetry correction."""
    import numpy as np
    values = [np.asarray(v, dtype=float) for v in (actual, reference, cached)]
    if (any(v.shape != values[0].shape or not np.isfinite(v).all() for v in values)
            or not np.isfinite([clock, reference_clock, cached_clock]).all()):
        raise ValueError('origin_replay_invalid')
    np.testing.assert_allclose(actual, reference, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(clock, reference_clock, rtol=0, atol=1e-12)
    return dict(same_host_replay_max_abs_difference=float(np.max(np.abs(values[0]-values[1]))),
        historical_cache_max_abs_difference=float(np.max(np.abs(values[0]-values[2]))),
        same_host_clock_difference=float(abs(clock-reference_clock)),
        historical_cache_clock_difference=float(abs(clock-cached_clock)),
        cache_used_as_state_correction=False)


def make_request(assets, episode, origin_audits=None):
    import numpy as np
    from koopman.prepared_execution_v49 import PreparedCausalCommandState
    from koopman.command_state_v39 import CausalCommandState
    from koopman.cached_checks_v53 import CachedTrackingFeedback
    from koopman.execution_ledger_v48 import ExecutionCapture
    from koopman.recovery_solver_v50 import PlanningRequest
    name = episode.case['configuration']; run = episode.case['run_id']
    assert episode.case['role'] == 'fit'
    live = PreparedCausalCommandState(name, episode.context, episode_id=run, zero_rotor_reset_verified=True)
    reference_live = CausalCommandState(name, episode.context, episode_id=run, zero_rotor_reset_verified=True)
    for i in range(256):
        live.record_issued(episode.arrays['issued_control'][i], physics_index=i, episode_id=run)
        reference_live.record_issued(episode.arrays['issued_control'][i], physics_index=i, episode_id=run)
    origin = live.snapshot(configuration=name, context=episode.context, origin_control=128, episode_id=run)
    reference_origin = reference_live.snapshot(configuration=name, context=episode.context, origin_control=128, episode_id=run)
    audit = verify_origin_replay(origin._actuator.current(), reference_origin._actuator.current(),
        episode.arrays['causal_rotor_speed'][256], origin._actuator.elapsed_time,
        reference_origin._actuator.elapsed_time, episode.arrays['actuator_time_s'][256])
    if origin_audits is not None: origin_audits[name] = audit
    x = episode.states[256].copy(); old = episode.arrays['issued_control'][255].copy()
    ref = np.array([5.5, 1., 0., 0., 0.]); domain = assets.domains[name]
    fallback = CachedTrackingFeedback(domain, episode.context).decide(x, ref, previous=old)
    if fallback['status'] != 'ready': raise ValueError('fixed_prefix_unavailable:'+name)
    prefix = np.repeat(fallback['command'][None], 8, axis=0)
    digest = hashlib.sha256(episode.arrays['issued_control'][:256].astype(np.float32).tobytes()).hexdigest()
    cap = ExecutionCapture('offline-v64', run, 'fit-reset', 256, digest, 0, 'z5.5-upright', 0,
        name, domain.context_key, domain.model_id, domain.identity, time.perf_counter(), x, ref, old, origin)
    return PlanningRequest('fixed-v64-'+name, cap, prefix)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-root', type=Path, required=True)
    parser.add_argument('--addon-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiler-dir', type=Path)
    parser.add_argument('--skip-workers', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    bootstrap(args.release_root.resolve(), args.addon_root.resolve(), args.compiler_dir)
    started = time.perf_counter(); worker = None
    report = dict(status='started', diagnostic_only=True, model_fits=0, physics_steps=0,
        formal_test_access=False, runtime_qualified=False, rows=[], workers=[], failures=[], origin_audits={},
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    def budget():
        if time.perf_counter()-started > 180: raise TimeoutError('v64_benchmark_budget')
    def save(name, data):
        with (args.output/name).open('x', encoding='utf8') as stream:
            json.dump(data, stream, indent=2, default=lambda x: x.tolist(), allow_nan=False)
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1); torch.set_num_interop_threads(1)
        from workflows.collect_runtime_v59 import HANDOFF_SHA
        from workflows.phase9_preflight_v59 import verify_release
        from workflows.runtime_assets_v56 import AssetLocation, load_assets, portable_model_factory
        from workflows.identify_sparse_world_v30 import load_fit_cache, from_record
        from koopman.compiled_projected_v43 import prepare_compiled
        from koopman.cached_checks_v53 import CachedRecoverySolver
        from koopman.compiled_recovery_v64 import upgrade_solver, portable_compiled_factory, portable_shared_factory
        from koopman.solver_worker_v49 import IsolatedSolverWorker
        report['cuda_available'] = torch.cuda.is_available()
        assert not report['cuda_available']
        report['release_sha256'] = verify_release(args.release_root)['release_sha256']
        assets = load_assets(AssetLocation(str(args.release_root.resolve()), '.', 'assets/v38/inputs', HANDOFF_SHA), model_key='nonlinear__pooled')
        report['model_sha256'] = assets.model_sha256
        model = from_record(json.loads(assets.model_path.read_text()))
        episodes = [e for e in load_fit_cache(args.release_root) if e.case['excitation']=='prbs']
        assert len(episodes) == 8
        report['source_hashes'] = {name: hashlib.sha256((args.addon_root/'koopman'/name).read_bytes()).hexdigest()
            for name in ('compiled_forecast_v64.py', 'bounded_mpc_v64.py', 'compiled_recovery_v64.py')}
        for episode in episodes:
            budget(); name = episode.case['configuration']
            request = make_request(assets, episode, report['origin_audits'])
            tick = time.perf_counter()
            predictor = prepare_compiled(model, episode.context)
            solvers = {label: CachedRecoverySolver(assets.domains[name], episode.context, predictor)
                       for label in ('original', 'compiled', 'shared')}
            upgrade_solver(solvers['compiled'])
            upgrade_solver(solvers['shared'], share_prefix=True)
            row = dict(configuration=name, origin_control=128, role='fit',
                       prepare_seconds=time.perf_counter()-tick, runs=[], comparisons=[])
            report['rows'].append(row)
            labels = list(solvers)
            expected = None
            for repeat in range(4):
                for label in labels[repeat % 3:]+labels[:repeat % 3]:
                    budget(); tick = time.perf_counter(); answer = solvers[label](request)
                    elapsed = 1000*(time.perf_counter()-tick)
                    row['runs'].append(dict(repeat=repeat, variant=label, wall_ms=elapsed,
                        solver_ms=answer['elapsed_ms'], status=answer['status'], reason=answer.get('reason')))
                    if answer['status'] not in ('selected', 'baseline'): raise ValueError('solver_failed:'+name+':'+label)
                    if expected is None: expected = answer
                    row['comparisons'].append(dict(repeat=repeat, variant=label, differences=compare(answer, expected)))
                    if repeat == 0: save(name+'-'+label+'.json', answer)
            print(json.dumps(dict(configuration=name, timings={label:[r['wall_ms'] for r in row['runs'] if r['variant']==label] for label in labels})), flush=True)
        if not args.skip_workers:
            episode = next(e for e in episodes if e.case['configuration']=='base')
            request = make_request(assets, episode); expected = None
            for label, factory in [('original', portable_model_factory), ('compiled', portable_compiled_factory), ('shared', portable_shared_factory)]:
                budget(); tick = time.perf_counter()
                spec = assets.worker_spec('base', compiler_directory=str(args.compiler_dir.resolve()) if args.compiler_dir else None)
                worker = IsolatedSolverWorker(factory, spec); worker.start(); event = None
                while event is None:
                    budget(); event = worker.poll()
                    if event is None: time.sleep(.0005)
                row = dict(variant=label, prepare_seconds=time.perf_counter()-tick, ready=event)
                report['workers'].append(row)
                if event['status'] != 'ready': raise ValueError('worker_not_ready:'+label)
                tick = time.perf_counter(); row['submit'] = worker.submit(request.request_id, request)
                if row['submit']['status'] != 'accepted': raise ValueError('worker_not_accepted')
                event = None
                while event is None:
                    budget(); event = worker.poll()
                    if event is None: time.sleep(.0005)
                row['round_trip_ms'] = 1000*(time.perf_counter()-tick)
                row['reply'] = event
                if event['status'] != 'result' or event['payload']['status'] not in ('selected', 'baseline'):
                    raise ValueError('worker_failed:'+label)
                if expected is None: expected = event['payload']
                row['differences'] = compare(event['payload'], expected)
                row['closed'] = worker.close(); worker = None
                if not all(row['closed'].values()): raise ValueError('worker_not_closed')
        report['status'] = 'equivalent_bounded_benchmark_complete'
    except BaseException as exc:
        report['status'] = 'failed'
        report['failures'].append(type(exc).__name__+':'+str(exc))
        import traceback
        traceback.print_exc()
    finally:
        if worker is not None: report['cleanup'] = worker.close()
        report['seconds'] = time.perf_counter()-started
        save('benchmark.json', report)
        print(json.dumps(dict(status=report['status'], seconds=report['seconds'], failures=report['failures'])), flush=True)
    return int(report['status'] != 'equivalent_bounded_benchmark_complete')


if __name__ == '__main__':
    raise SystemExit(main())

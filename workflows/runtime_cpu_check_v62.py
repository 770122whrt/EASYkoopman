"""One frozen fit-only MPC request with CUDA hidden; no physics or training.

This checks CPU execution on the server, not closed-loop benefit or boat timing.
The existing 100 ms worker deadline applies without retries.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMBA_NUM_THREADS'):
        os.environ[key] = '1'
    root = args.release_root.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(root))
    started = time.perf_counter()
    worker = None
    report = dict(diagnostic_only=True, runtime_qualified=False, closed_loop_qualified=False,
                  model_fits=0, physics_steps=0, formal_test_access=False,
                  cuda_visible_devices=os.environ['CUDA_VISIBLE_DEVICES'], requests=0,
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        report['cuda_available'] = torch.cuda.is_available()
        if report['cuda_available']:
            raise ValueError('cpu_check_cuda_still_visible')
        from workflows.collect_runtime_v59 import HANDOFF_SHA
        from workflows.phase9_preflight_v59 import verify_release
        from workflows.runtime_assets_v56 import AssetLocation, load_assets, portable_model_factory
        from workflows.identify_sparse_world_v30 import load_fit_cache
        from koopman.cached_checks_v53 import CachedTrackingFeedback
        from koopman.prepared_execution_v49 import PreparedCausalCommandState
        from koopman.execution_ledger_v48 import ExecutionCapture
        from koopman.recovery_solver_v50 import PlanningRequest
        from koopman.solver_worker_v49 import IsolatedSolverWorker
        report['release_sha256'] = verify_release(root)['release_sha256']
        assets = load_assets(AssetLocation(str(root), '.', 'assets/v38/inputs', HANDOFF_SHA), model_key='nonlinear__pooled')
        report['model_sha256'] = assets.model_sha256
        e = next(e for e in load_fit_cache(root) if e.case['configuration'] == 'base' and e.case['excitation'] == 'prbs')
        assert e.case['role'] == 'fit'
        report['case'] = e.case
        live = PreparedCausalCommandState('base', e.context, episode_id=e.case['run_id'], zero_rotor_reset_verified=True)
        for i in range(256):
            live.record_issued(e.arrays['issued_control'][i], physics_index=i, episode_id=e.case['run_id'])
        origin = live.snapshot(configuration='base', context=e.context, origin_control=128, episode_id=e.case['run_id'])
        np.testing.assert_allclose(origin._actuator.current(), e.arrays['causal_rotor_speed'][256], rtol=1e-12, atol=1e-12)
        x = e.states[256].copy()
        old = e.arrays['issued_control'][255].copy()
        ref = np.array([5.5, 1., 0., 0., 0.])
        domain = assets.domains['base']
        fallback = CachedTrackingFeedback(domain, e.context).decide(x, ref, previous=old)
        if fallback['status'] != 'ready':
            raise ValueError('cpu_check_fixed_prefix_unavailable')
        prefix = np.repeat(fallback['command'][None], 8, axis=0)
        digest = hashlib.sha256(e.arrays['issued_control'][:256].astype(np.float32).tobytes()).hexdigest()
        cap = ExecutionCapture('offline-cpu-check', e.case['run_id'], 'fit-reset', 256, digest, 0,
            'z5.5-upright', 0, 'base', domain.context_key, domain.model_id, domain.identity, time.perf_counter(), x, ref, old, origin)
        request = PlanningRequest('fixed-cpu-v62', cap, prefix)
        worker = IsolatedSolverWorker(portable_model_factory, assets.worker_spec('base'))
        tick = time.perf_counter()
        worker.start()
        event = None
        while event is None:
            event = worker.poll()
            if time.perf_counter() - started > 120:
                raise TimeoutError('cpu_check_budget')
            if event is None:
                time.sleep(.0005)
        report['ready'] = event
        report['prepare_seconds'] = time.perf_counter() - tick
        if event['status'] != 'ready':
            raise ValueError('cpu_check_worker_not_ready')
        tick = time.perf_counter()
        report['submit'] = worker.submit(request.request_id, request)
        report['requests'] = 1
        if report['submit']['status'] != 'accepted':
            raise ValueError('cpu_check_submit')
        event = None
        while event is None:
            event = worker.poll()
            if event is None:
                time.sleep(.0005)
        report['request_round_trip_ms'] = 1000 * (time.perf_counter() - tick)
        report['reply'] = event
        if event['status'] != 'result' or event['payload']['status'] not in ('baseline', 'selected'):
            raise ValueError('cpu_check_request_failed')
        report['status'] = 'one_cpu_request_completed'
    except BaseException as exc:
        report.update(status='diagnostic_exception', exception=type(exc).__name__ + ':' + str(exc))
    finally:
        if worker is not None:
            report['worker_closed'] = worker.close()
            if not all(report['worker_closed'].values()):
                report.update(status='diagnostic_exception', exception='worker_not_closed')
        report['seconds'] = time.perf_counter() - started
        with (args.output / 'diagnostic.json').open('x', encoding='utf8') as stream:
            json.dump(report, stream, indent=2, default=lambda value: value.tolist(), allow_nan=False)
        print(json.dumps({key: value for key, value in report.items() if key != 'reply'}), flush=True)
    return int(report['status'] != 'one_cpu_request_completed')


if __name__ == '__main__':
    raise SystemExit(main())

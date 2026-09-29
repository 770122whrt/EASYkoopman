"""One local relocation and one old/new base worker request, fit-only.

No simulator, refit, formal test access, or deployment. The asset copy remains
in a fresh destination. This qualifies asset lookup on the current host only;
the later executable release must qualify imports and target-host runtime.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def dump(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False,
                  default=lambda v: v.tolist())
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--assets-output', type=Path, required=True)
    parser.add_argument('--compiler-dir', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    for k in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMBA_NUM_THREADS'):
        os.environ[k] = '1'
    if args.output.exists() or args.assets_output.exists():
        raise FileExistsError('relocation_assay_destination_exists')
    sources = ['workflows/runtime_assets_v56.py', 'workflows/check_runtime_assets_v56.py', 'tests/test_runtime_assets_v56.py']
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    protocol = dict(schema='local-runtime-assets-v56-check', maximum_seconds=120.,
        assets_limit_bytes=96*1024**2, output_limit_bytes=16*1024**2,
        frozen_handoff_sha256='5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632',
        model_key='nonlinear__pooled', configuration='base', origin_control=128,
        horizon=20, prefix_controls=8, worker_timeout_ms=100.,
        requests_per_path=1, retries=0, new_fits=0, new_physics_steps=0,
        formal_test_access=False, rtol=1e-12, atol=1e-12,
        sources_sha256={p: sha(root/p) for p in sources},
        gate='same_eight_support_ids_and_same_old_new_worker_commands_predictions_and_cost',
        qualification='current_host_asset_relocation_only_not_target_host_or_executable_release')
    args.output.mkdir(parents=True)
    dump(args.output/'protocol.json', protocol)
    for p in sources:
        dest = args.output/'source'/p; dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((root/p).read_bytes())
    started = time.perf_counter(); worker = None; report = dict(status='failed', error=None)
    def budget():
        if time.perf_counter()-started >= protocol['maximum_seconds']:
            raise TimeoutError('relocation_assay_time_limit')
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1); torch.set_num_interop_threads(1)
        from workflows.runtime_assets_v56 import AssetLocation, load_assets, prepare_assets, portable_model_factory
        from workflows.identify_sparse_world_v30 import load_fit_cache
        from koopman.cached_checks_v53 import CachedTrackingFeedback, frozen_model_factory
        from koopman.recovery_solver_v50 import FrozenWorkerSpec, PlanningRequest
        from koopman.execution_ledger_v48 import ExecutionCapture
        from koopman.prepared_execution_v49 import PreparedCausalCommandState
        from koopman.solver_worker_v49 import IsolatedSolverWorker, WorkerLimits
        handoff = json.loads((root/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json').read_text())
        source = Path(handoff['frozen_source_directory']).relative_to(root)
        location = AssetLocation(str(root), source.as_posix(), (source.parent/'inputs').as_posix(), protocol['frozen_handoff_sha256'])
        original = load_assets(location, model_key=protocol['model_key'])
        moved = prepare_assets(location, args.assets_output, maximum_bytes=protocol['assets_limit_bytes']); budget()
        relocated = load_assets(moved, model_key=protocol['model_key'])
        assert {k:d.identity for k,d in original.domains.items()} == {k:d.identity for k,d in relocated.domains.items()}
        report['support_ids'] = {k:d.identity for k,d in relocated.domains.items()}
        e = next(e for e in load_fit_cache(Path(moved.root)) if e.case['configuration']=='base' and e.case['excitation']=='prbs')
        live = PreparedCausalCommandState('base', e.context, episode_id=e.case['run_id'], zero_rotor_reset_verified=True)
        for i in range(256):
            live.record_issued(e.arrays['issued_control'][i], physics_index=i, episode_id=e.case['run_id'])
        origin = live.snapshot(configuration='base', context=e.context, origin_control=128, episode_id=e.case['run_id'])
        np.testing.assert_allclose(origin._actuator.current(), e.arrays['causal_rotor_speed'][256], rtol=1e-12, atol=1e-12)
        x = e.states[256].copy(); old = e.arrays['issued_control'][255].copy(); ref = np.array([5.5,1.,0.,0.,0.])
        d = original.domains['base']; policy = CachedTrackingFeedback(d, e.context)
        fallback = policy.decide(x, ref, previous=old)
        if fallback['status'] != 'ready':
            raise ValueError('relocation_fixed_prefix_unavailable:' + str(fallback['reason']))
        prefix = np.repeat(fallback['command'][None], 8, axis=0)
        digest = hashlib.sha256(e.arrays['issued_control'][:256].astype(np.float32).tobytes()).hexdigest()
        cap = ExecutionCapture('offline-relocation-fit', e.case['run_id'], 'fit-reset', 256, digest, 0,
            'z5.5-upright', 0, 'base', d.context_key, d.model_id, d.identity, time.perf_counter(), x, ref, old, origin)
        request = PlanningRequest('fixed-relocation-v56', cap, prefix)
        old_spec = FrozenWorkerSpec(str(root), 'base', e.context, protocol['model_key'], d.model_id,
            location.handoff_sha256, d.identity, str(args.compiler_dir.resolve()))
        new_spec = relocated.worker_spec('base', compiler_directory=str(args.compiler_dir.resolve()))
        packets = []; report['paths'] = []
        for label, factory, spec in [('original_v53', frozen_model_factory, old_spec), ('relocated_v56', portable_model_factory, new_spec)]:
            budget(); worker = IsolatedSolverWorker(factory, spec, limits=WorkerLimits())
            tick = time.perf_counter(); worker.start(); event = None
            while event is None:
                budget(); event = worker.poll()
                if event is None: time.sleep(.001)
            row = dict(path=label, ready=event, prepare_seconds=time.perf_counter()-tick)
            report['paths'].append(row)
            if event['status'] != 'ready': raise ValueError('relocation_worker_not_ready')
            receipt = worker.submit(request.request_id, request); row['submit'] = receipt
            if receipt['status'] != 'accepted': raise ValueError('relocation_request_not_accepted')
            event = None
            while event is None:
                budget(); event = worker.poll()
                if event is None: time.sleep(.0005)
            row['reply'] = event
            if event['status'] != 'result' or event['payload']['status'] not in ('baseline','selected'):
                raise ValueError('relocation_request_failed')
            packets.append(event['payload']); row['closed'] = worker.close(); worker = None
            if not all(row['closed'].values()): raise ValueError('relocation_worker_cleanup')
        differences = {}
        for field in ('commands','predictions'):
            a,b = (np.asarray(p[field]) for p in packets)
            np.testing.assert_allclose(a,b,rtol=1e-12,atol=1e-12)
            differences[field] = float(np.max(np.abs(a-b)))
        for field in ('status','selected_index','cost','baseline_cost','binding'):
            if packets[0].get(field) != packets[1].get(field):
                raise ValueError('relocation_result_changed:' + field)
        assert live.physics_index == 256
        assert all(sha(root/p)==h for p,h in protocol['sources_sha256'].items())
        budget(); report.update(status='local_asset_relocation_GO', differences=differences,
                                 actual_history_advanced=False, closed_loop_qualified=False)
    except Exception as exc:
        report['error'] = type(exc).__name__ + ':' + str(exc)
    finally:
        if worker is not None: report['cleanup'] = worker.close()
        report['seconds'] = time.perf_counter()-started
        dump(args.output/'result.json', report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('paths','support_ids')}, ensure_ascii=False), flush=True)
    return 0 if report['status']=='local_asset_relocation_GO' else 1


if __name__ == '__main__':
    raise SystemExit(main())

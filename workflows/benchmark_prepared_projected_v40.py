"""Fit-only, interleaved before/after timing of the prepared v30 predictor.

Frozen r23 supplies all dependencies and the original model. The new v40
adapter and unchanged v39 branch API are loaded by file. No refit or Isaac.
"""
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
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--stage', choices=('pilot', 'full'), required=True)
    parser.add_argument('--pilot', type=Path)
    args = parser.parse_args()
    if 'workflows' in sys.modules or 'koopman' in sys.modules:
        raise RuntimeError('run_benchmark_file_directly_for_frozen_imports')
    project = Path(__file__).resolve().parents[1]
    helper_path = project/'workflows/benchmark_command_state_v39.py'
    helper = load_file('v40_benchmark_helpers', helper_path)
    candidate_path = project/'koopman/prepared_projected_v40.py'
    branch_path = project/'koopman/command_state_v39.py'
    old_dir = project/'docs/evidence/phase9/command-state-v39-20260920'
    old = helper.read(old_dir/'protocol.json')
    assert helper.sha(branch_path) == old['candidate_sha256']
    handoff_path = project/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    handoff = helper.read(handoff_path)
    assert helper.sha(handoff_path) == old['handoff_sha256']
    frozen = Path(handoff['frozen_source_directory'])
    package = frozen.parent
    pilot_binding = None
    if args.stage == 'full':
        if args.pilot is None:
            raise ValueError('full_assay_requires_pilot')
        pilot = helper.read(args.pilot/'result.json')
        pilot_protocol = helper.read(args.pilot/'protocol.json')
        assert pilot['protocol_sha256'] == helper.sha(args.pilot/'protocol.json')
        assert pilot['status'] == 'local_pilot_go' and len(pilot['rows']) == 8
        assert pilot_protocol['candidate_sha256'] == helper.sha(candidate_path)
        assert pilot_protocol['runner_sha256'] == helper.sha(__file__)
        assert pilot_protocol['branch_sha256'] == helper.sha(branch_path)
        pilot_binding = helper.sha(args.pilot/'result.json')
    if args.output.exists():
        raise FileExistsError('assay_output_already_exists')
    args.output.mkdir(parents=True)
    full = args.stage == 'full'
    protocol = dict(schema='prepared-projected-v40-assay-v1', stage=args.stage,
        origins=[0, 64, 128] if full else [128], horizons=[20, 60, 128] if full else [20],
        scopes=['pooled', 'heldout'] if full else ['pooled'], configurations=old['configurations'],
        repetitions=3 if full else 5, warmups_per_path=1, maximum_seconds=600 if full else 180,
        output_limit_bytes=128*1024**2 if full else 16*1024**2, processes=1, threads=1,
        pilot_gate='median_cell_speedup>=1.10_and_all_cells>=0.95',
        rtol=helper.RTOL, atol=helper.ATOL, candidate_sha256=helper.sha(candidate_path),
        branch_sha256=helper.sha(branch_path), runner_sha256=helper.sha(__file__),
        helper_sha256=helper.sha(helper_path), handoff_sha256=helper.sha(handoff_path),
        baseline_protocol_sha256=helper.sha(old_dir/'protocol.json'), pilot_result_sha256=pilot_binding,
        new_fits=0, new_server_runs=0, formal_test_access=False)
    helper.dump(args.output/'protocol.json', protocol)
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[key] = '1'
    sys.path.insert(0, str(frozen))
    started = time.monotonic()
    deadline = started+protocol['maximum_seconds']
    rows, preparations = [], []
    status, error = 'failed', None
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        from workflows.projected_release_v38 import verify_bundle
        from workflows.identify_sparse_world_v30 import load_fit_cache, from_record
        from koopman.command_prediction_v37 import forecast_commands
        verify_bundle(frozen, package/'inputs', handoff['source_commit'])
        candidate = load_file('v40_prepared_candidate', candidate_path)
        branch = load_file('v40_unchanged_branch_v39', branch_path)
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
            prepared = {}
            for scope in protocol['scopes']:
                key = 'nonlinear__'+('pooled' if scope == 'pooled' else 'heldout-'+name)
                t = time.perf_counter()
                prepared[key] = candidate.prepare_projected(models[key], e.context)
                preparations.append(dict(configuration=name, model_key=key,
                                         milliseconds=1000*(time.perf_counter()-t)))
            live = branch.CausalCommandState(name, e.context, episode_id=episode_id,
                                            zero_rotor_reset_verified=True)
            for origin in protocol['origins']:
                for i in range(live.physics_index, 2*origin):
                    if time.monotonic() >= deadline:
                        raise TimeoutError('prepared_assay_budget')
                    live.record_issued(e.arrays['issued_control'][i], physics_index=i, episode_id=episode_id)
                snapshot = live.snapshot(configuration=name, context=e.context, origin_control=origin, episode_id=episode_id)
                x = e.states[2*origin]
                for horizon in protocol['horizons']:
                    drive = e.arrays['issued_control'][2*origin:2*(origin+horizon):2]
                    assert len(drive) == horizon
                    for key, fast in prepared.items():
                        calls = dict(original=lambda: snapshot.forecast(x, drive, models[key], deadline=deadline),
                                     prepared=lambda: snapshot.forecast(x, drive, fast, deadline=deadline))
                        elapsed = {label: [] for label in calls}
                        difference = {field: 0. for field in helper.FIELDS}
                        for repeat in range(protocol['repetitions']+1):
                            order = list(calls)
                            if (len(rows)+repeat) % 2:
                                order.reverse()
                            results = {}
                            for label in order:
                                t = time.perf_counter()
                                results[label] = calls[label]()
                                duration = 1000*(time.perf_counter()-t)
                                if repeat:
                                    elapsed[label].append(duration)
                            diff = helper.compare_forecasts(results['original'], results['prepared'])
                            for field, value in diff.items():
                                difference[field] = max(difference[field], value)
                        reference = forecast_commands(x, e.arrays['issued_control'][:2*origin], drive,
                            name, e.context, models[key], origin_control=origin, deadline=deadline)
                        helper.compare_forecasts(reference, results['prepared'])
                        assert live.physics_index == 2*origin
                        timing = {label: dict(p50_ms=float(np.median(samples)),
                                             worst_ms=float(max(samples))) for label, samples in elapsed.items()}
                        rows.append(dict(configuration=name, episode_id=episode_id, role='fit',
                            trace_sha256=e.trace_sha256, origin_control=origin, horizon_control=horizon,
                            model_key=key, maximum_absolute_difference=difference,
                            milliseconds=elapsed, timing=timing,
                            speedup_p50=timing['original']['p50_ms']/timing['prepared']['p50_ms']))
            print(json.dumps(dict(configuration=name, cells=len(rows), seconds=time.monotonic()-started)), flush=True)
        assert len(rows) == (144 if full else 8)
        verify_bundle(frozen, package/'inputs', handoff['source_commit'])
        assert helper.sha(candidate_path) == protocol['candidate_sha256']
        assert helper.sha(branch_path) == protocol['branch_sha256']
        assert helper.sha(__file__) == protocol['runner_sha256']
        if time.monotonic() >= deadline:
            raise TimeoutError('prepared_assay_budget')
        speeds = [row['speedup_p50'] for row in rows]
        go = np.median(speeds) >= 1.10 and min(speeds) >= .95
        status = 'local_full_equivalence_complete' if full else ('local_pilot_go' if go else 'local_pilot_no_go')
    except Exception as exc:
        error = f'{type(exc).__name__}:{exc}'
    result = dict(status=status, error=error, seconds=time.monotonic()-started,
        created_at=datetime.datetime.now().astimezone().isoformat(), protocol_sha256=helper.sha(args.output/'protocol.json'),
        cpu=helper.cpu_name(), python=sys.version, model_preparations=preparations, rows=rows,
        evidence_level='local_fit_equivalence_and_cost_only', controller_promoted=False,
        limitations=['preparation_cost_reported_separately', 'three_or_five_repeats_descriptive_only',
                     'no_optimization_or_real_time_or_closed_loop_evidence'])
    payload = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n'
    if len(payload.encode('utf8'))+(args.output/'protocol.json').stat().st_size > protocol['output_limit_bytes']:
        raise RuntimeError('prepared_assay_output_budget')
    with (args.output/'result.json').open('x', encoding='utf8') as stream:
        stream.write(payload)
    print(json.dumps(dict(status=status, seconds=result['seconds'], error=error)), flush=True)
    if status not in ('local_pilot_go', 'local_full_equivalence_complete'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

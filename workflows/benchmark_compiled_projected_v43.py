"""Bounded fit-only comparison of compiled model execution in the same v42 batch path."""
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
    parser.add_argument('--compiler-dir', required=True, type=Path)
    args = parser.parse_args()
    if 'workflows' in sys.modules or 'koopman' in sys.modules:
        raise RuntimeError('run_benchmark_file_directly_for_frozen_imports')
    project = Path(__file__).resolve().parents[1]
    helper = load_file('allocation_assay_helper', project/'workflows/benchmark_command_state_v39.py')
    previous = project/'docs/evidence/phase9/allocation-v42-pilot-20260920'
    old_protocol, old_result = helper.read(previous/'protocol.json'), helper.read(previous/'result.json')
    assert old_result['status'] == 'local_prepared_allocation_go'
    assert old_result['protocol_sha256'] == helper.sha(previous/'protocol.json')
    for name, digest in old_protocol['sources'].items():
        assert helper.sha(project/name) == digest
    handoff_path = project/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    assert helper.sha(handoff_path) == old_protocol['handoff_sha256']
    handoff = helper.read(handoff_path)
    frozen = Path(handoff['frozen_source_directory'])
    sources = ['koopman/command_state_v39.py', 'koopman/prepared_projected_v40.py',
               'koopman/command_batch_v41.py', 'koopman/prepared_allocation_v42.py',
               'koopman/command_batch_v42.py', 'koopman/compiled_projected_v43.py', 'workflows/benchmark_command_state_v39.py',
               'workflows/benchmark_compiled_projected_v43.py', 'scripts/requirements_phase9_compile_v43.txt']
    tests = ['tests/test_compiled_projected_v43.py', 'tests/test_prepared_allocation_v42.py', 'tests/test_command_batch_v42.py',
             'tests/test_command_batch_v41.py', 'tests/test_prepared_projected_v40.py']
    bindings = {name: helper.sha(project/name) for name in sources+tests}
    if args.output.exists(): raise FileExistsError('allocation_assay_output_already_exists')
    args.output.mkdir(parents=True)
    protocol = dict(schema='compiled-projected-v43-assay-v1', configurations=handoff['configurations'],
        origin=128, horizon=20, candidates=8, scope='pooled', repetitions=3, warmups_per_path=1,
        maximum_seconds=180, output_limit_bytes=16*1024**2, processes=1, threads=1,
        candidate_recipe='recorded_fit_commands_plus_0.0005_sine_offsets_first_candidate_unchanged_clip_to_0.95',
        rtol=helper.RTOL, atol=helper.ATOL, sources=bindings,
        handoff_sha256=helper.sha(handoff_path), prior_result_sha256=helper.sha(previous/'result.json'),
        pilot_gate='median_speedup>=1.50_and_minimum_speedup>=1.0', compiler_directory=str(args.compiler_dir.resolve()), compiler_versions={'numba':'0.61.2','llvmlite':'0.44.0'}, fastmath=False,
        new_fits=0, new_server_runs=0, formal_test_access=False)
    helper.dump(args.output/'protocol.json', protocol)
    for name in sources+tests:
        target = args.output/'source'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream: stream.write((project/name).read_bytes())
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'): os.environ[key] = '1'
    assert args.compiler_dir.is_dir()
    sys.path.insert(0, str(args.compiler_dir.resolve()))
    sys.path.insert(0, str(frozen))
    started = time.monotonic()
    deadline = started+protocol['maximum_seconds']
    rows, status, error = [], 'failed', None
    runtime = {}
    try:
        import numpy as np
        import numba, llvmlite
        assert numba.__version__ == '0.61.2' and llvmlite.__version__ == '0.44.0'
        assert args.compiler_dir.resolve() in Path(numba.__file__).resolve().parents
        assert args.compiler_dir.resolve() in Path(llvmlite.__file__).resolve().parents
        runtime = dict(numpy=np.__version__, numba=numba.__version__, llvmlite=llvmlite.__version__)
        import torch
        torch.set_num_threads(1); torch.set_num_interop_threads(1)
        from workflows.projected_release_v38 import verify_bundle
        from workflows.identify_sparse_world_v30 import load_fit_cache, from_record
        verify_bundle(frozen, frozen.parent/'inputs', handoff['source_commit'])
        modules = {}
        for name in sources[:6]:
            modules[Path(name).stem] = load_file(name[:-3].replace('/', '.'), project/name)
        episodes = [e for e in load_fit_cache(project) if e.case['excitation'] == 'prbs']
        assert len(episodes) == 8 and all(e.case['role'] == 'fit' for e in episodes)
        assert {e.case['configuration'] for e in episodes} == set(protocol['configurations'])
        entry = handoff['eligible_models']['nonlinear__pooled']
        model_path = frozen/entry['path']
        assert helper.sha(model_path) == entry['sha256']
        model = from_record(helper.read(model_path))
        for e in episodes:
            name, episode_id = e.case['configuration'], e.case['run_id']
            origin, horizon, count = protocol['origin'], protocol['horizon'], protocol['candidates']
            predictor = modules['prepared_projected_v40'].prepare_projected(model, e.context)
            preparation_started = time.perf_counter()
            compiled = modules['compiled_projected_v43'].prepare_compiled(model, e.context)
            preparation_seconds = time.perf_counter()-preparation_started
            live = modules['command_state_v39'].CausalCommandState(name, e.context,
                episode_id=episode_id, zero_rotor_reset_verified=True)
            for i in range(2*origin):
                if time.monotonic() >= deadline: raise TimeoutError('allocation_assay_budget')
                live.record_issued(e.arrays['issued_control'][i], physics_index=i, episode_id=episode_id)
            snapshot = live.snapshot(configuration=name, context=e.context, origin_control=origin, episode_id=episode_id)
            x = e.states[2*origin]
            recorded = e.arrays['issued_control'][2*origin:2*(origin+horizon):2]
            assert len(recorded) == horizon
            drive = np.repeat(recorded[None].astype(float), count, axis=0)
            offsets = np.arange(count)[:, None, None]+np.arange(horizon)[None, :, None]/7+np.arange(4)[None, None, :]
            drive[1:] += .0005*np.sin(offsets[1:])
            drive = np.clip(drive, -.95, .95)
            calls = {label: (lambda predict=value: modules['command_batch_v42'].forecast_batch(snapshot, x, drive, predict, deadline=deadline))
                     for label, value in [('v42', predictor), ('v43', compiled)]}
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
                for a, b in zip(results['v42'], results['v43']):
                    for field, value in helper.compare_forecasts(a, b).items():
                        maximum[field] = max(maximum[field], value)
            for commands, result in zip(drive, results['v43']):
                unchanged = snapshot.forecast(x, commands, model, deadline=deadline)
                for field, value in helper.compare_forecasts(unchanged, result).items():
                    maximum[field] = max(maximum[field], value)
            assert live.physics_index == 2*origin
            timing = {label: dict(p50_ms=float(np.median(samples)), worst_ms=float(max(samples)))
                      for label, samples in elapsed.items()}
            rows.append(dict(configuration=name, episode_id=episode_id, role='fit', trace_sha256=e.trace_sha256,
                model_sha256=entry['sha256'], preparation_seconds=preparation_seconds, kernel_signatures=len(modules['compiled_projected_v43']._step.signatures), timing=timing, milliseconds=elapsed,
                maximum_absolute_difference=maximum, speedup_p50=timing['v42']['p50_ms']/timing['v43']['p50_ms']))
            print(json.dumps(dict(configuration=name, cells=len(rows), seconds=time.monotonic()-started)), flush=True)
        verify_bundle(frozen, frozen.parent/'inputs', handoff['source_commit'])
        assert all(helper.sha(project/name) == digest for name, digest in bindings.items())
        if time.monotonic() >= deadline: raise TimeoutError('allocation_assay_budget')
        speedups = [row['speedup_p50'] for row in rows]
        go = np.median(speedups) >= 1.5 and min(speedups) >= 1.
        status = 'local_compiled_predictor_go' if go else 'local_compiled_predictor_no_go'
    except Exception as exc:
        error = f'{type(exc).__name__}:{exc}'
    result = dict(status=status, error=error, seconds=time.monotonic()-started, rows=rows,
        created_at=datetime.datetime.now().astimezone().isoformat(), protocol_sha256=helper.sha(args.output/'protocol.json'),
        cpu=helper.cpu_name(), python=sys.version, runtime=runtime, controller_promoted=False,
        evidence_level='local_fit_numerical_equivalence_and_cost_only',
        limitations=['small_command_perturbations_do_not_qualify_model_support', 'three_repeats_descriptive_only',
                     'whole_batch_latency_not_per_candidate', 'no_solver_or_closed_loop_qualification'])
    payload = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n'
    other_bytes = sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())
    if other_bytes+len(payload.encode('utf8')) > protocol['output_limit_bytes']:
        raise RuntimeError('allocation_assay_output_budget')
    with (args.output/'result.json').open('x', encoding='utf8') as stream: stream.write(payload)
    print(json.dumps(dict(status=status, seconds=result['seconds'], error=error)), flush=True)
    if status != 'local_compiled_predictor_go': raise SystemExit(1)


if __name__ == '__main__': main()

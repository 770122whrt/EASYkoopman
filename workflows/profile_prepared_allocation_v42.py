"""Two fit-only profiles locate costs after verified prepared allocation."""
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
    project = Path(__file__).resolve().parents[1]
    helper = load_file('v42_profile_helpers', project/'workflows/benchmark_command_state_v39.py')
    directory = project/'docs/evidence/phase9/allocation-v42-pilot-20260920'
    full = helper.read(directory/'result.json')
    prior = helper.read(directory/'protocol.json')
    assert full['status'] == 'local_prepared_allocation_go' and len(full['rows']) == 8
    assert full['protocol_sha256'] == helper.sha(directory/'protocol.json')
    assert all(helper.sha(project/name) == digest for name, digest in prior['sources'].items())
    handoff_path = project/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    assert helper.sha(handoff_path) == prior['handoff_sha256']
    handoff = helper.read(handoff_path)
    frozen = Path(handoff['frozen_source_directory'])
    protocol = dict(schema='allocation-v42-profile-v1', configurations=['base', 'uuv6_angled'],
        origin=128, horizon=20, candidates=8, scope='nonlinear__pooled', warmups=1,
        profiled_calls_per_configuration=1, maximum_seconds=60, output_limit_bytes=8*1024**2,
        full_result_sha256=helper.sha(directory/'result.json'), sources=prior['sources'],
        runner_sha256=helper.sha(__file__), formal_test_access=False, new_fits=0,
        new_server_runs=0, processes=1, threads=1)
    if args.output.exists(): raise FileExistsError('profile_output_exists')
    args.output.mkdir(parents=True)
    helper.dump(args.output/'protocol.json', protocol)
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'): os.environ[key] = '1'
    sys.path.insert(0, str(frozen))
    started = time.monotonic(); deadline = started+protocol['maximum_seconds']
    rows, status, error = [], 'failed', None
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1); torch.set_num_interop_threads(1)
        from workflows.projected_release_v38 import verify_bundle
        from workflows.identify_sparse_world_v30 import load_fit_cache, from_record
        verify_bundle(frozen, frozen.parent/'inputs', handoff['source_commit'])
        branch = load_file('koopman.command_state_v39', project/'koopman/command_state_v39.py')
        prepared = load_file('koopman.prepared_projected_v40', project/'koopman/prepared_projected_v40.py')
        load_file('koopman.prepared_allocation_v42', project/'koopman/prepared_allocation_v42.py')
        batch = load_file('koopman.command_batch_v42', project/'koopman/command_batch_v42.py')
        episodes = [e for e in load_fit_cache(project) if e.case['excitation'] == 'prbs'
                    and e.case['configuration'] in protocol['configurations']]
        assert len(episodes) == 2 and all(e.case['role'] == 'fit' for e in episodes)
        entry = handoff['eligible_models'][protocol['scope']]
        assert helper.sha(frozen/entry['path']) == entry['sha256']
        model = from_record(helper.read(frozen/entry['path']))
        for e in episodes:
            name, episode_id = e.case['configuration'], e.case['run_id']
            live = branch.CausalCommandState(name, e.context, episode_id=episode_id, zero_rotor_reset_verified=True)
            for i in range(256):
                if time.monotonic() >= deadline: raise TimeoutError('batch_profile_budget')
                live.record_issued(e.arrays['issued_control'][i], physics_index=i, episode_id=episode_id)
            snapshot = live.snapshot(configuration=name, context=e.context, origin_control=128, episode_id=episode_id)
            drive = np.repeat(e.arrays['issued_control'][256:296:2][None].astype(float), 8, axis=0)
            offsets = np.arange(8)[:, None, None]+np.arange(20)[None, :, None]/7+np.arange(4)[None, None, :]
            drive[1:] += .0005*np.sin(offsets[1:]); drive = np.clip(drive, -.95, .95)
            predictor = prepared.prepare_projected(model, e.context)
            def call(): return batch.forecast_batch(snapshot, e.states[256], drive, predictor, deadline=deadline)
            warm = call(); profile = cProfile.Profile(); got = profile.runcall(call)
            for a, b in zip(warm, got): helper.compare_forecasts(a, b)
            stats = pstats.Stats(profile)
            functions = []
            for (filename, line, function), (primitive, calls, own, cumulative, callers) in stats.stats.items():
                try: filename = Path(filename).relative_to(frozen).as_posix()
                except ValueError:
                    try: filename = 'candidate/'+Path(filename).relative_to(project).as_posix()
                    except ValueError: pass
                functions.append(dict(file=filename, line=line, function=function, calls=calls,
                    self_ms=1000*own, cumulative_ms=1000*cumulative))
            rows.append(dict(configuration=name, episode_id=episode_id, trace_sha256=e.trace_sha256,
                profiled_total_ms=1000*stats.total_tt,
                by_cumulative=sorted(functions, key=lambda f: -f['cumulative_ms'])[:40],
                by_self=sorted(functions, key=lambda f: -f['self_ms'])[:40]))
        verify_bundle(frozen, frozen.parent/'inputs', handoff['source_commit'])
        assert all(helper.sha(project/name) == digest for name, digest in prior['sources'].items())
        assert helper.sha(__file__) == protocol['runner_sha256']
        if time.monotonic() >= deadline: raise TimeoutError('batch_profile_budget')
        status = 'local_batch_profile_complete'
    except Exception as exc: error = f'{type(exc).__name__}:{exc}'
    result = dict(status=status, error=error, rows=rows, seconds=time.monotonic()-started,
        created_at=datetime.datetime.now().astimezone().isoformat(), protocol_sha256=helper.sha(args.output/'protocol.json'),
        evidence_level='local_fit_cost_diagnosis_only', controller_promoted=False,
        limitations=['two_configurations_only', 'cProfile_adds_overhead', 'not_a_real_time_measurement'])
    payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
    if len(payload.encode('utf8'))+(args.output/'protocol.json').stat().st_size > protocol['output_limit_bytes']:
        raise RuntimeError('batch_profile_output_budget')
    with (args.output/'result.json').open('x', encoding='utf8') as stream: stream.write(payload)
    print(json.dumps(dict(status=status, seconds=result['seconds'], error=error)), flush=True)
    if status != 'local_batch_profile_complete': raise SystemExit(1)


if __name__ == '__main__': main()

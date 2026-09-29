"""One-shot, bounded episode-parallel formal evaluation of frozen v30 models."""
import os
for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_key] = '1'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from koopman.physical_prediction_v29 import known_step
from workflows.identification_prediction_v32 import conditional_rollout, policy_forecast
from workflows.identify_sparse_world_v30 import from_record
from workflows.projected_adapter_v38 import load_episode
from workflows.projected_resource_v38 import resource_limits
from workflows.projected_budget_v38 import reserve, settle, validate_budget, write_budget
from workflows.projected_evaluation_v38 import PATHS, evaluate, expected_records
from workflows.projected_models_v38 import validate_manifest
from workflows.projected_prediction_v38 import forecast_full_commands, replay_planned_inputs
from workflows.projected_protocol_v38 import cases, digest, pulse, validate_case
from workflows.projected_release_v38 import (TRANSFER_ROOT, predictor_binding, read, sha,
    verify_accepted_stage, verify_bundle)
from workflows.run_projected_formal_v38 import check_disk
from workflows.sparse_evaluation_v32 import score_policy_prefix


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False,
        default=lambda a: a.tolist())+'\n', encoding='utf8')


def validate_workers(workers):
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError('formal_analysis_workers')
    return workers


def load_predictors(root, manifest, configuration):
    root = Path(root)
    validate_manifest(manifest, root)
    result = []
    for family, scope in PATHS:
        if family == 'persistence':
            predictor = lambda x, a, c: x.copy()
        elif family == 'known_physics':
            predictor = lambda x, a, c: known_step(x, a, c, angular_damping=float(np.float32(.05)), gyroscopic=True)
        else:
            key = family+'__'+('pooled' if scope == 'pooled' else 'heldout-'+configuration)
            entry = manifest['models'][key]
            if sha(root/entry['path']) != entry['sha256']:
                raise ValueError('formal_prediction_model_hash')
            predictor = from_record(read(root/entry['path']))
        result.append((family, scope, predictor))
    return result


def score_episode(episode, root, manifest, output, *, deadline):
    """Score an already semantically admitted episode, keeping every failure."""
    q = validate_case(episode.case)
    x = np.asarray(episode.states)
    issued = np.asarray(episode.arrays['issued_control'])
    if (q['role'] not in ('validation', 'test') or x.shape != (1025, 11) or issued.shape != (1024, 4)
            or not np.isfinite(x).all() or not np.isfinite(issued).all()
            or not np.array_equal(issued[::2], issued[1::2])
            or episode.acceptance.get('status') != 'identification_semantics_passed'
            or episode.acceptance.get('training_eligible') is not False
            or episode.acceptance.get('run_id') != q['run_id'] or episode.acceptance.get('role') != q['role']
            or episode.acceptance.get('source_commit') != episode.source_commit):
        raise ValueError('formal_analysis_episode')
    def check():
        if time.monotonic() >= deadline:
            raise TimeoutError('formal_analysis_deadline')
    check()
    commands = issued[::2].copy()
    cached = replay_planned_inputs(np.zeros((0, 4)), commands, q['configuration'], episode.context,
                                  origin_control=0, deadline=deadline)
    # Adapter and cache are separately implemented command-only recurrences.
    for expected, actual in ((episode.acceleration, cached['acceleration']),
                            (episode.arrays['pwm'], cached['pwm']),
                            (episode.arrays['causal_rotor_speed'][1:], cached['rotor_speed']),
                            (episode.arrays['actuator_time_s'][1:], cached['physics_time_s'])):
        if not np.array_equal(expected, actual):
            raise ValueError('formal_command_cache_parity')
    predictors = load_predictors(root, manifest, q['configuration'])
    output = Path(output)
    output.mkdir(exist_ok=False, parents=True)
    np.savez_compressed(output/'episode.npz', states=x, issued_control=issued,
        acceleration=cached['acceleration'], rotor_speed=cached['rotor_speed'],
        physics_time_s=cached['physics_time_s'])
    dump(output/'episode.json', dict(case=q, context=asdict(episode.context), source_commit=episode.source_commit,
        trace_sha256=episode.trace_sha256, acceptance=episode.acceptance, arrays_sha256=sha(output/'episode.npz')))
    records = []
    try:
        for family, scope, predictor in predictors:
            check()
            base = dict(run_id=q['run_id'], configuration=q['configuration'], role=q['role'], family=family,
                scope=scope, trace_sha256=episode.trace_sha256,
                predictor_binding_sha256=predictor_binding(manifest, family, scope, q['configuration']))
            for horizon in (1, 20, 60, 128):
                check()
                metric = conditional_rollout(x, cached['acceleration'], predictor, episode.context, horizon)
                metric['conditional_future_recorded_inputs'] = False
                metric['conditional_future_planned_commands'] = True
                records.append(dict(base, mode='conditional_projected', origin_control=128, **metric))
            full = forecast_full_commands(x[0], np.zeros((0, 4)), commands, q['configuration'], episode.context,
                                          predictor, origin_control=0, deadline=deadline)
            np.savez_compressed(output/(family+'__'+scope+'__full.npz'),
                predictions=full['predictions'], commands=full['issued_commands'])
            metric = score_policy_prefix(x[1:], full, 512)
            records.append(dict(base, mode='full_episode', origin_control=0, origins=1, **metric))
            check()
            forecast = policy_forecast(x[256].copy(), issued[:256].copy(), pulse(q)[128:256],
                q['configuration'], episode.context, predictor, deadline=deadline)
            np.savez_compressed(output/(family+'__'+scope+'__policy.npz'),
                predictions=forecast['predictions'], commands=forecast['commands'])
            dump(output/(family+'__'+scope+'__forecasts.json'), dict(
                full={k: v for k, v in full.items() if not isinstance(v, np.ndarray)},
                policy={k: v for k, v in forecast.items() if not isinstance(v, np.ndarray)}))
            for horizon in (20, 60, 128):
                metric = score_policy_prefix(x[257:], forecast, horizon)
                records.append(dict(base, mode='policy_self_recurrence', origin_control=128, origins=1, **metric))
            dump(output/'scores.json', records)
        check()
    finally:
        dump(output/'scores.json', records)
    return dict(scores=records, model_fits=0, command_cache_exact=True,
        artifact_sha256={p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()})


def verify_worker_result(native_exit, result, q, source, freeze_sha, manifest_digest):
    expected = dict(status='completed_projected_case', case=q, source_commit=source,
                    freeze_sha256=freeze_sha, model_manifest_digest=manifest_digest, model_fits=0)
    if type(native_exit) is not int or native_exit != 0 or not isinstance(result, dict):
        raise ValueError('formal_worker_native_failure')
    if any(result.get(k) != v or type(result.get(k)) is not type(v) for k, v in expected.items()):
        raise ValueError('formal_worker_identity')
    expected_rows = [r for r in expected_records(q['role']) if r['run_id'] == q['run_id']]
    rows = result.get('scores', [])
    key = lambda r: tuple(r[k] for k in ('family', 'scope', 'mode', 'horizon_control_intervals'))
    try:
        index = {key(r): r for r in rows}
        if len(rows) != 48 or len(index) != 48:
            raise ValueError('formal_worker_score_inventory')
        for r in expected_rows:
            actual = index[key(r)]
            if any(actual.get(k) != v or type(actual.get(k)) is not type(v) for k, v in r.items()):
                raise ValueError('formal_worker_score_inventory')
    except (KeyError, TypeError) as exc:
        raise ValueError('formal_worker_score_inventory') from exc
    return result


def work(root, transfer, role, case_id, deadline):
    root, transfer = Path(root), Path(transfer)
    matches = [q for q in cases(role) if q['run_id'] == case_id]
    if role not in ('validation', 'test') or len(matches) != 1:
        raise ValueError('formal_analysis_case')
    q = matches[0]
    source = read(transfer/'freeze.json')['source_commit']
    _, manifest = verify_bundle(root, transfer, source)
    freeze_sha = sha(transfer/'freeze.json')
    budget = read(transfer/'budget.json')
    validate_budget(budget, freeze_sha)
    if (not budget['attempts'] or (budget['attempts'][-1]['bucket'], budget['attempts'][-1]['name'],
            budget['attempts'][-1]['status']) != ('analysis', 'formal_analysis:'+role, 'reserved')):
        raise ValueError('formal_analysis_not_reserved')
    acceptance = read(transfer/(role+'-pullback.json'))
    from workflows.projected_release_v38 import stage_identity, stage_directory
    data_source,data_freeze=stage_identity(read(transfer/'freeze.json'),role,freeze_sha)
    if (acceptance.get('role') != role or acceptance.get('source_commit') != data_source
            or acceptance.get('freeze_sha256') != data_freeze):
        raise ValueError('formal_analysis_acceptance')
    output = transfer/(role+'-analysis')/'cases'/case_id
    if output.exists():
        raise ValueError('formal_analysis_case_already_attempted')
    status = dict(status='running', case=q, source_commit=source, freeze_sha256=freeze_sha,
                  model_manifest_digest=digest(manifest), model_fits=0)
    try:
        episode = load_episode(stage_directory(transfer,role)/case_id/'trace.json', q, data_source,
                               acceptance['trace_sha256'][case_id], root)
        status.update(score_episode(episode, root, manifest, output, deadline=deadline))
        status['status'] = 'completed_projected_case'
    except BaseException as exc:
        status.update(status='failed', exception=f'{type(exc).__name__}:{exc}')
        raise
    finally:
        output.mkdir(parents=True, exist_ok=True)
        dump(output/'result.json', status)


def run(root, transfer, role, *, workers=4):
    root, transfer = Path(root), Path(transfer)
    validate_workers(workers)
    if role not in ('validation', 'test'):
        raise ValueError('formal_analysis_role')
    from workflows.collect_koopman_v21_identification import _repository_commit
    source = _repository_commit()
    _, manifest = verify_bundle(root, transfer, source)
    freeze_sha = sha(transfer/'freeze.json')
    acceptance = verify_accepted_stage(root, transfer, role, source, freeze_sha)
    if role == 'test':
        from workflows.projected_release_v38 import verify_collection_release
        verify_collection_release(root, transfer, source, 'test')
    output = transfer/(role+'-analysis')
    if output.exists():
        raise ValueError('formal_analysis_role_already_attempted')
    budget_path = transfer/'budget.json'
    budget = read(budget_path)
    remaining = resource_limits(budget)['analysis_seconds']-budget['charged_seconds']['analysis']
    if remaining < 60:
        raise ValueError('formal_analysis_budget')
    budget = reserve(budget, 'analysis', 'formal_analysis:'+role, remaining)
    write_budget(budget_path, budget)
    started, exit_code = time.monotonic(), 1
    deadline = started+remaining-15
    output.mkdir()
    (output/'cases').mkdir()
    selected, active, completed = cases(role), [], {}
    status = dict(status='running', role=role, source_commit=source, freeze_sha256=freeze_sha,
        model_manifest_digest=digest(manifest), acceptance_digest=digest(acceptance),
        model_fits=0, model_handoff=False, workers=workers, native_workers=[])
    next_case = 0
    def finish(item, forced=False):
        process, q, log = item
        native = process.wait(timeout=10)
        log.close()
        record = dict(case=q['run_id'], native_exit=native, forced_stop=forced)
        status['native_workers'].append(record)
        dump(output/(q['run_id']+'.worker-exit.json'), record)
        return native
    try:
        while next_case < len(selected) or active:
            if time.monotonic() >= deadline:
                raise TimeoutError('formal_analysis_wall_budget')
            while next_case < len(selected) and len(active) < workers:
                check_disk(root, transfer)
                q = selected[next_case]
                log = (output/(q['run_id']+'.log')).open('x')
                command = [sys.executable, '-B', '-m', 'workflows.evaluate_projected_formal_v38',
                    '--stage', role, '--transfer', str(transfer), '--worker-case', q['run_id'], '--deadline', str(deadline)]
                try:
                    process = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                except BaseException:
                    log.close()
                    raise
                active.append((process, q, log))
                next_case += 1
            for item in list(active):
                process, q, log = item
                if process.poll() is None:
                    continue
                native = finish(item)
                active.remove(item)
                case_dir = output/'cases'/q['run_id']
                result = read(case_dir/'result.json') if (case_dir/'result.json').is_file() else None
                verify_worker_result(native, result, q, source, freeze_sha, digest(manifest))
                artifacts = result['artifact_sha256']
                if set(artifacts) != {p.name for p in case_dir.iterdir() if p.is_file() and p.name != 'result.json'}:
                    raise ValueError('formal_worker_artifact_inventory')
                for name, h in artifacts.items():
                    if Path(name).name != name or sha(case_dir/name) != h:
                        raise ValueError('formal_worker_artifact_hash')
                completed[q['run_id']] = result
                print(json.dumps(dict(completed_case=q['run_id'], completed=len(completed), total=24)), flush=True)
                dump(output/'progress.json', dict(completed=list(completed), total=24))
            time.sleep(.1)
        rows = [r for q in selected for r in completed[q['run_id']]['scores']]
        dump(output/'scores.json', rows)
        status.update(status='completed_projected_formal_evaluation', scores_digest=digest(rows),
            evaluation=evaluate(rows, role, bootstrap=True),
            case_result_sha256={q['run_id']: sha(output/'cases'/q['run_id']/'result.json') for q in selected})
        check_disk(root, transfer)
        if time.monotonic() >= deadline:
            raise TimeoutError('formal_analysis_wall_budget')
        exit_code = 0
    except BaseException as exc:
        status.update(status='incomplete', exception=f'{type(exc).__name__}:{exc}')
        raise
    finally:
        for process, q, log in active:
            if process.poll() is None:
                process.kill()
        for item in active:
            finish(item, forced=True)
        elapsed = time.monotonic()-started
        budget = settle(budget, 'analysis', 'formal_analysis:'+role, elapsed, exit_code)
        write_budget(budget_path, budget)
        status['seconds'] = elapsed
        dump(output/'result.json', status)
    validate_budget(budget, freeze_sha)
    return status


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('validation', 'test'), required=True)
    parser.add_argument('--transfer', default=TRANSFER_ROOT)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--worker-case')
    parser.add_argument('--deadline', type=float)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.worker_case:
        if args.deadline is None:
            raise ValueError('formal_worker_deadline_required')
        work(root, args.transfer, args.stage, args.worker_case, args.deadline)
    else:
        run(root, args.transfer, args.stage, workers=args.workers)

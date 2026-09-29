"""Independent saved-array arithmetic and conditional replay before test release.

Uses the frozen predictor for replay, but neither producer score routines nor
producer aggregates for the independent metrics. No fitting or data collection.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from workflows.projected_adapter_v38 import load_episode
from workflows.projected_archive_v38 import (accounted_analysis, _running_code_matches,
    ROTOR_RECOMPUTATION_ATOL, WRENCH_RECOMPUTATION_ATOL)
from workflows.projected_evaluation_v38 import PATHS, evaluate, index_records
from workflows.projected_protocol_v38 import cases, digest
from workflows.projected_release_v38 import read, sha, verify_bundle, predictor_binding, require_evaluation_agreement


def valid(x):
    x = np.asarray(x, float)
    return (np.isfinite(x).all(-1) & (np.abs(x[..., 0]) <= 100)
        & (np.abs(x[..., 5:]) <= 100).all(-1)
        & (np.abs(np.linalg.norm(x[..., 1:5], axis=-1)-1) <= .001))


def errors(truth, prediction):
    truth, prediction = np.asarray(truth, float), np.asarray(prediction, float)
    left = truth[:, 1:5]/np.linalg.norm(truth[:, 1:5], axis=1, keepdims=True)
    right = prediction[:, 1:5]/np.linalg.norm(prediction[:, 1:5], axis=1, keepdims=True)
    rotation = 2*np.arccos(np.minimum(1., np.abs(np.sum(left*right, axis=1))))
    return np.array([(truth[:, 0]-prediction[:, 0])**2, rotation**2,
        ((truth[:, 5:8]-prediction[:, 5:8])**2).mean(1),
        ((truth[:, 8:11]-prediction[:, 8:11])**2).mean(1)]).T


def prefix_metric(truth, prediction, horizon):
    truth, prediction = np.asarray(truth, float), np.asarray(prediction, float)
    n = 2*horizon
    complete = (prediction.ndim == truth.ndim == 2 and prediction.shape[1:] == truth.shape[1:] == (11,)
        and len(prediction) >= n and len(truth) >= n and valid(prediction[:n]).all())
    error = errors(truth[:n], prediction[:n]) if complete else None
    return dict(complete_aggregate=bool(complete), failed_origins=0 if complete else 1,
        endpoint_rmse=np.sqrt(error[-1]).tolist() if complete else None,
        path_rmse=np.sqrt(error.mean(0)).tolist() if complete else None)


def require_metric(actual, expected):
    for name in ('complete_aggregate', 'failed_origins'):
        if actual.get(name) != expected[name] or type(actual.get(name)) is not type(expected[name]):
            raise ValueError('formal_independent_metric:'+name)
    for name in ('endpoint_rmse', 'path_rmse'):
        if expected[name] is None:
            if actual.get(name) is not None:
                raise ValueError('formal_independent_metric:'+name)
        else:
            value = np.asarray(actual.get(name), float)
            # acos(dot(q1,q2)) loses absolute precision near zero rotation.
            # This is arithmetic agreement only; all scientific gates still use
            # the original scores and their unchanged cutoffs.
            if (value.shape != (4,) or not np.isfinite(value).all()
                    or not np.allclose(value, expected[name], rtol=1e-9, atol=[1e-11, 1e-7, 1e-11, 1e-11])):
                raise ValueError('formal_independent_metric:'+name)


def conditional_metric(x, acceleration, predictor, context, horizon, deadline):
    """Replay every legal origin; aggregate independently of producer scoring."""
    starts = np.arange(256, len(acceleration)-2*horizon+1, 2)
    prediction = x[starts].copy()
    alive = np.ones(len(starts), bool)
    summed = np.zeros((len(starts), 4)); endpoint = summed.copy()
    for offset in range(2*horizon):
        if time.monotonic() >= deadline:
            raise TimeoutError('formal_independent_audit_deadline')
        ids = np.flatnonzero(alive)
        if not len(ids):
            break
        try:
            with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
                following = np.asarray(predictor(prediction[ids], acceleration[starts[ids]+offset], context), float)
            if following.shape != (len(ids), 11):
                raise ValueError('formal_independent_prediction_shape')
            good = valid(following)
            prediction[ids] = following
        except (ValueError, FloatingPointError):
            good = np.zeros(len(ids), bool)
        alive[ids[~good]] = False
        ids = ids[good]
        if len(ids):
            endpoint[ids] = errors(x[starts[ids]+offset+1], prediction[ids])
            summed[ids] += endpoint[ids]
    complete = bool(alive.all())
    return dict(complete_aggregate=complete, failed_origins=int((~alive).sum()),
        endpoint_rmse=np.sqrt(endpoint.mean(0)).tolist() if complete else None,
        path_rmse=np.sqrt(summed.mean(0)/(2*horizon)).tolist() if complete else None)


def compare_episode_cache(cache, episode):
    """Keep measured arrays exact; admit tiny command-only reconstruction drift.

    The full independent physical validator must already have accepted episode.
    Compare acceleration in wrench units so tolerances do not depend on mass or
    inertia. Return the admitted producer input for arithmetic replay: substituting
    another platform's reconstruction would evaluate a different input sequence.
    """
    expected = dict(states=episode.states, issued_control=episode.arrays['issued_control'],
        acceleration=episode.acceleration, rotor_speed=episode.arrays['causal_rotor_speed'][1:],
        physics_time_s=episode.arrays['actuator_time_s'][1:])
    if set(cache) != set(expected):
        raise ValueError('formal_independent_cache:inventory')
    values = {}
    differences = {}
    for name, reference in expected.items():
        value = np.asarray(cache[name], float)
        if value.shape != reference.shape or not np.isfinite(value).all() or not np.isfinite(reference).all():
            raise ValueError('formal_independent_cache:'+name)
        delta = np.abs(value-reference)
        if name == 'acceleration':
            delta = delta*np.r_[[episode.context.mass]*3, episode.context.inertia]
            allowed = WRENCH_RECOMPUTATION_ATOL
        elif name == 'rotor_speed':
            allowed = ROTOR_RECOMPUTATION_ATOL
        else:
            allowed = 0.
        if np.any(delta > allowed):
            raise ValueError('formal_independent_cache:'+name)
        differences[name] = float(np.max(delta))
        values[name] = value.copy()
    return values['states'], values['acceleration'], dict(policy='causal-cache-agreement-v1',
        max_rotor_difference=differences['rotor_speed'], max_wrench_difference=differences['acceleration'],
        rotor_atol=ROTOR_RECOMPUTATION_ATOL, wrench_atol=WRENCH_RECOMPUTATION_ATOL,
        measured_state_command_clock_exact=True,
        replay_input='admitted_producer_cache')


def audit_case(episode, directory, root, manifest, *, deadline, cache_agreements=None):
    from workflows.evaluate_projected_formal_v38 import load_predictors
    directory = Path(directory); q = episode.case
    metadata = read(directory/'episode.json')
    if (metadata.get('case') != q or metadata.get('trace_sha256') != episode.trace_sha256
            or metadata.get('source_commit') != episode.source_commit
            or metadata.get('arrays_sha256') != sha(directory/'episode.npz')):
        raise ValueError('formal_independent_episode_binding')
    with np.load(directory/'episode.npz', allow_pickle=False) as cache:
        states, acceleration, agreement = compare_episode_cache(cache, episode)
    if cache_agreements is not None:
        cache_agreements.append(dict(run_id=q['run_id'], **agreement))
    rows = read(directory/'scores.json')
    index = {(r['family'], r['scope'], r['mode'], r['horizon_control_intervals']): r for r in rows}
    checked = 0
    for family, scope, predictor in load_predictors(root, manifest, q['configuration']):
        for horizon in (1, 20, 60, 128):
            metric = conditional_metric(states, acceleration, predictor,
                                        episode.context, horizon, deadline)
            require_metric(index[(family, scope, 'conditional_projected', horizon)], metric)
            checked += 1
        for mode, filename, start, horizons in (
                ('full_episode', 'full', 1, (512,)),
                ('policy_self_recurrence', 'policy', 257, (20, 60, 128))):
            with np.load(directory/(family+'__'+scope+'__'+filename+'.npz'), allow_pickle=False) as arrays:
                prediction = arrays['predictions']
                for horizon in horizons:
                    metric = prefix_metric(episode.states[start:], prediction, horizon)
                    require_metric(index[(family, scope, mode, horizon)], metric)
                    checked += 1
    if checked != 48:
        raise ValueError('formal_independent_case_inventory')
    return checked


def audit(root, raw, directory, budget_path, expected_result_sha, *, remote_bytes, analysis_transfer=None):
    """Run from the verified local clone on newly pulled server analysis output."""
    root, raw, directory = Path(root), Path(raw), Path(directory)
    destination = directory.parent/(directory.name+'-audit.json')
    if destination.exists() or sha(directory/'result.json') != expected_result_sha:
        raise ValueError('formal_independent_result_or_existing_audit')
    role = read(directory/'result.json')['role']
    selected = cases(role)
    if role not in ('validation', 'test'):
        raise ValueError('formal_independent_role')
    local = sum(p.stat().st_size for p in raw.parent.parent.rglob('*') if p.is_file())
    if type(remote_bytes) is not int or remote_bytes < 0 or remote_bytes+local >= 4*1024**3:
        raise ValueError('formal_independent_disk_cap')
    with accounted_analysis(budget_path, 'independent_analysis:'+role) as deadline:
        source = read(raw/'inputs/freeze.json')['source_commit']
        freeze_sha = sha(raw/'inputs/freeze.json')
        data_source,data_freeze=source,freeze_sha
        _, manifest = verify_bundle(raw/'source', raw/'inputs', source)
        acceptance = read(raw.parent/'acceptance.json')
        if analysis_transfer is not None:
            from workflows.projected_release_v38 import stage_identity
            analysis_transfer=Path(analysis_transfer)
            frozen=read(analysis_transfer/'freeze.json')
            source=frozen['source_commit'];freeze_sha=sha(analysis_transfer/'freeze.json')
            _,manifest=verify_bundle(root,analysis_transfer,source)
            if stage_identity(frozen,role,freeze_sha)!=(data_source,data_freeze):
                raise ValueError('formal_independent_data_source_identity')
            _running_code_matches(raw/'source',acceptance.get('auditor_revision'))
        else:
            _running_code_matches(raw/'source')
        if read(budget_path)['freeze_sha256'] != freeze_sha:
            raise ValueError('formal_independent_budget_identity')
        from workflows.projected_archive_v38 import validate_inventory_identity
        from workflows.formal_evidence_v25 import verify_raw
        inventory = read(raw/'inventory.json')
        verify_raw(raw, inventory)
        validate_inventory_identity(inventory, role, data_source, data_freeze)
        if (acceptance.get('status') != 'projected_formal_source_runtime_inventory_pullback_accepted'
                or acceptance.get('source_commit') != data_source or acceptance.get('freeze_sha256') != data_freeze
                or acceptance.get('role') != role):
            raise ValueError('formal_independent_raw_acceptance')
        result, rows = read(directory/'result.json'), read(directory/'scores.json')
        expected = dict(status='completed_projected_formal_evaluation', role=role, source_commit=source,
            freeze_sha256=freeze_sha, model_manifest_digest=digest(manifest), acceptance_digest=digest(acceptance),
            scores_digest=digest(rows), model_fits=0, model_handoff=False)
        if any(result.get(k) != v or type(result.get(k)) is not type(v) for k, v in expected.items()):
            raise ValueError('formal_independent_result_binding')
        index_records(rows, role)
        native = result.get('native_workers', [])
        ids = {q['run_id'] for q in selected}
        if (len(native) != len(ids) or {r['case'] for r in native} != ids
                or any(type(r['native_exit']) is not int or r['native_exit'] != 0
                       or r.get('forced_stop') is not False for r in native)
                or set(result.get('case_result_sha256', {})) != ids):
            raise ValueError('formal_independent_native_inventory')
        rebuilt, cache_agreements = [], []
        for q in selected:
            name = q['run_id']; case_dir = directory/'cases'/name
            if sha(case_dir/'result.json') != result['case_result_sha256'][name]:
                raise ValueError('formal_independent_case_result_hash')
            child = read(case_dir/'result.json')
            from workflows.evaluate_projected_formal_v38 import verify_worker_result
            verify_worker_result(0, child, q, source, freeze_sha, digest(manifest))
            artifacts = child['artifact_sha256']
            if set(artifacts) != {p.name for p in case_dir.iterdir() if p.is_file() and p.name != 'result.json'}:
                raise ValueError('formal_independent_artifact_inventory')
            for name, h in artifacts.items():
                if Path(name).name != name or sha(case_dir/name) != h:
                    raise ValueError('formal_independent_artifact_hash')
            case_rows = read(case_dir/'scores.json')
            if child['scores'] != case_rows:
                raise ValueError('formal_independent_case_scores')
            for row in case_rows:
                if (row.get('trace_sha256') != acceptance['trace_sha256'][q['run_id']]
                        or row.get('predictor_binding_sha256') != predictor_binding(manifest, row['family'], row['scope'], q['configuration'])):
                    raise ValueError('formal_independent_score_binding')
            episode = load_episode(raw/role/q['run_id']/'trace.json', q, data_source,
                                   acceptance['trace_sha256'][q['run_id']], raw/'source')
            audit_case(episode, case_dir, root, manifest, deadline=deadline, cache_agreements=cache_agreements)
            rebuilt.extend(case_rows)
            print(json.dumps(dict(independently_checked=q['run_id'], rows=len(rebuilt))), flush=True)
        if rebuilt != rows:
            raise ValueError('formal_independent_aggregate')
        require_evaluation_agreement(result['evaluation'], evaluate(rows, role, bootstrap=True))
        report = dict(status='independent_projected_analysis_accepted', role=role, source_commit=source,
            freeze_sha256=freeze_sha, result_sha256=sha(directory/'result.json'), scores_sha256=sha(directory/'scores.json'),
            raw_acceptance_sha256=sha(raw.parent/'acceptance.json'), rows_checked=len(rows),
            conditional_replayed=576, full_and_policy_array_metrics=576, model_fits=0, model_handoff=False,
            evaluation_pass=result['evaluation']['pass'], predictor_math='reuses_frozen_predictors',
            independent_arithmetic=True, full_policy_regeneration=False, cache_agreements=cache_agreements)
    destination.write_text(json.dumps(report, indent=2)+'\n', encoding='utf8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw', required=True)
    parser.add_argument('--analysis', required=True)
    parser.add_argument('--budget', required=True)
    parser.add_argument('--result-sha256', required=True)
    parser.add_argument('--remote-bytes', required=True, type=int)
    parser.add_argument('--transfer', help='New analysis inputs only when auditing inherited validation')
    args = parser.parse_args()
    print(json.dumps(audit(Path(__file__).resolve().parents[1], args.raw, args.analysis,
        args.budget, args.result_sha256, remote_bytes=args.remote_bytes, analysis_transfer=args.transfer), indent=2))

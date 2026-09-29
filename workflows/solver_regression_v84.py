"""Six bounded offline NLP regressions at authenticated historical origins.

All arms initialize from the identical recorded physical plan. The parent
independently checks every supplied incumbent and worker plan under its own
model. This is solver-capability evidence, never closed-loop control benefit.
Run the parent under the usual 600-second process-group supervisor as a final
outer hard bound. Children reserve 15 seconds of their 90-second envelope for
the existing supervisor's TERM/KILL cleanup; no physics or fitting is called.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np


ARMS = ('P', 'Rc_0.001', 'Rc_0.1')


def plain(value):
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, dict): return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [plain(v) for v in value]
    return value


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_identity_map(identities):
    result = {}
    for path, sha in identities.items():
        key = str(Path(path).resolve())
        if key in result and result[key] != sha:
            raise ValueError('regression_identity_alias_conflict')
        result[key] = sha
    return result


def verify_request_binding(group, request):
    # Both sides must have canonical keys before JSON serialization. Do not
    # conflate an input-path mismatch with a support/model content mismatch.
    if group['identities'] != request['expected_identities']:
        raise ValueError('regression_request_input_identities')
    if group['common_support_model_sha256'] != request['expected_support_model']:
        raise ValueError('regression_request_support_model')
    if group['common_support_id'] != request['expected_support_id']:
        raise ValueError('regression_request_support_id')


def summarize_solver_outcomes(entries):
    attempted = completed = converged = failures = preserved = 0
    for entry in entries:
        child = entry.get('child')
        receipt = entry['receipt']
        valid_worker = receipt['native_exit'] == 0 and receipt['group_stopped'] is True
        solver = child.get('solver') if child is not None else None
        attempted += int(solver is not None)
        output_ok = valid_worker and child is not None and child.get('commands') is not None
        completed += int(output_ok)
        converged += int(output_ok and solver is not None and solver.get('success') is True)
        failures += int(not valid_worker or child is None)
        preserved += int(entry['selection']['exact_feasible'])
    if not attempted:
        status = 'failed_all_workers_before_nlp'
    elif failures or len(entries) != 6:
        status = 'completed_with_worker_failures'
    elif completed != 6:
        status = 'completed_with_nlp_failures_or_timeouts'
    elif converged != 6:
        status = 'completed_with_unconverged_nlp'
    else:
        status = 'completed_offline_regression_not_control_benefit'
    return dict(status=status, nlp_attempted=attempted, nlp_plan_outputs=completed,
                nlp_converged=converged, worker_failures=failures,
                preserved_feasible_plans=preserved)


def write_new(path, value):
    with Path(path).open('x', encoding='utf8') as f:
        json.dump(plain(value), f, indent=2, allow_nan=False)


def child_timeout(elapsed, total=600):
    available = total - elapsed - 20  # 15 cleanup + 5 final evidence write
    return min(75., available) if available >= 1 else None


def bound_violation(values, lower, upper):
    v = np.asarray(values, float)
    return float(max(0., np.max(np.asarray(lower) - v), np.max(v - np.asarray(upper))))


def select_verified_plan(checker, origin, state, previous, reference, recorded,
                         *, candidate=None, worker_status):
    """Ignore worker costs/feasibility flags; only independent checks select."""
    plans = dict(recorded)
    if candidate is not None: plans['new_nlp_plan'] = candidate
    checks, feasible = {}, []
    for name, plan in plans.items():
        a = np.asarray(plan, float)
        if a.shape != (checker.horizon, 4) or not np.isfinite(a).all():
            check = dict(feasible=False, cost=None, reason='full_plan_invalid')
        else:
            check = checker.check(origin, state, a, previous, reference)
        checks[name] = {k: v for k, v in check.items() if k != 'predictions'}
        if check['feasible'] and check['cost'] is not None and np.isfinite(check['cost']):
            feasible.append((float(check['cost']), name, a.astype(np.float32)))
    old = [r for r in feasible if r[1] != 'new_nlp_plan']
    incumbent = min(old, key=lambda r: r[0]) if old else None
    chosen = min(feasible, key=lambda r: r[0]) if feasible else None
    nlp_return = next((r for r in feasible if r[1] == 'new_nlp_plan'), None)
    return dict(exact_feasible=chosen is not None, selected_source=chosen[1] if chosen else None,
        cost=chosen[0] if chosen else None, commands=chosen[2] if chosen else None,
        best_recorded_source=incumbent[1] if incumbent else None,
        best_recorded_cost=incumbent[0] if incumbent else None,
        improvement_over_best_recorded=incumbent[0]-chosen[0] if incumbent and chosen else None,
        checks=checks, worker_status=worker_status,
        known_feasible_plan_missed=bool(incumbent and (chosen is None or chosen[0] > incumbent[0])),
        nlp_return_missed_known_feasible=bool(incumbent and (
            nlp_return is None or nlp_return[0] > incumbent[0]+1e-8)),
        nlp_comparison_tolerance=1e-8,
        global_optimum_claimed=False, closed_loop_benefit_claimed=False)


def exact_residuals(checker, origin, state, previous, reference, commands):
    """Numerical residuals in original units; no mixed-unit scalar score."""
    from koopman.control_objective_v44 import state_features
    from koopman.bounded_mpc_v44 import COMMAND_ATOL
    from koopman.preview_solver_v80 import PLANNING_MARGIN
    checked = checker.check(origin, state, commands, previous, reference)
    if not checked['feasible']:
        return dict(feasible=False, reason=checked['reason'])
    a = np.asarray(commands, np.float32).astype(float)
    x = checked['predictions']; d = checker.domain
    raw = np.asarray([checker.plant.allocator.command(u, pre_tam=True)['pwm_raw'] for u in a])
    features = state_features(x, checker.mask)
    return dict(feasible=True,
        command_support=bound_violation(a, d.command_lower-COMMAND_ATOL, d.command_upper+COMMAND_ATOL),
        command_mask=float(max(0., np.max(abs(a*(1-checker.mask)))-COMMAND_ATOL)),
        command_slew=float(max(0., np.max(abs(np.diff(np.vstack([previous, a]), axis=0)))-.02-COMMAND_ATOL)),
        pwm_saturation=float(max(0., np.max(abs(raw))-.95-COMMAND_ATOL)),
        pwm_interior=float(max(0., PLANNING_MARGIN-np.min(abs(abs(raw)-float(np.float32(.02)))))),
        state_support=bound_violation(features, d.state_lower-1e-12, d.state_upper+1e-12),
        height_m=bound_violation(x[:, 0], 3.5, 7.5),
        linear_speed_m_s=float(max(0., np.max(np.linalg.norm(x[:, 5:8], axis=1))-1.5)),
        angular_speed_rad_s=float(max(0., np.max(np.linalg.norm(x[:, 8:11], axis=1))-3.)),
        tilt_cosine=float(max(0., .5-1e-12-np.min(features[:, 3]))))


def load_group(config, paths, assets, models, historical_models):
    from workflows.analyze_initial_plans_v82 import (
        _read_trace, _bind_model, _origin_record, verify_common_origins, ARMS as OLD_ARMS)
    from workflows.analyze_executed_prediction_v82 import MODEL_CONTENT_SHA256
    from koopman.preview_solver_v82 import load_model, verify_support
    from koopman.compact_residual_v84 import validate_record, prepare_compact
    from koopman.physical_control_v76 import PhysicalPredictor
    from koopman.preview_solver_v80 import ExactChecker
    from workflows.identify_sparse_world_v30 import from_record
    from workflows.protocol_v77 import settings
    models, historical_models = Path(models).resolve(), Path(historical_models).resolve()
    paths = {name: str(Path(path).resolve()) for name, path in paths.items()}
    if set(paths) not in ({'physics'}, set(OLD_ARMS)):
        raise ValueError('regression_trace_inventory')
    loaded = {}; identities = {}; records = {}
    if len(paths) > 1:
        for ridge, expected in MODEL_CONTENT_SHA256.items():
            path = Path(historical_models) / f'pooled__learned_{ridge}.json'
            model = load_model(path, digest(path)); verify_support(model, assets)
            if model.record['content_sha256'] != expected:
                raise ValueError('regression_historical_model_identity')
            loaded[ridge] = model; identities[str(path)] = digest(path)
    physical_record = json.loads(Path(assets.model_path).read_text(encoding='utf8'))
    physical = from_record(physical_record)
    for ridge in ('0.001', '0.1'):
        path = Path(models) / f'pooled__Rc_{ridge}.json'
        record = json.loads(path.read_text(encoding='utf8'))
        prior, _ = validate_record(record)
        if (record['ridge'] != float(ridge)
                or record['physical_prior']['fit_episode_hashes'] != physical_record['fit_episode_hashes']
                or record['physical_prior']['fit_source'] != physical_record['fit_source']
                or not np.array_equal(prior.matrix[:, 10:16], physical.matrix[:, 10:16])
                or prior.angular_damping != physical.angular_damping):
            raise ValueError('regression_matched_physical_prior')
        records['Rc_'+ridge] = record; identities[str(path)] = digest(path)
    infos, origins, plans, sources = {}, {}, {}, {}
    for arm, path in paths.items():
        data, source = _read_trace(path)
        _bind_model(data, arm, assets, loaded)
        info, origin, plan, detail = _origin_record(data, assets)
        if info['case']['configuration'] != config: raise ValueError('regression_configuration')
        infos[arm], origins[arm], plans['recorded_'+arm] = info, origin, plan
        sources[arm] = dict(**source, **detail)
        identities[str(Path(path))] = source['trace_sha256']
    common_check = verify_common_origins(infos) if len(infos) == 3 else dict(
        common_origin_source='single_authenticated_physics_origin_reused_for_all_new_arms')
    common = infos['physics']; context = assets.context(config)
    predictors = {'P': PhysicalPredictor(physical, context, identified=True),
        **{name: prepare_compact(record, context) for name, record in records.items()}}
    checkers = {name: ExactChecker(assets.domains[config], p, **settings('depth4_h20'))
                for name, p in predictors.items()}
    return dict(common=common, origin=origins['physics'], plans=plans, sources=sources,
        identities=canonical_identity_map(identities), common_check=common_check, predictors=predictors, checkers=checkers,
        domain=assets.domains[config], common_support_id=assets.domains[config].identity,
        common_support_model_sha256=assets.model_sha256)


def worker(request_path, output_path):
    from workflows.analyze_executed_prediction_v82 import load_analysis_assets
    from koopman.continuous_mpc_v80 import ContinuousMPC
    from workflows.protocol_v77 import settings
    request = json.loads(Path(request_path).read_text(encoding='utf8'))
    for path, expected in request['expected_identities'].items():
        if digest(path) != expected: raise ValueError('regression_input_changed')
    assets = load_analysis_assets(Path(request['root']), request['assets'])
    group = load_group(request['configuration'], request['paths'], assets,
                       request['models'], request['historical_models'])
    verify_request_binding(group, request)
    model = request['model']; info = group['common']; origin = group['origin']
    solver = ContinuousMPC(group['domain'], group['predictors'][model],
                           **settings('depth4_h20'), max_iterations=600, solve_seconds=60.)
    result = solver.solve(origin=origin, initial_state=info['state'],
        baseline=group['plans']['recorded_physics'], previous=info['startup_command'],
        reference=info['case']['reference'])
    result.pop('predictions', None)
    result.update(configuration=request['configuration'], model=model,
                  initial_plan_sha256=group['sources']['physics']['plan_sha256'])
    write_new(output_path, result)


def run(traces, assets_path, models, historical_models, root, output):
    from workflows.analyze_executed_prediction_v82 import load_analysis_assets, analysis_platform
    from workflows.run_continuous_v76 import run as supervised_run
    if sys.platform != 'linux': raise ValueError('regression_linux_process_group_required')
    started = time.monotonic(); output = Path(output)
    root, assets_path = Path(root).resolve(), Path(assets_path).resolve()
    models, historical_models = Path(models).resolve(), Path(historical_models).resolve()
    output.mkdir(parents=True, exist_ok=False)
    entries = json.loads(Path(traces).read_text(encoding='utf8'))
    if set(entries) != {'base', 'uuv4'}: raise ValueError('regression_configuration_inventory')
    entries = {config: {arm: str(Path(path).resolve()) for arm, path in paths.items()}
               for config, paths in entries.items()}
    assets = load_analysis_assets(Path(root), assets_path)
    report = dict(schema='offline-solver-regression-v84/1', status='running',
        global_optimum_claimed=False, closed_loop_benefit_claimed=False, new_physics_runs=0,
        new_fits=0, maximum_solves=6, total_wall_seconds_limit=600,
        per_solve_limits=dict(iterations=600, cpu_seconds=60, execution_wall_seconds=75,
                              cleanup_reserve_seconds=15, wall_envelope_seconds=90),
        same_initialization='recorded_physics_first_plan_for_all_models',
        historical_plans_used_only_as_initialization_and_offline_incumbents=True,
        common_origin_sources={}, analysis_platform=analysis_platform(), solves=[])
    def save():
        report['wall_seconds'] = time.monotonic()-started
        (output/'report.json').write_text(json.dumps(plain(report), indent=2, allow_nan=False), encoding='utf8')
    save()
    try:
        for config in ('base', 'uuv4'):
            group = load_group(config, entries[config], assets, models, historical_models)
            report['common_origin_sources'][config] = dict(sources=group['sources'],
                common_check=group['common_check'], input_identities=group['identities'],
                support_model_sha256=group['common_support_model_sha256'], support_id=group['common_support_id'])
            info, origin = group['common'], group['origin']
            for model in ARMS:
                timeout = child_timeout(time.monotonic()-started)
                if timeout is None:
                    report['status'] = 'budget_exhausted'; return report
                checker = group['checkers'][model]
                initial_check = checker.check(origin, info['state'], group['plans']['recorded_physics'],
                                              info['startup_command'], info['case']['reference'])
                name = config+'__'+model; request_path = output/(name+'.request.json')
                child_path = output/(name+'.child.json')
                request = dict(root=str(Path(root).resolve()), assets=str(Path(assets_path).resolve()),
                    models=str(Path(models).resolve()), historical_models=str(Path(historical_models).resolve()),
                    configuration=config, model=model, paths=entries[config],
                    expected_identities=group['identities'], expected_support_model=group['common_support_model_sha256'],
                    expected_support_id=group['common_support_id'])
                write_new(request_path, request)
                timeout = child_timeout(time.monotonic()-started)
                if timeout is None:
                    report['status'] = 'budget_exhausted'; return report
                receipt = supervised_run([sys.executable, '-B', '-m', 'workflows.solver_regression_v84',
                    '--worker', str(request_path.resolve()), '--output', str(child_path.resolve())],
                    output/(name+'.log'), timeout)
                child = json.loads(child_path.read_text(encoding='utf8')) if child_path.exists() else None
                if child is not None and (child.get('configuration') != config or child.get('model') != model
                        or child.get('initial_plan_sha256') != group['sources']['physics']['plan_sha256']):
                    raise ValueError('regression_child_identity')
                worker_status = child.get('reason') or child['status'] if child else 'child_failed_or_timeout'
                candidate = child.get('commands') if child is not None and receipt['native_exit'] == 0 else None
                selected = select_verified_plan(checker, origin, info['state'], info['startup_command'],
                    info['case']['reference'], group['plans'], candidate=candidate, worker_status=worker_status)
                residuals = exact_residuals(checker, origin, info['state'], info['startup_command'],
                    info['case']['reference'], selected['commands']) if selected['exact_feasible'] else None
                report['solves'].append(dict(configuration=config, model=model, receipt=receipt,
                    initialized_from=group['sources']['physics']['plan_sha256'],
                    initial_plan_feasible=initial_check['feasible'], child=child,
                    selection=selected, exact_constraint_residuals=residuals,
                    optimizer_constraint_residual=None if child is None else child.get('constraint_violation')))
                save()
                if not receipt['group_stopped']:
                    raise RuntimeError('regression_child_cleanup_failed')
                if child is None or receipt['native_exit'] != 0:
                    report['solver_outcomes'] = summarize_solver_outcomes(report['solves'])
                    report['status'] = report['solver_outcomes']['status']
                    return report
                if not selected['exact_feasible']:
                    report['status'] = 'no_feasible_plan'; return report
        report['solver_outcomes'] = summarize_solver_outcomes(report['solves'])
        report['status'] = report['solver_outcomes']['status']
        return report
    except BaseException as exc:
        report.update(status='failed', exception=type(exc).__name__+':'+str(exc))
        raise
    finally:
        save()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--worker', type=Path)
    p.add_argument('--traces', type=Path)
    p.add_argument('--assets', type=Path)
    p.add_argument('--models', type=Path)
    p.add_argument('--historical-models', type=Path)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    if a.worker:
        worker(a.worker, a.output)
    else:
        if any(v is None for v in (a.traces, a.assets, a.models)):
            p.error('--traces, --assets and --models are required')
        historical = a.historical_models or a.root/'docs/evidence/phase9/learned-velocity-v81-20260926/normalized-quaternion'
        result = run(a.traces, a.assets, a.models, historical, a.root, a.output)
        print(json.dumps(dict(status=result['status'], solves=len(result['solves']), wall_seconds=result['wall_seconds'])))
        if result['status'] != 'completed_offline_regression_not_control_benefit': return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

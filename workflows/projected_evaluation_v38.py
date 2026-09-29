"""Episode-paired formal gates. No data admission or role release by a score alone."""
import numpy as np

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from workflows.projected_protocol_v38 import cases

PATHS = [('nonlinear', 'pooled'), ('nonlinear', 'heldout'), ('linear', 'pooled'),
         ('linear', 'heldout'), ('known_physics', 'none'), ('persistence', 'none')]
METRICS = ('endpoint_rmse', 'path_rmse')


def policy():
    return dict(version='projected-formal-v38-fixed-evaluation', roles=['validation', 'test'],
        paths=[list(v) for v in PATHS], conditional_horizons=[1, 20, 60, 128],
        primary_accuracy_horizons=[20, 60, 128], start_control=128,
        full_episode_control_horizon=512, full_episode_accuracy='descriptive; completeness required',
        policy_origins=[128], policy_horizons=[20, 60, 128], policy_maximum_horizon=128,
        primary_scopes=['pooled', 'heldout'], denominator_floor=[.001]*4,
        conditional_limits=dict(macro=.95, each_configuration_macro=1.05,
            each_configuration_group=1.10, over_linear_macro=.95, each_configuration_over_linear=1.05),
        policy_each_configuration_macro_max=1.05,
        velocity_gate=dict(modes=['conditional_projected', 'policy_self_recurrence'],
            normalized_velocity_ratio_max=.90, minimum_improved_episodes_per_configuration=2,
            total_episodes_per_configuration=3, zero_over_zero_ratio=1., improvement='strict_S_less_than_B'),
        all_six_paths_complete_required=True,
        bootstrap=dict(replicates=2000, seed=9600, percentiles=[2.5, 97.5],
            unit='configuration_stratified_paired_episode', promotion_gate=False),
        known_physics='descriptive; no unique learning benefit inferred from parity',
        complete_lift_recurrence=False, model_handoff=False)


def expected_records(role):
    if role not in ('validation', 'test'):
        raise ValueError('formal_score_role')
    records = []
    for q in cases(role):
        for family, scope in PATHS:
            for mode, horizons in (('conditional_projected', (1, 20, 60, 128)),
                                   ('full_episode', (512,)), ('policy_self_recurrence', (20, 60, 128))):
                for horizon in horizons:
                    origin = 0 if mode == 'full_episode' else 128
                    count = 385-horizon if mode == 'conditional_projected' else 1
                    records.append(dict(run_id=q['run_id'], configuration=q['configuration'], role=role,
                        family=family, scope=scope, mode=mode, horizon_control_intervals=horizon,
                        origin_control=origin, origins=count))
    return records


def _key(row):
    return tuple(row[k] for k in ('run_id', 'family', 'scope', 'mode', 'horizon_control_intervals'))


def index_records(records, role):
    expected = {_key(row): row for row in expected_records(role)}
    index = {}
    for row in records:
        try:
            key = _key(row)
            fields = expected[key]
            if key in index or any(row.get(k) != v or type(row.get(k)) is not type(v) for k, v in fields.items()):
                raise ValueError('formal_score_inventory')
            if (type(row.get('complete_aggregate')) is not bool or type(row.get('failed_origins')) is not int
                    or not 0 <= row['failed_origins'] <= row['origins']):
                raise ValueError('formal_score_failure_semantics')
            if row['complete_aggregate']:
                if row['failed_origins']:
                    raise ValueError('formal_score_failure_semantics')
                for metric in METRICS:
                    a = np.asarray(row[metric], dtype=float)
                    if a.shape != (4,) or not np.isfinite(a).all() or np.any(a < 0):
                        raise ValueError('formal_score_metric')
            elif not row['failed_origins'] or any(row[m] is not None for m in METRICS):
                raise ValueError('formal_score_failure_semantics')
            index[key] = row
        except (KeyError, TypeError) as exc:
            raise ValueError('formal_score_inventory') from exc
    if set(index) != set(expected):
        raise ValueError('formal_score_inventory')
    return index


def _ratio(a, b):
    # Nonnegative scores, exact zero tie. A tiny nonzero baseline is not a tie.
    a, b = np.broadcast_arrays(np.asarray(a, float), np.asarray(b, float))
    result = np.ones_like(a)
    np.divide(a, b, out=result, where=b != 0)
    result = np.where((b == 0) & (a > 0), np.inf, result)
    return float(result) if result.ndim == 0 else result


def _finite(value):
    return float(value) if np.isfinite(value) else None


def _comparison(index, catalog, mode, scope, horizon, metric):
    triples = [[index[(q['run_id'], family, s, mode, horizon)]
                for family, s in (('nonlinear', scope), ('linear', scope), ('persistence', 'none'))]
               for q in catalog]
    if not all(row['complete_aggregate'] for triple in triples for row in triple):
        return None
    candidate, linear, persistence = [np.array([triple[i][metric] for triple in triples]) for i in range(3)]
    denominator = np.maximum(persistence, .001)
    return candidate/denominator, linear/denominator, persistence/denominator


def bootstrap_indices(role):
    catalog = cases(role)
    if role not in ('validation', 'test'):
        raise ValueError('formal_score_role')
    rng = np.random.default_rng(9600)
    groups = [np.flatnonzero([q['configuration'] == c for q in catalog]) for c in SUPPORTED_EMBODIMENTS]
    return np.concatenate([rng.choice(g, size=(2000, 3), replace=True) for g in groups], axis=1)


def evaluate(records, role, *, bootstrap=False):
    index = index_records(records, role)
    catalog = cases(role)
    p = policy()
    masks = {c: np.array([q['configuration'] == c for q in catalog]) for c in SUPPORTED_EMBODIMENTS}
    gates, intervals = [], []
    sampling = bootstrap_indices(role) if bootstrap else None
    for mode in ('conditional_projected', 'policy_self_recurrence'):
        for scope in ('pooled', 'heldout'):
            for horizon in (20, 60, 128):
                for metric in METRICS:
                    item = dict(mode=mode, scope=scope, horizon=horizon, metric=metric,
                                pass_=False, accuracy_pass=False, velocity_pass=False)
                    values = _comparison(index, catalog, mode, scope, horizon, metric)
                    if values is not None:
                        candidate, linear, persistence = values
                        groups = {c: candidate[m].mean(0) for c, m in masks.items()}
                        relative = _ratio(candidate.mean(), linear.mean())
                        config_relative = {c: _ratio(candidate[m].mean(), linear[m].mean()) for c, m in masks.items()}
                        score = candidate[:, 2:].mean(1)
                        base = persistence[:, 2:].mean(1)
                        velocity_ratio = _ratio(score.mean(), base.mean())
                        wins = {c: int(np.count_nonzero(score[m] < base[m])) for c, m in masks.items()}
                        velocity_pass = velocity_ratio <= .90 and min(wins.values()) >= 2
                        if mode == 'conditional_projected':
                            accuracy = (candidate.mean() <= .95
                                and all(v.mean() <= 1.05 and v.max() <= 1.10 for v in groups.values())
                                and relative <= .95 and max(config_relative.values()) <= 1.05)
                        else:
                            accuracy = all(v.mean() <= 1.05 for v in groups.values())
                        item.update(normalized_macro=float(candidate.mean()),
                            per_configuration_groups={c: v.tolist() for c, v in groups.items()},
                            over_linear_macro=_finite(relative),
                            per_configuration_over_linear={c: _finite(v) for c, v in config_relative.items()},
                            velocity_ratio=_finite(velocity_ratio), velocity_episode_wins=wins,
                            accuracy_pass=bool(accuracy), velocity_pass=bool(velocity_pass),
                            pass_=bool(accuracy and velocity_pass))
                        if sampling is not None:
                            macro = candidate.mean(1)[sampling].mean(1)
                            ratio = _ratio(score[sampling].mean(1), base[sampling].mean(1))
                            # Undefined/infinite improvement ratios remain explicitly unavailable.
                            ci = np.percentile(ratio, [2.5, 97.5]).tolist() if np.isfinite(ratio).all() else None
                            intervals.append(dict(mode=mode, scope=scope, horizon=horizon, metric=metric,
                                normalized_macro_95=np.percentile(macro, [2.5, 97.5]).tolist(), velocity_ratio_95=ci))
                    item['pass'] = item.pop('pass_')
                    gates.append(item)
    all_complete = all(row['complete_aggregate'] for row in index.values())
    return dict(role=role, all_paths_complete=all_complete, expected_records=len(index), gates=gates,
        bootstrap=dict(p['bootstrap'], intervals=intervals) if bootstrap else None,
        model_handoff=False) | {'pass': bool(all_complete and all(g['pass'] for g in gates))}

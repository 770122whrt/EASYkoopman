"""Local formal-contract counterexamples; none are simulation evidence."""
import copy
from pathlib import Path

import numpy as np
import pytest


def test_catalog_is_new_disjoint_fixed_and_nontraining():
    from workflows.projected_protocol_v38 import cases, protocol, validate_case
    from workflows.identification_protocol_v29 import cases as old29
    from workflows.identification_protocol_v32 import cases as old32
    qs = cases()
    assert len(qs) == len({q['run_id'] for q in qs}) == len({q['seed'] for q in qs}) == 56
    assert {r: len(cases(r)) for r in ('preflight', 'validation', 'test')} == {
        'preflight': 8, 'validation': 24, 'test': 24}
    assert not {q['seed'] for q in qs} & {q['seed'] for q in old29() + old32()}
    assert sum(q['intervals'] for q in qs) == 26624
    assert protocol()['resource_cap'] == dict(collector_seconds=5400, native_case_seconds=300,
        native_cases=56, analysis_seconds=3600, analysis_processes=4, disk_bytes=4 * 1024**3)
    for q in qs:
        validate_case(q)
        assert q['training_eligible'] is False
        for change in ({'seed': 0}, {'intervals': 320}, {'training_eligible': 0}, {'seed': float(q['seed'])}):
            with pytest.raises(ValueError):
                validate_case(dict(q, **change))
    with pytest.raises(ValueError):
        cases('fit')


def test_physical_frequencies_not_cycle_counts_are_retained():
    from workflows.projected_protocol_v38 import cases, pulse, protocol
    from workflows.workpoint_v27 import mechanics
    for q in cases():
        u = pulse(q)
        np.testing.assert_array_equal(u, pulse(copy.deepcopy(q)))
        assert u.dtype == np.float32 and u.shape == (q['intervals'], 4)
        assert not u[:128].any() and np.all(np.abs(u) <= [2, 1, .5, .25])
        mask = np.array(mechanics(q['configuration'])['control_mask_4'], bool)
        assert not u[:, ~mask].any()
        assert np.linalg.matrix_rank(u[128:, mask]) == mask.sum()
    for family in ('multisine', 'chirp'):
        q = next(q for q in cases('validation') if q['configuration'] == 'base' and q['excitation'] == family)
        n = q['intervals'] - 128
        phase = np.random.default_rng(q['seed']).uniform(-np.pi, np.pi, (4, 3))
        ticks = np.arange(n)
        for axis, amp in enumerate([2, 1, .5, .25]):
            if family == 'multisine':
                # Independent physical-time expression, not normalized episode time.
                freq = np.array([1 + axis, 3 + axis, 5 + axis]) / (192 / 60)
                expected = amp * np.sin(2 * np.pi * (ticks / 60)[:, None] * freq + phase[axis]).mean(1)
            else:
                f0, f1 = np.array([1 + axis / 4, 4 + axis]) / (192 / 60)
                time = ticks / 60
                expected = amp * np.sin(2 * np.pi * (f0 * time + .5 * (f1 - f0) / (n / 60) * time**2) + phase[axis, 0])
            np.testing.assert_allclose(pulse(q)[128:, axis], expected, rtol=0, atol=1.2e-7)
    assert protocol()['excitation']['reference_excitation_intervals'] == 192


@pytest.mark.parametrize('role', ['preflight', 'validation', 'test'])
def test_native_zero_never_admits_pending_or_wrong_role_outputs(role):
    from workflows.projected_protocol_v38 import cases, guarded_exit_code
    q = cases(role)[0]
    good = dict(status='completed_identification_pending_acceptance', request=q,
                source_commit='a' * 40, model_fits=0, training_eligible=False)
    assert guarded_exit_code(0, good, q, 'a' * 40) == 0
    assert guarded_exit_code(-9, good, q, 'a' * 40) == 137
    for bad in (None, {}, dict(good, status='started_identification'), dict(good, model_fits=True),
                dict(good, request=dict(q, role='fit')), dict(good, source_commit='b' * 40)):
        assert guarded_exit_code(0, bad, q, 'a' * 40) == 1


def scores(role='validation', candidate=.5):
    from workflows.projected_evaluation_v38 import expected_records
    rows = expected_records(role)
    for r in rows:
        value = candidate if r['family'] == 'nonlinear' else 1.
        r.update(complete_aggregate=True, failed_origins=0,
                 endpoint_rmse=[value] * 4, path_rmse=[value] * 4)
    return rows


def test_exact_score_inventory_and_all_primary_gates():
    from workflows.projected_evaluation_v38 import evaluate
    rows = scores()
    assert len(rows) == 1152
    assert evaluate(rows, 'validation')['pass']
    for bad in (rows[:-1], rows + [rows[0]], [dict(r, role='test') for r in rows]):
        with pytest.raises(ValueError):
            evaluate(bad, 'validation')
    bad = copy.deepcopy(rows)
    bad[0]['origins'] -= 1
    with pytest.raises(ValueError):
        evaluate(bad, 'validation')
    with pytest.raises(ValueError):
        evaluate(rows, 'preflight')


def test_zero_velocity_ties_do_not_pass_gain_even_with_tiny_pose_errors():
    from workflows.projected_evaluation_v38 import evaluate
    rows = scores(candidate=1e-5)
    for r in rows:
        for metric in ('endpoint_rmse', 'path_rmse'):
            r[metric][2:] = [0., 0.]
    result = evaluate(rows, 'validation')
    assert not result['pass']
    assert all(not g['velocity_pass'] and g['velocity_ratio'] == 1. for g in result['gates'])


@pytest.mark.parametrize('family,scope,mode', [
    ('known_physics', 'none', 'conditional_projected'),
    ('linear', 'heldout', 'policy_self_recurrence'),
    ('nonlinear', 'pooled', 'full_episode'),
])
def test_failed_strong_baseline_or_full_prediction_blocks_go(family, scope, mode):
    from workflows.projected_evaluation_v38 import evaluate
    rows = scores()
    r = next(r for r in rows if (r['family'], r['scope'], r['mode']) == (family, scope, mode))
    r.update(complete_aggregate=False, failed_origins=1, endpoint_rmse=None, path_rmse=None)
    assert not evaluate(rows, 'validation')['pass']
    r['endpoint_rmse'] = [0.] * 4
    with pytest.raises(ValueError):
        evaluate(rows, 'validation')


def test_bad_configuration_cannot_hide_in_macro_and_episode_votes_are_paired():
    from workflows.projected_evaluation_v38 import evaluate
    rows = scores(candidate=.01)
    for r in rows:
        if r['family'] == 'nonlinear' and r['configuration'] == 'base':
            r['endpoint_rmse'] = r['path_rmse'] = [1.11, 0, .01, .01]
    assert not evaluate(rows, 'validation')['pass']
    rows = scores(candidate=.01)
    # Two failures of improvement in one configuration, despite a tiny global mean.
    ids = sorted({r['run_id'] for r in rows if r['configuration'] == 'base'})[:2]
    for r in rows:
        if r['family'] == 'nonlinear' and r['run_id'] in ids:
            r['endpoint_rmse'] = r['path_rmse'] = [0, 0, 1., 1.]
    result = evaluate(rows, 'validation')
    assert not result['pass']
    assert all(g['velocity_episode_wins']['base'] == 1 for g in result['gates'])


def test_bootstrap_resamples_episodes_within_configuration_and_is_paired():
    from workflows.projected_evaluation_v38 import bootstrap_indices, evaluate
    from workflows.projected_protocol_v38 import cases
    indices = bootstrap_indices('validation')
    assert indices.shape == (2000, 24)
    np.testing.assert_array_equal(indices, bootstrap_indices('validation'))
    configs = np.array([q['configuration'] for q in cases('validation')])
    assert np.all(configs[indices] == configs[None])
    result = evaluate(scores(), 'validation', bootstrap=True)
    assert result['bootstrap']['unit'] == 'configuration_stratified_paired_episode'
    for item in result['bootstrap']['intervals']:
        assert item['normalized_macro_95'] == [.5, .5]
        assert item['velocity_ratio_95'] == [.5, .5]


def test_manifest_binds_operational_columns_models_and_training_exclusion():
    from workflows.projected_models_v38 import build_manifest, validate_manifest
    root = Path(__file__).resolve().parents[1]
    m = build_manifest(root)
    validate_manifest(m, root)
    assert len(m['models']) == 18 and m['active_output_columns'] == list(range(10, 16))
    assert m['complete_lift_recurrence'] is False and m['model_fits'] == 0
    for name, item in m['models'].items():
        if '__heldout-' in name:
            assert name.split('__heldout-')[1] not in item['training_configurations']
    for change in ({'active_output_columns': list(range(16))}, {'models': {}}, {'model_fits': 1}):
        with pytest.raises(ValueError):
            validate_manifest(dict(m, **change), root)
    bad = copy.deepcopy(m)
    bad['models']['nonlinear__pooled']['active_matrix_sha256'] = '0' * 64
    with pytest.raises(ValueError):
        validate_manifest(bad, root)

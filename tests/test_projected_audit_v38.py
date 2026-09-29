"""Independent arithmetic/file checks; fixtures are not experiment evidence."""
import copy
import json
import numpy as np
import pytest


def test_independent_prefix_uses_all_physics_ticks_and_component_rmse():
    from workflows.audit_projected_v38 import prefix_metric
    truth = np.tile([5., 1., 0., 0., 0., 0., 0., 0., 0., 0., 0.], (4, 1))
    predicted = truth.copy()
    predicted[:, 1:5] *= -1  # Equivalent quaternion, not a rotation error.
    predicted[:, 0] += [1., 2., 3., 4.]
    predicted[:, 5:8] = [3., 0., 0.]
    predicted[:, 8:11] = [0., 6., 0.]
    metric = prefix_metric(truth, predicted, 2)
    np.testing.assert_allclose(metric['endpoint_rmse'], [4., 0., np.sqrt(3), np.sqrt(12)])
    np.testing.assert_allclose(metric['path_rmse'], [np.sqrt(7.5), 0., np.sqrt(3), np.sqrt(12)])
    assert metric['complete_aggregate'] and metric['failed_origins'] == 0
    assert not prefix_metric(truth, predicted[:-1], 2)['complete_aggregate']
    predicted[0, 1:5] = 0
    assert not prefix_metric(truth, predicted, 2)['complete_aggregate']


def test_array_audit_requires_matching_metrics_and_failure_semantics():
    from workflows.audit_projected_v38 import require_metric
    good = dict(complete_aggregate=True, failed_origins=0, endpoint_rmse=[1., 2., 3., 4.], path_rmse=[.1]*4)
    require_metric(good, good)
    for bad in (dict(good, path_rmse=[.2]*4), dict(good, failed_origins=1),
                dict(good, complete_aggregate=False), dict(good, endpoint_rmse=None)):
        with pytest.raises(ValueError, match='formal_independent_metric'):
            require_metric(bad, good)


def test_unbound_or_missing_analysis_audit_cannot_release_test(tmp_path):
    from workflows.projected_release_v38 import verify_analysis_audit
    result = tmp_path/'validation-analysis'; result.mkdir()
    (result/'result.json').write_text('{}')
    (result/'scores.json').write_text('[]')
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_analysis_audit(tmp_path, 'validation', 'a'*40, 'b'*64)
    record = dict(status='independent_projected_analysis_accepted', role='validation',
        source_commit='a'*40, freeze_sha256='b'*64, result_sha256='c'*64,
        scores_sha256='d'*64, rows_checked=1152, model_handoff=False)
    (tmp_path/'validation-analysis-audit.json').write_text(json.dumps(record))
    (tmp_path/'validation-pullback.json').write_text('{}')
    (result/'result.json').write_text('{"evaluation":{"pass":true}}')
    with pytest.raises(ValueError):
        verify_analysis_audit(tmp_path, 'validation', 'a'*40, 'b'*64)
    from workflows.projected_release_v38 import sha
    record.update(result_sha256=sha(result/'result.json'), scores_sha256=sha(result/'scores.json'),
        raw_acceptance_sha256=sha(tmp_path/'validation-pullback.json'), conditional_replayed=576,
        full_and_policy_array_metrics=576, independent_arithmetic=True, model_fits=0, evaluation_pass=True)
    (tmp_path/'validation-analysis-audit.json').write_text(json.dumps(record))
    assert verify_analysis_audit(tmp_path, 'validation', 'a'*40, 'b'*64) == record
    (result/'scores.json').write_text('[1]')
    with pytest.raises(ValueError):
        verify_analysis_audit(tmp_path, 'validation', 'a'*40, 'b'*64)


def test_empty_runtime_directory_is_not_runtime_evidence(tmp_path):
    from workflows.projected_archive_v38 import verify_runtime
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_runtime(tmp_path)


def test_metric_recomputation_allows_rotation_roundoff_but_not_a_changed_score():
    from workflows.audit_projected_v38 import require_metric
    expected = dict(complete_aggregate=True, failed_origins=0,
                    endpoint_rmse=[1e-6, 0., 1e-5, 1e-4], path_rmse=[1e-6, 0., 1e-5, 1e-4])
    tiny = copy.deepcopy(expected)
    tiny['path_rmse'][1] = 2.9802322387695312e-8  # acos near a unit dot product
    require_metric(tiny, expected)
    for index, amount in ((0, 1e-7), (1, 1e-5), (2, 1e-7), (3, 1e-7)):
        bad = copy.deepcopy(expected); bad['path_rmse'][index] += amount
        with pytest.raises(ValueError, match='formal_independent_metric'):
            require_metric(bad, expected)


def cache_fixture():
    from types import SimpleNamespace
    episode = SimpleNamespace(states=np.zeros((5, 11)), acceleration=np.zeros((4, 6)),
        arrays={'issued_control': np.zeros((4, 4)), 'causal_rotor_speed': np.zeros((5, 6)),
                'actuator_time_s': np.arange(5)/120},
        context=SimpleNamespace(mass=100., inertia=np.array([1., 2., 3.])))
    cache = dict(states=episode.states.copy(), issued_control=episode.arrays['issued_control'].copy(),
        acceleration=episode.acceleration.copy(), rotor_speed=episode.arrays['causal_rotor_speed'][1:].copy(),
        physics_time_s=episode.arrays['actuator_time_s'][1:].copy())
    return episode, cache


def test_cache_admission_returns_canonical_inputs_after_bounded_independent_comparison():
    from workflows.audit_projected_v38 import compare_episode_cache
    episode, cache = cache_fixture()
    cache['rotor_speed'][0, 0] = 3.1e-5
    cache['acceleration'][0, 0] = 4e-8  # 4e-6 N with mass100
    states, acceleration, agreement = compare_episode_cache(cache, episode)
    assert np.array_equal(states, cache['states'])
    assert acceleration[0, 0] == 4e-8  # Replay the admitted producer input, not a different local reconstruction.
    assert agreement['max_rotor_difference'] == 3.1e-5
    assert agreement['max_wrench_difference'] == pytest.approx(4e-6)


@pytest.mark.parametrize('name,delta', [('states', 1e-12), ('issued_control', 1e-12),
    ('physics_time_s', 1e-12), ('rotor_speed', 1.01e-4), ('acceleration', 1.01e-7)])
def test_cache_rejects_changed_identity_arrays_and_out_of_tolerance_inputs(name, delta):
    from workflows.audit_projected_v38 import compare_episode_cache
    episode, cache = cache_fixture()
    cache[name].flat[0] += delta
    with pytest.raises(ValueError, match='formal_independent_cache'):
        compare_episode_cache(cache, episode)


@pytest.mark.parametrize('name', ['states', 'issued_control', 'physics_time_s', 'rotor_speed', 'acceleration'])
def test_cache_rejects_nonfinite_or_wrong_shape(name):
    from workflows.audit_projected_v38 import compare_episode_cache
    episode, cache = cache_fixture()
    bad = {**cache, name: cache[name][:-1]}
    with pytest.raises(ValueError, match='formal_independent_cache'):
        compare_episode_cache(bad, episode)
    cache[name].flat[0] = float('nan')
    with pytest.raises(ValueError, match='formal_independent_cache'):
        compare_episode_cache(cache, episode)

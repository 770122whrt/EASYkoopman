"""Prepared geometry must preserve the admitted projected predictor, not refit it."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import numpy as np
import pytest

from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS, SUPPORTED_EMBODIMENTS
from koopman.projected_edmd_v24 import PhysicalContext
from koopman.sparse_world_edmd_v30 import core_matrix
from workflows.identify_sparse_world_v30 import SparseModel
from workflows.workpoint_v27 import mechanics


def context(name='base'):
    m = mechanics(name)
    return PhysicalContext(m['mass_kg'], m['inertia_kg_m2'], m['cob_m'], m['volume_m3'],
                           EMBODIMENT_CONFIGS[name]['drag_multiplier'])


def model(family='nonlinear'):
    d = np.linspace(.01, .12, 6)
    q = np.linspace(.03, .08, 6) if family == 'nonlinear' else np.zeros(6)
    angular = float(np.float32(.05))
    return SparseModel(family, core_matrix(family, d, q, angular), d, q, angular, {})


def states(count=7):
    rng = np.random.default_rng(405)
    x = rng.normal(size=(count, 11))
    x[:, 0] += 5.5
    x[:, 1:5] /= np.linalg.norm(x[:, 1:5], axis=1, keepdims=True)
    # Include half-turn attitude and norm just inside the original admission.
    x[0, 1:5] = [0, 1.0009, 0, 0]
    return x


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
@pytest.mark.parametrize('family', ['linear', 'nonlinear'])
@pytest.mark.parametrize('count', [1, 7])
def test_prepared_one_step_matches_reference_all_contexts(name, family, count):
    from koopman.prepared_projected_v40 import prepare_projected
    c, m, x = context(name), model(family), states(count)
    u = np.random.default_rng(406).normal(size=(count, 6))
    original_x, original_u = x.copy(), u.copy()
    predict = prepare_projected(m, c)
    np.testing.assert_allclose(predict(x, u, c), m(x, u, c), rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(x, original_x)
    np.testing.assert_array_equal(u, original_u)


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
def test_256_tick_recurrence_and_parallel_branches_are_equivalent(name):
    from koopman.prepared_projected_v40 import prepare_projected
    c, m = context(name), model()
    predict = prepare_projected(m, c)
    x = np.array([[5.5, 1, 0, 0, 0, .02, -.03, .01, .01, .01, -.01]])
    inputs = np.random.default_rng(407).uniform(-.15, .15, (256, 6))

    def run(predictor, sign):
        result, y = [], x.copy()
        for u in inputs:
            y = predictor(y, sign*u[None], c)
            result.append(y.copy())
        return np.asarray(result)

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(run, predict, 1), pool.submit(run, predict, -1)
        np.testing.assert_allclose(a.result(), run(m, 1), rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(b.result(), run(m, -1), rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize('change', ['nan_state', 'bad_quaternion', 'state_shape', 'nan_input', 'input_shape'])
def test_invalid_runtime_values_still_rejected(change):
    from koopman.prepared_projected_v40 import prepare_projected
    c, m, x, u = context(), model(), states(1), np.zeros((1, 6))
    if change == 'nan_state': x[0, 0] = np.nan
    if change == 'bad_quaternion': x[0, 1:5] = 0
    if change == 'state_shape': x = x[0]
    if change == 'nan_input': u[0, 0] = np.nan
    if change == 'input_shape': u = np.zeros((1, 4))
    with pytest.raises(ValueError): m(x, u, c)
    with pytest.raises(ValueError): prepare_projected(m, c)(x, u, c)


@pytest.mark.parametrize('field,value', [('mass', 30.), ('volume', .02), ('rho', 1000.),
    ('beta', .002), ('gravity', 9.8), ('drag_multiplier', .7),
    ('inertia', np.array([.6, .7, .8])), ('cob', np.array([.01, .02, .03]))])
def test_prepared_context_cannot_silently_follow_changed_mechanics(field, value):
    from koopman.prepared_projected_v40 import prepare_projected
    c = context()
    predict = prepare_projected(model(), c)
    with pytest.raises(ValueError, match='context'):
        predict(states(1), np.zeros((1, 6)), replace(c, **{field: value}))


def test_preparation_copies_model_and_accepts_equal_context_values():
    from koopman.prepared_projected_v40 import prepare_projected
    c, m, x, u = context(), model(), states(1), np.zeros((1, 6))
    expected = m(x, u, c)
    predict = prepare_projected(m, c)
    m.matrix[:] = np.nan
    m.damping[:] = 99
    np.testing.assert_allclose(predict(x, u, replace(c)), expected, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize('change', ['matrix_shape', 'matrix_nan', 'velocity_constraint', 'damping_nan', 'angular_nan'])
def test_invalid_model_rejected_before_any_forecast(change):
    from koopman.prepared_projected_v40 import prepare_projected
    m = model()
    if change == 'matrix_shape': m = replace(m, matrix=np.eye(3))
    if change == 'matrix_nan': m.matrix[0, 0] = np.nan
    if change == 'velocity_constraint': m.matrix[0, 10] += 1
    if change == 'damping_nan': m.damping[0] = np.nan
    if change == 'angular_nan': m = replace(m, angular_damping=np.nan)
    with pytest.raises(ValueError): prepare_projected(m, context())


def test_single_step_reuses_old_rotation_instead_of_six_geometry_evaluations(monkeypatch):
    import koopman.prepared_projected_v40 as prepared
    rotation = prepared.rotation
    calls = []

    def count(q):
        calls.append(q.copy())
        return rotation(q)

    monkeypatch.setattr(prepared, 'rotation', count)
    c = context()
    prepared.prepare_projected(model(), c)(states(), np.zeros((7, 6)), c)
    assert len(calls) == 2  # one old state, one new state; no semantic shortcuts

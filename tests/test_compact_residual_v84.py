"""Structural, causal and artifact contracts for the compact residual arm."""
from dataclasses import replace
import importlib

import numpy as np
import pytest

from test_learned_velocity_v81 import record as learned_record
from test_prepared_projected_v40 import context, states
from koopman.sparse_world_edmd_v30 import feature_names, predict_projected


def api():
    return importlib.import_module('koopman.compact_residual_v84')


def training():
    rng = np.random.default_rng(684)
    features = rng.normal(size=(600, 53))
    features[:, -1] = 1
    prior = np.asarray(learned_record()['velocity_matrix'])
    return features, prior, np.ones(len(features))


def make_record():
    a = api()
    f, prior, w = training()
    k, stats = a.fit_compact(f, f @ prior, w, prior)
    return a.make_record(learned_record()['physical_prior'], k, stats, ridge=.001)


def test_zero_residual_is_exact_prior_and_known_geometry():
    a = api()
    f, prior, w = training()
    k, stats = a.fit_compact(f, f @ prior, w, prior)
    np.testing.assert_array_equal(k, prior)
    assert stats['independent_coefficients'] == 15
    assert stats['allowed_matrix_entries'] == 27
    r = a.make_record(learned_record()['physical_prior'], k, stats, ridge=.001)
    c, x = context(), states(7)
    u = np.random.default_rng(4).normal(size=(7, 6))
    prepared = a.prepare_compact(r, c)
    from koopman.learned_velocity_v81 import prepare_learned
    np.testing.assert_array_equal(prepared(x, u, c), prepare_learned(learned_record(), c)(x, u, c))


def test_tied_drag_is_learned_but_forbidden_coupling_is_exactly_zero():
    a = api()
    f, prior, w = training()
    basis, names = a.structural_basis()
    target = f @ prior + np.einsum('nf,fo->no', f, .2 * basis[0])
    fitted, stats = a.fit_compact(f, target, w, prior)
    delta = fitted - prior
    mask = a.structural_mask()
    np.testing.assert_array_equal(delta[~mask], 0)
    assert np.sqrt(np.mean((f @ fitted - target) ** 2)) < .001
    assert len(names) == 15
    indices = {n: i for i, n in enumerate(feature_names('nonlinear'))}
    tied = [delta[indices[f'axis_velocity_0_{j}'], j] for j in range(3)]
    np.testing.assert_allclose(tied, tied[0], rtol=0, atol=1e-14)
    assert not mask[indices['z']].any()
    assert not mask[indices['constant']].any()
    assert not mask[indices['axis_quadratic_0_0'], 3:].any()


def test_unexcited_columns_remain_prior_without_centering_noise():
    a = api()
    f, prior, w = training()
    f[:] = 0
    f[:, -1] = 1
    y = f @ prior + .03
    fitted, stats = a.fit_compact(f, y, w, prior)
    np.testing.assert_array_equal(fitted, prior)
    assert stats['identified_basis_indices'] == []
    assert stats['design_rank'] == 0


def test_prepared_parity_height_invariance_and_immutable_context():
    a = api()
    r = make_record()
    names = feature_names('nonlinear')
    for j in range(3):
        r['velocity_matrix'][names.index(f'axis_velocity_0_{j}')][j] += .01
    r = a.seal_record(r)
    c, x = context(), states(5)
    u = np.zeros((5, 6))
    p = a.prepare_compact(r, c)
    matrix = p._symbolic_base._matrix
    expected = predict_projected(x, u, c, matrix, 'nonlinear', p._symbolic_base._angular_damping)
    np.testing.assert_allclose(p(x, u, c), expected, atol=1e-14)
    shifted = x.copy()
    shifted[:, 0] += .25
    np.testing.assert_array_equal(p(x, u, c)[:, 1:], p(shifted, u, c)[:, 1:])
    with pytest.raises(ValueError, match='context'):
        p(x, u, replace(c, mass=c.mass + 1))
    with pytest.raises(ValueError):
        matrix.setflags(write=True)


@pytest.mark.parametrize('kind', ['hash', 'forbidden', 'untied', 'prior', 'role'])
def test_invalid_artifacts_fail_closed(kind):
    a = api()
    r = make_record()
    if kind == 'hash':
        r['ridge'] = .1
    elif kind == 'forbidden':
        r['velocity_matrix'][0][0] += .001
    elif kind == 'untied':
        r['velocity_matrix'][feature_names('nonlinear').index('axis_velocity_0_0')][0] += .001
    elif kind == 'prior':
        r['physical_prior']['fit_episode_hashes']['test_episode'] = 'c' * 64
    else:
        r['audit']['training_role'] = 'test'
    if kind != 'hash':
        r = a.seal_record(r)
    with pytest.raises(ValueError):
        a.prepare_compact(r, context())


def test_validation_ridge_and_data_are_finite_nonempty_and_source_only():
    a = api()
    f, prior, w = training()
    with pytest.raises(ValueError):
        a.fit_compact(f[:0], np.empty((0, 6)), w[:0], prior)
    with pytest.raises(ValueError):
        a.fit_compact(f, f @ prior, w, prior, ridge=1.)
    bad = f.copy()
    bad[0, 0] = np.nan
    with pytest.raises(ValueError):
        a.fit_compact(bad, f @ prior, w, prior)


@pytest.mark.parametrize('name', ['base', 'uuv4', 'heavy_moderate', 'asymmetric'])
def test_existing_symbolic_plant_accepts_wrapper_and_matches_nonzero_residual(name):
    pytest.importorskip('casadi')
    from koopman.continuous_prediction_v76 import SymbolicPlant
    a = api()
    f, prior, w = training()
    basis, _ = a.structural_basis()
    delta = .007 * basis[0] - .003 * basis[-1]
    fitted, stats = a.fit_compact(f, f @ (prior + delta), w, prior)
    r = a.make_record(learned_record()['physical_prior'], fitted, stats, ridge=.001)
    c, x = context(name), states(4)
    p = a.prepare_compact(r, c)
    plant = SymbolicPlant(p, name)
    u = np.random.default_rng(84).uniform(-.1, .1, (4, 6))
    actual = np.stack([np.asarray(plant.step(s, control)).ravel() for s, control in zip(x, u)])
    np.testing.assert_allclose(actual, p(x, u, c), atol=1e-11, rtol=1e-11)

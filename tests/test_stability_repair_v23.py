import numpy as np
import pytest

from koopman import stability_repair_v23 as repair


def data():
    rng = np.random.default_rng(8)
    design = rng.normal(size=(300, 66))
    design[:, 0] = 1
    coefficient = np.zeros((10, 66))
    coefficient[:7, [1, 8, 9, 10, 11, 12, 13]] = np.eye(7)
    scores = rng.normal(size=(7, 2))
    return design, design @ coefficient.T, coefficient, scores


def test_refit_constrains_state_recurrence_without_clipping_predictions():
    x, y, old, scores = data()
    coefficient, audit = repair.constrained_refit(x, y, old, scores, np.ones(7), ridge=1e-8,
                                                 radius=.99, max_iterations=3000)
    assert audit['converged']
    assert max(audit['scaled_operator_norms']) <= .99 + 1e-6
    assert np.array_equal(coefficient[7:], old[7:])
    assert np.linalg.norm(coefficient - old) > .1
    assert np.array_equal(old[:7, [1, 8, 9, 10, 11, 12, 13]], np.eye(7))


def test_unconverged_optimization_does_not_return_a_model():
    x, y, old, scores = data()
    with pytest.raises(ValueError, match='stability_refit_not_converged'):
        repair.constrained_refit(x, y, old, scores, np.ones(7), ridge=1e-8,
                                 radius=.99, max_iterations=1)


@pytest.mark.parametrize('scales,radius', [(np.zeros(7), .99), (np.ones(7), 1.01)])
def test_invalid_physical_scaling_or_radius_fails(scales, radius):
    x, y, old, scores = data()
    with pytest.raises(ValueError):
        repair.constrained_refit(x, y, old, scores, scales, ridge=1e-8, radius=radius)


def test_context_matrix_matches_actual_feature_based_prediction_derivative():
    rng = np.random.default_rng(23)
    coefficient = rng.normal(size=(10, 66))
    model = repair.DiagnosticCoefficientModel(coefficient)
    state = np.array([1.5, 1., 0., 0., 0., .1, .2, .3, .4, .5, .6])
    score = np.array([.8, -.3])
    memory, control = np.zeros(4), np.zeros(4)
    base = model.predict_increment(state, memory, control, platform_score=score)
    jac = np.zeros((7, 7))
    for j, index in enumerate([0, 5, 6, 7, 8, 9, 10]):
        changed = state.copy(); changed[index] += 1e-5
        jac[:, j] = (model.predict_increment(changed, memory, control, platform_score=score)[:7] - base[:7])/1e-5
    scales = np.arange(1., 8.)
    actual = np.eye(7) + jac * scales[None, :] / scales[:, None]
    mapped = np.eye(7) + (coefficient[:7] / scales[:, None]) @ repair.context_maps([score], scales)[0]
    np.testing.assert_allclose(actual, mapped, atol=1e-8)


def test_isotropic_problem_agrees_with_closed_form_constrained_optimum():
    design = np.eye(66)
    baseline = np.zeros((10, 66))
    columns = [1, 8, 9, 10, 11, 12, 13]
    baseline[:7, columns] = np.eye(7)
    coefficient, audit = repair.constrained_refit(design, design @ baseline.T, baseline,
        np.zeros((7, 2)), np.ones(7), ridge=1e-8, radius=.99)
    # Projection of 2I onto the radius-.99 spectral ball gives A=.99I.
    np.testing.assert_allclose(coefficient[:7, columns], -.01 * np.eye(7), atol=1e-6)
    expected = np.zeros_like(coefficient); expected[:7, columns] = -.01 * np.eye(7)
    np.testing.assert_allclose(coefficient, expected, atol=1e-6)

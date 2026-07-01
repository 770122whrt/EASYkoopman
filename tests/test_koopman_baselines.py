import numpy as np

from koopman.baselines import PersistenceBaseline, fit_simple_linear_baseline
from koopman.dataset import load_dataset
from koopman.evaluation import evaluate_model

from tests.test_koopman_dataset import FIXTURE


def test_persistence_baseline_predicts_current_state():
    dataset = load_dataset(FIXTURE)
    model = PersistenceBaseline()

    prediction = model.predict_next(dataset.X, dataset.U, dataset.R)

    np.testing.assert_allclose(prediction, dataset.X)


def test_simple_linear_baseline_fits_and_evaluates():
    dataset = load_dataset(FIXTURE)
    model = fit_simple_linear_baseline(dataset, ridge=1e-4)

    prediction = model.predict_next(dataset.X, dataset.U, dataset.R)
    metrics = evaluate_model(model, dataset, horizons=(2, 3))

    assert model.model_class == "simple_linear"
    assert prediction.shape == dataset.Y.shape
    assert metrics["multi_step_rmse@2"] >= 0.0

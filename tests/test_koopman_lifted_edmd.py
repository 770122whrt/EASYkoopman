import numpy as np

from koopman.dataset import load_dataset
from koopman.lifted_edmd import LiftedEDMDModel, fit_lifted_edmd

from tests.test_koopman_dataset import FIXTURE


def test_lifted_edmd_predicts_raw_state_and_round_trips(tmp_path):
    dataset = load_dataset(FIXTURE)
    model = fit_lifted_edmd(dataset, ridge=1e-4)

    prediction = model.predict_next(dataset.X, dataset.U, dataset.R)

    assert model.model_class == "paper_lifted_edmd"
    assert prediction.shape == dataset.Y.shape

    path = tmp_path / "lifted_model.json"
    model.save(path)
    loaded = LiftedEDMDModel.load(path)

    np.testing.assert_allclose(loaded.predict_next(dataset.X, dataset.U, dataset.R), prediction)

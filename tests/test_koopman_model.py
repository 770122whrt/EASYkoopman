import numpy as np

from koopman.dataset import load_dataset
from koopman.edmd import fit_edmd
from koopman.lifting import LiftingConfig
from koopman.model import KoopmanModel

from tests.test_koopman_dataset import FIXTURE


def test_koopman_model_save_load_round_trips_predictions(tmp_path):
    dataset = load_dataset(FIXTURE)
    model = fit_edmd(dataset, lifting_config=LiftingConfig(include_quadratic=False), ridge=1e-4)
    before = model.predict_next(dataset.X, dataset.U, dataset.R)

    path = tmp_path / "koopman_model.json"
    model.save(path)
    loaded = KoopmanModel.load(path)
    after = loaded.predict_next(dataset.X, dataset.U, dataset.R)

    assert loaded.version == model.version
    assert loaded.metadata["sample_count"] == dataset.sample_count
    np.testing.assert_allclose(after, before)


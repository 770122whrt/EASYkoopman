from pathlib import Path

import numpy as np
import pytest

from koopman.dataset import KoopmanDataset, load_dataset


FIXTURE = Path(__file__).parent / "fixtures" / "koopman_step_small.jsonl"


def test_load_dataset_from_jsonl_fixture_has_expected_arrays_and_metadata():
    dataset = load_dataset(FIXTURE)

    assert isinstance(dataset, KoopmanDataset)
    assert dataset.X.shape == (4, 11)
    assert dataset.U.shape == (4, 8)
    assert dataset.R.shape == (4, 5)
    assert dataset.Y.shape == (4, 11)
    assert dataset.t.shape == (4,)
    assert dataset.sample_count == 4
    assert dataset.dt == pytest.approx(1.0 / 60.0)
    assert dataset.trajectory_types == ("step",)
    assert dataset.controller_modes == ("legacy/Ssurface",)
    assert dataset.source_paths == (str(FIXTURE),)
    np.testing.assert_allclose(dataset.X[1], dataset.Y[0])


def test_load_dataset_rejects_empty_path_list():
    with pytest.raises(ValueError, match="at least one"):
        load_dataset([])


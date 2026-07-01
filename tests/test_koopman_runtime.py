import json

import numpy as np
import pytest

from koopman.dataset import load_dataset
from koopman.edmd import fit_edmd
from koopman.lifting import LiftingConfig
from koopman.runtime import KoopmanRuntimeError, load_koopman_runtime

from tests.test_koopman_dataset import FIXTURE


def _write_manifest(tmp_path, *, overrides=None):
    dataset = load_dataset(FIXTURE)
    model = fit_edmd(dataset, lifting_config=LiftingConfig(include_quadratic=False), ridge=1e-4)
    model_path = tmp_path / "direct_state.json"
    model.save(model_path)
    manifest = {
        "gate_status": "pass",
        "selected_candidate_id": "fixture_direct_state",
        "model_class": "direct_state",
        "model_path": str(model_path),
        "normalizer_path": None,
        "state_dim": 11,
        "reference_dim": 5,
        "control_dim": 8,
        "dt": dataset.dt or 1 / 60,
        "known_limitations": ["fixture limitation"],
        "metrics": {"test": {"multi_step_rmse@20": 0.1}},
    }
    if overrides:
        manifest.update(overrides)
    manifest_path = tmp_path / "selected_model_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, dataset


def test_load_koopman_runtime_accepts_valid_manifest_and_predicts(tmp_path):
    manifest_path, dataset = _write_manifest(tmp_path)

    runtime = load_koopman_runtime(manifest_path)
    prediction = runtime.predict_next(dataset.X[0], dataset.U[0], dataset.R[0])

    assert runtime.backend_used == "direct_state"
    assert runtime.model_class == "direct_state"
    assert runtime.backend_is_paper_style_lifted_edmd is False
    assert runtime.known_limitations == ("fixture limitation",)
    assert prediction.shape == (11,)
    assert np.isfinite(prediction).all()


def test_load_koopman_runtime_rejects_failed_gate(tmp_path):
    manifest_path, _ = _write_manifest(tmp_path, overrides={"gate_status": "fail"})

    with pytest.raises(KoopmanRuntimeError, match="gate_status"):
        load_koopman_runtime(manifest_path)


def test_load_koopman_runtime_rejects_missing_model_path(tmp_path):
    manifest_path, _ = _write_manifest(tmp_path, overrides={"model_path": str(tmp_path / "missing.json")})

    with pytest.raises(KoopmanRuntimeError, match="model_path"):
        load_koopman_runtime(manifest_path)


def test_load_koopman_runtime_rejects_unsupported_model_class(tmp_path):
    manifest_path, _ = _write_manifest(tmp_path, overrides={"model_class": "unsupported"})

    with pytest.raises(KoopmanRuntimeError, match="Unsupported model_class"):
        load_koopman_runtime(manifest_path)


def test_load_koopman_runtime_rejects_wrong_dimensions(tmp_path):
    manifest_path, _ = _write_manifest(tmp_path, overrides={"control_dim": 4})

    with pytest.raises(KoopmanRuntimeError, match="control_dim"):
        load_koopman_runtime(manifest_path)

import json

from koopman.dataset import load_dataset
from koopman.lifted_edmd import fit_lifted_edmd
from koopman.paper_lifted_selection import select_paper_lifted_from_sweep
from koopman.runtime import load_koopman_runtime

from tests.test_koopman_dataset import FIXTURE


def _candidate(candidate_id, model_path, *, rmse20, rmse60, status="pass", model_class="paper_lifted_edmd"):
    return {
        "candidate_id": candidate_id,
        "model_class": model_class,
        "model_path": str(model_path),
        "normalizer_path": None,
        "ridge": 1e-4,
        "lifting_variant": "selected_quadratic",
        "lifting_config": {"variant": "selected_quadratic", "include_bias": True},
        "normalization": "off",
        "state_dim": 11,
        "reference_dim": 5,
        "control_dim": 8,
        "dt": 1 / 60,
        "status": status,
        "validation_metrics": {
            "multi_step_rmse@20": rmse20,
            "multi_step_rmse@60": rmse60,
            "nonfinite_count": 0,
            "divergence_rate@20": 0.0,
            "diverged": False,
        },
    }


def test_select_paper_lifted_manifest_uses_best_passing_lifted_candidate_and_loads(tmp_path):
    dataset = load_dataset(FIXTURE)
    lifted = fit_lifted_edmd(dataset, ridge=1e-4)
    lifted_path = tmp_path / "lifted.json"
    lifted.save(lifted_path)
    direct_path = tmp_path / "direct.json"
    direct_path.write_text("{}", encoding="utf-8")
    sweep_path = tmp_path / "sweep_results.json"
    sweep_path.write_text(
        json.dumps(
            {
                "split_manifest_path": "split_manifest.json",
                "split": {
                    "train_logs": ["train.jsonl"],
                    "validation_logs": ["validation.jsonl"],
                    "test_logs": ["test.jsonl"],
                },
                "candidates": [
                    _candidate("direct_should_be_ignored", direct_path, rmse20=0.01, rmse60=0.01, model_class="direct_state"),
                    _candidate("lifted_worse", lifted_path, rmse20=0.40, rmse60=0.50),
                    _candidate("lifted_best", lifted_path, rmse20=0.20, rmse60=0.30),
                ],
                "baselines": {"persistence": {"validation_metrics": {"multi_step_rmse@20": 0.9}}},
            }
        ),
        encoding="utf-8",
    )

    manifest = select_paper_lifted_from_sweep(sweep_path, tmp_path / "paper_lifted_manifest.json")

    assert manifest["gate_status"] == "pass"
    assert manifest["model_class"] == "paper_lifted_edmd"
    assert manifest["selected_candidate_id"] == "lifted_best"
    assert manifest["selection_role"] == "paper_style_comparison_backend"
    assert manifest["known_limitations"]
    runtime = load_koopman_runtime(tmp_path / "paper_lifted_manifest.json")
    assert runtime.backend_is_paper_style_lifted_edmd


def test_select_paper_lifted_manifest_fails_closed_when_no_lifted_candidate_passes(tmp_path):
    model_path = tmp_path / "lifted.json"
    model_path.write_text("{}", encoding="utf-8")
    sweep_path = tmp_path / "sweep_results.json"
    sweep_path.write_text(
        json.dumps({"candidates": [_candidate("diverged", model_path, rmse20=0.1, rmse60=0.2, status="fail")]}),
        encoding="utf-8",
    )

    manifest = select_paper_lifted_from_sweep(sweep_path, tmp_path / "paper_lifted_manifest.json")

    assert manifest["gate_status"] == "fail"
    assert manifest["model_class"] == "paper_lifted_edmd"
    assert "no passing paper_lifted_edmd" in manifest["known_limitations"][0]

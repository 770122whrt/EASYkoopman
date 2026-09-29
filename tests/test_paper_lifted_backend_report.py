import json
import shutil

from koopman.dataset import load_dataset
from koopman.edmd import fit_edmd
from koopman.lifted_edmd import fit_lifted_edmd
from koopman.lifting import LiftingConfig
from koopman.paper_lifted_selection import select_paper_lifted_from_sweep
from koopman.splits import create_explicit_split, write_split_manifest
from workflows.evaluate_paper_lifted_backend import main as evaluate_main

from tests.test_koopman_dataset import FIXTURE


def _copy_fixture(tmp_path, name):
    path = tmp_path / name
    shutil.copyfile(FIXTURE, path)
    return path


def _write_manifests_and_split(tmp_path):
    train = _copy_fixture(tmp_path, "train.jsonl")
    validation = _copy_fixture(tmp_path, "validation.jsonl")
    test = _copy_fixture(tmp_path, "test.jsonl")
    split_path = tmp_path / "split_manifest.json"
    write_split_manifest(
        create_explicit_split(train_logs=[train], validation_logs=[validation], test_logs=[test]),
        split_path,
    )

    dataset = load_dataset(FIXTURE)
    direct = fit_edmd(dataset, lifting_config=LiftingConfig(include_quadratic=False), ridge=1e-4)
    lifted = fit_lifted_edmd(dataset, ridge=1e-4)
    direct_path = tmp_path / "direct.json"
    lifted_path = tmp_path / "lifted.json"
    direct.save(direct_path)
    lifted.save(lifted_path)

    direct_manifest_path = tmp_path / "selected_model_manifest.json"
    direct_manifest_path.write_text(
        json.dumps(
            {
                "gate_status": "pass",
                "selected_candidate_id": "direct_fixture",
                "model_class": "direct_state",
                "model_path": str(direct_path),
                "state_dim": 11,
                "reference_dim": 5,
                "control_dim": 8,
                "dt": dataset.dt or 1 / 60,
                "known_limitations": ["direct_state baseline"],
            }
        ),
        encoding="utf-8",
    )

    sweep_path = tmp_path / "sweep_results.json"
    sweep_path.write_text(
        json.dumps(
            {
                "split": {"train_logs": [str(train)], "validation_logs": [str(validation)], "test_logs": [str(test)]},
                "candidates": [
                    {
                        "candidate_id": "paper_fixture",
                        "model_class": "paper_lifted_edmd",
                        "model_path": str(lifted_path),
                        "normalizer_path": None,
                        "ridge": 1e-4,
                        "lifting_variant": "selected_quadratic",
                        "lifting_config": {"variant": "selected_quadratic"},
                        "normalization": "off",
                        "state_dim": 11,
                        "reference_dim": 5,
                        "control_dim": 8,
                        "dt": dataset.dt or 1 / 60,
                        "status": "pass",
                        "validation_metrics": {"multi_step_rmse@20": 0.1, "multi_step_rmse@60": 0.2},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    paper_manifest_path = tmp_path / "paper_lifted_manifest.json"
    select_paper_lifted_from_sweep(sweep_path, paper_manifest_path)
    return direct_manifest_path, paper_manifest_path, split_path


def test_paper_lifted_backend_report_compares_prediction_metrics_side_by_side(tmp_path):
    direct_manifest_path, paper_manifest_path, split_path = _write_manifests_and_split(tmp_path)
    output_path = tmp_path / "backend_prediction_comparison.json"

    assert evaluate_main(
        [
            "--direct-manifest",
            str(direct_manifest_path),
            "--paper-manifest",
            str(paper_manifest_path),
            "--split-manifest",
            str(split_path),
            "--output",
            str(output_path),
        ]
    ) == 0

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["direct_state"]["backend_used"] == "direct_state"
    assert report["paper_lifted_edmd"]["backend_used"] == "paper_lifted_edmd"
    assert "validation_metrics" in report["paper_lifted_edmd"]
    assert "test_metrics" in report["paper_lifted_edmd"]
    assert report["paper_lifted_edmd"]["nonfinite_count"] >= 0
    assert report["recommendation"] in {"paper_lifted_eligible_for_isaac_smoke", "paper_lifted_diagnostic_only"}
    assert report["known_limitations"]

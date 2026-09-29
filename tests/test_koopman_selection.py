import json

from koopman.selection import select_model_from_sweep


def test_selection_fails_when_candidate_does_not_beat_baselines(tmp_path):
    model_path = tmp_path / "model.json"
    model_path.write_text("{}", encoding="utf-8")
    sweep_path = tmp_path / "sweep.json"
    sweep_path.write_text(
        json.dumps(
            {
                "split": {
                    "train_logs": ["train.jsonl"],
                    "validation_logs": ["validation.jsonl"],
                    "test_logs": ["test.jsonl"],
                },
                "candidates": [
                    {
                        "candidate_id": "candidate",
                        "model_class": "direct_state",
                        "model_path": str(model_path),
                        "normalizer_path": None,
                        "ridge": 1e-4,
                        "lifting_config": {"variant": "linear"},
                        "status": "pass",
                        "validation_metrics": {
                            "multi_step_rmse@20": 2.0,
                            "multi_step_rmse@60": 2.0,
                            "diverged": False,
                        },
                    }
                ],
                "baselines": {
                    "persistence": {"validation_metrics": {"multi_step_rmse@20": 1.0}},
                    "simple_linear": {"validation_metrics": {"multi_step_rmse@20": 1.5}},
                },
            }
        ),
        encoding="utf-8",
    )

    manifest = select_model_from_sweep(sweep_path, tmp_path / "selected.json")

    assert manifest["gate_status"] == "fail"
    assert "not beat" in manifest["known_limitations"][0]
    assert json.loads((tmp_path / "selected.json").read_text(encoding="utf-8"))["gate_status"] == "fail"

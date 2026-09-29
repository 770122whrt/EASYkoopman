from koopman.gate_report import write_gate_report


def test_gate_report_contains_decision_and_baseline_summary(tmp_path):
    manifest = {
        "gate_status": "fail",
        "model_class": "direct_state",
        "model_path": "model.json",
        "train_logs": ["train.jsonl"],
        "validation_logs": ["validation.jsonl"],
        "test_logs": ["test.jsonl"],
        "metrics": {"validation": {"multi_step_rmse@20": 2.0}},
        "baselines": {"persistence": {"validation_metrics": {"multi_step_rmse@20": 1.0}}},
        "known_limitations": ["selected model did not beat baselines"],
    }
    sweep = {
        "candidates": [
            {
                "candidate_id": "candidate",
                "model_class": "direct_state",
                "status": "fail",
                "validation_metrics": {"multi_step_rmse@20": 2.0},
            }
        ]
    }

    report_path = tmp_path / "gate_report.md"
    write_gate_report(manifest, sweep, report_path)

    text = report_path.read_text(encoding="utf-8")
    assert "Gate Status: fail" in text
    assert "Baseline Comparison" in text
    assert "selected model did not beat baselines" in text

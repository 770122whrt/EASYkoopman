import json

from koopman.dataset import load_dataset
from koopman.lifted_edmd import fit_lifted_edmd
from workflows.run_koopman_mpc_offline import main as offline_main

from tests.test_koopman_dataset import FIXTURE


def test_offline_mpc_report_marks_paper_lifted_backend_and_bounded_commands(tmp_path):
    dataset = load_dataset(FIXTURE)
    model = fit_lifted_edmd(dataset, ridge=1e-4)
    model_path = tmp_path / "paper_lifted.json"
    model.save(model_path)
    manifest_path = tmp_path / "paper_lifted_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "gate_status": "pass",
                "selected_candidate_id": "paper_fixture",
                "model_class": "paper_lifted_edmd",
                "model_path": str(model_path),
                "state_dim": 11,
                "reference_dim": 5,
                "control_dim": 8,
                "dt": dataset.dt or 1 / 60,
                "selection_role": "paper_style_comparison_backend",
                "known_limitations": ["paper-style backend needs Isaac smoke"],
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "paper_lifted_offline_mpc.json"

    assert offline_main(
        [
            "--manifest",
            str(manifest_path),
            "--log",
            str(FIXTURE),
            "--max_samples",
            "2",
            "--output",
            str(output_path),
        ]
    ) == 0

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["backend_used"] == "paper_lifted_edmd"
    assert report["backend_is_paper_style_lifted_edmd"] is True
    assert report["command_bounded"] is True
    assert report["pwm_min"] >= -1.0
    assert report["pwm_max"] <= 1.0
    assert "latency_budget_met" in report

import json

from koopman.dataset import load_dataset
from koopman.edmd import fit_edmd
from koopman.lifted_edmd import fit_lifted_edmd
from koopman.lifting import LiftingConfig
from workflows.check_koopman_mpc_backend import main as backend_main
from workflows.run_koopman_mpc_offline import main as offline_main

from tests.test_koopman_dataset import FIXTURE


def _write_phase3_fixture(tmp_path):
    dataset = load_dataset(FIXTURE)
    direct = fit_edmd(dataset, lifting_config=LiftingConfig(include_quadratic=False), ridge=1e-4)
    lifted = fit_lifted_edmd(dataset, ridge=1e-4)
    direct_path = tmp_path / "direct.json"
    lifted_path = tmp_path / "lifted.json"
    direct.save(direct_path)
    lifted.save(lifted_path)
    manifest = {
        "gate_status": "pass",
        "selected_candidate_id": "direct_fixture",
        "model_class": "direct_state",
        "model_path": str(direct_path),
        "state_dim": 11,
        "reference_dim": 5,
        "control_dim": 8,
        "dt": dataset.dt or 1 / 60,
        "known_limitations": [],
    }
    manifest_path = tmp_path / "selected_model_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    sweep = {
        "candidates": [
            {
                "candidate_id": "lifted_fixture",
                "model_class": "paper_lifted_edmd",
                "model_path": str(lifted_path),
                "status": "pass",
                "validation_metrics": {"multi_step_rmse@20": 0.2, "multi_step_rmse@60": 0.3},
            }
        ]
    }
    sweep_path = tmp_path / "sweep_results.json"
    sweep_path.write_text(json.dumps(sweep), encoding="utf-8")
    return manifest_path, sweep_path


def test_offline_mpc_workflow_writes_latency_fallback_and_backend_report(tmp_path):
    manifest_path, _ = _write_phase3_fixture(tmp_path)
    output_path = tmp_path / "offline_smoke.json"

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
    assert report["backend_used"] == "direct_state"
    assert "backend_reason" in report
    assert report["sample_count"] == 2
    assert report["pwm_min"] >= -1.0
    assert report["pwm_max"] <= 1.0
    assert "average_latency_ms" in report
    assert "fallback_count" in report
    assert "known_limitations" in report


def test_backend_check_compares_direct_and_paper_lifted_candidates(tmp_path):
    manifest_path, sweep_path = _write_phase3_fixture(tmp_path)
    output_path = tmp_path / "backend_check.json"

    assert backend_main(
        [
            "--manifest",
            str(manifest_path),
            "--sweep_results",
            str(sweep_path),
            "--log",
            str(FIXTURE),
            "--max_samples",
            "2",
            "--output",
            str(output_path),
        ]
    ) == 0

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["backend_used"] in {"direct_state", "paper_lifted_edmd"}
    assert "backend_reason" in report
    assert "direct_state_metrics" in report
    assert "paper_lifted_edmd_metrics" in report
    assert "paper_alignment_note" in report
    assert report["paper_lifted_edmd_metrics"]["candidate_id"] == "lifted_fixture"

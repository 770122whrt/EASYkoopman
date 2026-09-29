import json
from pathlib import Path

from workflows.summarize_phase4_evaluation import main


def test_phase4_summary_workflow_writes_json_and_markdown(tmp_path: Path):
    fixture = Path(__file__).parent / "fixtures" / "koopman_step_small.jsonl"
    output_json = tmp_path / "metrics_summary.json"
    output_md = tmp_path / "metrics_summary.md"

    assert main(["--logs", str(fixture), "--output-json", str(output_json), "--output-md", str(output_md)]) == 0

    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["run_count"] == 1
    assert report["runs"][0]["controller_mode"] == "legacy/Ssurface"
    assert report["runs"][0]["backend_used"] == "legacy"
    assert report["eligible_for_phase45_baseline"] is True

    markdown = output_md.read_text(encoding="utf-8")
    assert "| Trajectory | Controller | Backend | Samples | Depth RMSE | Attitude RMSE | Fallback | Max Latency ms | PWM Bounded |" in markdown
    assert "| step | legacy/Ssurface | legacy | 4 |" in markdown

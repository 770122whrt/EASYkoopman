import json

from workflows.evaluate_koopman import main as evaluate_main
from workflows.train_koopman import main as train_main

from tests.test_koopman_dataset import FIXTURE


def test_train_and_evaluate_cli_run_on_fixture(tmp_path):
    model_path = tmp_path / "model.json"
    metrics_path = tmp_path / "metrics.json"

    assert train_main([str(FIXTURE), "--output", str(model_path), "--ridge", "0.0001"]) == 0
    assert model_path.exists()

    assert evaluate_main(["--model", str(model_path), "--logs", str(FIXTURE), "--output", str(metrics_path)]) == 0
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    assert metrics["sample_count"] == 4
    assert "one_step_rmse" in metrics

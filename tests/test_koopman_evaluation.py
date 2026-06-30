import json

from koopman.dataset import load_dataset
from koopman.edmd import fit_edmd
from koopman.evaluation import evaluate_model, write_metrics

from tests.test_koopman_dataset import FIXTURE


def test_evaluate_model_reports_one_step_and_multi_step_metrics(tmp_path):
    dataset = load_dataset(FIXTURE)
    model = fit_edmd(dataset, ridge=1e-4)

    metrics = evaluate_model(model, dataset, horizon=3)

    assert metrics["sample_count"] == 4
    assert metrics["multi_step_horizon"] == 3
    assert metrics["one_step_rmse"] >= 0.0
    assert metrics["depth_rmse"] >= 0.0
    assert metrics["velocity_rmse"] >= 0.0
    assert metrics["multi_step_rmse"] >= 0.0

    path = tmp_path / "metrics.json"
    write_metrics(metrics, path)
    assert json.loads(path.read_text(encoding="utf-8"))["sample_count"] == 4


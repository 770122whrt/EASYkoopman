import math
from pathlib import Path

from koopman.evaluation_logs import summarize_log_path
from koopman_data import KoopmanDataLogger, build_koopman_sample
from tests.test_koopman_data import valid_sample_kwargs


def _write_samples(path: Path, samples: list[dict]) -> None:
    with KoopmanDataLogger(path) as logger:
        for sample in samples:
            logger.write(sample)


def test_summarize_log_path_reports_legacy_tracking_and_pwm_metrics():
    fixture = Path(__file__).parent / "fixtures" / "koopman_step_small.jsonl"

    summary = summarize_log_path(fixture)

    assert summary["sample_count"] == 4
    assert summary["trajectory_type"] == "step"
    assert summary["controller_mode"] == "legacy/Ssurface"
    assert summary["backend_used"] == "legacy"
    assert summary["depth_rmse"] > 1.0
    assert summary["attitude_angle_rmse"] == 0.0
    assert summary["fallback_rate"] == 0.0
    assert summary["status_counts"] == {}
    assert summary["mean_latency_ms"] == 0.0
    assert summary["pwm_bounded"] is True
    assert summary["nonfinite_count"] == 0
    assert summary["pwm_saturation_rate"] == 0.0
    assert summary["mean_delta_pwm_l2"] > 0.0


def test_summarize_log_path_reports_solver_diagnostics(tmp_path: Path):
    log_path = tmp_path / "paper_lifted_step.jsonl"
    first = build_koopman_sample(**valid_sample_kwargs(t=1.0 / 60.0, pwm_8d=[0.0] * 8))
    first["controller_mode"] = "koopman_mpc/Ssurface"
    first["solver_diagnostics"] = {
        "backend_used": "paper_lifted_edmd",
        "status": "ok",
        "latency_ms": 10.0,
        "latency_budget_met": True,
        "fallback_used": False,
    }
    second = build_koopman_sample(**valid_sample_kwargs(t=2.0 / 60.0, pwm_8d=[1.0, -1.0] * 4))
    second["controller_mode"] = "koopman_mpc/Ssurface"
    second["solver_diagnostics"] = {
        "backend_used": "paper_lifted_edmd",
        "status": "fallback",
        "latency_ms": 13.0,
        "latency_budget_met": False,
        "fallback_used": True,
    }
    _write_samples(log_path, [first, second])

    summary = summarize_log_path(log_path)

    assert summary["backend_used"] == "paper_lifted_edmd"
    assert summary["fallback_rate"] == 0.5
    assert summary["status_counts"] == {"fallback": 1, "ok": 1}
    assert summary["mean_latency_ms"] == 11.5
    assert summary["max_latency_ms"] == 13.0
    assert summary["latency_budget_violation_rate"] == 0.5
    assert summary["pwm_saturation_rate"] == 0.5
    assert math.isclose(summary["max_delta_pwm_l2"], math.sqrt(8.0))

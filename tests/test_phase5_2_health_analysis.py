import pytest

from workflows.analyze_phase5_2_health import analyze_samples


def _sample(
    *,
    depth: float,
    reference_depth: float,
    pwm: list[float],
    fallback_used: bool,
    fallback_reason: str | None,
    clip_rate: float,
    latency_ms: float,
) -> dict:
    return {
        "state": [depth, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "next_state": [depth, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "reference": [reference_depth, 1.0, 0.0, 0.0, 0.0],
        "pwm_8d": pwm,
        "policy_action_clip_rate": clip_rate,
        "solver_diagnostics": {
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "latency_ms": latency_ms,
        },
    }


def test_analyze_phase5_2_health_reports_fallback_saturation_clip_and_depth():
    summary = analyze_samples(
        [
            _sample(
                depth=2.0,
                reference_depth=1.0,
                pwm=[1.0] * 8,
                fallback_used=True,
                fallback_reason="timeout",
                clip_rate=0.50,
                latency_ms=30.0,
            ),
            _sample(
                depth=1.0,
                reference_depth=1.0,
                pwm=[0.5] * 8,
                fallback_used=False,
                fallback_reason=None,
                clip_rate=0.00,
                latency_ms=10.0,
            ),
        ],
        pwm_saturation_threshold=0.99,
    )

    assert summary["sample_count"] == 2
    assert summary["fallback_rate"] == pytest.approx(0.5)
    assert summary["fallback_reason_counts"] == {"timeout": 1}
    assert summary["pwm_saturation_rate"] == pytest.approx(0.5)
    assert summary["policy_action_clip_rate_mean"] == pytest.approx(0.25)
    assert summary["depth_rmse"] == pytest.approx(0.70710678)
    assert summary["latency_ms_mean"] == pytest.approx(20.0)

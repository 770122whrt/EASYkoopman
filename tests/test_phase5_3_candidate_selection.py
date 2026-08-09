import pytest

from workflows.select_phase5_3_candidate import (
    _load_metrics,
    metric_improvement,
    score_phase53_candidate,
    select_phase53_candidate,
)


REWARD_V1_BASELINE = {
    "fallback_rate_mean": 0.1248,
    "pwm_saturation_rate_mean": 0.3379,
    "policy_action_clip_rate_mean": 0.1393,
    "latency_ms_mean": 11.7225,
    "depth_rmse_mean": 0.9360,
    "attitude_rmse_mean": 0.7434,
}

BASELINE_RERUN_FLOOR = {
    "fallback_rate_mean": 0.2333,
    "pwm_saturation_rate_mean": 0.2293,
    "policy_action_clip_rate_mean": 0.0517,
    "latency_ms_mean": 11.8990,
    "depth_rmse_mean": 0.8564,
    "attitude_rmse_mean": 0.8135,
}


def test_metric_improvement_is_lower_is_better_and_clipped():
    assert metric_improvement(0.50, 0.25) == pytest.approx(0.50)
    assert metric_improvement(0.50, 0.75) == pytest.approx(-0.50)
    assert metric_improvement(0.10, 1.00) == pytest.approx(-1.0)


def test_load_metrics_accepts_windows_utf8_bom(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text('{"fallback_rate_mean": 0.1}', encoding="utf-8-sig")

    assert _load_metrics(path)["fallback_rate_mean"] == pytest.approx(0.1)


def test_score_phase5_3_candidate_uses_multi_metric_gate_not_saturation_only():
    candidate = {
        "fallback_rate_mean": 0.1300,
        "pwm_saturation_rate_mean": 0.2500,
        "policy_action_clip_rate_mean": 0.1000,
        "latency_ms_mean": 11.0,
        "depth_rmse_mean": 0.9000,
        "attitude_rmse_mean": 0.7400,
    }

    score = score_phase53_candidate(
        "cross_reward_v1_adapter_soft",
        candidate,
        comparison_baseline=REWARD_V1_BASELINE,
        health_floor=BASELINE_RERUN_FLOOR,
    )

    assert score["promotion_gate_passed"] is True
    assert score["health_score"] > 0.0
    assert score["improvements"]["pwm_saturation_rate_mean"] > 0.15
    assert score["improvements"]["policy_action_clip_rate_mean"] > 0.10
    assert score["health_floor_label"] == "partial_improvement"


def test_score_phase5_3_candidate_rejects_fallback_regression_even_if_saturation_improves():
    candidate = {
        "fallback_rate_mean": 0.1600,
        "pwm_saturation_rate_mean": 0.2500,
        "policy_action_clip_rate_mean": 0.1000,
        "latency_ms_mean": 11.0,
        "depth_rmse_mean": 0.9000,
        "attitude_rmse_mean": 0.7400,
    }

    score = score_phase53_candidate(
        "cross_reward_v1_adapter_soft",
        candidate,
        comparison_baseline=REWARD_V1_BASELINE,
        health_floor=BASELINE_RERUN_FLOOR,
    )

    assert score["promotion_gate_passed"] is False
    assert any("fallback_rate_mean" in reason for reason in score["failure_reasons"])


def test_select_phase5_3_candidate_picks_best_passing_cross_and_reports_no_forced_promotion():
    candidates = {
        "cross_reward_v1_adapter_soft": {
            "fallback_rate_mean": 0.1300,
            "pwm_saturation_rate_mean": 0.2500,
            "policy_action_clip_rate_mean": 0.1000,
            "latency_ms_mean": 11.0,
            "depth_rmse_mean": 0.9000,
            "attitude_rmse_mean": 0.7400,
        },
        "cross_reward_v1_mpc_health": {
            "fallback_rate_mean": 0.1600,
            "pwm_saturation_rate_mean": 0.2000,
            "policy_action_clip_rate_mean": 0.5000,
            "latency_ms_mean": 11.0,
            "depth_rmse_mean": 2.0000,
            "attitude_rmse_mean": 0.7000,
        },
    }

    selection = select_phase53_candidate(
        candidates,
        comparison_baseline=REWARD_V1_BASELINE,
        health_floor=BASELINE_RERUN_FLOOR,
    )

    assert selection["selected_profile_id"] == "cross_reward_v1_adapter_soft"
    assert selection["selection_status"] == "selected_partial_improvement"
    assert selection["best_non_promoted_profile_id"] == "cross_reward_v1_mpc_health"

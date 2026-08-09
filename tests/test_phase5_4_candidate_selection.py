import json

import pytest

from workflows.select_phase5_4_candidate import _load_metrics, score_phase54_candidate, select_phase54_candidate


BASELINE_RERUN = {
    "sample_count": 1050,
    "fallback_rate_mean": 0.2333,
    "pwm_saturation_rate_mean": 0.2293,
    "policy_action_clip_rate_mean": 0.0517,
    "latency_ms_mean": 11.8990,
    "latency_ms_max": 13.0,
    "latency_budget_violation_rate": 0.0,
    "depth_rmse_mean": 0.8564,
    "attitude_rmse_mean": 0.8135,
    "fallback_reason_counts": {"timeout": 30, "no_cost_improvement": 20},
}

REWARD_V1 = {
    "sample_count": 1050,
    "fallback_rate_mean": 0.1248,
    "pwm_saturation_rate_mean": 0.3379,
    "policy_action_clip_rate_mean": 0.1393,
    "latency_ms_mean": 11.7225,
    "latency_ms_max": 13.0,
    "latency_budget_violation_rate": 0.0,
    "depth_rmse_mean": 0.9360,
    "attitude_rmse_mean": 0.7434,
    "fallback_reason_counts": {"timeout": 15, "no_cost_improvement": 20},
}

CROSS_REWARD_MPC = {
    "sample_count": 1050,
    "fallback_rate_mean": 0.3105,
    "pwm_saturation_rate_mean": 0.1192,
    "policy_action_clip_rate_mean": 0.0400,
    "latency_ms_mean": 11.8692,
    "latency_ms_max": 14.0,
    "latency_budget_violation_rate": 0.0,
    "depth_rmse_mean": 0.7173,
    "attitude_rmse_mean": 0.7354,
    "fallback_reason_counts": {"timeout": 220, "no_cost_improvement": 105},
}


def baselines():
    return {
        "baseline_rerun": BASELINE_RERUN,
        "reward_v1_only": REWARD_V1,
        "cross_reward_v1_mpc_health": CROSS_REWARD_MPC,
    }


def test_phase5_4_selector_rejects_latency_max_even_when_mean_is_good():
    candidate = {
        **REWARD_V1,
        "fallback_rate_mean": 0.1300,
        "pwm_saturation_rate_mean": 0.2500,
        "latency_ms_mean": 12.0,
        "latency_ms_max": 51.0,
        "latency_budget_violation_rate": 0.05,
    }

    score = score_phase54_candidate("r_pwm030", candidate, comparison_baselines=baselines())

    assert score["hard_gate_passed"] is False
    assert any("latency_ms_max" in reason for reason in score["failure_reasons"])


def test_phase5_4_track_r_can_pass_when_fallback_is_preserved_and_pwm_improves():
    candidate = {
        **REWARD_V1,
        "fallback_rate_mean": 0.1300,
        "pwm_saturation_rate_mean": 0.2800,
        "policy_action_clip_rate_mean": 0.1200,
        "depth_rmse_mean": 0.9000,
        "latency_ms_max": 13.0,
        "latency_budget_violation_rate": 0.0,
    }

    score = score_phase54_candidate("r_pwm030", candidate, comparison_baselines=baselines())

    assert score["hard_gate_passed"] is True
    assert score["selection_status"] == "track_pass"
    assert score["protected_strength_failures"] == []


def test_phase5_4_track_rm_promising_partial_when_fallback_only_reaches_floor():
    candidate = {
        **CROSS_REWARD_MPC,
        "fallback_rate_mean": 0.2200,
        "pwm_saturation_rate_mean": 0.1300,
        "policy_action_clip_rate_mean": 0.0500,
        "depth_rmse_mean": 0.7200,
        "attitude_rmse_mean": 0.7350,
        "latency_ms_max": 18.0,
        "latency_budget_violation_rate": 0.02,
        "fallback_reason_counts": {"timeout": 110, "no_cost_improvement": 110},
    }

    score = score_phase54_candidate("rm_timeout14", candidate, comparison_baselines=baselines())

    assert score["hard_gate_passed"] is True
    assert score["selection_status"] == "promising_partial"
    assert any("full reward_v1 fallback" in reason for reason in score["remaining_bottlenecks"])


def test_phase5_4_fallback_reason_gate_flags_no_cost_tradeoff():
    candidate = {
        **CROSS_REWARD_MPC,
        "fallback_rate_mean": 0.2200,
        "pwm_saturation_rate_mean": 0.1300,
        "policy_action_clip_rate_mean": 0.0500,
        "depth_rmse_mean": 0.7200,
        "attitude_rmse_mean": 0.7350,
        "latency_ms_max": 18.0,
        "latency_budget_violation_rate": 0.02,
        "fallback_reason_counts": {"timeout": 100, "no_cost_improvement": 160},
    }

    score = score_phase54_candidate("rm_timeout14", candidate, comparison_baselines=baselines())

    assert score["fallback_reason_gate_passed"] is False
    assert any("no_cost_improvement" in reason for reason in score["failure_reasons"])


def test_phase5_4_selection_prefers_smaller_parameter_distance_for_similar_scores():
    candidates = {
        "r_pwm025": {
            **REWARD_V1,
            "fallback_rate_mean": 0.1300,
            "pwm_saturation_rate_mean": 0.2800,
            "policy_action_clip_rate_mean": 0.1200,
            "depth_rmse_mean": 0.9000,
            "latency_ms_max": 13.0,
            "latency_budget_violation_rate": 0.0,
        },
        "r_pwm035": {
            **REWARD_V1,
            "fallback_rate_mean": 0.1300,
            "pwm_saturation_rate_mean": 0.2750,
            "policy_action_clip_rate_mean": 0.1200,
            "depth_rmse_mean": 0.9000,
            "latency_ms_max": 13.0,
            "latency_budget_violation_rate": 0.0,
        },
    }

    selection = select_phase54_candidate(candidates, comparison_baselines=baselines(), round2_complete=True)

    assert selection["selection_status"] == "track_pass"
    assert selection["selected_profile_id"] == "r_pwm025"
    assert selection["selected_score"]["minimal_parameter_selected"] is True


def test_phase5_4_final_selection_is_blocked_until_round2_or_diagnostic_stop():
    candidates = {
        "r_pwm030": {
            **REWARD_V1,
            "fallback_rate_mean": 0.1300,
            "pwm_saturation_rate_mean": 0.2800,
            "policy_action_clip_rate_mean": 0.1200,
            "depth_rmse_mean": 0.9000,
            "latency_ms_max": 13.0,
            "latency_budget_violation_rate": 0.0,
        }
    }

    selection = select_phase54_candidate(candidates, comparison_baselines=baselines(), round2_complete=False)

    assert selection["selection_status"] == "promising_partial"
    assert selection["final_selection_blocked"] is True
    assert selection["selected_profile_id"] is None


def test_phase5_4_selector_loads_phase5_2_profile_summary(tmp_path):
    summary_path = tmp_path / "phase5_2_experiment_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "profiles": {
                    "baseline_rerun": {
                        "averages": {
                            "fallback_rate": 0.23,
                            "pwm_saturation_rate": 0.22,
                            "policy_action_clip_rate_mean": 0.05,
                            "latency_ms_mean": 12.0,
                            "depth_rmse": 0.85,
                            "attitude_rmse": 0.81,
                        },
                        "trajectories": {
                            "step": {
                                "latency_ms_max": 13.0,
                                "fallback_reason_counts": {"timeout": 3},
                            },
                            "sine": {
                                "latency_ms_max": 14.0,
                                "fallback_reason_counts": {"no_cost_improvement": 2},
                            },
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    metrics = _load_metrics(summary_path, profile_id="baseline_rerun")

    assert metrics["fallback_rate_mean"] == pytest.approx(0.23)
    assert metrics["pwm_saturation_rate_mean"] == pytest.approx(0.22)
    assert metrics["depth_rmse_mean"] == pytest.approx(0.85)
    assert metrics["latency_ms_max"] == pytest.approx(14.0)
    assert metrics["latency_budget_violation_rate"] == pytest.approx(0.0)
    assert metrics["fallback_reason_counts"] == {"timeout": 3.0, "no_cost_improvement": 2.0}

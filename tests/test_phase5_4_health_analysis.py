import pytest

from workflows.analyze_phase5_2_health import analyze_samples
from workflows.plan_phase5_4_refinement import plan_phase54_refinement_profiles


def sample(*, trajectory_type="step", fallback=False, reason=None, latency=10.0):
    return {
        "trajectory_type": trajectory_type,
        "state": [0.0, 1.0, 0.0, 0.0, 0.0],
        "next_state": [0.1, 1.0, 0.0, 0.0, 0.0],
        "reference": [0.0, 1.0, 0.0, 0.0, 0.0],
        "pwm_8d": [0.0, 0.99, -1.0, 0.1, 0.2, 0.3, 0.4, 0.5],
        "policy_action_clip_rate": 0.25,
        "solver_diagnostics": {
            "fallback_used": fallback,
            "fallback_reason": reason,
            "latency_ms": latency,
        },
    }


def test_phase5_4_health_analysis_reports_latency_violation_and_reason_by_trajectory():
    summary = analyze_samples(
        [
            sample(trajectory_type="step", fallback=True, reason="timeout", latency=12.0),
            sample(trajectory_type="sine", fallback=True, reason="no_cost_improvement", latency=25.0),
            sample(trajectory_type="sine", fallback=False, latency=8.0),
        ],
        latency_budget_ms=20.0,
    )

    assert summary["latency_budget_violation_rate"] == pytest.approx(1 / 3)
    assert summary["fallback_reason_counts_by_trajectory"]["step"]["timeout"] == 1
    assert summary["fallback_reason_counts_by_trajectory"]["sine"]["no_cost_improvement"] == 1


def test_phase5_4_refinement_planner_recommends_nearest_smaller_timeout():
    selection = {
        "selection_status": "track_pass",
        "selected_profile_id": "rm_timeout16",
        "selected_score": {
            "profile_id": "rm_timeout16",
            "track": "RM",
            "remaining_bottlenecks": ["fallback above full reward_v1 fallback target"],
        },
    }

    plan = plan_phase54_refinement_profiles(selection)

    assert plan["refinement_required"] is True
    assert "rm_timeout15" in plan["recommended_profile_ids"]
    assert plan["nearest_smaller_candidate_required"] is True

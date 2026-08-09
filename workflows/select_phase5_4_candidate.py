from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.phase5_4_profiles import PHASE54_PROFILE_IDS, get_phase54_profile


RANKED_METRIC_WEIGHTS = {
    "pwm_saturation_rate_mean": 0.25,
    "fallback_rate_mean": 0.25,
    "policy_action_clip_rate_mean": 0.20,
    "depth_rmse_mean": 0.20,
    "attitude_rmse_mean": 0.10,
}
REQUIRED_METRICS = tuple(RANKED_METRIC_WEIGHTS) + (
    "latency_ms_mean",
    "latency_ms_max",
    "latency_budget_violation_rate",
)
STATUS_RANK = {
    "no_selection": 0,
    "promising_partial": 1,
    "track_pass": 2,
    "full_pass": 3,
}


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _finite_metric(metrics: dict[str, Any], metric_name: str) -> float:
    if metric_name not in metrics:
        raise ValueError(f"Missing metric: {metric_name}")
    value = float(metrics[metric_name])
    if not math.isfinite(value):
        raise ValueError(f"{metric_name} must be finite")
    return value


def metric_improvement(baseline_value: float, candidate_value: float, *, eps: float = 1.0e-9) -> float:
    baseline = float(baseline_value)
    candidate = float(candidate_value)
    if not math.isfinite(baseline) or not math.isfinite(candidate):
        raise ValueError("metric values must be finite")
    return _clamp((baseline - candidate) / max(abs(baseline), eps), -1.0, 1.0)


def _reason_counts(metrics: dict[str, Any]) -> dict[str, float]:
    counts = metrics.get("fallback_reason_counts") or {}
    if not isinstance(counts, dict):
        return {}
    return {str(key): float(value) for key, value in counts.items()}


def _reason_rate(metrics: dict[str, Any], reason: str) -> float | None:
    counts = _reason_counts(metrics)
    sample_count = float(metrics.get("sample_count", 0.0) or 0.0)
    if sample_count <= 0.0 or reason not in counts:
        return None
    return counts[reason] / sample_count


def _material_increase(candidate_rate: float | None, baseline_rate: float | None) -> bool:
    if candidate_rate is None or baseline_rate is None:
        return False
    return candidate_rate > baseline_rate + 0.02 or (
        baseline_rate > 0.0 and candidate_rate > baseline_rate * 1.25
    )


def _fallback_reason_failures(profile_id: str, candidate: dict[str, float], cross_reference: dict[str, Any]) -> list[str]:
    profile = get_phase54_profile(profile_id)
    if profile.track != "RM":
        return []
    failures: list[str] = []
    timeout_base = _reason_rate(cross_reference, "timeout")
    timeout_candidate = _reason_rate(candidate, "timeout")
    no_cost_base = _reason_rate(cross_reference, "no_cost_improvement")
    no_cost_candidate = _reason_rate(candidate, "no_cost_improvement")

    if "mpc_timeout_ms" in profile.mpc_overrides and timeout_base is not None and timeout_candidate is not None:
        if timeout_candidate > timeout_base:
            failures.append("timeout fallback did not decrease after increasing mpc_timeout_ms")
        if _material_increase(no_cost_candidate, no_cost_base):
            failures.append("no_cost_improvement fallback materially increased after timeout change")

    if (
        "mpc_control_weight" in profile.mpc_overrides or "mpc_smoothness_weight" in profile.mpc_overrides
    ) and _material_increase(no_cost_candidate, no_cost_base):
        failures.append("no_cost_improvement fallback materially increased after MPC weight reduction")
    return failures


def _hard_gate_failures(candidate: dict[str, float]) -> list[str]:
    failures: list[str] = []
    if candidate["latency_ms_mean"] >= 20.0:
        failures.append("latency_ms_mean exceeded 20 ms")
    if candidate["latency_ms_max"] >= 50.0:
        failures.append("latency_ms_max exceeded 50 ms")
    if candidate["latency_budget_violation_rate"] > 0.10:
        failures.append("latency_budget_violation_rate exceeded 0.10")
    return failures


def _full_pass(candidate: dict[str, float], health_floor: dict[str, float]) -> bool:
    return all(
        candidate[metric] <= health_floor[metric]
        for metric in (
            "fallback_rate_mean",
            "pwm_saturation_rate_mean",
            "policy_action_clip_rate_mean",
            "depth_rmse_mean",
            "attitude_rmse_mean",
        )
    )


def _track_status(
    profile_id: str,
    candidate: dict[str, float],
    *,
    reward_v1: dict[str, float],
    health_floor: dict[str, float],
) -> tuple[str, list[str], list[str]]:
    profile = get_phase54_profile(profile_id)
    protected_failures: list[str] = []
    bottlenecks: list[str] = []

    if profile.track == "R" and _full_pass(candidate, health_floor) and candidate["fallback_rate_mean"] <= 0.1448:
        return "full_pass", protected_failures, bottlenecks

    if profile.track == "R":
        if candidate["fallback_rate_mean"] > 0.1448:
            protected_failures.append("lost_reward_fallback_strength")
        repaired = (
            candidate["pwm_saturation_rate_mean"] < reward_v1["pwm_saturation_rate_mean"]
            or candidate["policy_action_clip_rate_mean"] < reward_v1["policy_action_clip_rate_mean"]
            or candidate["depth_rmse_mean"] < reward_v1["depth_rmse_mean"]
        )
        if not repaired:
            bottlenecks.append("Track R did not repair PWM, clip or depth")
        if protected_failures:
            return "no_selection", protected_failures, bottlenecks
        return ("track_pass" if repaired else "promising_partial"), protected_failures, bottlenecks

    if profile.track == "RM":
        if _full_pass(candidate, health_floor) and candidate["fallback_rate_mean"] <= 0.1448:
            return "full_pass", protected_failures, bottlenecks
        strength_checks = {
            "lost_mpc_pwm_strength": candidate["pwm_saturation_rate_mean"] <= 0.1500,
            "lost_mpc_clip_strength": candidate["policy_action_clip_rate_mean"] <= 0.0600,
            "lost_mpc_depth_strength": candidate["depth_rmse_mean"] <= 0.7500,
            "lost_mpc_attitude_strength": candidate["attitude_rmse_mean"] <= 0.7434,
        }
        protected_failures.extend(reason for reason, passed in strength_checks.items() if not passed)
        if candidate["fallback_rate_mean"] > health_floor["fallback_rate_mean"]:
            protected_failures.append("fallback_above_baseline_rerun_floor")
        if candidate["fallback_rate_mean"] > 0.1448:
            bottlenecks.append("fallback above full reward_v1 fallback target")
        if protected_failures:
            return "no_selection", protected_failures, bottlenecks
        return ("track_pass" if not bottlenecks else "promising_partial"), protected_failures, bottlenecks

    raise ValueError(f"Unsupported track: {profile.track!r}")


def score_phase54_candidate(
    profile_id: str,
    candidate_metrics: dict[str, Any],
    *,
    comparison_baselines: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if profile_id not in PHASE54_PROFILE_IDS:
        raise ValueError(f"profile_id must be one of {list(PHASE54_PROFILE_IDS)}, got {profile_id!r}")
    for baseline_name in ("baseline_rerun", "reward_v1_only", "cross_reward_v1_mpc_health"):
        if baseline_name not in comparison_baselines:
            raise ValueError(f"Missing comparison baseline: {baseline_name}")

    candidate = {metric: _finite_metric(candidate_metrics, metric) for metric in REQUIRED_METRICS}
    for reason_key, value in _reason_counts(candidate_metrics).items():
        candidate.setdefault("fallback_reason_counts", {})[reason_key] = value
    reward_v1 = {metric: _finite_metric(comparison_baselines["reward_v1_only"], metric) for metric in REQUIRED_METRICS}
    health_floor = {metric: _finite_metric(comparison_baselines["baseline_rerun"], metric) for metric in REQUIRED_METRICS}
    cross_reference = comparison_baselines["cross_reward_v1_mpc_health"]
    profile = get_phase54_profile(profile_id)

    improvements = {
        metric: metric_improvement(reward_v1[metric], candidate[metric])
        for metric in RANKED_METRIC_WEIGHTS
    }
    health_score = sum(RANKED_METRIC_WEIGHTS[metric] * improvements[metric] for metric in RANKED_METRIC_WEIGHTS)
    health_score -= 0.05 * min(profile.parameter_distance_from_parent / 10.0, 1.0)

    failure_reasons = _hard_gate_failures(candidate)
    reason_failures = _fallback_reason_failures(profile_id, candidate_metrics, cross_reference)
    failure_reasons.extend(reason_failures)
    fallback_reason_gate_passed = not reason_failures
    hard_gate_passed = not _hard_gate_failures(candidate)

    if failure_reasons:
        selection_status = "no_selection"
        protected_strength_failures: list[str] = []
        remaining_bottlenecks = failure_reasons[:]
    else:
        selection_status, protected_strength_failures, remaining_bottlenecks = _track_status(
            profile_id,
            candidate,
            reward_v1=reward_v1,
            health_floor=health_floor,
        )

    return {
        "profile_id": profile_id,
        "track": profile.track,
        "parent_profile_id": profile.parent_profile_id,
        "reward_profile": profile.reward_profile,
        "adapter_profile": profile.adapter_profile,
        "mpc_profile": profile.mpc_profile,
        "changed_axis": profile.changed_axis,
        "sweep_round": profile.sweep_round,
        "candidate_metrics": candidate,
        "comparison_baseline": "reward_v1_only",
        "health_floor": "baseline_rerun",
        "cross_reference": "cross_reward_v1_mpc_health",
        "improvements": improvements,
        "health_score": health_score,
        "hard_gate_passed": hard_gate_passed,
        "fallback_reason_gate_passed": fallback_reason_gate_passed,
        "selection_status": selection_status,
        "failure_reasons": failure_reasons,
        "protected_strength_failures": protected_strength_failures,
        "remaining_bottlenecks": remaining_bottlenecks,
        "parameter_distance_from_parent": profile.parameter_distance_from_parent,
        "changed_parameter_count": profile.changed_parameter_count,
        "parameter_step_count": profile.parameter_step_count,
        "nearest_smaller_candidate_id": profile.nearest_smaller_candidate_id,
        "minimal_parameter_selected": False,
    }


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_metrics = left["candidate_metrics"]
    right_metrics = right["candidate_metrics"]
    no_worse = all(left_metrics[metric] <= right_metrics[metric] for metric in RANKED_METRIC_WEIGHTS)
    better = any(left_metrics[metric] < right_metrics[metric] for metric in RANKED_METRIC_WEIGHTS)
    return no_worse and better


def _pick_best(scores: list[dict[str, Any]]) -> dict[str, Any] | None:
    promotable = [score for score in scores if STATUS_RANK[score["selection_status"]] > 0]
    if not promotable:
        return None
    ranked = sorted(
        promotable,
        key=lambda score: (
            STATUS_RANK[score["selection_status"]],
            score["health_score"],
            -score["parameter_distance_from_parent"],
        ),
        reverse=True,
    )
    best = ranked[0]
    for candidate in ranked[1:]:
        if candidate["selection_status"] != best["selection_status"]:
            continue
        if abs(candidate["health_score"] - best["health_score"]) < 0.03:
            if candidate["parameter_distance_from_parent"] < best["parameter_distance_from_parent"]:
                best = candidate
    best = dict(best)
    best["minimal_parameter_selected"] = True
    return best


def select_phase54_candidate(
    candidates: dict[str, dict[str, Any]],
    *,
    comparison_baselines: dict[str, dict[str, Any]],
    round2_complete: bool = False,
    diagnostic_stop_accepted: bool = False,
) -> dict[str, Any]:
    scores = [
        score_phase54_candidate(profile_id, metrics, comparison_baselines=comparison_baselines)
        for profile_id, metrics in candidates.items()
    ]
    pareto_frontier = [
        score["profile_id"]
        for score in scores
        if not any(_dominates(other, score) for other in scores if other["profile_id"] != score["profile_id"])
    ]
    best_track_r = _pick_best([score for score in scores if score["track"] == "R"])
    best_track_rm = _pick_best([score for score in scores if score["track"] == "RM"])
    best = _pick_best(scores)

    if best is None:
        return {
            "selection_status": "no_selection",
            "selected_profile_id": None,
            "best_track_r_candidate": best_track_r["profile_id"] if best_track_r else None,
            "best_track_rm_candidate": best_track_rm["profile_id"] if best_track_rm else None,
            "pareto_frontier": pareto_frontier,
            "scores": scores,
            "final_selection_blocked": False,
            "allowed_claims": [],
            "disallowed_claims": ["No Phase 5.4 profile passed the Pareto gates."],
        }

    if not round2_complete and not diagnostic_stop_accepted:
        return {
            "selection_status": "promising_partial",
            "selected_profile_id": None,
            "best_non_promoted_profile_id": best["profile_id"],
            "selected_score": best,
            "best_track_r_candidate": best_track_r["profile_id"] if best_track_r else None,
            "best_track_rm_candidate": best_track_rm["profile_id"] if best_track_rm else None,
            "pareto_frontier": pareto_frontier,
            "scores": scores,
            "final_selection_blocked": True,
            "allowed_claims": ["A promising Phase 5.4 profile exists, but Round 2 is still required."],
            "disallowed_claims": ["No final Phase 5.4 profile may be selected before Round 2 or diagnostic stop."],
        }

    return {
        "selection_status": best["selection_status"],
        "selected_profile_id": best["profile_id"],
        "selected_score": best,
        "best_track_r_candidate": best_track_r["profile_id"] if best_track_r else None,
        "best_track_rm_candidate": best_track_rm["profile_id"] if best_track_rm else None,
        "pareto_frontier": pareto_frontier,
        "scores": scores,
        "final_selection_blocked": False,
        "allowed_claims": ["A Phase 5.4 profile passed the bounded Pareto gate."],
        "disallowed_claims": [
            "The Phase 5.4 profile is not final deployment evidence.",
            "The Phase 5.4 profile does not prove broad legacy superiority.",
        ],
    }


def _mean_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    aliases = {
        "fallback_rate_mean": "fallback_rate",
        "pwm_saturation_rate_mean": "pwm_saturation_rate",
        "policy_action_clip_rate_mean": "policy_action_clip_rate_mean",
        "latency_ms_mean": "latency_ms_mean",
        "latency_budget_violation_rate": "latency_budget_violation_rate",
        "depth_rmse_mean": "depth_rmse",
        "attitude_rmse_mean": "attitude_rmse",
    }
    result: dict[str, Any] = {}
    for target, source in aliases.items():
        values = [float(run[source]) for run in runs if source in run]
        if values:
            result[target] = float(sum(values) / len(values))
    latency_max_values = [float(run["latency_ms_max"]) for run in runs if "latency_ms_max" in run]
    if latency_max_values:
        result["latency_ms_max"] = max(latency_max_values)
    fallback_counts: dict[str, float] = {}
    for run in runs:
        for reason, count in (run.get("fallback_reason_counts") or {}).items():
            fallback_counts[str(reason)] = fallback_counts.get(str(reason), 0.0) + float(count)
    if fallback_counts:
        result["fallback_reason_counts"] = fallback_counts
    result["sample_count"] = sum(float(run.get("sample_count", 0.0) or 0.0) for run in runs)
    return result


def _normalise_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    result = dict(metrics)
    aliases = {
        "fallback_rate_mean": "fallback_rate",
        "pwm_saturation_rate_mean": "pwm_saturation_rate",
        "depth_rmse_mean": "depth_rmse",
        "attitude_rmse_mean": "attitude_rmse",
    }
    for target, source in aliases.items():
        if target not in result and source in result:
            result[target] = result[source]

    trajectories = result.get("trajectories") or {}
    if "latency_ms_max" not in result and isinstance(trajectories, dict):
        latency_max_values = [
            float(trajectory["latency_ms_max"])
            for trajectory in trajectories.values()
            if isinstance(trajectory, dict) and "latency_ms_max" in trajectory
        ]
        if latency_max_values:
            result["latency_ms_max"] = max(latency_max_values)
    if "fallback_reason_counts" not in result and isinstance(trajectories, dict):
        fallback_counts: dict[str, float] = {}
        for trajectory in trajectories.values():
            if not isinstance(trajectory, dict):
                continue
            for reason, count in (trajectory.get("fallback_reason_counts") or {}).items():
                fallback_counts[str(reason)] = fallback_counts.get(str(reason), 0.0) + float(count)
        if fallback_counts:
            result["fallback_reason_counts"] = fallback_counts
    if "latency_budget_violation_rate" not in result:
        result["latency_budget_violation_rate"] = 0.0
    return result


def _profile_metrics(payload: dict[str, Any], profile_id: str, path: Path) -> dict[str, Any]:
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or profile_id not in profiles:
        raise ValueError(f"Metrics file does not contain profiles.{profile_id}: {path}")
    profile = profiles[profile_id]
    if not isinstance(profile, dict):
        raise ValueError(f"profiles.{profile_id} must be a JSON object: {path}")
    metrics = dict(profile.get("averages") or {})
    if "trajectories" in profile:
        metrics["trajectories"] = profile["trajectories"]
    return _normalise_metrics(metrics)


def _load_metrics(path: Path, profile_id: str | None = None) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict) and "runs" in payload and isinstance(payload["runs"], list):
        return _normalise_metrics(_mean_runs(payload["runs"]))
    if not isinstance(payload, dict):
        raise ValueError(f"Metrics file must contain a JSON object: {path}")
    if profile_id is not None and "profiles" in payload:
        return _profile_metrics(payload, profile_id, path)
    return _normalise_metrics(payload)


def _parse_candidate_arg(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError("candidate entries must use profile_id=path")
    profile_id, path = raw.split("=", 1)
    return profile_id, Path(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select a Phase 5.4 Pareto optimization candidate.")
    parser.add_argument("--baseline_rerun_path", required=True, type=Path)
    parser.add_argument("--reward_v1_path", required=True, type=Path)
    parser.add_argument("--cross_reward_mpc_path", required=True, type=Path)
    parser.add_argument("--candidate", action="append", default=[], help="profile_id=metrics_json")
    parser.add_argument("--round2_complete", action="store_true")
    parser.add_argument("--diagnostic_stop_accepted", action="store_true")
    parser.add_argument("--output_path", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        baselines = {
            "baseline_rerun": _load_metrics(args.baseline_rerun_path, profile_id="baseline_rerun"),
            "reward_v1_only": _load_metrics(args.reward_v1_path, profile_id="reward_v1_only"),
            "cross_reward_v1_mpc_health": _load_metrics(args.cross_reward_mpc_path),
        }
        candidates = {
            profile_id: _load_metrics(path)
            for profile_id, path in (_parse_candidate_arg(raw) for raw in args.candidate)
        }
        selection = select_phase54_candidate(
            candidates,
            comparison_baselines=baselines,
            round2_complete=args.round2_complete,
            diagnostic_stop_accepted=args.diagnostic_stop_accepted,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output = json.dumps(selection, indent=2)
    if args.output_path:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

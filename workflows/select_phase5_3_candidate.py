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

from koopman.phase5_3_profiles import PHASE53_PROFILE_IDS, get_phase53_profile


RANKED_METRIC_WEIGHTS = {
    "pwm_saturation_rate_mean": 0.30,
    "fallback_rate_mean": 0.20,
    "policy_action_clip_rate_mean": 0.20,
    "depth_rmse_mean": 0.20,
    "attitude_rmse_mean": 0.10,
}
REQUIRED_METRICS = tuple(RANKED_METRIC_WEIGHTS) + ("latency_ms_mean",)


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


def _relation_to_floor(candidate_value: float, floor_value: float, *, tolerance: float = 1.0e-9) -> str:
    if candidate_value < floor_value - tolerance:
        return "better"
    if candidate_value > floor_value + tolerance:
        return "worse"
    return "equal"


def _health_floor_label(relations: dict[str, str], promotion_gate_passed: bool) -> str:
    if not promotion_gate_passed:
        return "no_promotion"
    if relations["pwm_saturation_rate_mean"] == "worse" or relations["depth_rmse_mean"] == "worse":
        return "partial_improvement"
    return "health_floor_preserved"


def _promotion_failure_reasons(
    candidate: dict[str, float],
    baseline: dict[str, float],
    improvements: dict[str, float],
) -> list[str]:
    failure_reasons: list[str] = []

    pwm_pass = (
        candidate["pwm_saturation_rate_mean"] <= baseline["pwm_saturation_rate_mean"] - 0.05
        or improvements["pwm_saturation_rate_mean"] >= 0.15
    )
    if not pwm_pass:
        failure_reasons.append("pwm_saturation_rate_mean did not improve enough versus reward_v1_only")

    clip_pass = (
        candidate["policy_action_clip_rate_mean"] <= baseline["policy_action_clip_rate_mean"] - 0.02
        or improvements["policy_action_clip_rate_mean"] >= 0.10
    )
    depth_pass = (
        candidate["depth_rmse_mean"] <= baseline["depth_rmse_mean"] - 0.03
        or improvements["depth_rmse_mean"] >= 0.05
    )
    if not (clip_pass or depth_pass):
        failure_reasons.append("neither policy_action_clip_rate_mean nor depth_rmse_mean improved enough")

    if candidate["fallback_rate_mean"] > baseline["fallback_rate_mean"] + 0.02:
        failure_reasons.append("fallback_rate_mean regressed by more than 0.02 versus reward_v1_only")
    if candidate["attitude_rmse_mean"] > baseline["attitude_rmse_mean"] * 1.05:
        failure_reasons.append("attitude_rmse_mean exceeded the 5 percent regression guard")
    if candidate["latency_ms_mean"] >= 20.0:
        failure_reasons.append("latency_ms_mean exceeded the 20 ms guard")

    return failure_reasons


def score_phase53_candidate(
    profile_id: str,
    candidate_metrics: dict[str, Any],
    *,
    comparison_baseline: dict[str, Any],
    health_floor: dict[str, Any],
) -> dict[str, Any]:
    if profile_id not in PHASE53_PROFILE_IDS:
        raise ValueError(f"profile_id must be one of {list(PHASE53_PROFILE_IDS)}, got {profile_id!r}")

    candidate = {metric: _finite_metric(candidate_metrics, metric) for metric in REQUIRED_METRICS}
    baseline = {metric: _finite_metric(comparison_baseline, metric) for metric in REQUIRED_METRICS}
    floor = {metric: _finite_metric(health_floor, metric) for metric in REQUIRED_METRICS}
    improvements = {
        metric: metric_improvement(baseline[metric], candidate[metric])
        for metric in RANKED_METRIC_WEIGHTS
    }
    health_score = sum(RANKED_METRIC_WEIGHTS[metric] * improvements[metric] for metric in RANKED_METRIC_WEIGHTS)
    failure_reasons = _promotion_failure_reasons(candidate, baseline, improvements)
    promotion_gate_passed = not failure_reasons
    health_floor_relation = {
        metric: _relation_to_floor(candidate[metric], floor[metric])
        for metric in REQUIRED_METRICS
    }
    health_floor_label = _health_floor_label(health_floor_relation, promotion_gate_passed)
    profile = get_phase53_profile(profile_id)

    return {
        "profile_id": profile_id,
        "reward_profile": profile.reward_profile,
        "adapter_profile": profile.adapter_profile,
        "mpc_profile": profile.mpc_profile,
        "changed_axis": profile.changed_axis,
        "risk_level": profile.risk_level,
        "candidate_metrics": candidate,
        "comparison_baseline": "reward_v1_only",
        "health_floor": "baseline_rerun",
        "improvements": improvements,
        "health_score": health_score,
        "promotion_gate_passed": promotion_gate_passed,
        "failure_reasons": failure_reasons,
        "health_floor_relation": health_floor_relation,
        "health_floor_label": health_floor_label,
    }


def recommend_next_tuning_axis(profile_id: str) -> dict[str, Any]:
    get_phase53_profile(profile_id)
    if profile_id == "cross_reward_v1_adapter_soft":
        return {
            "selected_combination": profile_id,
            "next_tuning_axis": "adapter_scale_and_saturation_reward_sweep",
            "parameters_to_sweep_next": [
                "adapter_rpy_delta_scale",
                "adapter_depth_delta_scale",
                "phase5_2_w_pwm_sat",
                "phase5_2_w_action",
                "phase5_2_w_delta_action",
            ],
            "final_policy_claim_allowed": False,
        }
    if profile_id in {"cross_reward_v1_mpc_health", "cross_adapter_soft_mpc_health"}:
        return {
            "selected_combination": profile_id,
            "next_tuning_axis": "mpc_weight_sweep_with_clip_guard",
            "parameters_to_sweep_next": [
                "mpc_control_weight",
                "mpc_smoothness_weight",
                "mpc_delta_pwm_limit",
            ],
            "final_policy_claim_allowed": False,
        }
    if profile_id == "cross_reward_v1_adapter_soft_mpc_health":
        return {
            "selected_combination": profile_id,
            "next_tuning_axis": "defer_until_pairwise_review",
            "parameters_to_sweep_next": [],
            "final_policy_claim_allowed": False,
        }
    raise ValueError(f"Unsupported Phase 5.3 profile: {profile_id!r}")


def select_phase53_candidate(
    candidates: dict[str, dict[str, Any]],
    *,
    comparison_baseline: dict[str, Any],
    health_floor: dict[str, Any],
) -> dict[str, Any]:
    scores = [
        score_phase53_candidate(
            profile_id,
            metrics,
            comparison_baseline=comparison_baseline,
            health_floor=health_floor,
        )
        for profile_id, metrics in candidates.items()
    ]
    ranked = sorted(scores, key=lambda item: item["health_score"], reverse=True)
    passing = [item for item in ranked if item["promotion_gate_passed"]]
    failing = [item for item in ranked if not item["promotion_gate_passed"]]

    if not passing:
        best_non_promoted = ranked[0] if ranked else None
        return {
            "selection_status": "no_selection",
            "selected_profile_id": None,
            "best_non_promoted_profile_id": best_non_promoted["profile_id"] if best_non_promoted else None,
            "scores": scores,
            "allowed_claims": [],
            "disallowed_claims": [
                "No Phase 5.3 cross combination passed the multi-metric promotion gate.",
            ],
        }

    selected = passing[0]
    handoff = recommend_next_tuning_axis(selected["profile_id"])
    status = "selected_promoted"
    if selected["health_floor_label"] == "partial_improvement":
        status = "selected_partial_improvement"
    return {
        "selection_status": status,
        "selected_profile_id": selected["profile_id"],
        "best_non_promoted_profile_id": failing[0]["profile_id"] if failing else None,
        "selected_score": selected,
        "scores": scores,
        **handoff,
        "allowed_claims": [
            "A Phase 5.3 cross-combination family was selected for the next tuning phase.",
        ],
        "disallowed_claims": [
            "The selected cross is not a final or deployment-ready PPO policy.",
            "The selected cross does not prove PPO+Koopman-MPC superiority over legacy control.",
        ],
    }


def _load_metrics(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict) and "runs" in payload and isinstance(payload["runs"], list):
        runs = payload["runs"]
        if not runs:
            raise ValueError(f"No runs in metrics file: {path}")
        return _mean_runs(runs)
    if not isinstance(payload, dict):
        raise ValueError(f"Metrics file must contain a JSON object: {path}")
    return payload


def _mean_runs(runs: list[dict[str, Any]]) -> dict[str, float]:
    aliases = {
        "fallback_rate_mean": "fallback_rate",
        "pwm_saturation_rate_mean": "pwm_saturation_rate",
        "policy_action_clip_rate_mean": "policy_action_clip_rate_mean",
        "latency_ms_mean": "latency_ms_mean",
        "depth_rmse_mean": "depth_rmse",
        "attitude_rmse_mean": "attitude_rmse",
    }
    result: dict[str, float] = {}
    for target, source in aliases.items():
        values = [float(run[source]) for run in runs if source in run]
        if values:
            result[target] = float(sum(values) / len(values))
    return result


def _parse_candidate_arg(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError("candidate entries must use profile_id=path")
    profile_id, path = raw.split("=", 1)
    return profile_id, Path(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select the best Phase 5.3 cross-combination candidate.")
    parser.add_argument("--comparison_baseline_path", required=True, type=Path)
    parser.add_argument("--health_floor_path", required=True, type=Path)
    parser.add_argument("--candidate", action="append", default=[], help="profile_id=metrics_json")
    parser.add_argument("--output_path", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        candidates = {
            profile_id: _load_metrics(path)
            for profile_id, path in (_parse_candidate_arg(raw) for raw in args.candidate)
        }
        selection = select_phase53_candidate(
            candidates,
            comparison_baseline=_load_metrics(args.comparison_baseline_path),
            health_floor=_load_metrics(args.health_floor_path),
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

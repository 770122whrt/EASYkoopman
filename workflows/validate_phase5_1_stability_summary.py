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

from koopman.ppo_training_adapter import (
    ADAPTER_MODE,
    PHASE5_1_PROVENANCE_BY_EVIDENCE_LEVEL,
    PHASE5_1_TRAINING_EVIDENCE_LEVELS,
    PHASE5_CONTROLLER_PATH,
    PHASE5_RESULT_BUCKET,
    PHASE5_REWARD_PROFILE,
)


REQUIRED_FIELDS = (
    "checkpoint_found",
    "selected_checkpoint",
    "selected_rule",
    "checkpoint_provenance",
    "result_bucket",
    "ppo_evidence_level",
    "controller_path",
    "adapter_mode",
    "koopman_backend",
    "reward_profile",
    "observation_dim",
    "action_dim",
    "adapter_refresh_count",
    "adapter_refresh_before_env_step",
    "policy_action_clip_rate",
    "training_loop_fallback_rate",
    "training_loop_latency_ms_mean",
    "training_loop_latency_ms_max",
    "training_loop_pwm_min",
    "training_loop_pwm_max",
    "nonfinite_observation_count",
    "nonfinite_action_count",
    "nonfinite_reward_count",
    "completion_status",
)


WARNING_THRESHOLDS = {
    "policy_action_clip_rate": 0.5,
    "training_loop_fallback_rate": 0.2,
    "training_loop_latency_ms_mean": 20.0,
    "training_loop_latency_ms_max": 50.0,
    "latency_budget_violation_rate": 0.1,
}


def _load_summary(path: str | Path) -> dict[str, Any]:
    summary_path = Path(path)
    if not summary_path.exists():
        raise ValueError(f"summary path does not exist: {summary_path}")
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("stability summary must be a JSON object")
    return payload


def _require_fields(summary: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in summary]
    if missing:
        raise ValueError(f"Missing Phase 5.1 stability fields: {missing}")


def _as_float(summary: dict[str, Any], field_name: str) -> float | None:
    value = summary.get(field_name, "unavailable")
    if value == "unavailable":
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite or 'unavailable'")
    return numeric


def _require_expected_values(summary: dict[str, Any]) -> None:
    evidence_level = summary["ppo_evidence_level"]
    if evidence_level not in PHASE5_1_TRAINING_EVIDENCE_LEVELS:
        raise ValueError(f"ppo_evidence_level must be one of {list(PHASE5_1_TRAINING_EVIDENCE_LEVELS)}")
    expected_values = {
        "result_bucket": PHASE5_RESULT_BUCKET,
        "checkpoint_provenance": PHASE5_1_PROVENANCE_BY_EVIDENCE_LEVEL[evidence_level],
        "controller_path": PHASE5_CONTROLLER_PATH,
        "adapter_mode": ADAPTER_MODE,
        "koopman_backend": "direct_state",
        "reward_profile": PHASE5_REWARD_PROFILE,
        "observation_dim": 9,
        "action_dim": 4,
    }
    for field_name, expected in expected_values.items():
        if summary[field_name] != expected:
            raise ValueError(f"{field_name} must be {expected!r}, got {summary[field_name]!r}")


def _require_hard_health(summary: dict[str, Any]) -> None:
    if summary["checkpoint_found"] is not True:
        raise ValueError("checkpoint_found must be true")
    checkpoint = Path(str(summary["selected_checkpoint"]))
    if not checkpoint.exists():
        raise ValueError(f"selected_checkpoint does not exist: {checkpoint}")
    if int(summary["adapter_refresh_count"]) <= 0:
        raise ValueError("adapter_refresh_count must be greater than zero")
    if summary["adapter_refresh_before_env_step"] is not True:
        raise ValueError("adapter_refresh_before_env_step must be true")
    for field_name in ("nonfinite_observation_count", "nonfinite_action_count", "nonfinite_reward_count"):
        if int(summary[field_name]) != 0:
            raise ValueError(f"{field_name} must be zero")
    pwm_min = _as_float(summary, "training_loop_pwm_min")
    pwm_max = _as_float(summary, "training_loop_pwm_max")
    if pwm_min is not None and pwm_min < -1.0:
        raise ValueError("training_loop_pwm_min must be within [-1, 1]")
    if pwm_max is not None and pwm_max > 1.0:
        raise ValueError("training_loop_pwm_max must be within [-1, 1]")


def _collect_warnings(summary: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for field_name, threshold in WARNING_THRESHOLDS.items():
        value = _as_float(summary, field_name)
        if value is not None and value > threshold:
            warnings.append(f"{field_name}={value} exceeds warning threshold {threshold}")
    return warnings


def validate_phase5_1_stability_summary(path: str | Path) -> dict[str, Any]:
    summary_path = Path(path)
    summary = _load_summary(summary_path)
    _require_fields(summary)
    _require_expected_values(summary)
    _require_hard_health(summary)
    warnings = _collect_warnings(summary)
    return {
        "stable_training_gate": "pass_with_warnings" if warnings else "pass",
        "summary_path": str(summary_path),
        "selected_checkpoint": summary["selected_checkpoint"],
        "selected_weight_status": summary.get("selected_weight_status", "candidate_only"),
        "warnings": warnings,
        "recommendation": _recommend_next_step(warnings),
    }


def _recommend_next_step(warnings: list[str]) -> str:
    joined = " ".join(warnings)
    if "fallback" in joined:
        return "fix_mpc_fallback"
    if "latency" in joined:
        return "fix_mpc_latency"
    if "clip" in joined:
        return "tune_adapter_scales"
    return "proceed_to_matched_evaluation"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Phase 5.1 stability summary JSON.")
    parser.add_argument("path", type=Path, help="Phase 5.1 stability summary JSON.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    try:
        result = validate_phase5_1_stability_summary(args.path)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"stable_training_gate={result['stable_training_gate']}")
        print(f"selected_checkpoint={result['selected_checkpoint']}")
        print(f"selected_weight_status={result['selected_weight_status']}")
        for warning in result["warnings"]:
            print(f"WARNING: {warning}")
        print(f"recommendation={result['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np


def _vector(sample: dict[str, Any], field_name: str, default: list[float] | None = None) -> list[float]:
    values = sample.get(field_name, default)
    if values is None:
        return []
    if hasattr(values, "tolist"):
        values = values.tolist()
    return [float(value) for value in values]


def _quat_sign_equivalent_error(left: list[float], right: list[float]) -> float:
    if len(left) != 4 or len(right) != 4:
        return float("nan")
    same = max(abs(a - b) for a, b in zip(left, right))
    opposite = max(abs(a + b) for a, b in zip(left, right))
    return min(same, opposite)


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"Expected JSON object in {path}")
            samples.append(payload)
    return samples


def analyze_samples(
    samples: Iterable[dict[str, Any]],
    *,
    pwm_saturation_threshold: float = 0.99,
    latency_budget_ms: float = 20.0,
) -> dict[str, Any]:
    sample_list = list(samples)
    if not sample_list:
        raise ValueError("No samples to analyze")

    fallback_count = 0
    fallback_reasons: Counter[str] = Counter()
    fallback_reasons_by_trajectory: dict[str, Counter[str]] = {}
    latency_values: list[float] = []
    latency_budget_violation_count = 0
    clip_values: list[float] = []
    pwm_values: list[float] = []
    pwm_saturated = 0
    pwm_total = 0
    depth_errors: list[float] = []
    attitude_errors: list[float] = []

    for sample in sample_list:
        diagnostics = sample.get("solver_diagnostics") or {}
        trajectory_type = str(sample.get("trajectory_type", "unknown"))
        fallback_used = bool(diagnostics.get("fallback_used", False))
        fallback_count += int(fallback_used)
        if fallback_used:
            reason = diagnostics.get("fallback_reason") or "unspecified"
            fallback_reasons[str(reason)] += 1
            fallback_reasons_by_trajectory.setdefault(trajectory_type, Counter())[str(reason)] += 1

        latency = diagnostics.get("latency_ms", 0.0) or 0.0
        latency_float = float(latency)
        latency_values.append(latency_float)
        latency_budget_violation_count += int(latency_float > latency_budget_ms)
        clip_values.append(float(sample.get("policy_action_clip_rate", 0.0) or 0.0))

        pwm = _vector(sample, "pwm_8d")
        pwm_values.extend(abs(value) for value in pwm)
        pwm_saturated += sum(1 for value in pwm if abs(value) >= pwm_saturation_threshold)
        pwm_total += len(pwm)

        state = _vector(sample, "next_state", _vector(sample, "state"))
        reference = _vector(sample, "reference")
        if len(state) >= 1 and len(reference) >= 1:
            depth_errors.append(state[0] - reference[0])
        if len(state) >= 5 and len(reference) >= 5:
            error = _quat_sign_equivalent_error(state[1:5], reference[1:5])
            if math.isfinite(error):
                attitude_errors.append(error)

    depth_rmse = float(np.sqrt(np.mean(np.square(depth_errors)))) if depth_errors else float("nan")
    attitude_rmse = float(np.sqrt(np.mean(np.square(attitude_errors)))) if attitude_errors else float("nan")
    latency_array = np.asarray(latency_values, dtype=float)
    clip_array = np.asarray(clip_values, dtype=float)
    pwm_array = np.asarray(pwm_values, dtype=float)

    return {
        "sample_count": len(sample_list),
        "fallback_count": int(fallback_count),
        "fallback_rate": float(fallback_count / len(sample_list)),
        "fallback_reason_counts": dict(sorted(fallback_reasons.items())),
        "latency_ms_mean": float(np.mean(latency_array)) if latency_array.size else 0.0,
        "latency_ms_max": float(np.max(latency_array)) if latency_array.size else 0.0,
        "latency_budget_ms": float(latency_budget_ms),
        "latency_budget_violation_rate": float(latency_budget_violation_count / len(sample_list)),
        "policy_action_clip_rate_mean": float(np.mean(clip_array)) if clip_array.size else 0.0,
        "policy_action_clip_rate_max": float(np.max(clip_array)) if clip_array.size else 0.0,
        "pwm_saturation_threshold": float(pwm_saturation_threshold),
        "pwm_saturation_rate": float(pwm_saturated / pwm_total) if pwm_total else 0.0,
        "pwm_abs_mean": float(np.mean(pwm_array)) if pwm_array.size else 0.0,
        "pwm_abs_max": float(np.max(pwm_array)) if pwm_array.size else 0.0,
        "depth_rmse": depth_rmse,
        "attitude_rmse": attitude_rmse,
        "fallback_reason_counts_by_trajectory": {
            trajectory_type: dict(sorted(reason_counts.items()))
            for trajectory_type, reason_counts in sorted(fallback_reasons_by_trajectory.items())
        },
    }


def analyze_log(
    path: str | Path,
    *,
    pwm_saturation_threshold: float = 0.99,
    latency_budget_ms: float = 20.0,
) -> dict[str, Any]:
    summary = analyze_samples(
        load_jsonl(path),
        pwm_saturation_threshold=pwm_saturation_threshold,
        latency_budget_ms=latency_budget_ms,
    )
    summary["path"] = str(path)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze Phase 5.2 PPO/Koopman health metrics from JSONL logs.")
    parser.add_argument("paths", nargs="+", type=Path, help="PPO/Koopman JSONL logs.")
    parser.add_argument("--pwm_saturation_threshold", type=float, default=0.99)
    parser.add_argument("--latency_budget_ms", type=float, default=20.0)
    parser.add_argument("--summary_path", type=Path, default=None, help="Optional JSON summary path.")
    args = parser.parse_args(argv)

    try:
        payload = {
            "runs": [
                analyze_log(
                    path,
                    pwm_saturation_threshold=args.pwm_saturation_threshold,
                    latency_budget_ms=args.latency_budget_ms,
                )
                for path in args.paths
            ]
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output = json.dumps(payload, indent=2)
    if args.summary_path:
        args.summary_path.parent.mkdir(parents=True, exist_ok=True)
        args.summary_path.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

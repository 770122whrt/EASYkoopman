from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.mpc import MPCBounds, MPCConfig, MPCWeights, tracking_cost
from koopman.runtime import load_koopman_runtime
from koopman.mpc_controller import KoopmanMPCController
from koopman_data import load_koopman_samples


DEFAULT_LIMITATIONS = [
    "selected backend is direct_state, not paper_lifted_edmd",
    "Phase 2.5 is an offline model gate, not closed-loop control evidence",
    "Phase 4 must compare legacy and Koopman MPC before performance claims",
]


def _config_from_args(args: argparse.Namespace) -> MPCConfig:
    return MPCConfig(
        horizon=args.horizon,
        timeout_ms=args.timeout_ms,
        bounds=MPCBounds(delta_pwm_limit=args.delta_pwm_limit),
        weights=MPCWeights(
            depth=args.depth_weight,
            attitude=args.attitude_weight,
            control=args.control_weight,
            smoothness=args.smoothness_weight,
        ),
    )


def run_offline(args: argparse.Namespace) -> dict:
    runtime = load_koopman_runtime(args.manifest, project_root=PROJECT_ROOT)
    controller = KoopmanMPCController(runtime, _config_from_args(args))
    samples = load_koopman_samples(args.log)[: args.max_samples]
    if not samples:
        raise ValueError("No samples available for offline MPC replay")

    previous_pwm = np.zeros(8)
    commands: list[list[float]] = []
    latencies: list[float] = []
    costs: list[float] = []
    fallback_count = 0
    for sample in samples:
        output = controller.command(
            np.asarray(sample["state"], dtype=float),
            np.asarray(sample["reference"], dtype=float),
            previous_pwm=previous_pwm,
            legacy_pwm=np.asarray(sample["pwm_8d"], dtype=float),
        )
        previous_pwm = output.pwm
        commands.append(output.pwm.tolist())
        latencies.append(float(output.diagnostics.get("latency_ms") or 0.0))
        fallback_count += int(output.fallback_used)
        costs.append(
            tracking_cost(
                np.asarray(sample["state"], dtype=float),
                np.asarray(sample["reference"], dtype=float),
                controller.config.weights,
            )
        )

    pwm_array = np.asarray(commands, dtype=float)
    command_bounded = bool(np.min(pwm_array) >= -1.0 and np.max(pwm_array) <= 1.0)
    latency_budget_met = bool(np.max(latencies) <= controller.config.timeout_ms) if latencies else True
    return {
        "manifest_path": str(args.manifest),
        "backend_used": runtime.backend_used,
        "backend_reason": f"selected manifest model_class is {runtime.model_class}",
        "backend_is_paper_style_lifted_edmd": runtime.backend_is_paper_style_lifted_edmd,
        "known_limitations": list(runtime.known_limitations) or list(DEFAULT_LIMITATIONS),
        "horizon": int(controller.config.horizon),
        "sample_count": len(samples),
        "average_latency_ms": float(np.mean(latencies)),
        "max_latency_ms": float(np.max(latencies)),
        "fallback_count": int(fallback_count),
        "fallback_rate": float(fallback_count / len(samples)),
        "pwm_min": float(np.min(pwm_array)),
        "pwm_max": float(np.max(pwm_array)),
        "command_bounded": command_bounded,
        "latency_budget_met": latency_budget_met,
        "mean_tracking_cost": float(np.mean(costs)),
        "first_commands": commands[:5],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Isaac-free Koopman MPC replay on logged samples.")
    parser.add_argument("--manifest", required=True, type=Path, help="Selected model manifest JSON.")
    parser.add_argument("--log", required=True, type=Path, help="Koopman JSONL log path.")
    parser.add_argument("--output", required=True, type=Path, help="Output offline report JSON.")
    parser.add_argument("--max_samples", type=int, default=10, help="Maximum samples to replay.")
    parser.add_argument("--horizon", type=int, default=5, help="MPC horizon.")
    parser.add_argument("--timeout_ms", type=float, default=12.0, help="MPC per-command timeout in milliseconds.")
    parser.add_argument("--delta_pwm_limit", type=float, default=0.35, help="Per-step PWM delta limit.")
    parser.add_argument("--depth_weight", type=float, default=1.0)
    parser.add_argument("--attitude_weight", type=float, default=1.0)
    parser.add_argument("--control_weight", type=float, default=0.01)
    parser.add_argument("--smoothness_weight", type=float, default=0.05)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_offline(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[INFO] wrote offline Koopman MPC report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

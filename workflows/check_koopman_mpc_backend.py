from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.mpc import MPCBounds, MPCConfig, MPCWeights
from koopman.mpc_controller import KoopmanMPCController
from koopman.runtime import load_koopman_runtime, load_koopman_runtime_from_manifest
from koopman_data import load_koopman_samples


DEFAULT_LIMITATIONS = [
    "selected backend is direct_state, not paper_lifted_edmd",
    "Phase 2.5 is an offline model gate, not closed-loop performance evidence",
    "Phase 4 must compare closed-loop performance before superiority claims",
]


def _score(candidate: dict) -> tuple[float, float]:
    metrics = candidate.get("validation_metrics", {})
    return (
        float(metrics.get("multi_step_rmse@20", float("inf"))),
        float(metrics.get("multi_step_rmse@60", float("inf"))),
    )


def select_best_paper_lifted_candidate(sweep_results: dict) -> dict | None:
    candidates = [
        candidate
        for candidate in sweep_results.get("candidates", [])
        if candidate.get("model_class") == "paper_lifted_edmd" and candidate.get("status") == "pass"
    ]
    candidates.sort(key=_score)
    return candidates[0] if candidates else None


def _runtime_from_candidate(candidate: dict, sweep_path: Path):
    manifest = _manifest_from_candidate(candidate)
    return load_koopman_runtime_from_manifest(manifest, manifest_path=sweep_path, project_root=PROJECT_ROOT)


def _manifest_from_candidate(candidate: dict) -> dict:
    return {
        "gate_status": "pass",
        "selected_candidate_id": candidate.get("candidate_id"),
        "model_class": candidate.get("model_class"),
        "model_path": candidate.get("model_path"),
        "state_dim": candidate.get("state_dim", 11),
        "reference_dim": candidate.get("reference_dim", 5),
        "control_dim": candidate.get("control_dim", 8),
        "dt": candidate.get("dt", 1 / 60),
        "known_limitations": [
            "paper_lifted_edmd backend selected by Phase 3 backend check, not by the Phase 2.5 selected manifest",
            "Phase 4 must compare closed-loop behavior before performance claims",
        ],
    }


def _evaluate_runtime(runtime, samples, config: MPCConfig) -> dict:
    controller = KoopmanMPCController(runtime, config)
    previous_pwm = np.zeros(8)
    commands = []
    latencies = []
    fallback_count = 0
    finite_prediction_count = 0
    costs = []
    for sample in samples:
        state = np.asarray(sample["state"], dtype=float)
        reference = np.asarray(sample["reference"], dtype=float)
        legacy_pwm = np.asarray(sample["pwm_8d"], dtype=float)
        try:
            prediction = runtime.predict_next(state, previous_pwm, reference)
            finite_prediction_count += int(np.isfinite(prediction).all())
        except Exception:
            pass
        output = controller.command(state, reference, previous_pwm=previous_pwm, legacy_pwm=legacy_pwm)
        previous_pwm = output.pwm
        commands.append(output.pwm)
        latencies.append(float(output.diagnostics.get("latency_ms") or 0.0))
        fallback_count += int(output.fallback_used)
        cost = output.diagnostics.get("cost")
        if cost is not None:
            costs.append(float(cost))
    command_array = np.asarray(commands, dtype=float)
    return {
        "backend_used": runtime.backend_used,
        "candidate_id": runtime.manifest.get("selected_candidate_id"),
        "finite_prediction_count": int(finite_prediction_count),
        "sample_count": len(samples),
        "fallback_count": int(fallback_count),
        "fallback_rate": float(fallback_count / max(len(samples), 1)),
        "average_latency_ms": float(np.mean(latencies)) if latencies else 0.0,
        "max_latency_ms": float(np.max(latencies)) if latencies else 0.0,
        "mean_horizon_cost": float(np.mean(costs)) if costs else float("inf"),
        "pwm_min": float(np.min(command_array)) if command_array.size else 0.0,
        "pwm_max": float(np.max(command_array)) if command_array.size else 0.0,
        "command_bounded": bool(command_array.size == 0 or (np.min(command_array) >= -1.0 and np.max(command_array) <= 1.0)),
    }


def _choose_backend(direct_metrics: dict, paper_metrics: dict | None) -> tuple[str, str]:
    if paper_metrics is None:
        return "direct_state", "no passing paper_lifted_edmd candidate was available"
    paper_safe = (
        paper_metrics["finite_prediction_count"] == paper_metrics["sample_count"]
        and paper_metrics["command_bounded"]
        and paper_metrics["fallback_rate"] <= direct_metrics["fallback_rate"]
    )
    paper_better_cost = paper_metrics["mean_horizon_cost"] < direct_metrics["mean_horizon_cost"]
    if paper_safe and paper_better_cost:
        return "paper_lifted_edmd", "paper_lifted_edmd was finite, bounded, no less safe, and lower offline horizon cost"
    return "direct_state", "direct_state kept for first Isaac smoke because it is the selected Phase 2.5 backend or safer offline"


def run_backend_check(args: argparse.Namespace) -> dict:
    direct_runtime = load_koopman_runtime(args.manifest, project_root=PROJECT_ROOT)
    sweep_results = json.loads(args.sweep_results.read_text(encoding="utf-8"))
    best_paper = select_best_paper_lifted_candidate(sweep_results)
    samples = load_koopman_samples(args.log)[: args.max_samples]
    if not samples:
        raise ValueError("No samples available for backend check")

    config = MPCConfig(
        horizon=args.horizon,
        timeout_ms=args.timeout_ms,
        bounds=MPCBounds(delta_pwm_limit=args.delta_pwm_limit),
        weights=MPCWeights(),
    )
    direct_metrics = _evaluate_runtime(direct_runtime, samples, config)
    paper_metrics = None
    if best_paper is not None:
        paper_runtime = _runtime_from_candidate(best_paper, args.sweep_results)
        paper_metrics = _evaluate_runtime(paper_runtime, samples, config)

    backend_used, backend_reason = _choose_backend(direct_metrics, paper_metrics)
    limitations = list(direct_runtime.known_limitations) or list(DEFAULT_LIMITATIONS)
    recommended_manifest_path = str(args.manifest)
    if backend_used == "paper_lifted_edmd" and best_paper is not None:
        recommended_manifest = _manifest_from_candidate(best_paper)
        recommended_path = args.output.with_name("backend_selected_manifest.json")
        recommended_path.parent.mkdir(parents=True, exist_ok=True)
        recommended_path.write_text(json.dumps(recommended_manifest, indent=2, sort_keys=True), encoding="utf-8")
        recommended_manifest_path = str(recommended_path)

    return {
        "backend_used": backend_used,
        "backend_reason": backend_reason,
        "recommended_manifest_path": recommended_manifest_path,
        "direct_state_metrics": direct_metrics,
        "paper_lifted_edmd_metrics": paper_metrics or {"status": "missing"},
        "paper_alignment_note": (
            "A direct_state smoke validates fallback-safe engineering integration. "
            "A paper_lifted_edmd smoke is closer to the Koopman-Sim2Real algorithmic form, "
            "but Phase 4 is still required before performance or full-paper-equivalence claims."
        ),
        "known_limitations": limitations,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare direct_state and paper_lifted_edmd backends before MPC smoke.")
    parser.add_argument("--manifest", required=True, type=Path, help="Selected model manifest JSON.")
    parser.add_argument("--sweep_results", required=True, type=Path, help="Phase 2.5 sweep_results.json.")
    parser.add_argument("--log", required=True, type=Path, help="Koopman JSONL log path for replay samples.")
    parser.add_argument("--output", required=True, type=Path, help="Output backend decision report JSON.")
    parser.add_argument("--max_samples", type=int, default=10)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--timeout_ms", type=float, default=12.0)
    parser.add_argument("--delta_pwm_limit", type=float, default=0.35)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_backend_check(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[INFO] wrote backend check report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

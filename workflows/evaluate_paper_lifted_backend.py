from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.dataset import load_dataset
from koopman.evaluation import evaluate_model, has_diverged
from koopman.runtime import load_koopman_runtime
from koopman.splits import read_split_manifest


def _evaluate_runtime(runtime, validation_logs: list[str], test_logs: list[str], horizons: tuple[int, ...]) -> dict[str, Any]:
    validation_dataset = load_dataset(validation_logs)
    test_dataset = load_dataset(test_logs)
    validation_metrics = evaluate_model(runtime.model, validation_dataset, horizons=horizons)
    test_metrics = evaluate_model(runtime.model, test_dataset, horizons=horizons)
    nonfinite_count = int(validation_metrics.get("nonfinite_count", 0)) + int(test_metrics.get("nonfinite_count", 0))
    diverged = has_diverged(validation_metrics) or has_diverged(test_metrics)
    return {
        "backend_used": runtime.backend_used,
        "candidate_id": runtime.manifest.get("selected_candidate_id"),
        "backend_is_paper_style_lifted_edmd": runtime.backend_is_paper_style_lifted_edmd,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "nonfinite_count": nonfinite_count,
        "diverged": bool(diverged),
        "known_limitations": list(runtime.known_limitations),
    }


def run_report(args: argparse.Namespace) -> dict[str, Any]:
    split = read_split_manifest(args.split_manifest)
    if not split.validation_logs or not split.test_logs:
        raise ValueError("split manifest must include validation and test logs")
    horizons = tuple(args.horizon)

    direct_runtime = load_koopman_runtime(args.direct_manifest, project_root=PROJECT_ROOT)
    paper_runtime = load_koopman_runtime(args.paper_manifest, project_root=PROJECT_ROOT)
    direct_report = _evaluate_runtime(direct_runtime, split.validation_logs, split.test_logs, horizons)
    paper_report = _evaluate_runtime(paper_runtime, split.validation_logs, split.test_logs, horizons)

    paper_eligible = (
        paper_runtime.backend_is_paper_style_lifted_edmd
        and paper_report["nonfinite_count"] == 0
        and not paper_report["diverged"]
    )
    recommendation = "paper_lifted_eligible_for_isaac_smoke" if paper_eligible else "paper_lifted_diagnostic_only"
    limitations = list(paper_report["known_limitations"]) or [
        "paper_lifted_edmd still requires Isaac smoke before Phase 4 performance claims"
    ]

    return {
        "direct_state": direct_report,
        "paper_lifted_edmd": paper_report,
        "recommendation": recommendation,
        "known_limitations": limitations,
        "comparison_note": (
            "This report compares prediction behavior only. Isaac smoke and closed-loop Phase 4 metrics "
            "are required before performance claims."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare direct-state and paper-lifted Koopman prediction metrics.")
    parser.add_argument("--direct-manifest", required=True, type=Path, help="Phase 2.5 direct-state selected manifest.")
    parser.add_argument("--paper-manifest", required=True, type=Path, help="Phase 3.5 paper_lifted_edmd manifest.")
    parser.add_argument("--split-manifest", required=True, type=Path, help="Train/validation/test split manifest.")
    parser.add_argument("--output", required=True, type=Path, help="Output comparison report JSON.")
    parser.add_argument("--horizon", action="append", type=int, default=None, help="Evaluation horizon; repeatable.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.horizon is None:
        args.horizon = [5, 20, 60]
    report = run_report(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[INFO] wrote paper lifted backend report to {args.output}")
    print(f"[INFO] recommendation={report['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

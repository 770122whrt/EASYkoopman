from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .dataset import load_dataset
from .evaluation import evaluate_model, has_diverged
from .lifted_edmd import LiftedEDMDModel
from .model import KoopmanModel


def _load_model(model_class: str, path: str | Path):
    if model_class == "direct_state":
        return KoopmanModel.load(path)
    if model_class == "paper_lifted_edmd":
        return LiftedEDMDModel.load(path)
    raise ValueError(f"Unsupported model_class: {model_class}")


def _score(metrics: dict[str, Any]) -> float:
    return float(metrics.get("multi_step_rmse@20", metrics.get("multi_step_rmse", float("inf"))))


def _baseline_scores(summary: dict) -> dict[str, float]:
    scores: dict[str, float] = {}
    for name, result in summary.get("baselines", {}).items():
        scores[name] = _score(result.get("validation_metrics", {}))
    return scores


def select_model_from_sweep(sweep_results_path: str | Path, output_path: str | Path) -> dict:
    summary = json.loads(Path(sweep_results_path).read_text(encoding="utf-8"))
    candidates = list(summary.get("candidates", []))
    candidates.sort(
        key=lambda candidate: (
            0 if candidate.get("status") == "pass" else 1,
            _score(candidate.get("validation_metrics", {})),
            float(candidate.get("validation_metrics", {}).get("multi_step_rmse@60", float("inf"))),
        )
    )
    selected = candidates[0] if candidates else {}
    limitations: list[str] = []
    gate_status = "fail"
    test_metrics: dict[str, Any] | None = None

    if not selected:
        limitations.append("no candidate models were available")
    elif selected.get("status") != "pass" or has_diverged(selected.get("validation_metrics", {})):
        limitations.append("selected candidate diverged on validation logs")
    else:
        selected_score = _score(selected.get("validation_metrics", {}))
        baselines = _baseline_scores(summary)
        if baselines and not all(selected_score < score for score in baselines.values()):
            limitations.append("selected candidate did not beat persistence and simple linear baselines")
        else:
            test_logs = summary.get("split", {}).get("test_logs", [])
            if not test_logs:
                limitations.append("no held-out test logs were available")
            else:
                model = _load_model(str(selected["model_class"]), selected["model_path"])
                test_dataset = load_dataset(test_logs)
                test_metrics = evaluate_model(model, test_dataset, horizons=summary.get("horizons", (5, 20, 60)))
                if has_diverged(test_metrics):
                    limitations.append("selected candidate diverged on held-out test logs")
                else:
                    gate_status = "pass"

    metrics: dict[str, Any] = {"validation": selected.get("validation_metrics", {})}
    if test_metrics is not None:
        metrics["test"] = test_metrics

    manifest = {
        "gate_status": gate_status,
        "selected_candidate_id": selected.get("candidate_id"),
        "model_class": selected.get("model_class"),
        "model_path": selected.get("model_path"),
        "normalizer_path": selected.get("normalizer_path"),
        "state_dim": selected.get("state_dim"),
        "reference_dim": selected.get("reference_dim"),
        "control_dim": selected.get("control_dim"),
        "dt": selected.get("dt"),
        "lifting_config": selected.get("lifting_config"),
        "ridge": selected.get("ridge"),
        "train_logs": summary.get("split", {}).get("train_logs", []),
        "validation_logs": summary.get("split", {}).get("validation_logs", []),
        "test_logs": summary.get("split", {}).get("test_logs", []),
        "metrics": metrics,
        "baselines": summary.get("baselines", {}),
        "known_limitations": limitations,
        "sweep_results_path": str(sweep_results_path),
    }

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest

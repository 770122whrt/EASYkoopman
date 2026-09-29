from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evaluation import has_diverged


PAPER_LIFTED_LIMITATIONS = [
    "paper_lifted_edmd is a paper-aligned comparison backend, not yet the primary selected controller backend",
    "Phase 3.5 must run offline MPC replay and Isaac smoke before Phase 4 performance claims",
    "Online adaptation remains deferred",
]


def _metric(candidate: dict[str, Any], key: str) -> float:
    return float(candidate.get("validation_metrics", {}).get(key, float("inf")))


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, float, int]:
    variant_penalty = 0 if candidate.get("lifting_variant") == "linear" else 1
    return (
        _metric(candidate, "multi_step_rmse@20"),
        _metric(candidate, "multi_step_rmse@60"),
        variant_penalty,
    )


def _passing_paper_lifted_candidates(sweep: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        candidate
        for candidate in sweep.get("candidates", [])
        if candidate.get("model_class") == "paper_lifted_edmd"
        and candidate.get("status") == "pass"
        and not has_diverged(candidate.get("validation_metrics", {}))
    ]
    candidates.sort(key=_candidate_sort_key)
    return candidates


def _manifest_from_candidate(candidate: dict[str, Any], sweep: dict[str, Any], sweep_results_path: str | Path) -> dict[str, Any]:
    split = sweep.get("split", {})
    limitations = [
        str(item)
        for item in candidate.get("known_limitations", [])
        if str(item).strip()
    ] or list(PAPER_LIFTED_LIMITATIONS)
    return {
        "gate_status": "pass",
        "selection_role": "paper_style_comparison_backend",
        "selected_candidate_id": candidate.get("candidate_id"),
        "model_class": "paper_lifted_edmd",
        "model_path": candidate.get("model_path"),
        "normalizer_path": candidate.get("normalizer_path"),
        "state_dim": candidate.get("state_dim"),
        "reference_dim": candidate.get("reference_dim"),
        "control_dim": candidate.get("control_dim"),
        "dt": candidate.get("dt"),
        "observable_config": candidate.get("lifting_config"),
        "lifting_config": candidate.get("lifting_config"),
        "lifting_variant": candidate.get("lifting_variant"),
        "normalization": candidate.get("normalization"),
        "ridge": candidate.get("ridge"),
        "train_logs": split.get("train_logs", []),
        "validation_logs": split.get("validation_logs", []),
        "test_logs": split.get("test_logs", []),
        "metrics": {"validation": candidate.get("validation_metrics", {})},
        "baselines": sweep.get("baselines", {}),
        "known_limitations": limitations,
        "sweep_results_path": str(sweep_results_path),
    }


def _failed_manifest(reason: str, sweep_results_path: str | Path) -> dict[str, Any]:
    return {
        "gate_status": "fail",
        "selection_role": "paper_style_comparison_backend",
        "selected_candidate_id": None,
        "model_class": "paper_lifted_edmd",
        "model_path": None,
        "normalizer_path": None,
        "state_dim": 11,
        "reference_dim": 5,
        "control_dim": 8,
        "dt": None,
        "metrics": {},
        "known_limitations": [reason],
        "sweep_results_path": str(sweep_results_path),
    }


def select_paper_lifted_from_sweep(sweep_results_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    """Select the best passing paper_lifted_edmd candidate as a comparison backend."""
    sweep_path = Path(sweep_results_path)
    sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
    candidates = _passing_paper_lifted_candidates(sweep)
    if not candidates:
        manifest = _failed_manifest("no passing paper_lifted_edmd candidate was available", sweep_path)
    else:
        manifest = _manifest_from_candidate(candidates[0], sweep, sweep_path)

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest

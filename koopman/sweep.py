from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .baselines import PersistenceBaseline, fit_simple_linear_baseline
from .dataset import load_dataset
from .edmd import fit_edmd
from .evaluation import evaluate_model, has_diverged, write_metrics
from .lifted_edmd import fit_lifted_edmd
from .lifting import LiftingConfig
from .normalization import write_normalizer_artifact
from .observables import PaperObservableConfig
from .splits import read_split_manifest, validate_split_manifest


DEFAULT_HORIZONS = (5, 20, 60)
DEFAULT_RIDGES = (1e-8, 1e-6, 1e-4, 1e-2)
DEFAULT_LIFTING_VARIANTS = ("linear", "selected_quadratic")
DEFAULT_NORMALIZATION_MODES = ("off", "standard")


def _safe_token(value: float | str) -> str:
    return str(value).replace("-", "m").replace("+", "").replace(".", "p")


def _status(metrics: dict) -> str:
    return "fail" if has_diverged(metrics) else "pass"


def _normalizer_path(model, target: Path, enabled: bool) -> str | None:
    if not enabled:
        return None
    write_normalizer_artifact(
        target,
        input_normalizer=getattr(model, "input_normalizer", None),
        target_normalizer=getattr(model, "target_normalizer", None),
    )
    return str(target)


def _candidate_sort_key(candidate: dict) -> tuple:
    metrics = candidate["validation_metrics"]
    return (
        0 if candidate["status"] == "pass" else 1,
        float(metrics.get("multi_step_rmse@20", float("inf"))),
        float(metrics.get("multi_step_rmse@60", float("inf"))),
        0 if candidate.get("lifting_variant") == "linear" else 1,
    )


def run_sweep(
    split_manifest_path: str | Path,
    output_dir: str | Path,
    *,
    ridge_values: Iterable[float] = DEFAULT_RIDGES,
    lifting_variants: Iterable[str] = DEFAULT_LIFTING_VARIANTS,
    normalization_modes: Iterable[str] = DEFAULT_NORMALIZATION_MODES,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
) -> dict:
    manifest = read_split_manifest(split_manifest_path)
    validate_split_manifest(manifest, final_gate=True)

    output = Path(output_dir)
    model_dir = output / "models"
    metrics_dir = output / "metrics"
    normalizer_dir = output / "normalizers"
    for directory in (model_dir, metrics_dir, normalizer_dir):
        directory.mkdir(parents=True, exist_ok=True)

    train_dataset = load_dataset(manifest.train_logs)
    validation_dataset = load_dataset(manifest.validation_logs)

    baselines = {
        "persistence": PersistenceBaseline(),
        "simple_linear": fit_simple_linear_baseline(train_dataset, ridge=1e-6),
    }
    baseline_results: dict[str, dict] = {}
    for name, model in baselines.items():
        metrics = evaluate_model(model, validation_dataset, horizons=horizons)
        baseline_results[name] = {
            "model_class": name,
            "validation_metrics": metrics,
            "status": _status(metrics),
        }
        write_metrics(metrics, metrics_dir / f"baseline_{name}_validation.json")

    candidates: list[dict] = []
    for ridge in ridge_values:
        for variant in lifting_variants:
            if variant not in {"linear", "selected_quadratic"}:
                raise ValueError("lifting variants must be 'linear' or 'selected_quadratic'")
            for normalization_mode in normalization_modes:
                if normalization_mode not in {"off", "standard"}:
                    raise ValueError("normalization modes must be 'off' or 'standard'")
                normalize = normalization_mode == "standard"

                direct_id = f"direct_state_{variant}_ridge_{_safe_token(ridge)}_norm_{normalization_mode}"
                direct = fit_edmd(
                    train_dataset,
                    lifting_config=LiftingConfig(include_quadratic=variant == "selected_quadratic"),
                    ridge=float(ridge),
                    normalize=normalize,
                    metadata={"model_class": "direct_state", "lifting_variant": variant},
                )
                direct_model_path = model_dir / f"{direct_id}.json"
                direct.save(direct_model_path)
                direct_metrics = evaluate_model(direct, validation_dataset, horizons=horizons)
                direct_normalizer_path = _normalizer_path(
                    direct,
                    normalizer_dir / f"{direct_id}.json",
                    normalize,
                )
                write_metrics(direct_metrics, metrics_dir / f"{direct_id}_validation.json")
                candidates.append(
                    {
                        "candidate_id": direct_id,
                        "model_class": "direct_state",
                        "model_path": str(direct_model_path),
                        "normalizer_path": direct_normalizer_path,
                        "ridge": float(ridge),
                        "lifting_variant": variant,
                        "lifting_config": direct.lifting_config.to_dict(),
                        "normalization": normalization_mode,
                        "state_dim": direct.state_dim,
                        "reference_dim": direct.reference_dim,
                        "control_dim": direct.control_dim,
                        "dt": train_dataset.dt,
                        "validation_metrics": direct_metrics,
                        "status": _status(direct_metrics),
                    }
                )

                lifted_id = f"paper_lifted_edmd_{variant}_ridge_{_safe_token(ridge)}_norm_{normalization_mode}"
                lifted = fit_lifted_edmd(
                    train_dataset,
                    observable_config=PaperObservableConfig(variant=variant),
                    ridge=float(ridge),
                    normalize=normalize,
                    metadata={"model_class": "paper_lifted_edmd", "lifting_variant": variant},
                )
                lifted_model_path = model_dir / f"{lifted_id}.json"
                lifted.save(lifted_model_path)
                lifted_metrics = evaluate_model(lifted, validation_dataset, horizons=horizons)
                lifted_normalizer_path = _normalizer_path(
                    lifted,
                    normalizer_dir / f"{lifted_id}.json",
                    normalize,
                )
                write_metrics(lifted_metrics, metrics_dir / f"{lifted_id}_validation.json")
                candidates.append(
                    {
                        "candidate_id": lifted_id,
                        "model_class": "paper_lifted_edmd",
                        "model_path": str(lifted_model_path),
                        "normalizer_path": lifted_normalizer_path,
                        "ridge": float(ridge),
                        "lifting_variant": variant,
                        "lifting_config": lifted.observable_config.to_dict(),
                        "normalization": normalization_mode,
                        "state_dim": lifted.state_dim,
                        "reference_dim": lifted.reference_dim,
                        "control_dim": lifted.control_dim,
                        "dt": train_dataset.dt,
                        "validation_metrics": lifted_metrics,
                        "status": _status(lifted_metrics),
                    }
                )

    candidates.sort(key=_candidate_sort_key)
    summary = {
        "status": "ok",
        "split_manifest_path": str(split_manifest_path),
        "split": manifest.to_dict(),
        "horizons": list(horizons),
        "baselines": baseline_results,
        "candidates": candidates,
        "best_candidate_id": candidates[0]["candidate_id"] if candidates else None,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "sweep_results.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary

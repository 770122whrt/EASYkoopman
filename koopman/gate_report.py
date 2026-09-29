from __future__ import annotations

from pathlib import Path


def _metric(metrics: dict, key: str) -> str:
    value = metrics.get(key)
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def render_gate_report(manifest: dict, sweep: dict) -> str:
    lines = [
        "# Phase 2.5 Koopman Model Gate Report",
        "",
        f"Gate Status: {manifest.get('gate_status', 'unknown')}",
        "",
        "## Selected Model",
        "",
        f"- Candidate: {manifest.get('selected_candidate_id', 'n/a')}",
        f"- Model class: {manifest.get('model_class', 'n/a')}",
        f"- Model path: {manifest.get('model_path', 'n/a')}",
        f"- Normalizer path: {manifest.get('normalizer_path') or 'none'}",
        f"- Ridge: {manifest.get('ridge', 'n/a')}",
        f"- dt: {manifest.get('dt', 'n/a')}",
        "",
        "## Data Split",
        "",
        f"- Train logs: {len(manifest.get('train_logs', []))}",
        f"- Validation logs: {len(manifest.get('validation_logs', []))}",
        f"- Test logs: {len(manifest.get('test_logs', []))}",
        "",
        "## Candidate Summary",
        "",
        "| Candidate | Class | Status | RMSE@20 | RMSE@60 |",
        "|---|---|---:|---:|---:|",
    ]
    for candidate in sweep.get("candidates", []):
        metrics = candidate.get("validation_metrics", {})
        lines.append(
            "| {candidate} | {model_class} | {status} | {rmse20} | {rmse60} |".format(
                candidate=candidate.get("candidate_id", "n/a"),
                model_class=candidate.get("model_class", "n/a"),
                status=candidate.get("status", "n/a"),
                rmse20=_metric(metrics, "multi_step_rmse@20"),
                rmse60=_metric(metrics, "multi_step_rmse@60"),
            )
        )

    lines.extend(
        [
            "",
            "## Baseline Comparison",
            "",
            "| Baseline | Status | RMSE@20 |",
            "|---|---:|---:|",
        ]
    )
    for name, baseline in manifest.get("baselines", {}).items():
        metrics = baseline.get("validation_metrics", {})
        lines.append(f"| {name} | {baseline.get('status', 'n/a')} | {_metric(metrics, 'multi_step_rmse@20')} |")

    validation = manifest.get("metrics", {}).get("validation", {})
    test = manifest.get("metrics", {}).get("test", {})
    lines.extend(
        [
            "",
            "## Held-Out Metrics",
            "",
            f"- Validation one-step RMSE: {_metric(validation, 'one_step_rmse')}",
            f"- Validation multi-step RMSE@20: {_metric(validation, 'multi_step_rmse@20')}",
            f"- Validation divergence_rate@20: {_metric(validation, 'divergence_rate@20')}",
            f"- Test one-step RMSE: {_metric(test, 'one_step_rmse')}",
            f"- Test multi-step RMSE@20: {_metric(test, 'multi_step_rmse@20')}",
            f"- Test divergence_rate@20: {_metric(test, 'divergence_rate@20')}",
            "",
            "## Known Limitations",
            "",
        ]
    )
    limitations = manifest.get("known_limitations") or ["none"]
    lines.extend(f"- {item}" for item in limitations)
    lines.extend(
        [
            "",
            "## Recommendation For Phase 3",
            "",
            (
                "Proceed to MPC integration with the selected manifest."
                if manifest.get("gate_status") == "pass"
                else "Do not start MPC integration with this model until the gate passes."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_gate_report(manifest: dict, sweep: dict, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_gate_report(manifest, sweep), encoding="utf-8")

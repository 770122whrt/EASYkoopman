"""Phase 5/6 offline state-manifold infrastructure.

This module is Isaac-independent and intentionally offline-first. It provides a
shared state-feature schema, SSWP context gates, and small bridge diagnostics
that can combine Flow Matching with state-only E-SUOT without touching the
online control path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import torch

from easyuuv_nc.esuot import ESUOTConfig, ESUOTTransport, LightOTConfig, LightOTTransport
from easyuuv_nc.esuot.semidual import pairwise_sq_dist

from .flow_matching import FlowMatchingConfig, ResidualFlowMLP, train_conditional_flow_matching
from .state_features import extract_state_features_from_csv, split_source_target_from_csv


PHASE56_STATE_FEATURE_COLUMNS = (
    "true_roll",
    "true_pitch",
    "true_yaw",
    "true_depth_v1",
    "runtime_motor_saturation_ratio",
    "runtime_motor_abs_max_raw",
    "phase4a_sswp_delta_norm",
    "phase4a_sswp_delta_abs_mean",
    "fault_efficiency_min",
    "depth_barrier_penalty",
)

PHASE56_SCHEMES = (
    "observed_direct",
    "safe_core_direct",
    "sswp_fault_to_safe",
)


@dataclass
class Phase56BridgeConfig:
    """Small offline configuration for Phase 5/6 bridge diagnostics."""

    max_samples: int = 128
    random_seed: int = 0
    fm_steps: int = 80
    fm_batch_size: int = 128
    fm_integration_steps: int = 12
    fm_hidden_dim: int = 64
    fm_depth: int = 2
    ot_eps: float = 0.1
    ot_iters: int = 120
    include_full_esuot: bool = False
    full_inner_iters: int = 12
    full_num_steps: int = 1
    device: str = "cpu"


def _num(frame: pd.DataFrame, column: str, default: float = np.nan) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([default] * len(frame), index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _bool_like(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([False] * len(frame), index=frame.index, dtype=bool)
    text = frame[column].astype(str).str.lower()
    if text.isin({"true", "false", "1", "0"}).any():
        return text.isin({"true", "1"})
    return _num(frame, column, default=0.0).fillna(0.0) >= 0.5


def _finite_mean(values: pd.Series) -> float | None:
    arr = values.to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None
    return float(np.mean(arr))


def _fraction(mask: pd.Series | np.ndarray) -> float:
    arr = np.asarray(mask, dtype=bool)
    if arr.size == 0:
        return 0.0
    return float(np.mean(arr))


def _take_rows(features: np.ndarray, frame: pd.DataFrame, mask: pd.Series | np.ndarray) -> tuple[np.ndarray, pd.DataFrame]:
    arr_mask = np.asarray(mask, dtype=bool)
    return features[arr_mask], frame.loc[arr_mask].reset_index(drop=True)


def _fallback_split(features: np.ndarray, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, pd.DataFrame, pd.DataFrame]:
    source, target = split_source_target_from_csv(frame, features)
    source_rows = frame.iloc[: len(source)].reset_index(drop=True)
    target_rows = frame.iloc[len(features) - len(target) :].reset_index(drop=True)
    return source, target, source_rows, target_rows


def _subsample(features: np.ndarray, max_samples: int, seed: int) -> np.ndarray:
    if features.shape[0] <= max_samples:
        return features
    rng = np.random.default_rng(int(seed))
    idx = np.sort(rng.choice(features.shape[0], size=max_samples, replace=False))
    return features[idx]


def _standardize(
    source: np.ndarray,
    target: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    both = np.concatenate([source, target], axis=0).astype(np.float32)
    mean = both.mean(axis=0)
    std = both.std(axis=0)
    std = np.where(std < 1.0e-6, 1.0, std)
    return (
        ((source - mean) / std).astype(np.float32),
        ((target - mean) / std).astype(np.float32),
        {"mean": mean.tolist(), "std": std.tolist()},
    )


def linear_geodesic_bridge(
    source: np.ndarray,
    target: np.ndarray,
    *,
    alpha: float,
) -> np.ndarray:
    """Simple discrete geodesic baseline: linear interpolation in state space."""

    alpha_f = float(np.clip(alpha, 0.0, 1.0))
    return ((1.0 - alpha_f) * np.asarray(source, dtype=np.float32) + alpha_f * np.asarray(target, dtype=np.float32)).astype(
        np.float32
    )


def phase56_alpha_to_index(num_trajectory_rows: int, *, alpha: float) -> int:
    """Map an alpha in [0, 1] to the closest FM trajectory row index."""

    if int(num_trajectory_rows) <= 0:
        raise ValueError("num_trajectory_rows must be positive.")
    alpha_f = float(np.clip(alpha, 0.0, 1.0))
    return max(min(int(round(alpha_f * (int(num_trajectory_rows) - 1))), int(num_trajectory_rows) - 1), 0)


def select_phase56_fm_target(
    trajectory: np.ndarray,
    *,
    alpha: float,
) -> tuple[np.ndarray, int]:
    """Select the alpha-indexed FM target manifold from a rollout trajectory."""

    traj = np.asarray(trajectory, dtype=np.float32)
    if traj.ndim != 3 or traj.shape[0] == 0:
        raise ValueError("trajectory must have shape (T, N, D) with T >= 1.")
    idx = phase56_alpha_to_index(traj.shape[0], alpha=alpha)
    return traj[idx], idx


def extract_phase56_features_from_csv(
    csv_path: str | Path,
    *,
    feature_columns: Iterable[str] | None = None,
) -> tuple[np.ndarray, list[str], pd.DataFrame]:
    """Extract deployable Phase 5/6 state features from a runtime CSV."""

    csv_df = pd.read_csv(Path(csv_path))
    requested = list(feature_columns or PHASE56_STATE_FEATURE_COLUMNS)
    available = [
        column
        for column in requested
        if column in csv_df.columns and pd.to_numeric(csv_df[column], errors="coerce").notna().any()
    ]
    if not available:
        raise ValueError(f"No Phase 5/6 feature columns found in {csv_path}.")
    feature_df = pd.DataFrame({column: pd.to_numeric(csv_df[column], errors="coerce") for column in available})
    mask = np.isfinite(feature_df.to_numpy(dtype=float)).all(axis=1)
    feature_df = feature_df.loc[mask].reset_index(drop=True)
    csv_df = csv_df.loc[mask].reset_index(drop=True)
    features = feature_df.to_numpy(dtype=np.float32)
    if features.ndim != 2 or features.shape[0] == 0:
        raise ValueError(f"Extracted empty Phase 5/6 features from {csv_path}.")
    return features, available, csv_df


def build_sswp_context_gate(frame: pd.DataFrame, *, quantile: float = 0.75) -> dict[str, Any]:
    """Build a deployable SSWP context gate from logged telemetry."""

    sswp = _num(frame, "phase4a_sswp_delta_norm", default=0.0).fillna(0.0)
    valid = _num(frame, "phase4a_sswp_valid", default=1.0).fillna(0.0) >= 0.5
    fault = _bool_like(frame, "fault_active")
    depth_safe = _num(frame, "depth_violation", default=0.0).fillna(0.0) < 0.5
    sat = _num(frame, "runtime_motor_saturation_ratio", default=0.0).fillna(0.0)
    sat_safe = sat <= 0.5
    threshold = float(np.nanquantile(sswp.to_numpy(dtype=float), float(quantile))) if len(sswp) else 0.0
    high_bias = valid & fault & depth_safe & (sswp >= threshold)
    low_bias = depth_safe & sat_safe & ((~fault) | (sswp <= float(np.nanquantile(sswp, 0.25))))
    return {
        "threshold": threshold,
        "high_bias_mask": high_bias,
        "low_bias_mask": low_bias,
        "summary": {
            "row_count": int(len(frame)),
            "high_bias_fraction": _fraction(high_bias),
            "low_bias_fraction": _fraction(low_bias),
            "fault_active_fraction": _fraction(fault),
            "depth_safe_fraction": _fraction(depth_safe),
            "sat_safe_fraction": _fraction(sat_safe),
            "sswp_delta_norm_mean": _finite_mean(sswp),
        },
    }


def build_phase56_split(
    frame: pd.DataFrame,
    features: np.ndarray,
    *,
    scheme: str,
) -> dict[str, Any]:
    """Build source/target matrices for one offline assembly scheme."""

    if scheme not in PHASE56_SCHEMES:
        raise ValueError(f"Unsupported Phase 5/6 scheme {scheme!r}; choose from {PHASE56_SCHEMES}.")

    depth_safe = _num(frame, "depth_violation", default=0.0).fillna(0.0) < 0.5
    sat = _num(frame, "runtime_motor_saturation_ratio", default=0.0).fillna(0.0)
    sat_safe = sat <= 0.25
    sswp_gate = build_sswp_context_gate(frame)

    if scheme == "observed_direct":
        source, target, source_rows, target_rows = _fallback_split(features, frame)
        note = "rho split if available, otherwise first-half to second-half."
    elif scheme == "safe_core_direct":
        source_mask = ~(depth_safe & sat_safe)
        target_mask = depth_safe & sat_safe
        source, source_rows = _take_rows(features, frame, source_mask)
        target, target_rows = _take_rows(features, frame, target_mask)
        if len(source) == 0 or len(target) == 0:
            source, target, source_rows, target_rows = _fallback_split(features, frame)
            note = "fallback to observed split because safe/unsafe masks were empty."
        else:
            note = "unsafe or near-saturation rows to safe-core rows."
    else:
        source, source_rows = _take_rows(features, frame, sswp_gate["high_bias_mask"])
        target, target_rows = _take_rows(features, frame, sswp_gate["low_bias_mask"])
        if len(source) == 0 or len(target) == 0:
            source, target, source_rows, target_rows = _fallback_split(features, frame)
            note = "fallback to observed split because SSWP high/low gates were empty."
        else:
            note = "high-SSWP persistent-bias rows to low-bias safe rows."

    return {
        "scheme": scheme,
        "source": source,
        "target": target,
        "source_rows": source_rows,
        "target_rows": target_rows,
        "note": note,
        "sswp_gate_summary": sswp_gate["summary"],
    }


def _as_torch(x: np.ndarray, device: str) -> torch.Tensor:
    return torch.as_tensor(x, dtype=torch.float32, device=torch.device(device))


def _mean_gap(source: torch.Tensor, target: torch.Tensor) -> float:
    d2 = pairwise_sq_dist(source, target)
    return float(torch.sqrt(d2.min(dim=1).values.clamp_min(0.0)).mean().item())


def _mean_cost(source: torch.Tensor, target: torch.Tensor) -> float:
    d2 = pairwise_sq_dist(source, target)
    return float(d2.min(dim=1).values.mean().item())


def evaluate_transport(
    source: np.ndarray | torch.Tensor,
    target: np.ndarray | torch.Tensor,
    moved: np.ndarray | torch.Tensor,
    *,
    device: str = "cpu",
) -> dict[str, float]:
    source_t = _as_torch(np.asarray(source, dtype=np.float32), device) if not isinstance(source, torch.Tensor) else source
    target_t = _as_torch(np.asarray(target, dtype=np.float32), device) if not isinstance(target, torch.Tensor) else target
    moved_t = _as_torch(np.asarray(moved, dtype=np.float32), device) if not isinstance(moved, torch.Tensor) else moved
    before_cost = _mean_cost(source_t, target_t)
    after_cost = _mean_cost(moved_t, target_t)
    before_gap = _mean_gap(source_t, target_t)
    after_gap = _mean_gap(moved_t, target_t)
    transport = torch.norm(moved_t - source_t, dim=1)
    return {
        "cost_before": before_cost,
        "cost_after": after_cost,
        "cost_reduction": before_cost - after_cost,
        "mean_gap_before": before_gap,
        "mean_gap_after": after_gap,
        "mean_gap_reduction": before_gap - after_gap,
        "transport_norm_mean": float(transport.mean().item()),
        "transport_norm_p95": float(torch.quantile(transport, 0.95).item()),
    }


def prepare_phase56_runtime_bundle(
    reference_csv: str | Path,
    *,
    feature_columns: Iterable[str],
    context_gate: str,
    fm_cfg: FlowMatchingConfig,
    max_samples: int,
    target_alpha: float,
    light_cfg: LightOTConfig | None = None,
) -> dict[str, Any]:
    """Build an alpha-aware Phase 5/6 runtime bundle from one reference CSV.

    The returned bundle is runtime-ready and can also be serialized via
    :func:`save_phase56_runtime_bundle`.
    """

    features, used_columns, csv_df = extract_phase56_features_from_csv(reference_csv, feature_columns=feature_columns)
    split = build_phase56_split(csv_df, features, scheme=context_gate)
    source = _subsample(split["source"], max(int(max_samples), 1), int(fm_cfg.seed or 0))
    target = _subsample(split["target"], max(int(max_samples), 1), int((fm_cfg.seed or 0)) + 17)
    if len(source) == 0 or len(target) == 0:
        raise ValueError("Phase 5/6 runtime bundle split produced an empty source or target set.")

    source_z, target_z, norm = _standardize(source, target)
    fm_result = train_conditional_flow_matching(source_z, target_z, cfg=fm_cfg)
    fm_model = fm_result["model"]
    fm_model.eval()
    trajectory = np.asarray(fm_result["trajectory"], dtype=np.float32)
    target_alpha_f = float(np.clip(target_alpha, 0.0, 1.0))
    fm_target, target_index = select_phase56_fm_target(trajectory, alpha=target_alpha_f)

    light_cfg = light_cfg or LightOTConfig(eps=0.1, num_iters=120, device=fm_cfg.device)
    source_t = _as_torch(source_z, light_cfg.device)
    target_t = _as_torch(fm_target, light_cfg.device)
    transport = LightOTTransport(light_cfg).fit(source_t, target_t)
    moved_t = transport.transport(source_t).detach().cpu()

    return {
        "reference_csv": str(reference_csv),
        "feature_columns": list(used_columns),
        "context_gate": str(context_gate),
        "max_samples": int(max_samples),
        "target_alpha": target_alpha_f,
        "target_index": int(target_index),
        "norm": {
            "mean": np.asarray(norm["mean"], dtype=np.float32),
            "std": np.asarray(norm["std"], dtype=np.float32),
        },
        "fm_cfg": fm_cfg,
        "fm_model": fm_model,
        "transport": transport,
        "target_t": target_t,
        "transport_source_t": source_t.detach().cpu(),
        "transport_moved_t": moved_t,
        "fm_summary": dict(fm_result["summary"]),
        "split_note": str(split["note"]),
        "sswp_gate_summary": dict(split["sswp_gate_summary"]),
    }


def prepare_phase56_runtime_bundle_from_features(
    source: np.ndarray,
    target: np.ndarray,
    *,
    fm_cfg: FlowMatchingConfig,
    max_samples: int,
    target_alpha: float,
    light_cfg: LightOTConfig | None = None,
    feature_columns: Iterable[str] | None = None,
    context_gate: str = "obs12_domain_tag",
    split_note: str = "",
    reference_tag: str = "",
) -> dict[str, Any]:
    """Build a runtime bundle directly from pre-split source/target arrays.

    D-3 (12-dim native obs FM): this is the CSV-free twin of
    :func:`prepare_phase56_runtime_bundle`. The caller supplies already-split
    ``source`` / ``target`` matrices (e.g. domain_tag=0 source vs domain_tag=2
    target rows of the native 12-dim policy observation), so the FM is trained
    in the *same* space the STDW replay buffer stores. Everything after the
    split is identical to the CSV path, so the returned dict is byte-compatible
    with :func:`save_phase56_runtime_bundle` / :func:`load_phase56_runtime_bundle`.

    Offline-only. Does not touch control and does not relax online_allowed.
    """

    source = np.asarray(source, dtype=np.float32)
    target = np.asarray(target, dtype=np.float32)
    if source.ndim != 2 or target.ndim != 2:
        raise ValueError("source/target must be 2-D (N, D) feature matrices.")
    if source.shape[1] != target.shape[1]:
        raise ValueError(
            f"source dim {source.shape[1]} != target dim {target.shape[1]}."
        )
    source = _subsample(source, max(int(max_samples), 1), int(fm_cfg.seed or 0))
    target = _subsample(target, max(int(max_samples), 1), int((fm_cfg.seed or 0)) + 17)
    if len(source) == 0 or len(target) == 0:
        raise ValueError("Empty source or target set for the 12-dim FM bundle.")

    source_z, target_z, norm = _standardize(source, target)
    fm_result = train_conditional_flow_matching(source_z, target_z, cfg=fm_cfg)
    fm_model = fm_result["model"]
    fm_model.eval()
    trajectory = np.asarray(fm_result["trajectory"], dtype=np.float32)
    target_alpha_f = float(np.clip(target_alpha, 0.0, 1.0))
    fm_target, target_index = select_phase56_fm_target(trajectory, alpha=target_alpha_f)

    light_cfg = light_cfg or LightOTConfig(eps=0.1, num_iters=120, device=fm_cfg.device)
    source_t = _as_torch(source_z, light_cfg.device)
    target_t = _as_torch(fm_target, light_cfg.device)
    transport = LightOTTransport(light_cfg).fit(source_t, target_t)
    moved_t = transport.transport(source_t).detach().cpu()

    dim = int(source.shape[1])
    columns = list(feature_columns) if feature_columns is not None else [f"obs{i}" for i in range(dim)]
    return {
        "reference_csv": str(reference_tag),
        "feature_columns": columns,
        "context_gate": str(context_gate),
        "max_samples": int(max_samples),
        "target_alpha": target_alpha_f,
        "target_index": int(target_index),
        "norm": {
            "mean": np.asarray(norm["mean"], dtype=np.float32),
            "std": np.asarray(norm["std"], dtype=np.float32),
        },
        "fm_cfg": fm_cfg,
        "fm_model": fm_model,
        "transport": transport,
        "target_t": target_t,
        "transport_source_t": source_t.detach().cpu(),
        "transport_moved_t": moved_t,
        "fm_summary": dict(fm_result["summary"]),
        "split_note": str(split_note or "obs12 domain_tag source(0)->target(2) split."),
        "sswp_gate_summary": {},
    }


def save_phase56_runtime_bundle(
    bundle: dict[str, Any],
    out_dir: str | Path,
) -> dict[str, str]:
    """Persist a runtime bundle so live runs can load it without rebuilding."""

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    fm_cfg = bundle.get("fm_cfg")
    fm_model = bundle.get("fm_model")
    if not isinstance(fm_cfg, FlowMatchingConfig):
        raise ValueError("bundle['fm_cfg'] must be a FlowMatchingConfig.")
    if not isinstance(fm_model, torch.nn.Module):
        raise ValueError("bundle['fm_model'] must be a torch.nn.Module.")

    target_t = bundle.get("target_t")
    transport_source_t = bundle.get("transport_source_t")
    transport_moved_t = bundle.get("transport_moved_t")
    if not isinstance(target_t, torch.Tensor):
        raise ValueError("bundle['target_t'] must be a torch.Tensor.")
    if not isinstance(transport_source_t, torch.Tensor):
        raise ValueError("bundle['transport_source_t'] must be a torch.Tensor.")
    if not isinstance(transport_moved_t, torch.Tensor):
        raise ValueError("bundle['transport_moved_t'] must be a torch.Tensor.")

    norm = bundle.get("norm")
    if not isinstance(norm, dict) or "mean" not in norm or "std" not in norm:
        raise ValueError("bundle['norm'] must contain mean/std arrays.")

    metadata = {
        "reference_csv": str(bundle.get("reference_csv", "")),
        "feature_columns": list(bundle.get("feature_columns", [])),
        "context_gate": str(bundle.get("context_gate", "")),
        "max_samples": int(bundle.get("max_samples", 0)),
        "target_alpha": float(bundle.get("target_alpha", 0.0)),
        "target_index": int(bundle.get("target_index", 0)),
        "split_note": str(bundle.get("split_note", "")),
        "sswp_gate_summary": dict(bundle.get("sswp_gate_summary", {})),
        "fm_summary": dict(bundle.get("fm_summary", {})),
        "fm_cfg": asdict(fm_cfg),
        "light_cfg": asdict(bundle["transport"].cfg),
    }

    (out_path / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    torch.save(
        {
            "fm_model_state_dict": fm_model.state_dict(),
            "feature_dim": int(target_t.shape[-1]),
            "norm_mean": torch.as_tensor(norm["mean"], dtype=torch.float32).cpu(),
            "norm_std": torch.as_tensor(norm["std"], dtype=torch.float32).cpu(),
            "target_t": target_t.detach().cpu(),
            "transport_source_t": transport_source_t.detach().cpu(),
            "transport_moved_t": transport_moved_t.detach().cpu(),
        },
        out_path / "bundle.pt",
    )
    return {
        "bundle_dir": str(out_path),
        "metadata_json": str(out_path / "metadata.json"),
        "bundle_pt": str(out_path / "bundle.pt"),
    }


def load_phase56_runtime_bundle(
    bundle_dir: str | Path,
    *,
    device: str = "cpu",
) -> dict[str, Any]:
    """Load a persisted Phase 5/6 runtime bundle."""

    bundle_path = Path(bundle_dir)
    metadata = json.loads((bundle_path / "metadata.json").read_text(encoding="utf-8"))
    payload = torch.load(bundle_path / "bundle.pt", map_location=torch.device(device))

    fm_cfg_payload = dict(metadata["fm_cfg"])
    fm_cfg_payload["device"] = device
    fm_cfg = FlowMatchingConfig(**fm_cfg_payload)
    light_cfg_payload = dict(metadata["light_cfg"])
    light_cfg_payload["device"] = device
    light_cfg = LightOTConfig(**light_cfg_payload)
    feature_dim = int(payload["feature_dim"])
    fm_model = ResidualFlowMLP(dim=feature_dim, hidden_dim=fm_cfg.hidden_dim, depth=fm_cfg.depth).to(torch.device(device))
    fm_model.load_state_dict(payload["fm_model_state_dict"])
    fm_model.eval()

    transport = LightOTTransport(light_cfg)
    transport._source = payload["transport_source_t"].to(torch.device(device)).float()
    transport._moved = payload["transport_moved_t"].to(torch.device(device)).float()
    transport._plan = None

    return {
        "reference_csv": str(metadata.get("reference_csv", "")),
        "feature_columns": list(metadata["feature_columns"]),
        "feature_dim": feature_dim,
        "context_gate": str(metadata["context_gate"]),
        "max_samples": int(metadata.get("max_samples", 0)),
        "target_alpha": float(metadata["target_alpha"]),
        "target_index": int(metadata["target_index"]),
        "norm": {
            "mean": payload["norm_mean"].detach().cpu().numpy().astype(np.float32),
            "std": payload["norm_std"].detach().cpu().numpy().astype(np.float32),
        },
        "fm_cfg": fm_cfg,
        "fm_model": fm_model,
        "transport": transport,
        "target_t": payload["target_t"].to(torch.device(device)).float(),
        "transport_source_t": payload["transport_source_t"].detach().cpu(),
        "transport_moved_t": payload["transport_moved_t"].detach().cpu(),
        "fm_summary": dict(metadata.get("fm_summary", {})),
        "split_note": str(metadata.get("split_note", "")),
        "sswp_gate_summary": dict(metadata.get("sswp_gate_summary", {})),
    }


def run_phase56_scheme(
    csv_path: str | Path,
    *,
    task_name: str,
    scheme: str,
    cfg: Phase56BridgeConfig,
    feature_columns: Iterable[str] | None = None,
) -> dict[str, Any]:
    features, columns, frame = extract_phase56_features_from_csv(csv_path, feature_columns=feature_columns)
    split = build_phase56_split(frame, features, scheme=scheme)
    source = _subsample(split["source"], cfg.max_samples, cfg.random_seed)
    target = _subsample(split["target"], cfg.max_samples, cfg.random_seed + 17)
    if len(source) == 0 or len(target) == 0:
        raise ValueError(f"Empty source/target split for {task_name} scheme={scheme}.")
    source_z, target_z, norm = _standardize(source, target)

    source_t = _as_torch(source_z, cfg.device)
    target_t = _as_torch(target_z, cfg.device)
    light = LightOTTransport(
        LightOTConfig(eps=cfg.ot_eps, num_iters=cfg.ot_iters, device=cfg.device)
    ).fit(source_t, target_t)
    light_moved = light.transport(source_t)
    light_metrics = evaluate_transport(source_t, target_t, light_moved, device=cfg.device)

    fm_result = train_conditional_flow_matching(
        source_z,
        target_z,
        cfg=FlowMatchingConfig(
            hidden_dim=cfg.fm_hidden_dim,
            depth=cfg.fm_depth,
            batch_size=cfg.fm_batch_size,
            num_steps=cfg.fm_steps,
            integration_steps=cfg.fm_integration_steps,
            device=cfg.device,
            seed=cfg.random_seed,
        ),
    )
    fm_moved = np.asarray(fm_result["moved"], dtype=np.float32)
    fm_terminal_metrics = evaluate_transport(source_z, target_z, fm_moved, device=cfg.device)
    linear_mid = linear_geodesic_bridge(source_z, target_z, alpha=0.5)
    linear_terminal = linear_geodesic_bridge(source_z, target_z, alpha=1.0)
    linear_mid_metrics = evaluate_transport(source_z, target_z, linear_mid, device=cfg.device)
    linear_terminal_metrics = evaluate_transport(source_z, target_z, linear_terminal, device=cfg.device)

    trajectory = np.asarray(fm_result["trajectory"], dtype=np.float32)
    mid_idx = max(min(trajectory.shape[0] // 2, trajectory.shape[0] - 1), 0)
    fm_mid = trajectory[mid_idx]
    mid_light = LightOTTransport(
        LightOTConfig(eps=cfg.ot_eps, num_iters=cfg.ot_iters, device=cfg.device)
    ).fit(source_t, _as_torch(fm_mid, cfg.device))
    mid_moved = mid_light.transport(source_t)
    fm_mid_light_metrics = evaluate_transport(source_t, _as_torch(fm_mid, cfg.device), mid_moved, device=cfg.device)
    linear_mid_light = LightOTTransport(
        LightOTConfig(eps=cfg.ot_eps, num_iters=cfg.ot_iters, device=cfg.device)
    ).fit(source_t, _as_torch(linear_mid, cfg.device))
    linear_mid_moved = linear_mid_light.transport(source_t)
    linear_mid_light_metrics = evaluate_transport(source_t, _as_torch(linear_mid, cfg.device), linear_mid_moved, device=cfg.device)

    terminal_light = LightOTTransport(
        LightOTConfig(eps=cfg.ot_eps, num_iters=cfg.ot_iters, device=cfg.device)
    ).fit(source_t, _as_torch(fm_moved, cfg.device))
    terminal_moved = terminal_light.transport(source_t)
    fm_terminal_light_metrics = evaluate_transport(source_t, target_t, terminal_moved, device=cfg.device)
    linear_terminal_light = LightOTTransport(
        LightOTConfig(eps=cfg.ot_eps, num_iters=cfg.ot_iters, device=cfg.device)
    ).fit(source_t, _as_torch(linear_terminal, cfg.device))
    linear_terminal_moved = linear_terminal_light.transport(source_t)
    linear_terminal_light_metrics = evaluate_transport(
        source_t, target_t, linear_terminal_moved, device=cfg.device
    )

    full_metrics: dict[str, Any] | None = None
    if cfg.include_full_esuot:
        full = ESUOTTransport(
            dim=source_t.shape[1],
            cfg=ESUOTConfig(
                eps=cfg.ot_eps,
                inner_iters=cfg.full_inner_iters,
                num_steps=cfg.full_num_steps,
                hidden=64,
                depth=2,
                device=cfg.device,
                seed=cfg.random_seed,
            ),
        ).fit(source_t, target_t)
        full_moved = full.transport(source_t)
        full_metrics = evaluate_transport(source_t, target_t, full_moved, device=cfg.device)
        full_metrics["losses"] = full.last_losses

    return {
        "task_name": task_name,
        "csv_path": str(csv_path),
        "scheme": scheme,
        "feature_columns": columns,
        "normalization": norm,
        "config": asdict(cfg),
        "split": {
            "source_size_raw": int(len(split["source"])),
            "target_size_raw": int(len(split["target"])),
            "source_size_used": int(len(source_z)),
            "target_size_used": int(len(target_z)),
            "note": split["note"],
            "sswp_gate_summary": split["sswp_gate_summary"],
        },
        "components": {
            "sswp_context_gate": {
                "health": (
                    "active" if split["sswp_gate_summary"]["high_bias_fraction"] > 0.0 else "inactive"
                ),
                "summary": split["sswp_gate_summary"],
            },
            "esuot_light_direct": light_metrics,
            "flow_matching_direct": dict(fm_result["summary"], **fm_terminal_metrics),
            "linear_midpoint_direct": linear_mid_metrics,
            "linear_terminal_direct": linear_terminal_metrics,
            "fm_midpoint_then_light_esuot": fm_mid_light_metrics,
            "fm_terminal_then_light_esuot": fm_terminal_light_metrics,
            "linear_midpoint_then_light_esuot": linear_mid_light_metrics,
            "linear_terminal_then_light_esuot": linear_terminal_light_metrics,
            "esuot_full_direct": full_metrics,
        },
        "gate": phase56_scheme_gate(
            light_metrics=light_metrics,
            fm_summary=fm_result["summary"],
            fm_terminal_metrics=fm_terminal_metrics,
            fm_terminal_light_metrics=fm_terminal_light_metrics,
            linear_mid_metrics=linear_mid_metrics,
            linear_terminal_metrics=linear_terminal_metrics,
            linear_mid_light_metrics=linear_mid_light_metrics,
            linear_terminal_light_metrics=linear_terminal_light_metrics,
            full_metrics=full_metrics,
        ),
    }


def phase56_scheme_gate(
    *,
    light_metrics: dict[str, float],
    fm_summary: dict[str, Any],
    fm_terminal_metrics: dict[str, float],
    fm_terminal_light_metrics: dict[str, float],
    linear_mid_metrics: dict[str, float],
    linear_terminal_metrics: dict[str, float],
    linear_mid_light_metrics: dict[str, float],
    linear_terminal_light_metrics: dict[str, float],
    full_metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    fm_strict_distribution = bool(float(fm_summary.get("terminal_mmd", np.inf)) < 1.0e-2)
    fm_geodesic_ready = bool(
        float(fm_summary.get("path_curvature", np.inf)) < 5.0e-2
        and fm_terminal_metrics["cost_after"] < fm_terminal_metrics["cost_before"]
        and fm_terminal_metrics["mean_gap_after"] < fm_terminal_metrics["mean_gap_before"]
    )
    fm_healthy = bool(fm_geodesic_ready)
    light_healthy = bool(light_metrics["cost_after"] < light_metrics["cost_before"])
    fm_to_esuot_healthy = bool(
        fm_terminal_light_metrics["cost_after"] < fm_terminal_light_metrics["cost_before"]
    )
    full_healthy = None
    if full_metrics is not None:
        full_healthy = bool(full_metrics["cost_after"] < full_metrics["cost_before"])
    linear_mid_healthy = bool(linear_mid_metrics["cost_after"] < linear_mid_metrics["cost_before"])
    linear_terminal_healthy = bool(linear_terminal_metrics["cost_after"] < linear_terminal_metrics["cost_before"])
    linear_mid_light_healthy = bool(
        linear_mid_light_metrics["cost_after"] < linear_mid_light_metrics["cost_before"]
    )
    linear_terminal_light_healthy = bool(
        linear_terminal_light_metrics["cost_after"] < linear_terminal_light_metrics["cost_before"]
    )
    return {
        "fm_healthy": fm_healthy,
        "fm_strict_distribution": fm_strict_distribution,
        "fm_geodesic_ready": fm_geodesic_ready,
        "light_esuot_healthy": light_healthy,
        "fm_to_light_esuot_healthy": fm_to_esuot_healthy,
        "linear_midpoint_healthy": linear_mid_healthy,
        "linear_terminal_healthy": linear_terminal_healthy,
        "linear_midpoint_to_light_healthy": linear_mid_light_healthy,
        "linear_terminal_to_light_healthy": linear_terminal_light_healthy,
        "full_esuot_healthy": full_healthy,
        "offline_bridge_ready": bool(fm_healthy and light_healthy and fm_to_esuot_healthy),
        "online_allowed": False,
        "reason": (
            "Offline bridge ready for enhanced validation."
            if fm_healthy and light_healthy and fm_to_esuot_healthy
            else "Keep improving offline bridge before enhanced validation."
        ),
    }


def run_phase56_target_sweep(
    csv_path: str | Path,
    *,
    task_name: str,
    scheme: str,
    cfg: Phase56BridgeConfig,
    feature_columns: Iterable[str] | None = None,
    alphas: Iterable[float] = (0.25, 0.5, 0.75),
) -> dict[str, Any]:
    """Run a finer-grained FM target sweep on one offline entry point."""

    features, columns, frame = extract_phase56_features_from_csv(csv_path, feature_columns=feature_columns)
    split = build_phase56_split(frame, features, scheme=scheme)
    source = _subsample(split["source"], cfg.max_samples, cfg.random_seed)
    target = _subsample(split["target"], cfg.max_samples, cfg.random_seed + 17)
    if len(source) == 0 or len(target) == 0:
        raise ValueError(f"Empty source/target split for {task_name} scheme={scheme}.")
    source_z, target_z, norm = _standardize(source, target)

    source_t = _as_torch(source_z, cfg.device)
    target_t = _as_torch(target_z, cfg.device)
    light = LightOTTransport(
        LightOTConfig(eps=cfg.ot_eps, num_iters=cfg.ot_iters, device=cfg.device)
    ).fit(source_t, target_t)
    light_moved = light.transport(source_t)
    light_metrics = evaluate_transport(source_t, target_t, light_moved, device=cfg.device)

    fm_result = train_conditional_flow_matching(
        source_z,
        target_z,
        cfg=FlowMatchingConfig(
            hidden_dim=cfg.fm_hidden_dim,
            depth=cfg.fm_depth,
            batch_size=cfg.fm_batch_size,
            num_steps=cfg.fm_steps,
            integration_steps=cfg.fm_integration_steps,
            device=cfg.device,
            seed=cfg.random_seed,
        ),
    )
    fm_moved = np.asarray(fm_result["moved"], dtype=np.float32)
    fm_terminal_metrics = evaluate_transport(source_z, target_z, fm_moved, device=cfg.device)

    trajectory = np.asarray(fm_result["trajectory"], dtype=np.float32)
    alpha_rows: list[dict[str, Any]] = []
    for alpha in alphas:
        alpha_f = float(np.clip(alpha, 0.0, 1.0))
        fm_target, idx = select_phase56_fm_target(trajectory, alpha=alpha_f)
        fm_target_t = _as_torch(fm_target, cfg.device)
        fm_alpha_light = LightOTTransport(
            LightOTConfig(eps=cfg.ot_eps, num_iters=cfg.ot_iters, device=cfg.device)
        ).fit(source_t, fm_target_t)
        fm_alpha_moved = fm_alpha_light.transport(source_t)
        fm_alpha_metrics = evaluate_transport(source_t, fm_target_t, fm_alpha_moved, device=cfg.device)

        linear_target = linear_geodesic_bridge(source_z, target_z, alpha=alpha_f)
        linear_target_t = _as_torch(linear_target, cfg.device)
        linear_alpha_light = LightOTTransport(
            LightOTConfig(eps=cfg.ot_eps, num_iters=cfg.ot_iters, device=cfg.device)
        ).fit(source_t, linear_target_t)
        linear_alpha_moved = linear_alpha_light.transport(source_t)
        linear_alpha_metrics = evaluate_transport(source_t, linear_target_t, linear_alpha_moved, device=cfg.device)

        alpha_rows.append(
            {
                "alpha": alpha_f,
                "trajectory_index": int(idx),
                "fm_then_light": fm_alpha_metrics,
                "linear_then_light": linear_alpha_metrics,
                "fm_beats_linear": bool(fm_alpha_metrics["cost_after"] < linear_alpha_metrics["cost_after"]),
            }
        )

    return {
        "task_name": task_name,
        "csv_path": str(csv_path),
        "scheme": scheme,
        "feature_columns": columns,
        "normalization": norm,
        "config": asdict(cfg),
        "split": {
            "source_size_raw": int(len(split["source"])),
            "target_size_raw": int(len(split["target"])),
            "source_size_used": int(len(source_z)),
            "target_size_used": int(len(target_z)),
            "note": split["note"],
            "sswp_gate_summary": split["sswp_gate_summary"],
        },
        "base_components": {
            "esuot_light_direct": light_metrics,
            "flow_matching_direct": dict(fm_result["summary"], **fm_terminal_metrics),
        },
        "alpha_rows": alpha_rows,
    }


__all__ = [
    "PHASE56_SCHEMES",
    "PHASE56_STATE_FEATURE_COLUMNS",
    "Phase56BridgeConfig",
    "build_phase56_split",
    "build_sswp_context_gate",
    "evaluate_transport",
    "extract_phase56_features_from_csv",
    "load_phase56_runtime_bundle",
    "phase56_alpha_to_index",
    "phase56_scheme_gate",
    "prepare_phase56_runtime_bundle",
    "run_phase56_scheme",
    "run_phase56_target_sweep",
    "save_phase56_runtime_bundle",
    "select_phase56_fm_target",
]

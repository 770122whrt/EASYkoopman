"""State-only feature extraction helpers for Phase 2b / Phase 3 standalone tools.

The goal is to provide a small, Isaac-independent contract that turns either a
``stdw_output.csv`` table or a persisted ``buffer.pt`` payload into a stable
state-only feature matrix suitable for offline diagnostics such as
Flow Matching or state-only E-SUOT.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import torch


DEFAULT_STATE_FEATURE_COLUMNS = (
    "true_roll",
    "true_pitch",
    "true_yaw",
    "true_depth_v1",
    "runtime_motor_saturation_ratio",
    "runtime_motor_abs_max_raw",
)


def _as_float_series(csv_df: pd.DataFrame, column: str) -> pd.Series | None:
    if column not in csv_df.columns:
        return None
    values = pd.to_numeric(csv_df[column], errors="coerce")
    if values.isna().all():
        return None
    return values


def available_state_feature_columns(
    csv_df: pd.DataFrame,
    preferred_columns: Iterable[str] = DEFAULT_STATE_FEATURE_COLUMNS,
) -> list[str]:
    columns: list[str] = []
    for column in preferred_columns:
        series = _as_float_series(csv_df, column)
        if series is not None:
            columns.append(column)
    return columns


def extract_state_features_from_csv(
    csv_path: str | Path,
    *,
    feature_columns: Iterable[str] | None = None,
    drop_nan: bool = True,
) -> tuple[np.ndarray, list[str], pd.DataFrame]:
    csv_path = Path(csv_path)
    csv_df = pd.read_csv(csv_path)
    selected = list(feature_columns or available_state_feature_columns(csv_df))
    if not selected:
        raise ValueError(f"No usable state feature columns found in {csv_path}.")

    feature_df = pd.DataFrame({column: pd.to_numeric(csv_df[column], errors="coerce") for column in selected})
    if drop_nan:
        mask = np.isfinite(feature_df.to_numpy(dtype=float)).all(axis=1)
        feature_df = feature_df.loc[mask].reset_index(drop=True)
        csv_df = csv_df.loc[mask].reset_index(drop=True)

    features = feature_df.to_numpy(dtype=np.float32)
    if features.ndim != 2 or features.shape[0] == 0:
        raise ValueError(f"Extracted empty features from {csv_path}.")
    return features, selected, csv_df


def load_state_features_from_buffer(
    buffer_path: str | Path,
    *,
    key: str = "states",
) -> torch.Tensor:
    payload = torch.load(Path(buffer_path), map_location="cpu")
    if key not in payload or payload[key] is None:
        raise KeyError(f"{key!r} missing in buffer payload {buffer_path}.")
    tensor = payload[key]
    if not isinstance(tensor, torch.Tensor):
        tensor = torch.as_tensor(tensor)
    if tensor.ndim != 2:
        raise ValueError(f"Expected 2-D tensor for {key!r}, got shape {tuple(tensor.shape)}.")
    return tensor.float()


def split_source_target_from_csv(
    csv_df: pd.DataFrame,
    features: np.ndarray,
    *,
    rho_threshold: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    if "rho" in csv_df.columns:
        rho = pd.to_numeric(csv_df["rho"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        source = features[rho < rho_threshold]
        target = features[rho >= rho_threshold]
        if len(source) > 0 and len(target) > 0:
            return source, target

    midpoint = max(len(features) // 2, 1)
    source = features[:midpoint]
    target = features[midpoint:]
    if len(target) == 0:
        target = features.copy()
    return source, target


def split_source_target_from_buffer(
    buffer_path: str | Path,
    *,
    source_tag: int = 0,
    target_tags: tuple[int, ...] = (2, 1),
) -> dict[str, torch.Tensor]:
    payload: dict[str, Any] = torch.load(Path(buffer_path), map_location="cpu")
    states = torch.as_tensor(payload["states"]).float()
    domain_tags = torch.as_tensor(payload["domain_tags"]).long()
    size = int(payload.get("size", states.shape[0]))
    states = states[:size]
    domain_tags = domain_tags[:size]

    src_mask = domain_tags == int(source_tag)
    tgt_mask = torch.zeros_like(src_mask, dtype=torch.bool)
    for tag in target_tags:
        tgt_mask |= domain_tags == int(tag)
    if not torch.any(tgt_mask):
        tgt_mask = ~src_mask

    source = states[src_mask]
    target = states[tgt_mask]
    if source.numel() == 0 or target.numel() == 0:
        midpoint = max(states.shape[0] // 2, 1)
        source = states[:midpoint]
        target = states[midpoint:]
        if target.numel() == 0:
            target = states.clone()
    return {"source": source, "target": target, "domain_tags": domain_tags}


__all__ = [
    "DEFAULT_STATE_FEATURE_COLUMNS",
    "available_state_feature_columns",
    "extract_state_features_from_csv",
    "load_state_features_from_buffer",
    "split_source_target_from_csv",
    "split_source_target_from_buffer",
]

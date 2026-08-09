# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""CLI 参数解析小工具（bool/axes/p_diag/grad_mask/channel_indices/axes 格式化）。

（由 adapt.py 拆分而来，函数体逐字节保真。）
"""

from __future__ import annotations

import argparse
from typing import Optional, Tuple

import torch


def _bool_arg(value: str) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y", "t"}


def _parse_axes(spec: str) -> Tuple[int, ...]:
    spec = (spec or "").strip()
    if not spec:
        return (0,)
    return tuple(int(x.strip()) for x in spec.split(",") if x.strip())


def _parse_p_diag(spec: str) -> Tuple[float, float, float, float]:
    parts = [float(x.strip()) for x in (spec or "1,1,1,1").split(",") if x.strip()]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--lyapunov_p_diag must have 4 comma-separated floats")
    return tuple(parts)  # type: ignore[return-value]


def _parse_zeta_grad_mask(mask_text: str | None) -> Optional[torch.Tensor]:
    """Parse an optional 4-D zeta gradient mask from CLI text."""

    if mask_text is None:
        return None
    parts = [item.strip() for item in str(mask_text).split(",") if item.strip()]
    if len(parts) != 4:
        raise SystemExit("--stdw_zeta_grad_mask expects exactly 4 comma-separated values.")
    try:
        values = [float(item) for item in parts]
    except ValueError as exc:
        raise SystemExit("--stdw_zeta_grad_mask must contain numeric values.") from exc
    return torch.as_tensor(values, dtype=torch.float32)


def _parse_channel_indices(spec: str, limit: int) -> list[int]:
    channels: list[int] = []
    for part in str(spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            idx = int(part)
        except ValueError:
            continue
        if 0 <= idx < limit and idx not in channels:
            channels.append(idx)
    return channels


def _format_axes(axes: Tuple[int, ...]) -> str:
    if not axes:
        return "none"
    return ",".join(str(int(a)) for a in axes)


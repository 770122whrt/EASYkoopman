# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""环境 I/O：drift router / 初始扰动 / reset / runtime 快照 / checkpoint 保存 / phase4a 锚点契约。

（由 adapt.py 拆分而来，函数体逐字节保真。）
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import torch

from .cli_parsers import _parse_axes
from .policy import _safe_vector_corr


def _read_initial_cob_xy(raw_env) -> Tuple[float, float]:
    """Read the current base COM->COB xy offset for optional drift routing."""
    env = raw_env.unwrapped
    base = getattr(env, "_base_com_to_cob_offsets", None)
    if base is None:
        base = getattr(env, "com_to_cob_offsets", None)
    if base is None:
        return (0.0, 0.0)
    try:
        row = base[0].detach().cpu().tolist()
        return (float(row[0]), float(row[1]))
    except Exception:
        return (0.0, 0.0)


def _resolve_drift_router(raw_env, args: argparse.Namespace) -> Tuple[float, Tuple[int, ...], Tuple[float, float]]:
    """Resolve the effective drift target/axes without changing defaults.

    The current wrapper applies ``base_offset + frac * target_drift``.  For an
    already asymmetric body (e.g. x=y=0.05), adding another +0.05 on x is a
    perturbation rather than a correction.  This optional router maps such cases
    to a corrective drift while keeping the legacy path unchanged by default.
    """
    target = float(args.target_drift)
    axes = _parse_axes(args.drift_axes)
    xy = _read_initial_cob_xy(raw_env)
    if not bool(args.auto_drift_router) or str(args.drift_router_mode) == "off":
        return target, axes, xy

    if str(args.drift_router_mode) != "offset_correct":
        raise ValueError(f"Unsupported drift_router_mode: {args.drift_router_mode!r}")

    threshold = float(args.drift_router_xy_threshold)
    candidates = [(0, xy[0]), (1, xy[1])]
    selected = [(axis, value) for axis, value in candidates if abs(value) >= threshold]
    if not selected:
        print(
            f"[DRIFT-ROUTER] no xy offset above threshold={threshold:.4f}; "
            f"keeping target={target:.4f}, axes={axes}",
            flush=True,
        )
        return target, axes, xy

    signs = {1 if value > 0.0 else -1 for _, value in selected}
    if len(signs) > 1:
        # The wrapper currently supports one scalar target for all selected axes.
        # Use only the dominant axis to avoid correcting one axis while worsening another.
        axis, value = max(selected, key=lambda item: abs(item[1]))
        selected = [(axis, value)]

    axes = tuple(axis for axis, _ in selected)
    target = -sum(value for _, value in selected) / float(len(selected))
    print(
        f"[DRIFT-ROUTER] mode=offset_correct xy=({xy[0]:.4f},{xy[1]:.4f}) "
        f"threshold={threshold:.4f} -> target={target:.4f}, axes={axes}",
        flush=True,
    )
    return target, axes, xy


def _set_initial_disturbance(env, args, yaml_disturbance: dict | None = None) -> None:
    yaml_disturbance = yaml_disturbance or {}
    kwargs = dict(noise_std=args.noise_std, noise_corr=args.noise_corr)
    if "mode" not in yaml_disturbance:
        kwargs["mode"] = args.wave_mode
    if "base_vel" not in yaml_disturbance:
        kwargs["base_vel"] = list(args.wave_base_vel)
    if "amplitude" not in yaml_disturbance:
        kwargs["amplitude"] = list(args.wave_amplitude)
    if "frequency" not in yaml_disturbance:
        kwargs["frequency"] = list(args.wave_frequency)
    env.unwrapped.apply_runtime_domain_shift(**kwargs)


def _reset_wrapper_env(env):
    out = env.reset()
    return out[0] if isinstance(out, tuple) else out


def _runtime_control_snapshot(env, enabled: bool) -> dict[str, object]:
    """Read optional low-level control diagnostics from env_id=0."""
    if not enabled:
        return {}
    inner = env.unwrapped

    def _row(name: str) -> list[float]:
        value = getattr(inner, name, None)
        if value is None or not isinstance(value, torch.Tensor) or value.numel() == 0:
            return []
        try:
            row = value[0] if value.ndim > 1 else value
            return [float(x) for x in row.detach().cpu().reshape(-1).tolist()]
        except Exception:
            return []

    pid = _row("_last_pid_value")
    motor_raw = _row("_last_motor_values_raw")
    motor_clip = _row("_last_motor_values_clipped")
    geo_zeta1 = _row("_geo_zeta1_runtime")
    sat = getattr(inner, "_last_motor_saturation_ratio", None)
    try:
        sat_ratio = float(sat[0].detach().cpu().item()) if isinstance(sat, torch.Tensor) else float("nan")
    except Exception:
        sat_ratio = float("nan")
    return {
        "runtime_control_logged": True,
        "runtime_pid_value": pid,
        "runtime_pid_roll": pid[0] if len(pid) > 0 else float("nan"),
        "runtime_pid_pitch": pid[1] if len(pid) > 1 else float("nan"),
        "runtime_pid_yaw": pid[2] if len(pid) > 2 else float("nan"),
        "runtime_pid_depth": pid[3] if len(pid) > 3 else float("nan"),
        "runtime_motor_raw": motor_raw,
        "runtime_motor_clipped": motor_clip,
        "runtime_motor_count": len(motor_clip),
        "runtime_motor_saturation_ratio": sat_ratio,
        "runtime_motor_abs_max_raw": max((abs(x) for x in motor_raw), default=float("nan")),
        "runtime_motor_abs_max_clipped": max((abs(x) for x in motor_clip), default=float("nan")),
        "runtime_geo_zeta1": geo_zeta1,
        "runtime_geo_zeta1_roll": geo_zeta1[0] if len(geo_zeta1) > 0 else float("nan"),
        "runtime_geo_zeta1_pitch": geo_zeta1[1] if len(geo_zeta1) > 1 else float("nan"),
        "runtime_geo_zeta1_yaw": geo_zeta1[2] if len(geo_zeta1) > 2 else float("nan"),
    }


def _runtime_reference_context(raw_env) -> tuple[str, str, str]:
    """Read current reference branch for env_id=0 before any auto-reset side effect is lost."""
    try:
        reference_mode_runtime = str(getattr(raw_env.unwrapped.cfg, "reference_mode", "step"))
    except Exception:
        reference_mode_runtime = "step"
    mixed_reference_branch = ""
    mixed_reference_is_flip = ""
    if reference_mode_runtime == "mixed_sine_flip360":
        try:
            is_flip_runtime = bool(raw_env.unwrapped._ref_is_flip[0].item())
            mixed_reference_is_flip = str(int(is_flip_runtime))
            mixed_reference_branch = "flip360" if is_flip_runtime else "sine"
        except Exception:
            mixed_reference_is_flip = ""
            mixed_reference_branch = ""
    return reference_mode_runtime, mixed_reference_branch, mixed_reference_is_flip


def _save_stdw_checkpoint(
    *,
    ckpt_dir: Path,
    step: int,
    policy,
    obs_normalizer,
    optimizer,
    metadata: Dict[str, object],
    export_deploy_jit: bool,
    dummy_obs_dim: int,
    device: torch.device | str,
) -> Dict[str, Optional[str]]:
    """Save an RSL-RL-compatible adapted checkpoint plus optional deploy JIT."""
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    stem = f"stdw_step_{int(step):06d}"
    ckpt_path = ckpt_dir / f"{stem}.pt"
    payload = {
        "model_state_dict": {k: v.detach().cpu() for k, v in policy.state_dict().items()},
        "optimizer_state_dict": optimizer.state_dict() if optimizer is not None else None,
        "iter": int(step),
        "infos": dict(metadata),
    }
    torch.save(payload, ckpt_path)
    meta_path = ckpt_dir / f"{stem}.json"

    deploy_path: Optional[Path] = None
    if export_deploy_jit:
        try:
            deploy_model = torch.nn.Sequential(copy.deepcopy(obs_normalizer).cpu(), copy.deepcopy(policy.actor).cpu())
            deploy_model.eval()
            dummy = torch.zeros(1, int(dummy_obs_dim), dtype=torch.float32)
            traced = torch.jit.trace(deploy_model, dummy, strict=False)
            deploy_path = ckpt_dir / f"{stem}_deploy.jit"
            traced.save(str(deploy_path))
        except Exception as exc:
            print(f"[WARN] deploy JIT export failed at step {step}: {exc}")
    # Restore caller device/training mode after deepcopy-only export.
    policy.to(device)
    if obs_normalizer is not None:
        obs_normalizer.to(device)
    meta_payload = {
        **metadata,
        "checkpoint_path": str(ckpt_path),
        "deploy_jit_path": str(deploy_path) if deploy_path is not None else None,
    }
    meta_path.write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")
    return {
        "checkpoint_path": str(ckpt_path),
        "metadata_path": str(meta_path),
        "deploy_jit_path": str(deploy_path) if deploy_path is not None else None,
    }


def _phase4a_empty_anchor_contract(prefix: str) -> Dict[str, object]:
    return {
        f"{prefix}_anchor": [],
        f"{prefix}_valid": 0,
        f"{prefix}_delta_norm": float("nan"),
        f"{prefix}_delta_abs_mean": float("nan"),
        f"{prefix}_action_corr": float("nan"),
        f"{prefix}_equals_clipped_action": float("nan"),
        f"{prefix}_to_clipped_action_max_abs": float("nan"),
        f"{prefix}_target_clip_channel_fraction": float("nan"),
        f"{prefix}_action_out_of_unit_channel_fraction": float("nan"),
    }


def _phase4a_anchor_contract(prefix: str, action: np.ndarray, anchor: np.ndarray) -> Dict[str, object]:
    if action.shape != anchor.shape or action.size == 0:
        return _phase4a_empty_anchor_contract(prefix)
    if not np.all(np.isfinite(action)) or not np.all(np.isfinite(anchor)):
        return _phase4a_empty_anchor_contract(prefix)
    clipped_action = np.clip(action, -1.0, 1.0)
    delta = anchor - action
    anchor_to_clip_abs = np.abs(anchor - clipped_action)
    return {
        f"{prefix}_anchor": [float(x) for x in anchor.reshape(-1).tolist()],
        f"{prefix}_valid": 1,
        f"{prefix}_delta_norm": float(np.linalg.norm(delta)),
        f"{prefix}_delta_abs_mean": float(np.mean(np.abs(delta))),
        f"{prefix}_action_corr": _safe_vector_corr(action.reshape(-1).tolist(), anchor.reshape(-1).tolist()),
        f"{prefix}_equals_clipped_action": float(float(np.max(anchor_to_clip_abs)) <= 1.0e-6),
        f"{prefix}_to_clipped_action_max_abs": float(np.max(anchor_to_clip_abs)),
        f"{prefix}_target_clip_channel_fraction": float(np.mean(np.abs(anchor) >= 0.999)),
        f"{prefix}_action_out_of_unit_channel_fraction": float(np.mean(np.abs(action) > 1.0)),
    }


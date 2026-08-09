"""Minimal standalone Flow Matching utilities for Phase 2b / Phase 3.

This module intentionally stays Isaac-independent and pure torch so it can be
used for standalone diagnostics before any online integration is attempted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import torch
import torch.nn as nn


@dataclass
class FlowMatchingConfig:
    hidden_dim: int = 64
    depth: int = 2
    learning_rate: float = 1.0e-3
    weight_decay: float = 1.0e-5
    batch_size: int = 256
    num_steps: int = 300
    integration_steps: int = 16
    device: str = "cpu"
    seed: int | None = 0


class ResidualFlowMLP(nn.Module):
    """Predict velocity field v(x_t, t) for conditional flow matching."""

    def __init__(self, dim: int, hidden_dim: int = 64, depth: int = 2) -> None:
        super().__init__()
        in_dim = dim + 1
        layers: list[nn.Module] = []
        for _ in range(max(depth, 1)):
            layers.append(nn.Linear(in_dim, hidden_dim))
            layers.append(nn.GELU())
            in_dim = hidden_dim
        layers.append(nn.Linear(in_dim, dim))
        self.net = nn.Sequential(*layers)

    def forward(self, xt: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
        if t.ndim == 1:
            t = t.unsqueeze(1)
        return self.net(torch.cat([xt, t], dim=1))


def _to_device_float(x: np.ndarray | torch.Tensor, device: torch.device) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        return x.to(device).float()
    return torch.as_tensor(x, device=device, dtype=torch.float32)


def _sample_aligned_pairs(
    source: torch.Tensor,
    target: torch.Tensor,
    batch_size: int,
) -> tuple[torch.Tensor, torch.Tensor]:
    src_idx = torch.randint(0, source.shape[0], (batch_size,), device=source.device)
    tgt_idx = torch.randint(0, target.shape[0], (batch_size,), device=target.device)
    return source[src_idx], target[tgt_idx]


def integrate_flow_euler(
    model: nn.Module,
    source: torch.Tensor,
    *,
    integration_steps: int = 16,
) -> tuple[torch.Tensor, torch.Tensor]:
    x = source.clone()
    traj = [x.detach().cpu()]
    dt = 1.0 / max(int(integration_steps), 1)
    for step in range(max(int(integration_steps), 1)):
        t = torch.full((x.shape[0], 1), step * dt, device=x.device, dtype=x.dtype)
        v = model(x, t)
        x = x + dt * v
        traj.append(x.detach().cpu())
    return x, torch.stack(traj, dim=0)


def compute_terminal_mmd(
    moved: torch.Tensor,
    target: torch.Tensor,
    *,
    sigma: float = 1.0,
) -> float:
    def _rbf(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        d2 = torch.cdist(a, b, p=2.0).pow(2)
        return torch.exp(-d2 / max(2.0 * sigma * sigma, 1.0e-6))

    k_xx = _rbf(moved, moved).mean()
    k_yy = _rbf(target, target).mean()
    k_xy = _rbf(moved, target).mean()
    return float((k_xx + k_yy - 2.0 * k_xy).detach().cpu().item())


def compute_path_curvature(trajectory: torch.Tensor) -> float:
    if trajectory.ndim != 3 or trajectory.shape[0] < 3:
        return 0.0
    first = trajectory[1:] - trajectory[:-1]
    second = first[1:] - first[:-1]
    return float(second.norm(dim=-1).mean().item())


def train_conditional_flow_matching(
    source: np.ndarray | torch.Tensor,
    target: np.ndarray | torch.Tensor,
    *,
    cfg: FlowMatchingConfig | None = None,
) -> dict[str, Any]:
    cfg = cfg or FlowMatchingConfig()
    device = torch.device(cfg.device)
    if cfg.seed is not None:
        torch.manual_seed(int(cfg.seed))
        np.random.seed(int(cfg.seed))

    source_t = _to_device_float(source, device)
    target_t = _to_device_float(target, device)
    if source_t.ndim != 2 or target_t.ndim != 2:
        raise ValueError("source and target must be 2-D feature matrices.")
    if source_t.shape[1] != target_t.shape[1]:
        raise ValueError("source and target feature dims must match.")

    model = ResidualFlowMLP(
        dim=source_t.shape[1],
        hidden_dim=cfg.hidden_dim,
        depth=cfg.depth,
    ).to(device)
    opt = torch.optim.AdamW(
        model.parameters(),
        lr=cfg.learning_rate,
        weight_decay=cfg.weight_decay,
    )

    loss_trace: list[float] = []
    for _ in range(max(int(cfg.num_steps), 1)):
        x0, x1 = _sample_aligned_pairs(source_t, target_t, max(int(cfg.batch_size), 1))
        t = torch.rand((x0.shape[0], 1), device=device, dtype=x0.dtype)
        xt = (1.0 - t) * x0 + t * x1
        target_v = x1 - x0
        pred_v = model(xt, t)
        loss = torch.mean((pred_v - target_v) ** 2)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        loss_trace.append(float(loss.detach().cpu().item()))

    moved, trajectory = integrate_flow_euler(
        model,
        source_t,
        integration_steps=cfg.integration_steps,
    )
    summary = {
        "config": asdict(cfg),
        "feature_dim": int(source_t.shape[1]),
        "source_size": int(source_t.shape[0]),
        "target_size": int(target_t.shape[0]),
        "loss_initial": float(loss_trace[0]),
        "loss_final": float(loss_trace[-1]),
        "loss_min": float(min(loss_trace)),
        "terminal_mmd": compute_terminal_mmd(moved, target_t),
        "terminal_mean_gap_l2": float(torch.norm(moved.mean(dim=0) - target_t.mean(dim=0)).item()),
        "path_curvature": compute_path_curvature(trajectory),
    }
    return {
        "model": model,
        "summary": summary,
        "trajectory": trajectory.numpy(),
        "moved": moved.detach().cpu().numpy(),
        "loss_trace": np.asarray(loss_trace, dtype=np.float32),
    }


__all__ = [
    "FlowMatchingConfig",
    "ResidualFlowMLP",
    "compute_path_curvature",
    "compute_terminal_mmd",
    "integrate_flow_euler",
    "train_conditional_flow_matching",
]

#!/usr/bin/env python3
"""B5-a: offline forward-dynamics proxy f(s, a) -> s' on obs12 transitions.

B5 migrates the slow-loop ``L_tgt`` semantics from an action-space pseudo-label
anchor to a target-domain STATE-manifold match. The state match
``L_tgt_state = || f(s_tgt, policy(s_tgt)) - z_bridge ||^2`` needs a differentiable
action->next-state channel ``f(s, a) -> s'`` that does NOT exist yet (the Flow
Matching model is a state->state distribution bridge, not forward dynamics).

This tool trains that proxy purely offline from the STDW replay buffer's real
``(states, actions, next_states)`` transitions:

  - predict the residual ``delta = s' - s`` (standardized) with a small MLP, so
    the identity/near-static transition is easy and the net models the dynamics
    correction;
  - hold out a random fraction of rows for evaluation and report one-step MSE /
    R^2 both globally and per domain bucket (tag0 source / tag1 intermediate /
    tag2 target), since the proxy must not collapse across the domain shift.

Scope guard:
- offline-only supervised regression; does not run Isaac, does not load the RL
  policy, does not touch the fast-loop action path or the live slow-loop loss;
- output is a standalone proxy ``.pt`` + ``summary.json`` for the later B5-b
  diagnostic; it is NOT wired into control;
- ``online_allowed`` stays false.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import torch
import torch.nn as nn


_THIS = Path(__file__).resolve()
_PKG_ROOT = _THIS.parents[2]  # .../easyuuv_stdw
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))


class InverseDynamicsProxy(nn.Module):
    def __init__(self, state_dim=12, action_dim=8, hidden_dim=128, depth=3):
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim
        
        # Input: state_t and state_{t+1}
        in_dim = state_dim * 2
        
        layers = []
        layers.append(nn.Linear(in_dim, hidden_dim))
        layers.append(nn.ELU())
        for _ in range(depth - 1):
            layers.append(nn.Linear(hidden_dim, hidden_dim))
            layers.append(nn.ELU())
        layers.append(nn.Linear(hidden_dim, action_dim))
        self.net = nn.Sequential(*layers)
        
    def forward(self, state, next_state):
        x = torch.cat([state, next_state], dim=-1)
        return self.net(x)


def _load_buffer(path: Path) -> dict[str, Any]:
    d = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(d, dict):
        raise ValueError(f"Unexpected buffer payload type {type(d)} in {path}")
    size = int(d.get("size", 0))
    if size <= 0:
        raise ValueError(f"Buffer {path} has no live rows (size={size}).")
    for key in ("states", "actions", "next_states", "domain_tags"):
        if d.get(key) is None:
            raise ValueError(f"Buffer {path} missing required field {key!r}.")
    return {
        "size": size,
        "states": d["states"][:size].float(),
        "actions": d["actions"][:size].float(),
        "next_states": d["next_states"][:size].float(),
        "domain_tags": d["domain_tags"][:size].long(),
    }


def _load_buffers(paths: list[Path]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load and concatenate one or more obs12 buffers (same embodiment/schema).

    Single-path input reproduces :func:`_load_buffer` byte-for-byte. Multi-path
    input concatenates rows after validating that state/action dims match, so a
    proxy can be trained on a larger pooled transition set.
    """

    if not paths:
        raise ValueError("No buffer paths provided.")
    parts = [_load_buffer(p) for p in paths]
    state_dim = int(parts[0]["states"].shape[-1])
    action_dim = int(parts[0]["actions"].shape[-1])
    for p, part in zip(paths, parts):
        if int(part["states"].shape[-1]) != state_dim or int(part["actions"].shape[-1]) != action_dim:
            raise ValueError(
                f"Buffer {p} dim mismatch (state {part['states'].shape[-1]}/{state_dim}, "
                f"action {part['actions'].shape[-1]}/{action_dim}); pool only same-schema buffers."
            )
    pooled = {
        "size": int(sum(part["size"] for part in parts)),
        "states": torch.cat([part["states"] for part in parts], dim=0),
        "actions": torch.cat([part["actions"] for part in parts], dim=0),
        "next_states": torch.cat([part["next_states"] for part in parts], dim=0),
        "domain_tags": torch.cat([part["domain_tags"] for part in parts], dim=0),
    }
    provenance = [{"path": str(p), "rows": int(part["size"])} for p, part in zip(paths, parts)]
    return pooled, provenance


def _standardize_fit(x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    mean = x.mean(dim=0)
    std = x.std(dim=0)
    std = torch.where(std < 1.0e-6, torch.ones_like(std), std)
    return mean, std


def _r2(pred: torch.Tensor, true: torch.Tensor) -> float:
    """Coefficient of determination aggregated over all dims (variance-weighted)."""

    ss_res = ((true - pred) ** 2).sum().item()
    ss_tot = ((true - true.mean(dim=0, keepdim=True)) ** 2).sum().item()
    if ss_tot <= 1.0e-12:
        return float("nan")
    return float(1.0 - ss_res / ss_tot)


def main() -> None:
    ap = argparse.ArgumentParser(description="B5-a offline forward-dynamics proxy trainer.")
    ap.add_argument("--buffer", type=str, default=None, help="single obs12 buffer.pt with (s,a,s') transitions.")
    ap.add_argument(
        "--buffer-glob",
        type=str,
        default=None,
        help="glob for multiple same-schema obs12 buffers to pool (e.g. all uuv6 buffers).",
    )
    ap.add_argument("--out-proxy", type=str, required=True, help="output proxy .pt path.")
    ap.add_argument("--out-json", type=str, required=True, help="output summary json path.")
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=400)
    ap.add_argument("--batch-size", type=int, default=512)
    ap.add_argument("--lr", type=float, default=1.0e-3)
    ap.add_argument("--weight-decay", type=float, default=1.0e-5)
    ap.add_argument("--heldout-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    torch.manual_seed(int(args.seed))
    np.random.seed(int(args.seed))

    if bool(args.buffer) == bool(args.buffer_glob):
        raise SystemExit("Provide exactly one of --buffer or --buffer-glob.")
    if args.buffer:
        buf_paths = [Path(args.buffer)]
    else:
        import glob as _glob

        buf_paths = sorted(Path(p) for p in _glob.glob(str(args.buffer_glob), recursive=True))
        if not buf_paths:
            raise SystemExit(f"--buffer-glob matched no files: {args.buffer_glob!r}")
    data, buf_provenance = _load_buffers(buf_paths)
    buf_path = buf_paths[0] if len(buf_paths) == 1 else Path(str(args.buffer_glob))
    n = data["size"]
    s_all = data["states"]
    a_all = data["actions"]
    sn_all = data["next_states"]
    tags_all = data["domain_tags"]
    state_dim = int(s_all.shape[-1])
    action_dim = int(a_all.shape[-1])

    # Train/held-out split (row-random).
    perm = torch.randperm(n)
    n_eval = max(int(round(n * float(args.heldout_frac))), 1)
    eval_idx = perm[:n_eval]
    train_idx = perm[n_eval:]

    s_tr, a_tr, sn_tr = s_all[train_idx], a_all[train_idx], sn_all[train_idx]
    s_ev, a_ev, sn_ev = s_all[eval_idx], a_all[eval_idx], sn_all[eval_idx]
    tags_ev = tags_all[eval_idx]

    # Standardize INPUTS from train set: state, action. Residual target is
    # standardized by state-residual std so all 12 dims contribute comparably.
    s_mean, s_std = _standardize_fit(s_tr)
    a_mean, a_std = _standardize_fit(a_tr)
    delta_tr = sn_tr - s_tr
    d_mean, d_std = _standardize_fit(delta_tr)
    # residual scale used for de-standardization back to raw next-state:
    # we predict standardized residual, target = (delta - d_mean)/d_std.
    # Then delta_raw_pred = pred*d_std + d_mean; s'_pred = s + delta_raw_pred.

    def _norm_s(x: torch.Tensor) -> torch.Tensor:
        return (x - s_mean) / s_std

    def _norm_a(x: torch.Tensor) -> torch.Tensor:
        return (x - a_mean) / a_std

    def _delta_target(sn: torch.Tensor, s: torch.Tensor) -> torch.Tensor:
        return ((sn - s) - d_mean) / d_std

    model = InverseDynamicsProxy(state_dim, action_dim, hidden_dim=int(args.hidden), depth=int(args.depth))
    opt = torch.optim.AdamW(model.parameters(), lr=float(args.lr), weight_decay=float(args.weight_decay))

    s_tr_n = _norm_s(s_tr)
    sn_tr_n = _norm_s(sn_tr)
    y_tr = _norm_a(a_tr)

    n_train = int(s_tr_n.shape[0])
    bs = min(int(args.batch_size), n_train)
    loss_trace: list[float] = []
    model.train()
    for _ in range(int(args.epochs)):
        b = torch.randint(0, n_train, (bs,))
        pred = model(s_tr_n[b], sn_tr_n[b])
        loss = ((pred - y_tr[b]) ** 2).mean()
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        loss_trace.append(float(loss.detach().item()))

    # ---- Evaluation helper closures (de-standardize action back to raw). ----
    def _eval(s_raw: torch.Tensor, sn_raw: torch.Tensor, a_raw: torch.Tensor) -> dict[str, float]:
        model.eval()
        with torch.no_grad():
            pred_std = model(_norm_s(s_raw), _norm_s(sn_raw))
            y_std = _norm_a(a_raw)
            mse_std = float(((pred_std - y_std) ** 2).mean().item())
            r2_std = _r2(pred_std, y_std)
            a_pred = pred_std * a_std + a_mean
            mse_raw = float(((a_pred - a_raw) ** 2).mean().item())
            r2_raw = _r2(a_pred, a_raw)
        return {
            "n": int(s_raw.shape[0]),
            "mse_action_std": mse_std,
            "r2_action_std": r2_std,
            "mse_action_raw": mse_raw,
            "r2_action_raw": r2_raw,
        }

    eval_global = _eval(s_ev, sn_ev, a_ev)
    train_global = _eval(s_tr, sn_tr, a_tr)

    per_domain: dict[str, Any] = {}
    for tag in (0, 1, 2):
        mask = tags_ev == tag
        cnt = int(mask.sum().item())
        if cnt == 0:
            per_domain[str(tag)] = {"n": 0}
            continue
        per_domain[str(tag)] = _eval(s_ev[mask], sn_ev[mask], a_ev[mask])

    out_proxy = Path(args.out_proxy)
    out_proxy.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "state_dim": state_dim,
            "action_dim": action_dim,
            "hidden": int(args.hidden),
            "depth": int(args.depth),
            "norm": {
                "s_mean": s_mean.tolist(),
                "s_std": s_std.tolist(),
                "a_mean": a_mean.tolist(),
                "a_std": a_std.tolist(),
            },
            "predicts": "standardized_action",
            "reconstruct": "a = pred * a_std + a_mean",
            "online_allowed": False,
        },
        out_proxy,
    )

    summary = {
        "online_allowed": False,
        "boundary_note": (
            "Phase 8 offline inverse-dynamics proxy f(s,s')->a trained on real obs12 "
            "buffer transitions. Diagnostic infrastructure for the Phase 8 Action Anchor "
            "L_tgt; NOT wired into control or the live slow-loop loss."
        ),
        "buffer": str(buf_path),
        "n_buffers": len(buf_paths),
        "buffer_provenance": buf_provenance,
        "n_rows": n,
        "state_dim": state_dim,
        "action_dim": action_dim,
        "split": {"train": int(train_idx.numel()), "heldout": int(eval_idx.numel()), "heldout_frac": float(args.heldout_frac)},
        "train_config": {
            "hidden": int(args.hidden),
            "depth": int(args.depth),
            "epochs": int(args.epochs),
            "batch_size": bs,
            "lr": float(args.lr),
            "weight_decay": float(args.weight_decay),
            "seed": int(args.seed),
        },
        "loss_initial": float(loss_trace[0]),
        "loss_final": float(loss_trace[-1]),
        "loss_min": float(min(loss_trace)),
        "train_global": train_global,
        "heldout_global": eval_global,
        "heldout_per_domain": per_domain,
        "proxy_path": str(out_proxy),
    }
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2))
    print(f"[written] {out_proxy}")
    print(f"[written] {out_json}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

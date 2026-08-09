"""Thin adapter bridging the E-SUOT backends to the STDW slow loop.

In the OPR path the slow loop compares the fine-tuned policy on target-domain
states against a physics-derived anchor::

    mse_tgt = (( policy(B_tgt["states"]) - B_tgt["pseudo_actions"] )**2)

OPR builds ``pseudo_actions`` from the low-level PID correction scaled by the
Jacobian inverse ``J_inv`` -- i.e. an explicit physical prior.  This adapter
produces the *same shaped* anchor purely by optimal-transport of the
state-action distribution, with **no physical prior**:

  1. Form joint vectors ``x = [state, action]`` for the source and target
     batches drawn from the replay buffer.
  2. Transport the *source* joint distribution toward the *target* support
     (``esuot_full`` -> neural T_θ / Algorithm 1; ``esuot_light`` -> Sinkhorn
     barycentric).  The transport cost ``1/(2η)||x-T(x)||²`` keeps the moved
     points close to the good source behaviour while pulling them to the target
     support -- exactly the "intermediate domain" anchor.
  3. Read out an action for each target state by nearest-neighbour on the moved
     *state* part, returning ``(N_tgt, action_dim)`` aligned to ``B_tgt["states"]``.

The adapter never touches ``_base_com_to_cob_offsets``, ``_read_jacobian_inv_diag``
or the micro-probe, satisfying the no-prior requirement (PLAN §6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import torch

from .light import LightOTConfig, LightOTTransport
from .semidual import pairwise_sq_dist
from .transport import ESUOTConfig, ESUOTTransport


@dataclass
class AdapterConfig:
    """Backend selection + shared E-SUOT hyper-parameters."""

    backend: str = "esuot_light"        # esuot_full | esuot_light
    eps: float = 0.1
    eta: float = 1.0
    lambda1: float = 1.0
    lambda2: float = 1.0
    divergence: str = "kl"
    inner_iters: int = 50               # ES-A: epochs per w/T step
    num_steps: int = 1                  # ES-A: number of intermediate domains
    sinkhorn_iters: int = 200           # ES-B: Sinkhorn iterations
    hidden: int = 64
    depth: int = 2
    device: str = "cpu"
    seed: Optional[int] = None


class DomainAdaptAdapter:
    """Produce a target anchor for the STDW slow loop via E-SUOT transport."""

    def __init__(self, cfg: AdapterConfig) -> None:
        if cfg.backend not in {"esuot_full", "esuot_light"}:
            raise ValueError(
                f"DomainAdaptAdapter backend must be esuot_full|esuot_light, got {cfg.backend!r}"
            )
        self.cfg = cfg
        self.device = torch.device(cfg.device)
        self._last_info: Dict[str, float] = {}

    # ------------------------------------------------------------------
    @staticmethod
    def _joint(states: torch.Tensor, actions: torch.Tensor) -> torch.Tensor:
        return torch.cat([states.float(), actions.float()], dim=-1)

    def compute_target_anchor(
        self, B_src: Dict[str, torch.Tensor], B_tgt: Dict[str, torch.Tensor]
    ) -> torch.Tensor:
        """Return an ``(N_tgt, action_dim)`` anchor replacing ``pseudo_actions``.

        Args:
            B_src: source batch with keys ``states`` (M, S), ``actions`` (M, A).
            B_tgt: target batch with keys ``states`` (N, S), ``actions`` (N, A).
        """
        src_states = B_src["states"].to(self.device).float()
        src_actions = B_src["actions"].to(self.device).float()
        tgt_states = B_tgt["states"].to(self.device).float()
        tgt_actions = B_tgt["actions"].to(self.device).float()

        action_dim = src_actions.shape[-1]
        x_src = self._joint(src_states, src_actions)        # (M, S+A)
        x_tgt = self._joint(tgt_states, tgt_actions)        # (N, S+A)
        dim = x_src.shape[-1]

        if self.cfg.backend == "esuot_full":
            esuot_cfg = ESUOTConfig(
                eps=self.cfg.eps,
                eta=self.cfg.eta,
                lambda1=self.cfg.lambda1,
                lambda2=self.cfg.lambda2,
                divergence=self.cfg.divergence,
                num_steps=self.cfg.num_steps,
                inner_iters=self.cfg.inner_iters,
                hidden=self.cfg.hidden,
                depth=self.cfg.depth,
                device=self.cfg.device,
                seed=self.cfg.seed,
            )
            model = ESUOTTransport(dim=dim, cfg=esuot_cfg).fit(x_src, x_tgt)
            moved = model.transport(x_src)                  # (M, S+A)
            self._last_info = dict(model.last_losses)
        else:  # esuot_light
            light_cfg = LightOTConfig(
                eps=self.cfg.eps,
                num_iters=self.cfg.sinkhorn_iters,
                device=self.cfg.device,
            )
            model = LightOTTransport(light_cfg).fit(x_src, x_tgt)
            moved = model.transport(x_src)                  # (M, S+A)
            self._last_info = {}

        moved_states = moved[:, : src_states.shape[-1]]     # (M, S)
        moved_actions = moved[:, src_states.shape[-1]:]     # (M, A)

        # Align to target states: each target state takes the moved action of its
        # nearest moved-source state (conditional action readout, prior-free).
        d2 = pairwise_sq_dist(tgt_states, moved_states)     # (N, M)
        nn_idx = torch.argmin(d2, dim=1)                    # (N,)
        anchor = moved_actions[nn_idx]                      # (N, A)
        anchor = torch.clamp(anchor, -1.0, 1.0)
        if anchor.shape[-1] != action_dim:
            raise RuntimeError(
                f"anchor action_dim {anchor.shape[-1]} != expected {action_dim}"
            )
        return anchor

    @property
    def last_info(self) -> Dict[str, float]:
        return dict(self._last_info)

    def compute_state_anchor(
        self, B_src: Dict[str, torch.Tensor], B_tgt: Dict[str, torch.Tensor]
    ) -> torch.Tensor:
        """Return an ``(N_tgt, state_dim)`` state anchor ``z_bridge`` for B5.

        Shares the exact same joint transport plan as :meth:`compute_target_anchor`,
        but reads out the **state** part of the moved joint vector instead of the
        action part. Used by the slow-loop when ``l_tgt_space`` is state_raw /
        state_latent / state_whitened: the state-match loss compares
        ``phi(f(s_tgt, pi(s_tgt)))`` against ``phi(z_bridge)`` in a proxy-defined
        phi space, so the transport target for the actor gradient is a *state*
        rather than an action anchor.

        This method is a pure read-out of the same OT plan; it does not train a
        new transport and never touches the policy graph. online_allowed stays
        false at the adapter boundary.
        """
        src_states = B_src["states"].to(self.device).float()
        src_actions = B_src["actions"].to(self.device).float()
        tgt_states = B_tgt["states"].to(self.device).float()
        tgt_actions = B_tgt["actions"].to(self.device).float()

        x_src = self._joint(src_states, src_actions)
        x_tgt = self._joint(tgt_states, tgt_actions)
        dim = x_src.shape[-1]

        if self.cfg.backend == "esuot_full":
            esuot_cfg = ESUOTConfig(
                eps=self.cfg.eps,
                eta=self.cfg.eta,
                lambda1=self.cfg.lambda1,
                lambda2=self.cfg.lambda2,
                divergence=self.cfg.divergence,
                num_steps=self.cfg.num_steps,
                inner_iters=self.cfg.inner_iters,
                hidden=self.cfg.hidden,
                depth=self.cfg.depth,
                device=self.cfg.device,
                seed=self.cfg.seed,
            )
            model = ESUOTTransport(dim=dim, cfg=esuot_cfg).fit(x_src, x_tgt)
            moved = model.transport(x_src)
        else:  # esuot_light
            light_cfg = LightOTConfig(
                eps=self.cfg.eps,
                num_iters=self.cfg.sinkhorn_iters,
                device=self.cfg.device,
            )
            model = LightOTTransport(light_cfg).fit(x_src, x_tgt)
            moved = model.transport(x_src)

        moved_states = moved[:, : src_states.shape[-1]]     # (M, S)
        d2 = pairwise_sq_dist(tgt_states, moved_states)     # (N, M)
        nn_idx = torch.argmin(d2, dim=1)                    # (N,)
        z_bridge = moved_states[nn_idx]                     # (N, S)
        return z_bridge


__all__ = ["DomainAdaptAdapter", "AdapterConfig"]

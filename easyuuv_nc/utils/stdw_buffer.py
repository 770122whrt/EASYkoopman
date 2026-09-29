"""STDW replay buffer with quantile-confidence filtering and ``.pt`` persistence.

This is the data backbone of the new STDW online adaptation workflow.  It
implements the (state, action, pseudo_action, reward, next_state, error,
stdw_mask, lyapunov_V, domain_tag, step) tuple required by the v3 plan, along
with a domain-aware ``sample_pair`` that mirrors the STDW paper's "cyclic batch
matching" between source/intermediate/target domains.

domain_tag conventions (see plan v3 §3.3):
- 0  source       : drift_frac <= 0.05
- 1  intermediate : 0.05 < drift_frac < 0.95
- 2  target       : drift_frac >= 0.95

Quantile filter (see plan §3.3 / STDW losses.pseudo_label_loss):
- Take the (1 - discard_ratio) quantile of the candidate `errors`; only keep
  samples with error <= tau.  When candidates < 32 we skip the filter to avoid
  numerical instability of `torch.quantile` on tiny populations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import torch


_DEFAULT_FIELDS = (
    "states",
    "actions",
    "pseudo_actions",
    "rewards",
    "next_states",
    "errors",
    "stdw_masks",
    "lyapunov_V",
    "domain_tags",
    "steps",
)

_TARGET_DOMAIN_MODES = (
    "target_then_intermediate",
    "target_intermediate_mix",
    "intermediate_only",
    "mixed_all",
    "domain_balanced_mix",
)


def _domain_tag_from_frac(frac: float) -> int:
    if frac <= 0.05:
        return 0
    if frac >= 0.95:
        return 2
    return 1


def _validate_domain_tag(tag: int) -> int:
    tag_i = int(tag)
    if tag_i not in (0, 1, 2):
        raise ValueError(f"domain_tag must be 0, 1, or 2; got {tag!r}.")
    return tag_i


class StdwReplayBuffer:
    """Ring buffer for STDW (s, a, a_pseudo, r, s', error, mask, V, tag, step) tuples."""

    def __init__(self, capacity: int = 50_000, device: Optional[torch.device | str] = None) -> None:
        self.capacity = int(capacity)
        self.device = torch.device(device) if device is not None else torch.device("cpu")
        self.size: int = 0
        self.position: int = 0
        # Lazily allocated when the first sample arrives so we can match dim.
        self.states: Optional[torch.Tensor] = None
        self.actions: Optional[torch.Tensor] = None
        self.pseudo_actions: Optional[torch.Tensor] = None
        self.next_states: Optional[torch.Tensor] = None
        self.rewards: torch.Tensor = torch.zeros(self.capacity, dtype=torch.float32, device=self.device)
        self.errors: torch.Tensor = torch.zeros(self.capacity, dtype=torch.float32, device=self.device)
        self.stdw_masks: torch.Tensor = torch.zeros(self.capacity, dtype=torch.float32, device=self.device)
        self.lyapunov_V: torch.Tensor = torch.zeros(self.capacity, dtype=torch.float32, device=self.device)
        self.domain_tags: torch.Tensor = torch.zeros(self.capacity, dtype=torch.long, device=self.device)
        self.steps: torch.Tensor = torch.zeros(self.capacity, dtype=torch.long, device=self.device)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_buffers(self, state: torch.Tensor, action: torch.Tensor) -> None:
        if self.states is None:
            state_dim = int(state.numel())
            action_dim = int(action.numel())
            self.states = torch.zeros(self.capacity, state_dim, dtype=torch.float32, device=self.device)
            self.actions = torch.zeros(self.capacity, action_dim, dtype=torch.float32, device=self.device)
            self.pseudo_actions = torch.zeros(self.capacity, action_dim, dtype=torch.float32, device=self.device)
            self.next_states = torch.zeros(self.capacity, state_dim, dtype=torch.float32, device=self.device)

    @staticmethod
    def _to_flat_1d(t: torch.Tensor | float | int) -> torch.Tensor:
        if not isinstance(t, torch.Tensor):
            t = torch.tensor(t, dtype=torch.float32)
        return t.detach().to(dtype=torch.float32).reshape(-1)

    @staticmethod
    def _to_scalar_float(value: torch.Tensor | float | int) -> float:
        if isinstance(value, torch.Tensor):
            return float(value.detach().reshape(-1)[0].item())
        return float(value)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def add(
        self,
        state: torch.Tensor,
        action: torch.Tensor,
        reward: torch.Tensor | float,
        next_state: torch.Tensor,
        error: torch.Tensor | float,
        drift_frac: torch.Tensor | float,
        step: torch.Tensor | int,
        *,
        pseudo_action: Optional[torch.Tensor] = None,
        stdw_mask: torch.Tensor | float = 1.0,
        lyapunov_V: torch.Tensor | float = 0.0,
        domain_tag_override: Optional[int] = None,
    ) -> None:
        state_v = self._to_flat_1d(state)
        action_v = self._to_flat_1d(action)
        next_state_v = self._to_flat_1d(next_state)
        if pseudo_action is None:
            pseudo_v = action_v.clone()
        else:
            pseudo_v = self._to_flat_1d(pseudo_action)

        self._ensure_buffers(state_v, action_v)

        idx = self.position
        self.states[idx] = state_v.to(self.device)
        self.actions[idx] = action_v.to(self.device)
        self.pseudo_actions[idx] = pseudo_v.to(self.device)
        self.next_states[idx] = next_state_v.to(self.device)
        self.rewards[idx] = self._to_scalar_float(reward)
        self.errors[idx] = self._to_scalar_float(error)
        self.stdw_masks[idx] = self._to_scalar_float(stdw_mask)
        self.lyapunov_V[idx] = self._to_scalar_float(lyapunov_V)

        frac_f = self._to_scalar_float(drift_frac)
        self.domain_tags[idx] = (
            _domain_tag_from_frac(frac_f)
            if domain_tag_override is None
            else _validate_domain_tag(int(domain_tag_override))
        )
        self.steps[idx] = int(self._to_scalar_float(step))

        self.position = (self.position + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def __len__(self) -> int:
        return self.size

    def domain_counts(self) -> Dict[int, int]:
        """Return the live row count in each source/intermediate/target bucket."""

        if self.size == 0:
            return {0: 0, 1: 0, 2: 0}
        tags = self.domain_tags[: self.size]
        return {tag: int((tags == tag).sum().item()) for tag in (0, 1, 2)}

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------

    def _candidate_indices(self, domain_tag: Optional[int]) -> torch.Tensor:
        if self.size == 0:
            return torch.empty(0, dtype=torch.long, device=self.device)
        all_idx = torch.arange(self.size, dtype=torch.long, device=self.device)
        if domain_tag is None:
            return all_idx
        mask = self.domain_tags[:self.size] == int(domain_tag)
        return all_idx[mask]

    def sample(
        self,
        batch_size: int,
        *,
        domain_tag: Optional[int] = None,
        use_quantile_filter: bool = True,
        discard_ratio: float = 0.1,
    ) -> Dict[str, torch.Tensor]:
        candidates = self._candidate_indices(domain_tag)
        if candidates.numel() == 0:
            # Fall back to any available samples to avoid empty returns.
            candidates = self._candidate_indices(None)
        if candidates.numel() == 0:
            raise RuntimeError("StdwReplayBuffer.sample called on empty buffer.")

        if use_quantile_filter and candidates.numel() >= 32 and 0.0 < discard_ratio < 1.0:
            errs = self.errors[candidates]
            tau = torch.quantile(errs, 1.0 - float(discard_ratio))
            keep_mask = errs <= tau
            kept = candidates[keep_mask]
            if kept.numel() >= 1:
                candidates = kept

        if candidates.numel() < batch_size:
            choice = candidates[torch.randint(0, candidates.numel(), (batch_size,), device=self.device)]
        else:
            perm = torch.randperm(candidates.numel(), device=self.device)[:batch_size]
            choice = candidates[perm]

        return {
            "states": self.states[choice].clone(),
            "actions": self.actions[choice].clone(),
            "pseudo_actions": self.pseudo_actions[choice].clone(),
            "next_states": self.next_states[choice].clone(),
            "rewards": self.rewards[choice].clone(),
            "errors": self.errors[choice].clone(),
            "stdw_masks": self.stdw_masks[choice].clone(),
            "lyapunov_V": self.lyapunov_V[choice].clone(),
            "domain_tags": self.domain_tags[choice].clone(),
            "steps": self.steps[choice].clone(),
        }

    @staticmethod
    def _merge_batches(batches: list[Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
        if not batches:
            raise RuntimeError("No batches to merge.")
        merged = {key: torch.cat([batch[key] for batch in batches], dim=0) for key in batches[0].keys()}
        n = int(merged["states"].shape[0])
        if n <= 1:
            return merged
        perm = torch.randperm(n, device=merged["states"].device)
        return {key: value[perm].clone() for key, value in merged.items()}

    def _sample_target_side(
        self,
        batch_size: int,
        *,
        target_domain_mode: str,
        target_intermediate_fraction: float,
        use_quantile_filter: bool,
        discard_ratio: float,
    ) -> Dict[str, torch.Tensor]:
        mode = str(target_domain_mode)
        if mode not in _TARGET_DOMAIN_MODES:
            raise ValueError(f"Unsupported target_domain_mode {mode!r}; choose from {_TARGET_DOMAIN_MODES}.")

        has_target = self._candidate_indices(2).numel() > 0
        has_intermediate = self._candidate_indices(1).numel() > 0

        if mode == "mixed_all":
            return self.sample(
                batch_size,
                domain_tag=None,
                use_quantile_filter=use_quantile_filter,
                discard_ratio=discard_ratio,
            )

        if mode == "domain_balanced_mix":
            live_tags = [tag for tag in (0, 1, 2) if self._candidate_indices(tag).numel() > 0]
            if not live_tags:
                return self.sample(
                    batch_size,
                    domain_tag=None,
                    use_quantile_filter=use_quantile_filter,
                    discard_ratio=discard_ratio,
                )
            base = int(batch_size) // len(live_tags)
            remainder = int(batch_size) % len(live_tags)
            batches: list[Dict[str, torch.Tensor]] = []
            for i, tag in enumerate(live_tags):
                n_tag = base + (1 if i < remainder else 0)
                if n_tag <= 0:
                    continue
                batches.append(
                    self.sample(
                        n_tag,
                        domain_tag=tag,
                        use_quantile_filter=use_quantile_filter,
                        discard_ratio=discard_ratio,
                    )
                )
            return self._merge_batches(batches)

        if mode == "target_then_intermediate":
            # Legacy behavior: target(tag2), then intermediate(tag1), then global.
            tgt_tag: Optional[int] = 2
            if not has_target:
                tgt_tag = 1 if has_intermediate else None
            return self.sample(
                batch_size,
                domain_tag=tgt_tag,
                use_quantile_filter=use_quantile_filter,
                discard_ratio=discard_ratio,
            )

        if mode == "intermediate_only":
            tgt_tag = 1 if has_intermediate else (2 if has_target else None)
            return self.sample(
                batch_size,
                domain_tag=tgt_tag,
                use_quantile_filter=use_quantile_filter,
                discard_ratio=discard_ratio,
            )

        # Opt-in B-2' mode: mix real target(tag2) and FM-enriched intermediate(tag1)
        # on the target side. Defaults never select this path.
        if has_target and has_intermediate:
            frac = min(max(float(target_intermediate_fraction), 0.0), 1.0)
            n_inter = int(round(int(batch_size) * frac))
            n_tgt = int(batch_size) - n_inter
            batches: list[Dict[str, torch.Tensor]] = []
            if n_tgt > 0:
                batches.append(
                    self.sample(
                        n_tgt,
                        domain_tag=2,
                        use_quantile_filter=use_quantile_filter,
                        discard_ratio=discard_ratio,
                    )
                )
            if n_inter > 0:
                batches.append(
                    self.sample(
                        n_inter,
                        domain_tag=1,
                        use_quantile_filter=use_quantile_filter,
                        discard_ratio=discard_ratio,
                    )
                )
            return self._merge_batches(batches)

        tgt_tag = 2 if has_target else (1 if has_intermediate else None)
        return self.sample(
            batch_size,
            domain_tag=tgt_tag,
            use_quantile_filter=use_quantile_filter,
            discard_ratio=discard_ratio,
        )

    def sample_pair(
        self,
        batch_size: int,
        rho: float,
        *,
        use_quantile_filter: bool = True,
        discard_ratio: float = 0.1,
        target_domain_mode: str = "target_then_intermediate",
        target_intermediate_fraction: float = 0.5,
    ):
        """Sample a (B_source, B_target, rho) tuple for STDW Eq.13.

        Default behavior is legacy: if the target bucket is empty, fall back to
        intermediate; if that is empty too, fall back to whatever the buffer
        contains. B-2' FM midpoint consumption is opt-in through
        target_domain_mode="target_intermediate_mix" or "intermediate_only".
        """

        half = max(int(batch_size) // 2, 1)
        # Source side ----------------------------------------------------
        src_candidates = self._candidate_indices(0)
        src_tag: Optional[int] = 0
        if src_candidates.numel() == 0:
            src_tag = None  # fallback to global pool

        b_src = self.sample(half, domain_tag=src_tag, use_quantile_filter=use_quantile_filter, discard_ratio=discard_ratio)
        b_tgt = self._sample_target_side(
            half,
            target_domain_mode=target_domain_mode,
            target_intermediate_fraction=target_intermediate_fraction,
            use_quantile_filter=use_quantile_filter,
            discard_ratio=discard_ratio,
        )
        return b_src, b_tgt, float(rho)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "capacity": self.capacity,
            "size": self.size,
            "position": self.position,
            "device": str(self.device),
            "rewards": self.rewards.detach().cpu(),
            "errors": self.errors.detach().cpu(),
            "stdw_masks": self.stdw_masks.detach().cpu(),
            "lyapunov_V": self.lyapunov_V.detach().cpu(),
            "domain_tags": self.domain_tags.detach().cpu(),
            "steps": self.steps.detach().cpu(),
        }
        for key in ("states", "actions", "pseudo_actions", "next_states"):
            tensor = getattr(self, key)
            payload[key] = tensor.detach().cpu() if tensor is not None else None
        torch.save(payload, path)

    def load(self, path: str | Path) -> None:
        path = Path(path)
        payload = torch.load(path, map_location=self.device)
        self.capacity = int(payload["capacity"])
        self.size = int(payload["size"])
        self.position = int(payload["position"])
        for key in ("rewards", "errors", "stdw_masks", "lyapunov_V", "domain_tags", "steps"):
            setattr(self, key, payload[key].to(self.device))
        for key in ("states", "actions", "pseudo_actions", "next_states"):
            tensor = payload.get(key)
            if tensor is not None:
                setattr(self, key, tensor.to(self.device))
            else:
                setattr(self, key, None)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _self_test() -> None:
    torch.manual_seed(0)
    buf = StdwReplayBuffer(capacity=2048, device="cpu")
    state_dim, action_dim = 9, 4

    for i in range(1000):
        # Spread drift_frac across all three domain_tag buckets.
        if i < 333:
            frac = 0.0
        elif i < 666:
            frac = 0.5
        else:
            frac = 1.0
        buf.add(
            state=torch.randn(state_dim),
            action=torch.randn(action_dim),
            reward=float(torch.randn(()).item()),
            next_state=torch.randn(state_dim),
            error=float(abs(torch.randn(()).item())),
            drift_frac=frac,
            step=i,
            pseudo_action=torch.randn(action_dim),
            stdw_mask=float(torch.randint(0, 2, ()).item()),
            lyapunov_V=float(torch.randn(()).item()),
        )

    for tag in (0, 1, 2):
        cand = buf._candidate_indices(tag)
        assert cand.numel() > 0, f"tag {tag} bucket empty"
    assert buf.domain_counts() == {0: 333, 1: 333, 2: 334}

    b_src, b_tgt, rho = buf.sample_pair(64, 0.7, use_quantile_filter=True, discard_ratio=0.1)
    assert b_src["states"].shape[0] == 32
    assert b_tgt["pseudo_actions"].shape[1] == action_dim
    assert torch.all(b_tgt["domain_tags"] == 2), "legacy target side must remain tag2 when available"
    assert rho == 0.7

    _, b_mix, _ = buf.sample_pair(
        64,
        0.7,
        use_quantile_filter=False,
        target_domain_mode="target_intermediate_mix",
        target_intermediate_fraction=0.25,
    )
    mix_tags = set(int(v.item()) for v in torch.unique(b_mix["domain_tags"]))
    assert mix_tags == {1, 2}, f"mixed target side expected tag1+tag2, got {mix_tags}"

    buf.add(
        state=torch.randn(state_dim),
        action=torch.randn(action_dim),
        reward=0.0,
        next_state=torch.randn(state_dim),
        error=0.0,
        drift_frac=0.0,
        step=1001,
        domain_tag_override=1,
    )
    assert int(buf.domain_tags[buf.position - 1].item()) == 1

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as fp:
        save_path = Path(fp.name)
    try:
        buf.save(save_path)
        buf2 = StdwReplayBuffer(capacity=2048, device="cpu")
        buf2.load(save_path)
        assert buf2.size == buf.size
        assert buf2.position == buf.position
        assert buf2.capacity == buf.capacity
        assert torch.allclose(buf2.errors, buf.errors)
        assert buf2.actions is not None and torch.allclose(buf2.actions, buf.actions)
    finally:
        save_path.unlink(missing_ok=True)

    print(
        f"[stdw_buffer] self-test OK | size={buf.size} pair=(B_src={b_src['states'].shape}, "
        f"B_tgt={b_tgt['states'].shape}) rho={rho}"
    )


if __name__ == "__main__":
    _self_test()

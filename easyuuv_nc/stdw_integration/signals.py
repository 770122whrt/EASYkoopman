"""Layer-2 physical-failsafe slow signals (SSWP / ATI) for the V1 stack.

This module implements the prompt §3 Plan A "Auto-Trim Integrator" (ATI) as an
Isaac-independent, pure-numpy building block. Its purpose is to turn the
low-level controller correction stream ``Δu(t)`` (deployable: allocator /
low-level PID output, NOT simulator-privileged) into a clean, low-frequency
steady-state wrench-projection (SSWP) bias, and to back-project that bias into a
*candidate* high-level pseudo-action via an analytic diagonal Jacobian inverse.

Design contract (mirrors ``AGENTS.md`` non-negotiables):

- **Plug-and-play / default identity.** Every helper is opt-in. When disabled or
  fed a zero signal it returns the unmodified action, so wiring it in changes
  nothing until explicitly enabled.
- **Diagnostic-first.** The default deliverable is the correlation-decoupling
  probe and the SSWP bias norm. The pseudo-action is a *candidate* only. It must
  NOT be used as an online action-space ``L_tgt`` until the ``corr < 0.7``
  nonclip gate is explicitly passed (this is a preserved negative result).
- **Deployable only.** Inputs are the low-level correction ``Δu`` (controller
  output) and the current high-level action ``a``. No CoM/CoB offset, no
  simulator ground-truth.

Physical polarity (prompt §3): with a persistent asymmetric bias, ``Δu_bar``
settles to a non-zero low-frequency value; the pseudo-action back-projection uses
a MINUS sign so the high-level target is pushed to counter-trim the bias:

    a_pseudo_safe = a - eta_safe * J_inv * Δu_bar

The high-frequency, zero-mean wave component is annihilated by the ~10 s EMA, so
``Δu_bar`` is decoupled from the policy's fast output (that decoupling is exactly
what the probe measures).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np


# 100 Hz control loop -> beta=0.999 is a ~10 s time constant (prompt §3 Plan A).
DEFAULT_SSWP_BETA = 0.999
# 6 s window RMS for the fast/slow correlation-decoupling probe.
DEFAULT_WINDOW_SECONDS = 6.0
DEFAULT_CONTROL_HZ = 100.0
# prompt §3 Plan A physical time constant of the very-slow EMA.
DEFAULT_SSWP_TIME_CONSTANT_S = 10.0
# corr>=0.7 means the slow signal is still shadowing the fast action -> NOT ready.
DEFAULT_DECOUPLE_CORR_GATE = 0.7


def beta_from_time_constant(time_constant_s: float, control_hz: float) -> float:
    """Map a physical EMA time constant (seconds) to a per-step beta.

    First-principles caliber fix: the prompt §3 Plan A design specifies a ~10 s
    slow-EMA time constant, NOT a raw beta. beta=0.999 only equals 10 s at
    100 Hz; the real env runs at 60 Hz, where the same raw beta silently becomes
    a ~16.7 s constant. This helper keeps the *physical* time constant invariant
    across control rates:

        beta = 1 - 1 / (time_constant_s * control_hz)

    e.g. 10 s @ 100 Hz -> 0.999, 10 s @ 60 Hz -> 0.99833. Clamped to a safe
    open interval so a degenerate (tau*hz <= 1) request cannot produce beta<=0.
    """
    tau = float(time_constant_s)
    hz = float(control_hz)
    if tau <= 0.0 or hz <= 0.0:
        return 0.0
    steps = tau * hz
    if steps <= 1.0:
        return 0.0
    return float(min(1.0 - 1.0 / steps, 0.999999))


@dataclass
class SSWPConfig:
    """Opt-in configuration for the SSWP / ATI slow-signal path."""

    enabled: bool = False
    beta: float = DEFAULT_SSWP_BETA
    # Optional physical EMA time constant (seconds). When set, it OVERRIDES the
    # raw ``beta`` via ``beta_from_time_constant(time_constant_seconds,
    # control_hz)`` so the slow-EMA horizon stays rate-invariant (prompt §3 Plan
    # A caliber). Default None => keep the raw ``beta`` (legacy identity).
    time_constant_seconds: float | None = None
    eta_safe: float = 0.0
    # Diagonal analytic Jacobian-inverse gains, one per high-level action channel
    # [roll/pitch, yaw_rate, thrust_n, depth]. Kept as an explicit vector so the
    # back-projection stays analytic and deployable. Default all-ones = identity
    # scaling; eta_safe=0 keeps the whole path identity regardless.
    jacobian_inv_diag: tuple[float, ...] | None = None
    action_dim: int = 4
    control_hz: float = DEFAULT_CONTROL_HZ
    window_seconds: float = DEFAULT_WINDOW_SECONDS
    clip_low: float = -1.0
    clip_high: float = 1.0

    def window_len(self) -> int:
        return max(int(round(float(self.window_seconds) * float(self.control_hz))), 1)

    def effective_beta(self) -> float:
        """Resolve the beta actually used by the slow EMA.

        If ``time_constant_seconds`` is set, derive a rate-invariant beta from it
        and ``control_hz``; otherwise fall back to the raw ``beta`` (legacy).
        """
        if self.time_constant_seconds is None:
            return float(self.beta)
        return beta_from_time_constant(self.time_constant_seconds, self.control_hz)


class SlowSignalEMA:
    """Very-slow exponential moving average of a vector signal.

    With ``beta=0.999`` at 100 Hz this is a ~10 s low-pass that annihilates the
    zero-mean wave component and retains only the persistent bias. It is
    initialized lazily on the first ``update`` so it adapts to the signal width.
    """

    def __init__(self, beta: float = DEFAULT_SSWP_BETA) -> None:
        self.beta = float(min(max(beta, 0.0), 0.999999))
        self._ema: np.ndarray | None = None
        self._count = 0

    def reset(self) -> None:
        self._ema = None
        self._count = 0

    @property
    def value(self) -> np.ndarray | None:
        return None if self._ema is None else self._ema.copy()

    @property
    def count(self) -> int:
        return self._count

    def update(self, x: Iterable[float] | np.ndarray) -> np.ndarray:
        arr = np.asarray(x, dtype=float).reshape(-1)
        if self._ema is None or self._ema.shape != arr.shape:
            self._ema = np.zeros_like(arr)
        self._ema = self.beta * self._ema + (1.0 - self.beta) * arr
        self._count += 1
        return self._ema.copy()


class WindowRMS:
    """Rolling per-channel RMS over a fixed window (default 6 s)."""

    def __init__(self, window_len: int) -> None:
        self.window_len = max(int(window_len), 1)
        self._buf: deque[np.ndarray] = deque(maxlen=self.window_len)

    def reset(self) -> None:
        self._buf.clear()

    def update(self, x: Iterable[float] | np.ndarray) -> np.ndarray:
        arr = np.asarray(x, dtype=float).reshape(-1)
        self._buf.append(arr)
        stack = np.stack(list(self._buf), axis=0)
        return np.sqrt(np.mean(np.square(stack), axis=0))

    @property
    def filled(self) -> bool:
        return len(self._buf) >= self.window_len


def resolve_jacobian_inv_diag(cfg: SSWPConfig) -> np.ndarray:
    """Return the diagonal analytic Jacobian-inverse gain vector.

    Defaults to an all-ones identity of length ``cfg.action_dim`` so the
    back-projection scaling is neutral until explicitly configured.
    """
    dim = int(cfg.action_dim)
    if cfg.jacobian_inv_diag is None:
        return np.ones(dim, dtype=float)
    diag = np.asarray(cfg.jacobian_inv_diag, dtype=float).reshape(-1)
    if diag.shape[0] != dim:
        raise ValueError(
            f"jacobian_inv_diag length {diag.shape[0]} != action_dim {dim}."
        )
    return diag


def sswp_pseudo_action(
    action: np.ndarray,
    sswp_bias: np.ndarray,
    cfg: SSWPConfig,
) -> np.ndarray:
    """Back-project a slow SSWP bias into a candidate high-level pseudo-action.

    ``a_pseudo_safe = clip(a - eta_safe * J_inv_diag * Δu_bar)``.

    With ``eta_safe=0`` (default) this is the identity, i.e. plug-and-play safe.
    The minus sign is the physical counter-trim polarity from prompt §3.
    """
    action = np.asarray(action, dtype=float).reshape(-1)
    if not cfg.enabled or float(cfg.eta_safe) == 0.0:
        return action.copy()
    bias = np.asarray(sswp_bias, dtype=float).reshape(-1)
    if bias.shape != action.shape:
        return action.copy()
    j_inv = resolve_jacobian_inv_diag(cfg)
    if j_inv.shape != action.shape:
        return action.copy()
    proposal = action - float(cfg.eta_safe) * (j_inv * bias)
    return np.clip(proposal, float(cfg.clip_low), float(cfg.clip_high))


def _safe_corr(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float).reshape(-1)
    b = np.asarray(b, dtype=float).reshape(-1)
    n = min(a.shape[0], b.shape[0])
    if n < 2:
        return float("nan")
    a = a[:n]
    b = b[:n]
    mask = np.isfinite(a) & np.isfinite(b)
    if int(mask.sum()) < 2:
        return float("nan")
    a = a[mask]
    b = b[mask]
    if np.std(a) < 1.0e-12 or np.std(b) < 1.0e-12:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def correlation_decoupling_probe(
    fast_action: np.ndarray,
    slow_bias: np.ndarray,
    *,
    corr_gate: float = DEFAULT_DECOUPLE_CORR_GATE,
) -> dict:
    """Measure whether the slow SSWP bias is decoupled from the fast action.

    Both inputs are (T, D) sequences (or (T,) flattened). Returns per-channel and
    aggregate absolute correlation and a ``decoupled`` gate result. The gate is
    the preserved-negative-result contract: only when ``max |corr| < corr_gate``
    across channels is the SSWP signal considered a non-shadowing, deployable
    candidate. This probe alone does NOT authorize online use.
    """
    fast = np.atleast_2d(np.asarray(fast_action, dtype=float))
    slow = np.atleast_2d(np.asarray(slow_bias, dtype=float))
    if fast.shape[0] == 1 and fast.shape[1] != slow.shape[1]:
        fast = fast.reshape(-1, 1)
    if slow.shape[0] == 1 and slow.shape[1] != fast.shape[1]:
        slow = slow.reshape(-1, 1)
    n = min(fast.shape[0], slow.shape[0])
    d = min(fast.shape[1], slow.shape[1])
    fast = fast[:n, :d]
    slow = slow[:n, :d]

    per_channel = [_safe_corr(fast[:, j], slow[:, j]) for j in range(d)]
    finite = [abs(c) for c in per_channel if np.isfinite(c)]
    max_abs_corr = float(np.max(finite)) if finite else float("nan")
    mean_abs_corr = float(np.mean(finite)) if finite else float("nan")
    decoupled = bool(np.isfinite(max_abs_corr) and max_abs_corr < float(corr_gate))
    return {
        "corr_gate": float(corr_gate),
        "per_channel_corr": [float(c) for c in per_channel],
        "max_abs_corr": max_abs_corr,
        "mean_abs_corr": mean_abs_corr,
        "n_samples": int(n),
        "n_channels": int(d),
        "decoupled": decoupled,
        # Explicit preserved-negative-result boundary: passing this probe is
        # necessary but NOT sufficient for online action-space L_tgt use.
        "online_action_target_ready": False,
    }


@dataclass
class SSWPRuntimeState:
    """Bundles the slow-signal filters for a live/offline SSWP pass."""

    cfg: SSWPConfig
    ema: SlowSignalEMA = field(init=False)
    rms: WindowRMS = field(init=False)

    def __post_init__(self) -> None:
        self.ema = SlowSignalEMA(beta=self.cfg.effective_beta())
        self.rms = WindowRMS(window_len=self.cfg.window_len())

    def reset(self) -> None:
        self.ema.reset()
        self.rms.reset()

    def step(self, low_level_delta: np.ndarray, action: np.ndarray) -> dict:
        """Advance one control step; return SSWP bias + candidate pseudo-action.

        Diagnostic-first: always returns the bias and a candidate anchor, but the
        anchor equals the input action unless ``enabled`` and ``eta_safe>0``.
        """
        delta = np.asarray(low_level_delta, dtype=float).reshape(-1)
        act = np.asarray(action, dtype=float).reshape(-1)
        bias = self.ema.update(delta)
        rms = self.rms.update(delta)
        anchor = sswp_pseudo_action(act, bias, self.cfg)
        return {
            "sswp_bias": bias,
            "sswp_bias_norm": float(np.linalg.norm(bias)),
            "sswp_window_rms": rms,
            "sswp_anchor": anchor,
            "sswp_anchor_delta_norm": float(np.linalg.norm(anchor - act)),
            "ema_count": int(self.ema.count),
        }


def compute_sswp_bias_series(
    low_level_delta_series: np.ndarray,
    *,
    beta: float = DEFAULT_SSWP_BETA,
) -> np.ndarray:
    """Offline: run the slow EMA over a (T, D) Δu sequence, return (T, D) bias."""
    seq = np.atleast_2d(np.asarray(low_level_delta_series, dtype=float))
    ema = SlowSignalEMA(beta=beta)
    out = np.empty_like(seq)
    for t in range(seq.shape[0]):
        out[t] = ema.update(seq[t])
    return out


__all__ = [
    "DEFAULT_SSWP_BETA",
    "DEFAULT_WINDOW_SECONDS",
    "DEFAULT_CONTROL_HZ",
    "DEFAULT_SSWP_TIME_CONSTANT_S",
    "DEFAULT_DECOUPLE_CORR_GATE",
    "beta_from_time_constant",
    "SSWPConfig",
    "SlowSignalEMA",
    "WindowRMS",
    "SSWPRuntimeState",
    "resolve_jacobian_inv_diag",
    "sswp_pseudo_action",
    "correlation_decoupling_probe",
    "compute_sswp_bias_series",
]

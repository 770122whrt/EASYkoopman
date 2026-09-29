from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from koopman_data import PWM_DIM, REFERENCE_DIM, STATE_DIM


@dataclass(frozen=True)
class PaperObservableConfig:
    variant: str = "selected_quadratic"
    state_dim: int = STATE_DIM
    reference_dim: int = REFERENCE_DIM
    control_dim: int = PWM_DIM
    include_bias: bool = True

    def __post_init__(self) -> None:
        if self.variant not in {"linear", "selected_quadratic"}:
            raise ValueError("variant must be 'linear' or 'selected_quadratic'")

    @property
    def state_slice(self) -> slice:
        return slice(0, self.state_dim)

    @property
    def feature_dim(self) -> int:
        size = self.state_dim + self.reference_dim + self.control_dim
        if self.variant == "selected_quadratic":
            size += 6 + self.control_dim
        if self.include_bias:
            size += 1
        return size

    def to_dict(self) -> dict:
        return {
            "variant": self.variant,
            "state_dim": self.state_dim,
            "reference_dim": self.reference_dim,
            "control_dim": self.control_dim,
            "include_bias": self.include_bias,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PaperObservableConfig":
        return cls(**data)


def _as_2d(values: np.ndarray, width: int, name: str) -> tuple[np.ndarray, bool]:
    array = np.asarray(values, dtype=float)
    was_1d = array.ndim == 1
    if was_1d:
        array = array.reshape(1, -1)
    if array.ndim != 2 or array.shape[1] != width:
        raise ValueError(f"{name} must have shape ({width},) or (n, {width})")
    return array, was_1d


def build_observables(
    state: np.ndarray,
    reference: np.ndarray,
    pwm: np.ndarray,
    config: PaperObservableConfig | None = None,
) -> np.ndarray:
    cfg = config or PaperObservableConfig()
    x, state_was_1d = _as_2d(state, cfg.state_dim, "state")
    r, reference_was_1d = _as_2d(reference, cfg.reference_dim, "reference")
    u, pwm_was_1d = _as_2d(pwm, cfg.control_dim, "pwm")
    if x.shape[0] != r.shape[0] or x.shape[0] != u.shape[0]:
        raise ValueError("state, reference and pwm must contain the same number of samples")

    pieces = [x, x[:, : cfg.reference_dim] - r, u]
    if cfg.variant == "selected_quadratic":
        pieces.extend([x[:, 5:11] ** 2, u**2])
    if cfg.include_bias:
        pieces.append(np.ones((x.shape[0], 1), dtype=float))

    observables = np.concatenate(pieces, axis=1)
    if observables.shape[1] != cfg.feature_dim:
        raise ValueError("observable feature dimension does not match config")
    if state_was_1d and reference_was_1d and pwm_was_1d:
        return observables[0]
    return observables

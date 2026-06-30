from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from koopman_data import REFERENCE_DIM, STATE_DIM


@dataclass(frozen=True)
class LiftingConfig:
    state_dim: int = STATE_DIM
    reference_dim: int = REFERENCE_DIM
    include_bias: bool = True
    include_reference: bool = True
    include_error: bool = True
    include_quadratic: bool = False

    @property
    def linear_feature_dim(self) -> int:
        size = self.state_dim
        if self.include_bias:
            size += 1
        if self.include_reference:
            size += self.reference_dim
        if self.include_error:
            size += self.reference_dim
        return size

    @property
    def feature_dim(self) -> int:
        if not self.include_quadratic:
            return self.linear_feature_dim
        quadratic_terms = self.linear_feature_dim - (1 if self.include_bias else 0)
        return self.linear_feature_dim + quadratic_terms

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "state_dim": self.state_dim,
            "reference_dim": self.reference_dim,
            "include_bias": self.include_bias,
            "include_reference": self.include_reference,
            "include_error": self.include_error,
            "include_quadratic": self.include_quadratic,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LiftingConfig":
        return cls(**data)


def _as_2d(values: np.ndarray, width: int, name: str) -> tuple[np.ndarray, bool]:
    array = np.asarray(values, dtype=float)
    was_1d = array.ndim == 1
    if was_1d:
        array = array.reshape(1, -1)
    if array.ndim != 2 or array.shape[1] != width:
        raise ValueError(f"{name} must have shape ({width},) or (n, {width})")
    return array, was_1d


def lift_state_reference(
    state: np.ndarray,
    reference: np.ndarray,
    config: LiftingConfig | None = None,
) -> np.ndarray:
    cfg = config or LiftingConfig()
    x, state_was_1d = _as_2d(state, cfg.state_dim, "state")
    r, reference_was_1d = _as_2d(reference, cfg.reference_dim, "reference")
    if x.shape[0] != r.shape[0]:
        raise ValueError("state and reference must contain the same number of samples")

    pieces: list[np.ndarray] = []
    if cfg.include_bias:
        pieces.append(np.ones((x.shape[0], 1), dtype=float))
    pieces.append(x)
    if cfg.include_reference:
        pieces.append(r)
    if cfg.include_error:
        pieces.append(x[:, : cfg.reference_dim] - r)

    linear = np.concatenate(pieces, axis=1)
    if cfg.include_quadratic:
        start = 1 if cfg.include_bias else 0
        features = np.concatenate([linear, linear[:, start:] ** 2], axis=1)
    else:
        features = linear

    if features.shape[1] != cfg.feature_dim:
        raise ValueError("lifting feature dimension does not match config")
    if state_was_1d and reference_was_1d:
        return features[0]
    return features


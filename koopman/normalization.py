from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class StandardNormalizer:
    mean: np.ndarray
    scale: np.ndarray

    def __post_init__(self) -> None:
        mean = np.asarray(self.mean, dtype=float)
        scale = np.asarray(self.scale, dtype=float)
        if mean.ndim != 1 or scale.ndim != 1 or mean.shape != scale.shape:
            raise ValueError("normalizer mean and scale must be one-dimensional arrays with the same shape")
        scale = np.where(scale == 0.0, 1.0, scale)
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "scale", scale)

    @classmethod
    def fit(cls, values: np.ndarray) -> "StandardNormalizer":
        array = np.asarray(values, dtype=float)
        if array.ndim != 2:
            raise ValueError("normalizer input must be a two-dimensional array")
        return cls(mean=np.mean(array, axis=0), scale=np.std(array, axis=0))

    def transform(self, values: np.ndarray) -> np.ndarray:
        return (np.asarray(values, dtype=float) - self.mean) / self.scale

    def inverse_transform(self, values: np.ndarray) -> np.ndarray:
        return np.asarray(values, dtype=float) * self.scale + self.mean

    def to_dict(self) -> dict:
        return {"kind": "standard", "mean": self.mean.tolist(), "scale": self.scale.tolist()}

    @classmethod
    def from_dict(cls, data: dict | None) -> "StandardNormalizer | None":
        if data is None:
            return None
        if data.get("kind") != "standard":
            raise ValueError(f"Unsupported normalizer kind: {data.get('kind')}")
        return cls(mean=np.asarray(data["mean"], dtype=float), scale=np.asarray(data["scale"], dtype=float))


def write_normalizer_artifact(
    path: str | Path,
    *,
    input_normalizer: StandardNormalizer | None,
    target_normalizer: StandardNormalizer | None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "input_normalizer": input_normalizer.to_dict() if input_normalizer else None,
                "target_normalizer": target_normalizer.to_dict() if target_normalizer else None,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

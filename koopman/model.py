from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from koopman_data import PWM_DIM, REFERENCE_DIM, STATE_DIM

from .lifting import LiftingConfig, lift_state_reference
from .normalization import StandardNormalizer


MODEL_VERSION = "koopman-edmd-v1"


@dataclass
class KoopmanModel:
    coefficient_matrix: np.ndarray
    lifting_config: LiftingConfig
    ridge: float
    state_dim: int = STATE_DIM
    reference_dim: int = REFERENCE_DIM
    control_dim: int = PWM_DIM
    metadata: dict[str, Any] = field(default_factory=dict)
    input_normalizer: StandardNormalizer | None = None
    target_normalizer: StandardNormalizer | None = None
    version: str = MODEL_VERSION
    model_class: str = "direct_state"

    def __post_init__(self) -> None:
        self.coefficient_matrix = np.asarray(self.coefficient_matrix, dtype=float)
        expected_width = self.lifting_config.feature_dim + self.control_dim
        if self.coefficient_matrix.shape != (self.state_dim, expected_width):
            raise ValueError(f"coefficient_matrix must have shape ({self.state_dim}, {expected_width})")

    def predict_next(self, state: np.ndarray, control: np.ndarray, reference: np.ndarray) -> np.ndarray:
        state_array = np.asarray(state, dtype=float)
        single = state_array.ndim == 1
        phi = lift_state_reference(state_array, reference, self.lifting_config)
        if phi.ndim == 1:
            phi = phi.reshape(1, -1)

        control_array = np.asarray(control, dtype=float)
        if control_array.ndim == 1:
            control_array = control_array.reshape(1, -1)
        if control_array.ndim != 2 or control_array.shape[1] != self.control_dim:
            raise ValueError(f"control must have shape ({self.control_dim},) or (n, {self.control_dim})")
        if control_array.shape[0] != phi.shape[0]:
            raise ValueError("state, control and reference must contain the same number of samples")

        design = np.concatenate([phi, control_array], axis=1)
        if self.input_normalizer:
            design = self.input_normalizer.transform(design)
        prediction = design @ self.coefficient_matrix.T
        if self.target_normalizer:
            prediction = self.target_normalizer.inverse_transform(prediction)
        return prediction[0] if single else prediction

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "model_class": self.model_class,
            "coefficient_matrix": self.coefficient_matrix.tolist(),
            "lifting_config": self.lifting_config.to_dict(),
            "ridge": self.ridge,
            "state_dim": self.state_dim,
            "reference_dim": self.reference_dim,
            "control_dim": self.control_dim,
            "metadata": self.metadata,
            "input_normalizer": self.input_normalizer.to_dict() if self.input_normalizer else None,
            "target_normalizer": self.target_normalizer.to_dict() if self.target_normalizer else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KoopmanModel":
        if data.get("version") != MODEL_VERSION:
            raise ValueError(f"Unsupported Koopman model version: {data.get('version')}")
        return cls(
            coefficient_matrix=np.asarray(data["coefficient_matrix"], dtype=float),
            lifting_config=LiftingConfig.from_dict(data["lifting_config"]),
            ridge=float(data["ridge"]),
            state_dim=int(data["state_dim"]),
            reference_dim=int(data["reference_dim"]),
            control_dim=int(data["control_dim"]),
            metadata=dict(data.get("metadata", {})),
            input_normalizer=StandardNormalizer.from_dict(data.get("input_normalizer")),
            target_normalizer=StandardNormalizer.from_dict(data.get("target_normalizer")),
            version=data["version"],
            model_class=str(data.get("model_class", "direct_state")),
        )

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "KoopmanModel":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

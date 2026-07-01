from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from koopman_data import PWM_DIM, REFERENCE_DIM, STATE_DIM

from .dataset import KoopmanDataset
from .normalization import StandardNormalizer
from .observables import PaperObservableConfig, build_observables


LIFTED_MODEL_VERSION = "paper-lifted-edmd-v1"


@dataclass
class LiftedEDMDModel:
    transition_matrix: np.ndarray
    observable_config: PaperObservableConfig
    ridge: float
    state_dim: int = STATE_DIM
    reference_dim: int = REFERENCE_DIM
    control_dim: int = PWM_DIM
    metadata: dict[str, Any] = field(default_factory=dict)
    input_normalizer: StandardNormalizer | None = None
    target_normalizer: StandardNormalizer | None = None
    version: str = LIFTED_MODEL_VERSION
    model_class: str = "paper_lifted_edmd"

    def __post_init__(self) -> None:
        self.transition_matrix = np.asarray(self.transition_matrix, dtype=float)
        expected = (self.observable_config.feature_dim, self.observable_config.feature_dim)
        if self.transition_matrix.shape != expected:
            raise ValueError(f"transition_matrix must have shape {expected}")

    def predict_next(self, state: np.ndarray, control: np.ndarray, reference: np.ndarray) -> np.ndarray:
        state_array = np.asarray(state, dtype=float)
        single = state_array.ndim == 1
        observables = build_observables(state_array, reference, control, self.observable_config)
        if observables.ndim == 1:
            observables = observables.reshape(1, -1)
        design = self.input_normalizer.transform(observables) if self.input_normalizer else observables
        predicted = design @ self.transition_matrix
        if self.target_normalizer:
            predicted = self.target_normalizer.inverse_transform(predicted)
        raw_state = predicted[:, self.observable_config.state_slice]
        return raw_state[0] if single else raw_state

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "model_class": self.model_class,
            "transition_matrix": self.transition_matrix.tolist(),
            "observable_config": self.observable_config.to_dict(),
            "ridge": self.ridge,
            "state_dim": self.state_dim,
            "reference_dim": self.reference_dim,
            "control_dim": self.control_dim,
            "metadata": self.metadata,
            "input_normalizer": self.input_normalizer.to_dict() if self.input_normalizer else None,
            "target_normalizer": self.target_normalizer.to_dict() if self.target_normalizer else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LiftedEDMDModel":
        if data.get("version") != LIFTED_MODEL_VERSION:
            raise ValueError(f"Unsupported lifted EDMD model version: {data.get('version')}")
        return cls(
            transition_matrix=np.asarray(data["transition_matrix"], dtype=float),
            observable_config=PaperObservableConfig.from_dict(data["observable_config"]),
            ridge=float(data["ridge"]),
            state_dim=int(data["state_dim"]),
            reference_dim=int(data["reference_dim"]),
            control_dim=int(data["control_dim"]),
            metadata=dict(data.get("metadata", {})),
            input_normalizer=StandardNormalizer.from_dict(data.get("input_normalizer")),
            target_normalizer=StandardNormalizer.from_dict(data.get("target_normalizer")),
            version=data["version"],
            model_class=str(data.get("model_class", "paper_lifted_edmd")),
        )

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "LiftedEDMDModel":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def fit_lifted_edmd(
    dataset: KoopmanDataset,
    *,
    observable_config: PaperObservableConfig | None = None,
    ridge: float = 1e-6,
    normalize: bool = False,
    metadata: dict[str, Any] | None = None,
) -> LiftedEDMDModel:
    if ridge < 0:
        raise ValueError("ridge must be non-negative")
    config = observable_config or PaperObservableConfig()
    current = build_observables(dataset.X, dataset.R, dataset.U, config)
    target = build_observables(dataset.Y, dataset.R, dataset.U, config)

    input_normalizer = StandardNormalizer.fit(current) if normalize else None
    target_normalizer = StandardNormalizer.fit(target) if normalize else None
    design = input_normalizer.transform(current) if input_normalizer else current
    target_design = target_normalizer.transform(target) if target_normalizer else target

    gram = design.T @ design
    if ridge > 0:
        gram = gram + ridge * np.eye(gram.shape[0])
    rhs = design.T @ target_design
    try:
        transition = np.linalg.solve(gram, rhs)
    except np.linalg.LinAlgError:
        transition = np.linalg.pinv(gram) @ rhs

    model_metadata = {
        "sample_count": dataset.sample_count,
        "source_paths": list(dataset.source_paths),
        "dt": dataset.dt,
        "trajectory_types": list(dataset.trajectory_types),
        "controller_modes": list(dataset.controller_modes),
    }
    if metadata:
        model_metadata.update(metadata)

    return LiftedEDMDModel(
        transition_matrix=transition,
        observable_config=config,
        ridge=ridge,
        state_dim=dataset.X.shape[1],
        reference_dim=dataset.R.shape[1],
        control_dim=dataset.U.shape[1],
        metadata=model_metadata,
        input_normalizer=input_normalizer,
        target_normalizer=target_normalizer,
    )

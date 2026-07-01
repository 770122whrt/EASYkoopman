from __future__ import annotations

from typing import Any

import numpy as np

from .dataset import KoopmanDataset
from .lifting import LiftingConfig, lift_state_reference
from .model import KoopmanModel
from .normalization import StandardNormalizer


def fit_edmd(
    dataset: KoopmanDataset,
    *,
    lifting_config: LiftingConfig | None = None,
    ridge: float = 1e-6,
    normalize: bool = False,
    metadata: dict[str, Any] | None = None,
) -> KoopmanModel:
    if ridge < 0:
        raise ValueError("ridge must be non-negative")

    config = lifting_config or LiftingConfig()
    phi = lift_state_reference(dataset.X, dataset.R, config)
    design = np.concatenate([phi, dataset.U], axis=1)
    target = dataset.Y
    input_normalizer = StandardNormalizer.fit(design) if normalize else None
    target_normalizer = StandardNormalizer.fit(target) if normalize else None
    fit_design = input_normalizer.transform(design) if input_normalizer else design
    fit_target = target_normalizer.transform(target) if target_normalizer else target

    gram = fit_design.T @ fit_design
    if ridge > 0:
        gram = gram + ridge * np.eye(gram.shape[0])
    rhs = fit_design.T @ fit_target
    try:
        coefficients = np.linalg.solve(gram, rhs).T
    except np.linalg.LinAlgError:
        coefficients = (np.linalg.pinv(gram) @ rhs).T

    model_metadata = {
        "sample_count": dataset.sample_count,
        "source_paths": list(dataset.source_paths),
        "dt": dataset.dt,
        "trajectory_types": list(dataset.trajectory_types),
        "controller_modes": list(dataset.controller_modes),
    }
    if metadata:
        model_metadata.update(metadata)

    return KoopmanModel(
        coefficient_matrix=coefficients,
        lifting_config=config,
        ridge=ridge,
        state_dim=dataset.X.shape[1],
        reference_dim=dataset.R.shape[1],
        control_dim=dataset.U.shape[1],
        metadata=model_metadata,
        input_normalizer=input_normalizer,
        target_normalizer=target_normalizer,
    )

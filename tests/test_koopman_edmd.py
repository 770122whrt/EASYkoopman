import numpy as np

from koopman.dataset import KoopmanDataset
from koopman.edmd import fit_edmd
from koopman.lifting import LiftingConfig


def test_edmd_recovers_synthetic_linear_controlled_dynamics():
    rng = np.random.default_rng(7)
    n = 80
    state_dim = 11
    control_dim = 8
    reference_dim = 5
    X = rng.normal(size=(n, state_dim))
    U = rng.normal(size=(n, control_dim)) * 0.1
    R = rng.normal(size=(n, reference_dim))

    bias = np.linspace(-0.05, 0.05, state_dim)
    state_matrix = np.eye(state_dim) * 0.92
    control_matrix = rng.normal(size=(control_dim, state_dim)) * 0.03
    reference_matrix = rng.normal(size=(reference_dim, state_dim)) * 0.02
    Y = bias + X @ state_matrix + U @ control_matrix + R @ reference_matrix

    dataset = KoopmanDataset(
        X=X,
        U=U,
        R=R,
        Y=Y,
        t=np.arange(n, dtype=float) / 60.0,
        source_paths=("synthetic",),
        dt=1.0 / 60.0,
        trajectory_types=("synthetic",),
        controller_modes=("fixture",),
    )

    model = fit_edmd(dataset, lifting_config=LiftingConfig(include_error=False), ridge=1e-10)
    pred = model.predict_next(X, U, R)

    assert model.state_dim == state_dim
    assert model.control_dim == control_dim
    assert model.reference_dim == reference_dim
    assert np.sqrt(np.mean((pred - Y) ** 2)) < 1e-8


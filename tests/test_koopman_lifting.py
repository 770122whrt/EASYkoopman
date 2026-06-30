import numpy as np
import pytest

from koopman.lifting import LiftingConfig, lift_state_reference


def test_lifting_is_deterministic_and_reports_expected_dimension():
    config = LiftingConfig(include_quadratic=False)
    state = np.arange(11, dtype=float)
    reference = np.arange(5, dtype=float) * 0.1

    first = lift_state_reference(state, reference, config)
    second = lift_state_reference(state, reference, config)

    assert first.shape == (config.feature_dim,)
    assert config.feature_dim == 1 + 11 + 5 + 5
    np.testing.assert_allclose(first, second)
    assert first[0] == 1.0


def test_lifting_adds_elementwise_quadratic_terms_when_enabled():
    linear_config = LiftingConfig(include_quadratic=False)
    quadratic_config = LiftingConfig(include_quadratic=True)
    state = np.arange(11, dtype=float)
    reference = np.arange(5, dtype=float)

    linear = lift_state_reference(state, reference, linear_config)
    quadratic = lift_state_reference(state, reference, quadratic_config)

    assert quadratic.shape == (quadratic_config.feature_dim,)
    assert quadratic_config.feature_dim == linear_config.feature_dim + (linear_config.feature_dim - 1)
    np.testing.assert_allclose(quadratic[: linear_config.feature_dim], linear)


def test_lifting_rejects_bad_dimensions():
    with pytest.raises(ValueError, match="state"):
        lift_state_reference(np.zeros(10), np.zeros(5))
    with pytest.raises(ValueError, match="reference"):
        lift_state_reference(np.zeros(11), np.zeros(4))


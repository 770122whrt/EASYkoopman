import numpy as np

from koopman.observables import PaperObservableConfig, build_observables


def test_paper_observables_keep_raw_state_as_first_slice():
    state = np.arange(11, dtype=float)
    reference = np.arange(5, dtype=float) * 0.1
    pwm = np.linspace(-0.5, 0.5, 8)
    config = PaperObservableConfig(variant="selected_quadratic")

    observable = build_observables(state, reference, pwm, config)

    assert config.state_slice == slice(0, 11)
    np.testing.assert_allclose(observable[config.state_slice], state)
    assert observable.shape == (config.feature_dim,)
    assert config.feature_dim == 39


def test_linear_observable_variant_omits_quadratic_terms():
    states = np.zeros((2, 11), dtype=float)
    references = np.ones((2, 5), dtype=float)
    pwms = np.zeros((2, 8), dtype=float)

    observables = build_observables(states, references, pwms, PaperObservableConfig(variant="linear"))

    assert observables.shape == (2, 25)

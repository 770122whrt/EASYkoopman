"""Contracts for bounded representation diagnostics, not model admission."""
import importlib.util
import numpy as np
import pytest


def module():
    assert importlib.util.find_spec('koopman.representation_probe_v23'), 'representation probe missing'
    from koopman import representation_probe_v23
    return representation_probe_v23


def state():
    x = np.zeros(11); x[1] = 1
    return x


def test_order_and_topology_mask_are_explicit():
    m = module(); u = np.array([[.1, .2, 0, .3], [.4, .5, 0, .6]])
    a = m.features(state(), np.array([1, 2, 0, 4]), u, variant='ordered_proxy', mask=[1, 1, 0, 1])
    b = m.features(state(), np.array([1, 2, 0, 4]), u[::-1], variant='ordered_proxy', mask=[1, 1, 0, 1])
    assert len(a) == 13 + 3 + 6
    np.testing.assert_array_equal(a[-6:], [.1, .2, .3, .4, .5, .6])
    assert not np.array_equal(a, b)
    assert len(m.features(state(), np.zeros(6), u, variant='last_speed', mask=[1, 1, 0, 1])) == 22


def test_scaled_mean_ridge_matches_objective_and_unpenalized_intercept():
    m = module(); rng = np.random.default_rng(73)
    x = rng.normal(size=(40, 8)); x[:, 0] = 7
    y = rng.normal(size=(40, 10)) + 11
    fitted = m.fit(x, y)
    z = (x - x.mean(0)) / np.maximum(x.std(0), 1e-6)
    expected = np.linalg.solve(z.T @ z / len(x) + .001*np.eye(8), z.T @ (y-y.mean(0)) / len(x))
    np.testing.assert_allclose(fitted.predict(x), y.mean(0) + z @ expected, atol=1e-12)
    np.testing.assert_allclose(fitted.predict(x.mean(0)), y.mean(0), atol=1e-12)
    before = fitted.mean.copy(); fitted.predict(x * 30 + 200)
    np.testing.assert_array_equal(before, fitted.mean)


def test_rollout_has_no_future_truth_input_and_failure_keeps_origin():
    m = module()
    class Counter:
        def predict(self, f):
            out = np.zeros(10); out[0] = 1
            return out
    memories = np.zeros((5, 4)); controls = np.zeros((5, 2, 4))
    result = m.rollout(Counter(), state(), memories, controls, variant='last_proxy', mask=[1]*4)
    assert result['status'] == 'success'
    np.testing.assert_array_equal(result['predictions'][:, 0], np.arange(1, 6))
    x = state(); x[0] = 99
    failure = m.rollout(Counter(), x, memories, controls, variant='last_proxy', mask=[1]*4)
    assert failure['status'] == 'failed' and failure['failed_step'] == 2
    assert failure['predictions'] is None


@pytest.mark.parametrize('bad', [np.nan, np.inf])
def test_nonfinite_fit_rejected(bad):
    x=np.ones((3, 4)); x[0, 0]=bad
    with pytest.raises(ValueError, match='fit_invalid'):
        module().fit(x, np.ones((3, 10)))


def test_mask_leak_is_rejected_instead_of_discarded():
    with pytest.raises(ValueError, match='masked_control'):
        module().features(state(), np.zeros(4), np.ones((2,4)), variant='last_proxy', mask=[1,1,0,1])

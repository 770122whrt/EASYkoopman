"""Compare same-host source replay; report historical-cache drift separately."""
import numpy as np
import pytest


def test_cached_origin_difference_is_reported_without_relaxing_replay_equivalence():
    from workflows.benchmark_compiled_mpc_v64 import verify_origin_replay
    actual = np.array([1., 2.]); reference = actual.copy(); cached = actual + 1e-5
    report = verify_origin_replay(actual, reference, cached, 2., 2., 2.)
    assert report['same_host_replay_max_abs_difference'] == 0
    assert report['historical_cache_max_abs_difference'] == pytest.approx(1e-5)
    assert report['cache_used_as_state_correction'] is False
    with pytest.raises(AssertionError):
        verify_origin_replay(actual+1e-6, reference, cached, 2., 2., 2.)


def test_clock_or_nonfinite_origin_cannot_be_ignored():
    from workflows.benchmark_compiled_mpc_v64 import verify_origin_replay
    with pytest.raises(AssertionError):
        verify_origin_replay(np.zeros(2), np.zeros(2), np.zeros(2), 2.01, 2., 2.)
    with pytest.raises(ValueError):
        verify_origin_replay(np.zeros(2), np.zeros(2), np.array([np.nan, 0]), 2., 2., 2.)

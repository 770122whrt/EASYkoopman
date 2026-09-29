"""Prepared allocation is checked end to end against unchanged batch v41."""
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.command_batch_v41 import forecast_batch as reference
from test_command_batch_v41 import setup, same


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
@pytest.mark.parametrize('origin,horizon,count', [(64, 20, 8), (128, 128, 3)])
def test_prepared_batch_matches_original_and_preserves_live_history(name, origin, horizon, count):
    from koopman.command_batch_v42 import forecast_batch
    live, saved, x, predictor = setup(name, origin)
    drive = np.random.default_rng(421).uniform(-.03, .03, (count, horizon, 4))
    drive[:, :, 3] += .12
    before = drive.copy()
    for a, b in zip(forecast_batch(saved, x, drive, predictor), reference(saved, x, drive, predictor)):
        same(a, b)
    np.testing.assert_array_equal(drive, before)
    assert live.physics_index == 2*origin


@pytest.mark.parametrize('mode', ['nan', 'raise'])
def test_failed_candidate_is_isolated_with_same_partial_prefix(mode):
    from koopman.command_batch_v42 import forecast_batch
    _, saved, x, _ = setup(origin=0)
    drive = np.zeros((3, 4, 4)); drive[1, :, 3] = .4
    def predict(states, acceleration, context):
        bad = np.abs(acceleration[:, 2]) > .02
        if mode == 'raise' and bad.any(): raise ValueError('branch_domain')
        result = states.copy(); result[:, 5:] += 1e-5*acceleration
        if mode == 'nan': result[bad] = np.nan
        return result
    actual = forecast_batch(saved, x, drive, predict)
    for a, b in zip(actual, reference(saved, x, drive, predict)): same(a, b)
    assert [r['complete'] for r in actual] == [True, False, True]


def test_parallel_order_and_output_ownership():
    from koopman.command_batch_v42 import forecast_batch
    _, saved, x, predict = setup('uuv6_angled')
    drive = np.random.default_rng(422).uniform(-.1, .1, (3, 4, 4))
    expected = reference(saved, x, drive, predict)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(forecast_batch, saved, x, drive, predict)
        b = pool.submit(forecast_batch, saved, x, drive[::-1], predict)
        first, second = a.result(), b.result()[::-1]
    for a, b, c in zip(expected, first, second): same(a, b); same(a, c)
    first[0]['origin_rotor_speed'][:] = 99
    assert not np.any(first[1]['origin_rotor_speed'] == 99)
    assert not np.any(saved._actuator.current() == 99)


def test_deadlines_input_bounds_and_origin_guards_are_retained():
    from koopman.command_batch_v42 import forecast_batch
    live, saved, x, predict = setup()
    for invalid in (np.zeros((65, 1, 4)), np.ones((1, 1, 4)), np.full((1, 1, 4), np.nan)):
        with pytest.raises(ValueError): forecast_batch(saved, x, invalid, predict)
    with pytest.raises(ValueError): forecast_batch(live, x, np.zeros((1, 1, 4)), predict)
    with pytest.raises(TimeoutError):
        forecast_batch(saved, x, np.zeros((1, 1, 4)), predict, deadline=time.monotonic()-1)
    def slow(states, u, c): time.sleep(.02); return states.copy()
    with pytest.raises(TimeoutError):
        forecast_batch(saved, x, np.zeros((1, 1, 4)), slow, deadline=time.monotonic()+.01)
    assert live.physics_index == 6

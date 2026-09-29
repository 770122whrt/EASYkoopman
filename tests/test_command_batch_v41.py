"""Batch candidates are independent v39 forecasts from one causal origin."""
from concurrent.futures import ThreadPoolExecutor
import time

import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.command_state_v39 import CausalCommandState
from koopman.prepared_projected_v40 import prepare_projected
from test_prepared_projected_v40 import context, model


def setup(name='base', origin=3):
    c = context(name)
    live = CausalCommandState(name, c, episode_id='batch-test', zero_rotor_reset_verified=True)
    for i in range(2*origin):
        live.record_issued([.01, -.01, .01, .13], physics_index=i, episode_id='batch-test')
    snapshot = live.snapshot(configuration=name, context=c, origin_control=origin, episode_id='batch-test')
    x = np.array([5.5, 1., 0, 0, 0, .01, -.01, 0, 0, 0, 0])
    return live, snapshot, x, prepare_projected(model(), c)


FIELDS = ('predictions', 'pwm', 'rotor_speed', 'acceleration', 'physics_time_s',
          'origin_rotor_speed', 'requested_commands', 'applied_control', 'issued_commands', 'control_mask')


def same(a, b):
    for key in ('complete', 'failure', 'completed_control_intervals', 'origin_control', 'origin_actuator_time_s'):
        assert a[key] == b[key], key
    for key in FIELDS:
        np.testing.assert_allclose(a[key], b[key], rtol=1e-12, atol=1e-12, err_msg=key)


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
@pytest.mark.parametrize('origin,horizon,count', [(0, 20, 1), (3, 60, 3), (7, 128, 8)])
def test_batch_matches_each_scalar_forecast_and_does_not_commit(name, origin, horizon, count):
    from koopman.command_batch_v41 import forecast_batch
    live, saved, x, predictor = setup(name, origin)
    drive = np.random.default_rng(411).uniform(-.03, .03, (count, horizon, 4))
    drive[:, :, 3] += .12
    original = drive.copy()
    actual = forecast_batch(saved, x, drive, predictor)
    assert len(actual) == count
    for command, result in zip(drive, actual):
        same(result, saved.forecast(x, command, predictor))
    np.testing.assert_array_equal(drive, original)
    assert live.physics_index == 2*origin


def test_order_parallel_and_returned_array_mutation_do_not_leak():
    from koopman.command_batch_v41 import forecast_batch
    live, saved, x, predictor = setup()
    drive = np.random.default_rng(412).uniform(-.1, .1, (3, 4, 4))
    first = forecast_batch(saved, x, drive, predictor)
    with ThreadPoolExecutor(max_workers=2) as pool:
        forward = pool.submit(forecast_batch, saved, x, drive, predictor)
        reverse = pool.submit(forecast_batch, saved, x, drive[::-1], predictor)
        for a, b, c in zip(first, forward.result(), reverse.result()[::-1]):
            same(a, b); same(a, c)
    first[0]['origin_rotor_speed'][:] = 99
    first[0]['predictions'][:] = 99
    assert not np.any(first[1]['origin_rotor_speed'] == 99)
    for i in range(6, 8):
        live.record_issued(np.zeros(4), physics_index=i, episode_id='batch-test')
    for command, result in zip(drive, forecast_batch(saved, x, drive, predictor)):
        same(result, saved.forecast(x, command, predictor))


@pytest.mark.parametrize('failure', ['nan', 'raise'])
def test_one_failed_branch_has_same_prefix_as_scalar_and_others_continue(failure):
    from koopman.command_batch_v41 import forecast_batch
    _, saved, x, _ = setup(origin=0)
    drive = np.zeros((3, 4, 4))
    drive[1, :, 3] = .4

    def selective(states, acceleration, c):
        bad = np.abs(acceleration[:, 2]) > .02
        if failure == 'raise' and bad.any():
            raise ValueError('branch_domain')
        result = states.copy()
        result[:, 5:] += 1e-5*acceleration
        if failure == 'nan': result[bad] = np.nan
        return result

    actual = forecast_batch(saved, x, drive, selective)
    for command, result in zip(drive, actual):
        same(result, saved.forecast(x, command, selective))
    assert actual[0]['complete'] and not actual[1]['complete'] and actual[2]['complete']


@pytest.mark.parametrize('shape', [(0, 2, 4), (65, 2, 4), (2, 0, 4), (2, 129, 4), (2, 4), (1, 2, 5)])
def test_batch_size_and_horizon_are_bounded(shape):
    from koopman.command_batch_v41 import forecast_batch
    _, saved, x, predictor = setup()
    with pytest.raises(ValueError): forecast_batch(saved, x, np.zeros(shape), predictor)


@pytest.mark.parametrize('value', [np.nan, np.inf, .951])
def test_bad_command_in_one_branch_is_rejected_before_any_call(value):
    from koopman.command_batch_v41 import forecast_batch
    live, saved, x, predictor = setup()
    drive = np.zeros((2, 2, 4)); drive[1, 0, 0] = value
    calls = []
    def counted(*args): calls.append(1); return predictor(*args)
    with pytest.raises(ValueError): forecast_batch(saved, x, drive, counted)
    assert not calls and live.physics_index == 6


@pytest.mark.parametrize('deadline', [True, np.nan, np.inf, 'later'])
def test_bad_deadline_is_rejected(deadline):
    from koopman.command_batch_v41 import forecast_batch
    _, saved, x, predictor = setup()
    with pytest.raises(ValueError, match='deadline'):
        forecast_batch(saved, x, np.zeros((2, 2, 4)), predictor, deadline=deadline)


def test_expired_deadline_and_blocking_call_return_never_commit():
    from koopman.command_batch_v41 import forecast_batch
    live, saved, x, predictor = setup()
    with pytest.raises(TimeoutError):
        forecast_batch(saved, x, np.zeros((2, 2, 4)), predictor, deadline=time.monotonic()-1)
    def slow(states, u, c): time.sleep(.02); return states.copy()
    with pytest.raises(TimeoutError):
        forecast_batch(saved, x, np.zeros((2, 2, 4)), slow, deadline=time.monotonic()+.01)
    assert live.physics_index == 6


def test_predictor_call_count_scales_with_ticks_not_candidate_count():
    from koopman.command_batch_v41 import forecast_batch
    _, saved, x, predictor = setup()
    sizes = []
    def counted(states, u, c): sizes.append(len(states)); return predictor(states, u, c)
    results = forecast_batch(saved, x, np.zeros((8, 3, 4)), counted)
    assert all(result['complete'] for result in results)
    assert sizes == [8]*6


def test_only_a_causal_origin_is_accepted():
    from koopman.command_batch_v41 import forecast_batch
    live, _, x, predictor = setup()
    with pytest.raises(ValueError, match='origin'):
        forecast_batch(live, x, np.zeros((1, 1, 4)), predictor)

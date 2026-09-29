"""Command cache and long-horizon continuity contracts, without Isaac."""
from dataclasses import replace

import numpy as np
import pytest

from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS, SUPPORTED_EMBODIMENTS
from koopman.command_prediction_v37 import forecast_commands
from koopman.projected_edmd_v24 import PhysicalContext
from workflows.workpoint_v27 import mechanics


def context(name):
    m = mechanics(name)
    c = PhysicalContext(m['mass_kg'], m['inertia_kg_m2'], m['cob_m'], m['volume_m3'],
                        EMBODIMENT_CONFIGS[name]['drag_multiplier'])
    return replace(c, mass=float(np.float32(1)/np.float32(np.float32(1)/np.float32(c.mass))))


def initial():
    return np.array([5.5, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0.])


def accumulating_predictor(x, a, c):
    # Deliberately simple, state-dependent accumulator exposes any block reset.
    y = x.copy()
    y[:, 5:] += 1e-6*a
    y[:, 0] += 1e-3*y[:, 7]
    return y


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
def test_cache_exactly_matches_real_interface_and_actual_mass(name):
    from workflows.projected_prediction_v38 import replay_planned_inputs
    c = context(name)
    rng = np.random.default_rng(123)
    history = np.repeat(rng.uniform(-.2, .2, (5, 4)), 2, axis=0)
    commands = rng.uniform(-.2, .2, (4, 4))
    r = forecast_commands(initial(), history, commands, name, c, accumulating_predictor, origin_control=5)
    cached = replay_planned_inputs(history, commands, name, c, origin_control=5)
    for key in ('pwm', 'rotor_speed', 'acceleration', 'applied_control', 'physics_time_s',
                'issued_commands', 'origin_rotor_speed'):
        np.testing.assert_array_equal(r[key], cached[key])
    assert r['origin_actuator_time_s'] == cached['origin_actuator_time_s']


def test_full512_chunking_has_no_state_rotor_or_clock_reset():
    from workflows.projected_prediction_v38 import replay_planned_inputs, forecast_full_commands
    rng = np.random.default_rng(124)
    commands = rng.uniform(-.15, .15, (512, 4))
    history = np.repeat(rng.uniform(-.2, .2, (3, 4)), 2, axis=0)
    original_history, original_commands = history.copy(), commands.copy()
    c = context('uuv6')
    cache = replay_planned_inputs(history, commands, 'uuv6', c, origin_control=3)
    result = forecast_full_commands(initial(), history, commands, 'uuv6', c,
                                    accumulating_predictor, origin_control=3)
    assert result['complete'] and result['predictions'].shape == (1024, 11)
    assert result['block_origins'] == [3, 131, 259, 387]
    x, expected = initial(), []
    for a in cache['acceleration']:
        x = accumulating_predictor(x[None], a[None], c)[0]
        expected.append(x.copy())
    np.testing.assert_array_equal(expected, result['predictions'])
    for key in ('acceleration', 'rotor_speed', 'physics_time_s', 'issued_commands'):
        np.testing.assert_array_equal(cache[key], result[key])
    assert np.all(np.diff(result['physics_time_s']) > 0)
    np.testing.assert_array_equal(history, original_history)
    np.testing.assert_array_equal(commands, original_commands)


def test_partial_second_block_failure_has_global_index_and_no_complete_flag():
    from workflows.projected_prediction_v38 import forecast_full_commands
    seen = []
    def fail(x, a, c):
        seen.append(1)
        return x.copy() if len(seen) < 260 else np.full_like(x, np.nan)
    result = forecast_full_commands(initial(), np.zeros((0, 4)), np.zeros((140, 4)),
                                    'base', context('base'), fail, origin_control=0)
    assert not result['complete'] and len(result['predictions']) == 259
    assert result['failure']['control_index'] == 129
    assert result['failure']['completed_physics_ticks'] == 259


def test_cache_and_long_api_reject_incomplete_history_bad_commands_and_future_truth():
    from workflows.projected_prediction_v38 import replay_planned_inputs, forecast_full_commands
    for history, commands, origin in ((np.zeros((2, 4)), np.zeros((1, 4)), 0),
                                      (np.zeros((0, 4)), np.ones((1, 4)), 0),
                                      (np.zeros((0, 4)), np.zeros((513, 4)), 0)):
        with pytest.raises(ValueError):
            replay_planned_inputs(history, commands, 'base', context('base'), origin_control=origin)
        with pytest.raises(ValueError):
            forecast_full_commands(initial(), history, commands, 'base', context('base'),
                                   accumulating_predictor, origin_control=origin)
    with pytest.raises(TypeError):
        forecast_full_commands(initial(), np.zeros((0, 4)), np.zeros((1, 4)), 'base', context('base'),
                               accumulating_predictor, origin_control=0, future_truth=np.zeros((2, 11)))

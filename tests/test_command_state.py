"""Causal command histories and immutable prediction branches."""
import numpy as np
import pytest

from control_fixtures import context, model, state
from koopman.command_state import CausalCommandState
from koopman.physical_predictor import PhysicalPredictor


def test_forecast_branches_are_causal_and_do_not_advance_actual_history():
    c = context()
    live = CausalCommandState('base', c, episode_id='causal', zero_rotor_reset_verified=True)
    command = np.array([0., 0., 0., .05])
    for index in range(16):
        live.record_issued(command, physics_index=index, episode_id='causal')
    origin = live.snapshot(configuration='base', context=c, origin_control=8, episode_id='causal')
    predictor = PhysicalPredictor(model(), c, identified=True)
    controls = np.tile(command, (8, 1))
    first = origin.forecast(state()[0], controls, predictor)
    changed = controls.copy()
    changed[6:, 3] = .15
    second = origin.forecast(state()[0], changed, predictor)
    assert first['complete'] and second['complete']
    np.testing.assert_array_equal(first['predictions'][:12], second['predictions'][:12])
    assert np.max(abs(first['predictions'][12:] - second['predictions'][12:])) > 0
    np.testing.assert_array_equal(origin.forecast(state()[0], controls, predictor)['predictions'],
                                  first['predictions'])
    assert live.physics_index == 16


def test_history_rejects_unknown_reset_missing_steps_and_wrong_episode():
    c = context()
    with pytest.raises(ValueError):
        CausalCommandState('base', c, episode_id='causal', zero_rotor_reset_verified=False)
    live = CausalCommandState('base', c, episode_id='causal', zero_rotor_reset_verified=True)
    for index, episode in [(1, 'causal'), (0, 'other')]:
        with pytest.raises(ValueError):
            live.record_issued(np.zeros(4), physics_index=index, episode_id=episode)
    with pytest.raises(ValueError):
        live.snapshot(configuration='base', context=c, origin_control=1, episode_id='causal')
    assert live.physics_index == 0

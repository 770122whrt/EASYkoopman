"""Observable contracts for causal command state; no simulator evidence."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import time

import numpy as np
import pytest

from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS, SUPPORTED_EMBODIMENTS
from koopman.command_prediction_v37 import forecast_commands
from koopman.physical_prediction_v29 import known_step
from koopman.projected_edmd_v24 import PhysicalContext
from workflows.workpoint_v27 import mechanics


def context(name='base'):
    m = mechanics(name)
    return PhysicalContext(m['mass_kg'], m['inertia_kg_m2'], m['cob_m'],
                           m['volume_m3'], EMBODIMENT_CONFIGS[name]['drag_multiplier'])


def initial():
    return np.array([5.5, 1., 0., 0., 0., 0., 0., 0., 0., 0., 0.])


def physics(x, a, c):
    return known_step(x, a, c, angular_damping=float(np.float32(.05)), gyroscopic=True)


def new_state(name='base', c=None, episode='test-episode'):
    from koopman.command_state_v39 import CausalCommandState
    return CausalCommandState(name, c or context(name), episode_id=episode,
                             zero_rotor_reset_verified=True)


def snapshot(state, origin=0, name='base', c=None, episode='test-episode'):
    return state.snapshot(configuration=name, context=c or context(name),
                          origin_control=origin, episode_id=episode)


FIELDS = ('predictions', 'pwm', 'rotor_speed', 'acceleration', 'physics_time_s',
          'origin_rotor_speed', 'applied_control', 'issued_commands', 'control_mask')


def assert_same(a, b):
    assert a['complete'] == b['complete']
    assert a['failure'] == b['failure']
    assert a['completed_control_intervals'] == b['completed_control_intervals']
    assert a['origin_actuator_time_s'] == b['origin_actuator_time_s']
    for key in FIELDS:
        np.testing.assert_allclose(a[key], b[key], rtol=1e-12, atol=1e-12, err_msg=key)


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
@pytest.mark.parametrize('origin,horizon', [(0, 20), (3, 60), (17, 128)])
def test_cached_origin_matches_full_replay_all_configurations(name, origin, horizon):
    c = context(name)
    history = np.repeat(np.tile([.01, -.01, .015, .12], (origin, 1)), 2, axis=0)
    drive = np.tile([-.01, .02, -.025, .16], (horizon, 1))
    live = new_state(name, c)
    for i, command in enumerate(history):
        live.record_issued(command, physics_index=i, episode_id='test-episode')
    old = forecast_commands(initial(), history, drive, name, c, physics, origin_control=origin)
    cached = snapshot(live, origin, name, c)
    got = cached.forecast(initial(), drive, physics)
    assert_same(got, old)
    assert live.physics_index == 2*origin


def test_saved_origin_and_parallel_branches_do_not_share_live_or_candidate_memory():
    live = new_state(); command = np.array([.02, 0, .01, .2])
    for i in range(6):
        live.record_issued(command, physics_index=i, episode_id='test-episode')
    saved = snapshot(live, 3)
    a = np.tile(command, (3, 1)); b = -a
    first = saved.forecast(initial(), a, physics)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(saved.forecast, initial(), a, physics)
        two = pool.submit(saved.forecast, initial(), b, physics)
        assert_same(first, one.result()); assert two.result()['complete']
    for i in range(6, 8):
        live.record_issued(-command, physics_index=i, episode_id='test-episode')
    assert_same(first, saved.forecast(initial(), a, physics))
    first['origin_rotor_speed'][:] = 99
    first['rotor_speed'][:] = 99
    again = saved.forecast(initial(), a, physics)
    assert not np.any(again['origin_rotor_speed'] == 99)
    assert not np.any(again['rotor_speed'] == 99)
    assert live.physics_index == 8


@pytest.mark.parametrize('index', [-1, 1, True, 0.0])
def test_skip_reorder_and_nonstrict_indices_are_rejected_without_advancing(index):
    live = new_state()
    with pytest.raises(ValueError, match='issued_sequence'):
        live.record_issued(np.zeros(4), physics_index=index, episode_id='test-episode')
    assert live.physics_index == 0


def test_half_interval_changed_hold_duplicate_and_episode_mismatch_are_rejected():
    live = new_state(); zero = np.zeros(4)
    live.record_issued(zero, physics_index=0, episode_id='test-episode')
    with pytest.raises(ValueError, match='origin'):
        snapshot(live, 0)
    for index, episode, command in [(0, 'test-episode', zero), (1, 'other', zero),
                                    (1, 'test-episode', np.ones(4)*.1)]:
        with pytest.raises(ValueError):
            live.record_issued(command, physics_index=index, episode_id=episode)
        assert live.physics_index == 1
    live.record_issued(zero, physics_index=1, episode_id='test-episode')
    for kwargs in [dict(origin=0), dict(origin=1, episode='other'), dict(origin=True),
                   dict(origin=1, name='uuv6', c=context('uuv6'))]:
        with pytest.raises(ValueError): snapshot(live, **kwargs)


def test_unknown_reset_and_wrong_or_changed_actual_context_are_rejected():
    from koopman.command_state_v39 import CausalCommandState
    for known in [False, None, 1]:
        with pytest.raises(ValueError, match='zero_reset'):
            CausalCommandState('base', context(), episode_id='episode', zero_rotor_reset_verified=known)
    with pytest.raises(ValueError, match='context'):
        new_state('base', context('uuv6'))
    authored = context('uuv6'); actual = replace(authored, mass=29.69999885559082)
    live = new_state('uuv6', actual)
    with pytest.raises(ValueError, match='context'):
        snapshot(live, 0, 'uuv6', authored)
    observed = []
    def inspect(x, a, c):
        observed.append(c.mass); return physics(x, a, c)
    snapshot(live, 0, 'uuv6', actual).forecast(initial(), np.zeros((1, 4)), inspect)
    assert observed == [actual.mass, actual.mass]


def test_partial_failure_and_deadline_do_not_modify_saved_or_live_origin():
    live = new_state(); origin = snapshot(live)
    u = np.tile([0, 0, 0, .2], (3, 1)); before = origin.forecast(initial(), u, physics)
    calls = []
    def fail(x, a, c):
        calls.append(1)
        return physics(x, a, c) if len(calls) == 1 else np.full((1, 11), np.nan)
    bad = origin.forecast(initial(), u, fail)
    assert bad['complete'] is False and bad['failure']['completed_physics_ticks'] == 1
    with pytest.raises(TimeoutError): origin.forecast(initial(), u, physics, deadline=time.monotonic()-1)
    with pytest.raises(RuntimeError):
        origin.forecast(initial(), u, lambda *args: (_ for _ in ()).throw(RuntimeError('broken')))
    assert_same(before, origin.forecast(initial(), u, physics))
    assert live.physics_index == 0


@pytest.mark.parametrize('deadline', [float('nan'), float('inf'), True, 'later'])
def test_invalid_deadlines_are_not_silently_unbounded(deadline):
    with pytest.raises(ValueError, match='deadline'):
        snapshot(new_state()).forecast(initial(), np.zeros((1, 4)), physics, deadline=deadline)


def test_invalid_inputs_and_output_mutation_cannot_change_committed_state():
    live = new_state()
    for bad in [np.ones(4), np.full(4, np.nan), np.zeros(3)]:
        with pytest.raises(ValueError): live.record_issued(bad, physics_index=0, episode_id='test-episode')
    origin = snapshot(live)
    for bad in [np.ones((1, 4)), np.zeros((129, 4)), np.zeros((0, 4)), np.zeros((1, 6))]:
        with pytest.raises(ValueError): origin.forecast(initial(), bad, physics)
    with pytest.raises(ValueError): origin.forecast(np.zeros(11), np.zeros((1, 4)), physics)
    assert live.physics_index == 0


def test_masked_yaw_remains_unavailable_for_uuv4():
    r = snapshot(new_state('uuv4'), name='uuv4').forecast(initial(), np.array([[0, 0, .5, 0.]]), physics)
    assert r['control_mask'][2] == 0 and r['pwm'].shape == (2, 4)
    assert not r['pwm'].any() and not r['applied_control'].any()


def test_deadline_crossed_inside_predictor_is_reported_without_committing(monkeypatch):
    import koopman.command_state_v39 as module
    clock = [0.]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    live = new_state(); origin = snapshot(live)
    def slow(x, a, c):
        clock[0] = 2.
        return physics(x, a, c)
    with pytest.raises(TimeoutError):
        origin.forecast(initial(), np.zeros((1, 4)), slow, deadline=1.)
    assert live.physics_index == 0
    assert origin.forecast(initial(), np.zeros((1, 4)), physics)['complete']


def test_external_context_and_input_arrays_do_not_alias_origin():
    c = context(); live = new_state(c=c); origin = snapshot(live, c=c)
    x = initial(); u = np.array([[0., 0., 0., .2]])
    expected = origin.forecast(x, u, physics)
    c.inertia.setflags(write=True); c.inertia[:] = 100.
    r = origin.forecast(x, u, physics)
    r['requested_commands'][:] = 0.; r['predictions'][:] = 0.
    assert u[0, 3] == .2 and x[0] == 5.5
    assert_same(expected, origin.forecast(x, u, physics))

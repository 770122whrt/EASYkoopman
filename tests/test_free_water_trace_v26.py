"""CPU observer contracts; these tests do not emulate contact physics."""
from types import SimpleNamespace
import pytest
from test_free_water_v26 import sample


def session(monkeypatch, *, stop=True, force=0.):
    from workflows.free_water_trace_v26 import FreeWaterTraceSession
    from workflows import control_trace_v23
    row = sample(); env = SimpleNamespace(num_envs=1)
    monkeypatch.setattr(control_trace_v23, 'backend_readback', lambda _: row['backend_after_physics'])
    contact = lambda: {'normal_force_world_n': [[0., 0., force]],
                       'body_paths': ['/World/envs/env_0/Robot/body'], 'physics_dt_s': .01}
    s = FreeWaterTraceSession(env, contact_getter=contact, stop_on_rejection=stop,
                             state_getter=lambda _: [[0.]*11], max_substeps=4)
    s.pending = row; s.substeps.append(row)
    return s, row


def test_after_physics_capture_preserves_record_then_stops_on_contact(monkeypatch):
    s, row = session(monkeypatch, force=2.)
    with pytest.raises(ValueError, match='measured_normal_contact'):
        s._finish_physics()
    assert s.pending is None
    assert row['free_water_screen_v26']['direct_contact_observed'] is True
    assert row['contact_after_physics_v26']['normal_force_world_n'] == [[0., 0., 2.]]


def test_free_motion_passes_with_measured_contact_zero(monkeypatch):
    s, row = session(monkeypatch)
    s._finish_physics()
    assert row['free_water_screen_v26']['screen_pass']
    assert row['free_water_screen_v26']['direct_contact_observed'] is False
    s._finish_physics()  # No duplicate sample at an already finished boundary.


def test_diagnostic_mode_records_rejection_without_accepting_it(monkeypatch):
    s, row = session(monkeypatch, stop=False, force=2.)
    s._finish_physics()
    assert not row['free_water_screen_v26']['screen_pass']


@pytest.mark.parametrize('bad', [None, {'normal_force_world_n': [[0., 0., 0.]]},
                               {'normal_force_world_n': [[0., 0., float('nan')]], 'body_paths': ['/body'], 'physics_dt_s': .01},
                               {'normal_force_world_n': [[0., 0., 0.]], 'body_paths': ['/body'], 'physics_dt_s': .02},
                               {'normal_force_world_n': [], 'body_paths': [], 'physics_dt_s': .01}])
def test_missing_contact_contract_fails_even_in_diagnostic_mode(monkeypatch, bad):
    s, row = session(monkeypatch, stop=False)
    s.contact_getter = lambda: bad
    with pytest.raises(ValueError, match='free_water_contact_contract'):
        s._finish_physics()
    assert 'free_water_screen_v26' not in row


def test_contact_body_identity_cannot_change_between_steps(monkeypatch):
    s, row = session(monkeypatch)
    s._finish_physics()
    s.pending = sample()
    s.contact_getter = lambda: {'normal_force_world_n': [[0., 0., 0.]],
                              'body_paths': ['/different'], 'physics_dt_s': .01}
    with pytest.raises(ValueError, match='free_water_contact_contract'):
        s._finish_physics()

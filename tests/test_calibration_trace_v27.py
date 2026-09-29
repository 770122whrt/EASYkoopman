from copy import deepcopy
import numpy as np
import pytest
from test_validate_free_water_v26 import trace_row


def row_and_geometry():
    row, geom = trace_row()
    row['state_after_physics_11'] = [[3., 1., 0., 0., 0., 0., 0., 0., 0., 0., 0.]]
    return row, geom


def test_domain_rejects_motion_before_contact():
    from workflows.calibration_trace_v27 import domain_screen
    row, g = row_and_geometry()
    row['state_after_physics_11'][0][8] = 3.1
    assert 'angular_speed_limit' in domain_screen(row, g, 3.)['reasons']


def test_domain_retains_normal_contact_failure():
    from workflows.calibration_trace_v27 import domain_screen
    row, g = row_and_geometry()
    row['contact_after_physics_v26']['normal_force_world_n'][0][2] = 2
    assert 'measured_normal_contact' in domain_screen(row, g, 3.)['reasons']


def test_tilt_and_horizontal_excursion_are_checked_separately():
    from workflows.calibration_trace_v27 import domain_screen
    row, g = row_and_geometry()
    row['state_after_physics_11'][0][1:5] = [np.cos(np.pi/5), np.sin(np.pi/5), 0, 0]
    row['backend_after_physics']['transform_actor_world_xyzw'][0][0] = 2.1
    reasons = domain_screen(row, g, 3.)['reasons']
    assert 'tilt_limit' in reasons and 'horizontal_displacement_limit' in reasons


def test_tail_gate_does_not_hide_startup_or_call_a_drifting_body_settled():
    from workflows.calibration_trace_v27 import tail_gate
    rows = [{'state_after_physics_11': [[5.5, 1, 0, 0, 0, 0, 0, .6, 0, 0, 0]]}] * 256
    gate = tail_gate(rows)
    assert gate['eligible_for_excitation'] is False
    assert gate['tail_physics_ticks'] == 64


def test_failed_collector_cannot_be_semantically_accepted():
    from workflows.validate_calibration_v27 import validate_trace
    from workflows.workpoint_v27 import cases
    with pytest.raises(ValueError, match='calibration_trace_status'):
        validate_trace({'status': 'failed_calibration'}, cases()[0], 'a'*40, '.')


def test_tampered_inverse_cannot_be_accepted_by_a_true_flag():
    from workflows.workpoint_v27 import calibrate, validate_calibration
    c = deepcopy(calibrate('base'))
    c['trim']['command_4'][3] = .9
    with pytest.raises(ValueError, match='calibration_static'):
        validate_calibration(c)


def test_masked_pulse_cannot_be_replaced_by_a_feasible_different_command():
    from workflows.workpoint_v27 import calibrate, validate_calibration
    c = deepcopy(calibrate('uuv4'))
    c['pulses'][2]['plus'] = c['pulses'][3]['plus']
    with pytest.raises(ValueError, match='calibration_static'):
        validate_calibration(c)


def test_runtime_hook_retains_offending_row_before_stopping(monkeypatch):
    from types import SimpleNamespace
    from workflows.calibration_trace_v27 import CalibrationTraceSession
    from workflows.free_water_trace_v26 import FreeWaterTraceSession
    row, g = row_and_geometry()
    row['state_after_physics_11'][0][8] = 3.1
    def finish(s): s.pending = None
    monkeypatch.setattr(FreeWaterTraceSession, '_finish_physics', finish)
    s = CalibrationTraceSession(SimpleNamespace(num_envs=1), starting_z=3.,
                                contact_getter=lambda: {}, geometry=g)
    s.pending = row
    with pytest.raises(ValueError, match='calibration_motion_rejected:angular_speed_limit'):
        s._finish_physics()
    assert s.pending is None
    assert row['calibration_screen_v27']['screen_pass'] is False


def test_float32_cross_platform_summary_roundoff_does_not_change_physical_gate():
    from workflows.workpoint_v27 import calibrate, validate_calibration
    c = deepcopy(calibrate('uuv6_angled'))
    c['pulses'][3]['plus']['steady_wrench_6_n_nm'][2] += 5.7220458984375e-6
    c['pulses'][3]['plus']['acceleration_error_6'][3] += 4.271101840383152e-6
    validate_calibration(c)
    c['pulses'][3]['plus']['steady_wrench_6_n_nm'][2] += .001
    with pytest.raises(ValueError, match='calibration_static_reconstruction'):
        validate_calibration(c)

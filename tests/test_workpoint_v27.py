import numpy as np
import pytest


def test_heavy_balance_keeps_catalog_volume_and_requires_large_upward_thrust():
    from workflows.workpoint_v27 import mechanics, required_wrench
    m = mechanics('heavy_moderate')
    assert m['mass_kg'] == pytest.approx(45.402, abs=1e-5)
    assert m['volume_m3'] == pytest.approx(.022747843530591776)
    assert required_wrench(m)[2] == pytest.approx(222.907, abs=.002)


def test_asymmetric_restoring_moment_is_part_of_trim():
    from workflows.workpoint_v27 import mechanics, required_wrench
    wrench = required_wrench(mechanics('asymmetric'))
    assert wrench[3] < -11 and wrench[4] > 11
    assert wrench[5] == 0


@pytest.mark.parametrize('name', ['base', 'long_body', 'heavy_moderate', 'asymmetric',
                                  'uuv6', 'uuv6_angled', 'uuv4', 'uuv4_angled'])
def test_trim_respects_full_mechanics_and_does_not_hide_deadzone(name):
    from workflows.workpoint_v27 import calibrate
    c = calibrate(name)
    assert c['trim']['within_tolerance']
    assert c['all_static_targets_supported']
    assert max(abs(x) for x in c['trim']['acceleration_error_6']) <= .1
    assert max(abs(x) for x in c['trim']['pwm_raw']) < .95
    if name.startswith('uuv4'):
        assert c['trim']['command_4'][2] == 0
    if name == 'base':
        assert c['trim']['acceleration_error_6'][2] != 0
        assert c['trim']['exact_equilibrium'] is False


def test_underactuated_target_and_nonfinite_input_are_rejected():
    from workflows.workpoint_v27 import solve_control, mechanics, required_wrench
    target = required_wrench(mechanics('uuv4'))
    target[5] = 1
    with pytest.raises(ValueError, match='uncontrollable_yaw'):
        solve_control('uuv4', target)
    target[5] = float('nan')
    with pytest.raises(ValueError, match='target_invalid'):
        solve_control('uuv4', target)


def test_impossible_target_is_not_clipped_into_success():
    from workflows.workpoint_v27 import solve_control
    c = solve_control('base', [0, 0, 1e6, 0, 0, 0])
    assert c['within_tolerance'] is False
    assert np.max(np.abs(c['command_4'])) <= .95


def test_calibration_schedule_retains_cold_start_and_masked_block():
    from workflows.workpoint_v27 import calibrate, commands, cases
    q = next(q for q in cases() if q['configuration'] == 'uuv4' and q['stage'] == 'excitation')
    c = calibrate('uuv4')
    a = commands(q, c)
    assert a.shape == (256, 4) and a.dtype == np.float32
    np.testing.assert_array_equal(a[:64], np.tile(c['trim']['command_4'], (64, 1)).astype(np.float32))
    assert np.all(a[:, 2] == 0)
    np.testing.assert_array_equal(a[160:208], np.tile(a[0], (48, 1)))
    assert q['role'] == 'calibration' and q['training_eligible'] is False


def test_case_matrix_is_fixed_and_diagnostic_only():
    from workflows.workpoint_v27 import cases, validate_case
    qs = cases()
    assert len(qs) == 16
    assert sum(q['intervals'] for q in qs) == 3072
    assert len({q['run_id'] for q in qs}) == 16
    assert all(8510 <= q['seed'] <= 8527 and q['starting_z_m'] == 5.5 for q in qs)
    bad = dict(qs[0], role='fit')
    with pytest.raises(ValueError, match='calibration_fixed_case'):
        validate_case(bad)

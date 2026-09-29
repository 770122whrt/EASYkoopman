import numpy as np
import pytest
from workflows.workpoint_v27 import solve_control
from workflows.feedback_inverse_v28 import solve_feasible_control


def test_yaw_deadzone_does_not_block_feasible_heave_and_attitude_solution():
    target = [0., 0., 11.560423435057439, -11.133077136107255,
              11.158597420296164, .1451229721840924]
    assert not solve_control('asymmetric', target)['within_tolerance']
    record = solve_feasible_control('asymmetric', target)
    assert record['within_tolerance']
    assert np.max(np.abs(record['command_4'])) <= .95
    assert record['pwm_headroom'] >= .05


def test_valid_original_solution_is_preserved():
    target = [0., 0., .209927, -11.12434, 11.12434, 0.]
    assert solve_feasible_control('asymmetric', target) == solve_control('asymmetric', target)


def test_long_body_can_cross_adjacent_deadzone_branches_without_relaxing_gates():
    target = [0., 0., .20990960642441062, .27160353522248226,
              5.79396919655718e-6, -6.166629080819306e-7]
    assert not solve_control('long_body', target)['within_tolerance']
    assert solve_feasible_control('long_body', target)['within_tolerance']


def test_later_long_body_feedback_has_a_feasible_branch():
    target = [0., 0., .20956699451560531, .12138596271549773,
              .003369339404737406, -.001528594438284878]
    assert solve_feasible_control('long_body', target)['within_tolerance']


def test_inverse_keeps_pwm_away_from_numerically_ambiguous_deadzone_faces():
    target = [0., 0., -2.1879433124270893, .685475171269587,
              -2.802516291600732e-7, 4.898375701836236e-6]
    r = solve_feasible_control('uuv6_angled', target)
    assert r['within_tolerance']
    assert np.min(np.abs(np.abs(r['pwm_raw'])-float(np.float32(.02)))) > 2e-6


@pytest.mark.parametrize('name', ['base','long_body','heavy_moderate','asymmetric',
                                 'uuv6','uuv6_angled','uuv4','uuv4_angled'])
def test_batched_source_map_matches_scalar_source_at_deadzone_and_regular_inputs(name):
    from workflows.feedback_inverse_v28 import batch_source_map
    from workflows.workpoint_v27 import _steady
    from workflows.control_seam_v23 import ControlKernel
    k = ControlKernel(name)
    u = np.vstack((np.eye(4)*.02, -np.eye(4)*.02,
                   np.random.default_rng(45).uniform(-.15,.15,size=(7,4)))).astype(np.float32)
    wrench, raw = batch_source_map(k, u)
    for i, command in enumerate(u):
        expected, sent = _steady(k, command)
        np.testing.assert_allclose(raw[i], sent['pwm_raw'], rtol=0, atol=1e-6)
        np.testing.assert_allclose(wrench[i], expected, rtol=0, atol=1e-4)

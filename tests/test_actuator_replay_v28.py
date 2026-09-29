import numpy as np
import pytest
from workflows.control_seam_v23 import ControlKernel
from workflows.actuator_replay_v28 import Float32PWMActuatorState


@pytest.mark.parametrize('configuration', ['base', 'asymmetric', 'uuv4', 'uuv6'])
def test_float32_deadzone_neighbors_follow_actual_source(configuration):
    k = ControlKernel(configuration)
    estimator = Float32PWMActuatorState(k.env._num_thrusters, tau=k.tau, dt=k.dt,
                                        clock='float32_accumulated_v1')
    boundary = np.float32(.02)
    values = [np.nextafter(boundary, np.float32(0)), boundary,
              np.nextafter(boundary, np.float32(1)), 0., -.4, .4]
    for value in values + [-v for v in values]:
        pwm = np.full(k.env._num_thrusters, value, dtype=np.float32)
        for _ in range(8):
            expected = k.advance(pwm)['speed']
            actual = estimator.advance_pwm(pwm)
            np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-3)


def test_subthreshold_float64_text_representation_is_float32_boundary():
    k = ControlKernel('asymmetric')
    estimator = Float32PWMActuatorState(8, tau=k.tau, dt=k.dt)
    p = float(np.float32(.02))
    assert p < .02
    speed = estimator.advance_pwm(np.full(8, p))
    assert np.all(speed > 2)


def test_invalid_input_does_not_round_into_valid_range():
    s = Float32PWMActuatorState(4, tau=.05, dt=1/120)
    for value in (1+1e-9, float('nan'), float('inf')):
        with pytest.raises(ValueError): s.advance_pwm(np.full(4, value))

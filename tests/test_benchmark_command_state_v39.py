"""The interface assay must reject incorrect actuator fields and partial paths."""
from copy import deepcopy
import numpy as np
import pytest


def result():
    return dict(complete=True, failure=None, completed_control_intervals=1, origin_control=0,
        origin_actuator_time_s=0., origin_rotor_speed=np.zeros(4), requested_commands=np.zeros((1, 4)),
        issued_commands=np.zeros((1, 4)), control_mask=np.array([1, 1, 0, 1]),
        applied_control=np.zeros((2, 4)), predictions=np.zeros((2, 11)), pwm=np.zeros((2, 4)),
        rotor_speed=np.zeros((2, 4)), acceleration=np.zeros((2, 6)), physics_time_s=np.array([1/120, 1/60]))


@pytest.mark.parametrize('field', ['pwm', 'rotor_speed', 'acceleration', 'physics_time_s', 'control_mask'])
def test_equal_predictions_cannot_hide_actuation_or_clock_difference(field):
    from workflows.benchmark_command_state_v39 import compare_forecasts
    a = result(); b = deepcopy(a); b[field].flat[0] += 1
    with pytest.raises(ValueError, match='equivalence'):
        compare_forecasts(a, b)


def test_small_tolerance_is_allowed_but_partial_or_nonfinite_is_not():
    from workflows.benchmark_command_state_v39 import compare_forecasts
    a = result(); b = deepcopy(a); b['predictions'][0, 0] += 1e-13
    assert compare_forecasts(a, b)['predictions'] == 1e-13
    b['predictions'][0, 0] = np.nan
    with pytest.raises(ValueError): compare_forecasts(a, b)
    a['complete'] = False; b = deepcopy(a)
    with pytest.raises(ValueError, match='incomplete'): compare_forecasts(a, b)

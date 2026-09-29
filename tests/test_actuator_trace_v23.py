import importlib.util
import copy
import numpy as np


def test_estimate_uses_commands_not_recorded_actuator_truth():
    assert importlib.util.find_spec('workflows.actuator_trace_v23') is not None, 'actuator trace not implemented'
    from workflows.actuator_trace_v23 import annotate_estimates
    rows=[{'physics_dt_s':1/120,'command':{'telemetry':{'motor_pwm_n':[[.1]*4]},'actuator_speed_n':[[0.]*4]}}]
    alternate=copy.deepcopy(rows);alternate[0]['command']['actuator_speed_n']=[[999.]*4]
    first=annotate_estimates(rows,np.zeros(4),tau=.05)
    second=annotate_estimates(alternate,np.zeros(4),tau=.05)
    np.testing.assert_array_equal(first,second)
    assert rows[0]['causal_speed_estimate_n']==alternate[0]['causal_speed_estimate_n']
    assert rows[0]['estimated_minus_actual_speed_n']!=alternate[0]['estimated_minus_actual_speed_n']
    assert rows[0]['command']['actuator_speed_n']==[[0.]*4]

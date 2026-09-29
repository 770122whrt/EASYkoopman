import copy

import pytest

from workflows import validate_control_trace_v23 as validator


def row(token):
    state = [[1.5, 1., 0., 0., 0., 0., 0., 0., 0., 0., 0.]]
    snapshot = {'state_11': state, 'telemetry': {'step_token': [token],
        'virtual_control_4': [[.1, .1, 0., .1]], 'control_mask_4': [[1, 1, 0, 1]],
        'motor_pwm_n': [[.1] * 4], 'applied_wrench_6': [[0.] * 6]},
        'actuator_speed_n': [[1.] * 4], '_last_motor_values_raw': [[.1] * 4],
        '_thrust': [[[0.] * 3]], '_moment': [[[0.] * 3]]}
    before = copy.deepcopy(snapshot)
    before['telemetry']['step_token'] = [token - 1]
    return {'control_index': 0, 'substep_index': token - 1, 'physics_dt_s': 1/120,
            'reset_generation': [1], 'before': before, 'command': snapshot,
            'state_after_physics_11': state,
            'actuator_update': {'speed_command_n': [[2.] * 4], 'end_time_s': [token/120]}}


def test_valid_two_substeps_are_accepted():
    validator.validate_interval([row(1), row(2)], configuration='uuv4')


def test_actual_float32_clock_crossing_two_seconds_is_not_a_missing_tick():
    # Exact values from the stopped freshpilot, with correct consecutive tokens.
    rows=[row(1),row(2)]
    rows[0]['actuator_update']['end_time_s']=[2.008331775665283]
    rows[1]['actuator_update']['end_time_s']=[2.01666522026062]
    validator.validate_interval(rows,configuration='uuv4')


@pytest.mark.parametrize('offset',[0,2/120,3/120,.001])
def test_float32_clock_rule_still_rejects_duplicate_missing_or_corrupt_tick(offset):
    import numpy as np
    rows=[row(1),row(2)];before=np.float32(2.008331775665283)
    rows[0]['actuator_update']['end_time_s']=[float(before)]
    rows[1]['actuator_update']['end_time_s']=[float(np.float32(before+np.float32(offset)))]
    with pytest.raises(ValueError,match='trace_actuator_time_seam'):
        validator.validate_interval(rows,configuration='uuv4')


@pytest.mark.parametrize('damage', ['masked_input', 'nonfinite_first', 'token', 'missing_step'])
def test_first_substep_or_timing_fault_is_not_hidden_by_last_snapshot(damage):
    rows = [row(1), row(2)]
    if damage == 'masked_input':
        rows[0]['command']['telemetry']['virtual_control_4'][0][2] = .2
    elif damage == 'nonfinite_first':
        rows[0]['actuator_update']['speed_command_n'][0][0] = float('nan')
    elif damage == 'token':
        rows[0]['command']['telemetry']['step_token'][0] = 5
    else:
        rows.pop()
    with pytest.raises(ValueError):
        validator.validate_interval(rows, configuration='uuv4')


def test_pair_comparison_checks_each_component_and_rejects_changed_state():
    diff = validator.compare_values({'state': [[1., 2.]]}, {'state': [[1., 2.0000001]]})
    assert diff['state/0/1'] < 1e-6
    with pytest.raises(ValueError, match='trace_pair_mismatch'):
        validator.compare_values({'state': [[1., 2.]]}, {'state': [[1., 2.01]]})


def pair():
    rows = []
    for i in range(32):
        for j in range(2):
            item = row(i * 2 + j + 1)
            item['control_index'] = i
            item['substep_index'] = j
            rows.append(item)
    on = {'status': 'completed_exploratory_trace', 'source_commit': 'a' * 40,
          'loaded_sources': {c: {'sha256': 'b' * 64} for c in ('EasyUUVEnv', 'DirectRLEnv')},
          'effective_cfg': {'decimation': 2}, 'topology': {'mask': [1, 1, 0, 1]},
          'mechanical_after_configuration': {'declared_mass': [[2.]], 'physx_mass': [[2.]],
              'declared_inertia': [[1.,1.,1.]], 'physx_inertia': [[[1.,0.,0.,0.,1.,0.,0.,0.,1.]]]},
          'mechanical_after_observed_reset': {'declared_mass': [[2.]], 'physx_mass': [[2.]],
              'declared_inertia': [[1.,1.,1.]], 'physx_inertia': [[[1.,0.,0.,0.,1.,0.,0.,0.,1.]]]},
          'request': {'trace': 'on', 'configuration': 'uuv4', 'observed_intervals': 32,
                      'preparation_intervals': 0}, 'substeps': rows,
          'initial_boundary': rows[0]['before'], 'observed_start_boundary': rows[0]['before'],
          'boundary_states': [{'state_11': r['state_after_physics_11']} for r in rows[1::2]]}
    off = copy.deepcopy(on)
    off['request']['trace'] = 'off'
    off['substeps'] = []
    return on, off


def test_full_pair_accepts_matched_inventory():
    result = validator.validate_pair(*pair())
    assert result['status'] == 'local_pair_checks_pass'


@pytest.mark.parametrize('damage',['missing','changed'])
def test_pair_requires_actual_mechanical_readback_and_matching_runtime(damage):
    on,off=pair()
    if damage=='missing':
        del on['mechanical_after_configuration']
    else:
        off['mechanical_after_observed_reset']['physx_inertia'][0][0][0]=9.
    with pytest.raises(ValueError):
        validator.validate_pair(on,off)


def test_full_pair_rejects_changed_initial_physical_state():
    on, off = pair()
    off['initial_boundary']['state_11'][0][0] += .1
    with pytest.raises(ValueError, match='trace_pair_mismatch'):
        validator.validate_pair(on, off)


def test_pair_rejects_unrecorded_state_jump_between_control_intervals():
    on, off = pair()
    on['substeps'][2]['before']['state_11'][0][5] = .5
    with pytest.raises(ValueError, match='trace_pair_mismatch'):
        validator.validate_pair(on, off)


def test_pair_cannot_agree_on_boundary_values_that_disagree_with_substeps():
    on, off = pair()
    on['boundary_states'] = copy.deepcopy(on['boundary_states'])
    off['boundary_states'] = copy.deepcopy(off['boundary_states'])
    on['boundary_states'][1]['state_11'][0][5] = .5
    off['boundary_states'][1]['state_11'][0][5] = .5
    with pytest.raises(ValueError, match='trace_pair_mismatch'):
        validator.validate_pair(on, off)


def test_pair_rejects_reset_generation_jump_inside_cold_episode():
    on, off = pair()
    on['substeps'][2]['reset_generation'] = [2]
    on['substeps'][3]['reset_generation'] = [2]
    with pytest.raises(ValueError, match='trace_unexpected_reset_generation'):
        validator.validate_pair(on, off)

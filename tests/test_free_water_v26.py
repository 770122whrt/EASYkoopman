"""Screening must reject impulses and unsafe altitude without diagnosing contact."""
from copy import deepcopy
import numpy as np
import pytest


def sample():
    # A 90-degree yaw maps body +x force into world +y.
    q = [0., 0., np.sqrt(.5), np.sqrt(.5)]
    before = {'transform_actor_world_xyzw': [[0., 0., 3., *q]],
              'velocity_com_world_6': [[1., 2., 3., 0., 0., 0.]],
              'mass_kg': [[2.]], 'gravity_disabled': [[0]],
              'gravity_world_m_s2': [0., 0., -9.81]}
    after = deepcopy(before)
    after['velocity_com_world_6'][0][:3] = [1., 2.01, 2.9019]
    command = deepcopy(before)
    command.update(_external_force_b=[[[2., 0., 0.]]],
                   _use_global_wrench_frame=False, has_external_wrench=True,
                   uses_external_wrench_positions=False)
    return {'before': {'backend': before}, 'command': {'backend': command},
            'backend_after_physics': after, 'physics_dt_s': .01}


def test_body_force_world_velocity_and_gravity_balance():
    from workflows.free_water_v26 import require_admissible_step
    result = require_admissible_step(sample())
    assert result['screen_pass']
    assert result['max_abs_velocity_residual_m_s'] < 1e-14
    assert result['direct_contact_observed'] is None


def test_large_unexplained_impulse_cannot_be_accepted_at_high_altitude():
    from workflows.free_water_v26 import screen_step, require_admissible_step
    row = sample()
    row['backend_after_physics']['velocity_com_world_6'][0][2] += .5
    result = screen_step(row)
    assert result['reasons'] == ['unexplained_linear_impulse']
    assert result['estimated_unexplained_impulse_norm_n_s'] == pytest.approx(1.)
    with pytest.raises(ValueError, match='unexplained_linear_impulse'):
        require_admissible_step(row)


def test_low_altitude_rejected_even_without_an_impulse():
    from workflows.free_water_v26 import screen_step
    row = sample()
    row['backend_after_physics']['transform_actor_world_xyzw'][0][2] = .9
    assert screen_step(row)['reasons'] == ['actor_altitude_below_operating_floor']


@pytest.mark.parametrize('mutation', ['nan', 'missing_force', 'zero_mass', 'changed_mass',
                                     'global_frame', 'disabled_gravity', 'bad_quaternion',
                                     'inactive_nonzero_force', 'bad_dt', 'multi_env'])
def test_incomplete_or_unsupported_contract_fails_closed(mutation):
    from workflows.free_water_v26 import screen_step
    row = sample()
    b = row['before']['backend']; c = row['command']['backend']
    if mutation == 'nan': b['velocity_com_world_6'][0][0] = float('nan')
    elif mutation == 'missing_force': del c['_external_force_b']
    elif mutation == 'zero_mass': b['mass_kg'] = [[0.]]
    elif mutation == 'changed_mass': row['backend_after_physics']['mass_kg'] = [[3.]]
    elif mutation == 'global_frame': c['_use_global_wrench_frame'] = True
    elif mutation == 'disabled_gravity': b['gravity_disabled'] = [[1]]
    elif mutation == 'bad_quaternion': b['transform_actor_world_xyzw'][0][3:] = [0.]*4
    elif mutation == 'inactive_nonzero_force': c['has_external_wrench'] = False
    elif mutation == 'bad_dt': row['physics_dt_s'] = 0.
    elif mutation == 'multi_env': b['velocity_com_world_6'] *= 2
    with pytest.raises(ValueError, match='free_water_contract'):
        screen_step(row)


@pytest.mark.parametrize('kwargs', [{'residual_limit_m_s': 0.},
                                   {'minimum_actor_z_m': float('nan')}])
def test_invalid_thresholds_rejected(kwargs):
    from workflows.free_water_v26 import screen_step
    with pytest.raises(ValueError, match='free_water_contract'):
        screen_step(sample(), **kwargs)


def test_zero_force_is_valid_when_backend_wrench_is_inactive():
    from workflows.free_water_v26 import screen_step
    row = sample()
    row['command']['backend'].update(_external_force_b=[[[0., 0., 0.]]], has_external_wrench=False)
    row['backend_after_physics']['velocity_com_world_6'][0][1] = 2.
    assert screen_step(row)['screen_pass']

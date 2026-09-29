"""Independent substep, actuator-clock and physical-backend checks."""
import numpy as np
from easyuuv_nc.embodiments import qualification_record

def _array(value, shape, label):
    array = np.asarray(value, dtype=float)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(f'trace_shape_or_nonfinite:{label}')
    return array


def validate_clock_step(before, after):
    """Validate an exact tick or its actual float32 accumulated-clock rounding.

    Past two seconds, one float32 ULP can exceed the old1e-7 absolute
    threshold. Accept only the precisely rounded next tick, not a wider
    generic tolerance that could hide a missing/duplicated update.
    """
    before, after = np.asarray(before, dtype=float), np.asarray(after, dtype=float)
    dt = 1 / 120
    if before.shape != after.shape or not np.isfinite(before).all() or not np.isfinite(after).all():
        raise ValueError('trace_actuator_time_seam')
    if np.allclose(after - before, dt, rtol=0, atol=1e-7):
        return
    a, b = before.astype(np.float32), after.astype(np.float32)
    if (not np.array_equal(a.astype(float), before) or not np.array_equal(b.astype(float), after)
            or np.any(after <= before) or np.any(np.spacing(np.maximum(np.abs(a), np.abs(b))) >= dt / 16)
            or not np.array_equal((a + np.float32(dt)).astype(float), after)):
        raise ValueError('trace_actuator_time_seam')


def compare_values(left, right, *, atol=1e-6, path=''):
    """Absolute differences per component, never a norm across physical units."""
    result = {}
    if isinstance(left, dict):
        if not isinstance(right, dict) or left.keys() != right.keys():
            raise ValueError(f'trace_pair_schema:{path}')
        for key in left:
            result.update(compare_values(left[key], right[key], atol=atol, path=f'{path}/{key}'.strip('/')))
    elif isinstance(left, list):
        if not isinstance(right, list) or len(left) != len(right):
            raise ValueError(f'trace_pair_schema:{path}')
        for i, (a, b) in enumerate(zip(left, right)):
            result.update(compare_values(a, b, atol=atol, path=f'{path}/{i}'.strip('/')))
    elif isinstance(left, (float, int)) and not isinstance(left, bool):
        if not isinstance(right, (float, int)) or not np.isfinite([left, right]).all():
            raise ValueError(f'trace_pair_nonfinite:{path}')
        difference = abs(left - right)
        if difference > atol:
            raise ValueError(f'trace_pair_mismatch:{path}:{difference}')
        result[path] = difference
    elif left != right:
        raise ValueError(f'trace_pair_mismatch:{path}')
    return result

def validate_two_substeps(rows, *, configuration):
    count = {'base': 8, 'uuv6': 6, 'uuv4': 4}[configuration]
    if len(rows) != 2:
        raise ValueError('trace_call_count_mismatch')
    for index, row in enumerate(rows):
        if row['substep_index'] != index or row['physics_dt_s'] != 1/120:
            raise ValueError('trace_timing_mismatch')
        command = row['command']
        telemetry = command['telemetry']
        token = _array(telemetry['step_token'], (1,), 'token')
        previous = _array(row['before']['telemetry']['step_token'], (1,), 'previous_token')
        if not np.array_equal(token, previous + 1):
            raise ValueError('trace_token_mismatch')
        control = _array(telemetry['virtual_control_4'], (1, 4), 'control')
        mask = _array(telemetry['control_mask_4'], (1, 4), 'mask')
        expected_mask = [[1, 1, 0 if configuration == 'uuv4' else 1, 1]]
        if not np.array_equal(mask, expected_mask) or np.any(np.abs(control) > 1 + 1e-6):
            raise ValueError('trace_control_bound_or_mask')
        if np.any(np.abs(control * (1-mask)) > 1e-6):
            raise ValueError('trace_masked_input')
        pwm = _array(telemetry['motor_pwm_n'], (1, count), 'pwm')
        raw = _array(command['_last_motor_values_raw'], (1, count), 'raw_pwm')
        if np.any(np.abs(pwm) > 1) or not np.allclose(pwm, np.clip(raw, -1, 1), rtol=0, atol=1e-6):
            raise ValueError('trace_pwm_clip_mismatch')
        for field, shape in (('actuator_speed_n', (1, count)), ('_thrust', (1, 1, 3)),
                             ('_moment', (1, 1, 3))):
            _array(command[field], shape, field)
        _array(telemetry['applied_wrench_6'], (1, 6), 'thruster_wrench')
        _array(row['actuator_update']['speed_command_n'], (1, count), 'speed_command')
        _array(row['actuator_update']['end_time_s'], (1,), 'actuator_time')
        for state in (row['before']['state_11'], row['state_after_physics_11']):
            x = _array(state, (1, 11), 'state')
            if abs(x[0, 0]) > 100 or np.any(np.abs(x[0, 5:]) > 100):
                raise ValueError('trace_state_bound')
            if abs(np.linalg.norm(x[0, 1:5]) - 1) > 1e-3:
                raise ValueError('trace_quaternion_invalid')
    if (rows[0]['reset_generation'] != rows[1]['reset_generation'] or
            rows[0]['control_index'] != rows[1]['control_index']):
        raise ValueError('trace_reset_or_interval_seam')
    compare_values(rows[0]['state_after_physics_11'], rows[1]['before']['state_11'])
    if rows[0]['command']['telemetry']['step_token'] != rows[1]['before']['telemetry']['step_token']:
        raise ValueError('trace_token_seam')
    times = [np.asarray(row['actuator_update']['end_time_s']) for row in rows]
    validate_clock_step(times[0], times[1])

def validate_micro_interval(rows,*,configuration):
    original=validate_two_substeps
    record=qualification_record(configuration)
    if not record['public']:raise ValueError('formal_configuration_not_public')
    for row in rows:
        if row['before']['telemetry']['configuration']!=configuration or row['command']['telemetry']['configuration']!=configuration:
            raise ValueError('formal_trace_configuration_mismatch')
    equivalent={8:'base',6:'uuv6',4:'uuv4'}[record['thruster_count']]
    original(rows,configuration=equivalent)

def same(a,b,*,atol=1e-6,label='values'):
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
    if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all() or not np.allclose(a,b,rtol=0,atol=atol):
        raise ValueError('runtime_validation_'+label)


def validate_interval(rows,*,configuration):
    if len(rows)!=4 or [r['substep_index'] for r in rows]!=[0,1,2,3]:raise ValueError('rate30_four_substeps')
    for offset in (0,2):
        validate_micro_interval([dict(row,substep_index=j) for j,row in enumerate(rows[offset:offset+2])],configuration=configuration)
    for row in rows[1:]:
        same(row['command']['telemetry']['virtual_control_4'],rows[0]['command']['telemetry']['virtual_control_4'],atol=1e-7,label='rate30_hold')


def check_state_backend(state,backend):
    from koopman.physics_context import rotation
    x=np.asarray(state,dtype=float)[0];pose=np.asarray(backend['transform_actor_world_xyzw'],dtype=float)
    velocity=np.asarray(backend['velocity_com_world_6'],dtype=float)
    if pose.shape!=(1,7) or velocity.shape!=(1,6):raise ValueError('runtime_backend_shape')
    same(x[0],pose[0,2],label='backend_depth')
    q=pose[0,[6,3,4,5]]
    if np.dot(x[1:5],q)<0:q=-q
    same(x[1:5],q,label='backend_attitude')
    r=rotation(x[1:5])
    same(x[5:8],r.T@velocity[0,:3],label='backend_body_velocity')
    same(x[8:],r.T@velocity[0,3:],label='backend_body_omega')

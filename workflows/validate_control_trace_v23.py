"""Local, fail-closed acceptance of a completed exploratory trace pair."""

import argparse
import json
from pathlib import Path

import numpy as np


def _array(value, shape, label):
    array = np.asarray(value, dtype=float)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(f'trace_shape_or_nonfinite:{label}')
    return array


def validate_interval(rows, *, configuration):
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


def validate_pair(on, off):
    if any(r['status'] != 'completed_exploratory_trace' for r in (on, off)):
        raise ValueError('trace_pair_not_completed')
    if on['request']['trace'] != 'on' or off['request']['trace'] != 'off':
        raise ValueError('trace_pair_mode')
    def common(spec):
        return {k: v for k, v in spec.items() if k not in {'run_id', 'trace', 'output_relative'}}
    compare_values(common(on['request']), common(off['request']), atol=0)
    if on['source_commit'] != off['source_commit']:
        raise ValueError('trace_pair_source_mismatch')
    for cls in ('EasyUUVEnv', 'DirectRLEnv'):
        if on['loaded_sources'][cls]['sha256'] != off['loaded_sources'][cls]['sha256']:
            raise ValueError('trace_pair_source_mismatch')
    compare_values(on['effective_cfg'], off['effective_cfg'], atol=0)
    compare_values(on['topology'], off['topology'])
    for field in ('mechanical_after_configuration', 'mechanical_after_observed_reset'):
        required = {'declared_mass', 'declared_inertia', 'physx_mass', 'physx_inertia'}
        if any(not isinstance(item.get(field), dict) or not required.issubset(item[field])
               for item in (on, off)):
            raise ValueError('trace_mechanical_readback_missing')
        compare_values(on[field], off[field])
    count = on['request']['observed_intervals'] + on['request']['preparation_intervals']
    if on['request']['observed_intervals'] != 32 or on['request']['preparation_intervals'] not in (0, 32):
        raise ValueError('trace_pair_budget_contract')
    if len(on['substeps']) != 2 * count or off['substeps']:
        raise ValueError('trace_pair_inventory')
    if len(on['boundary_states']) != count or len(off['boundary_states']) != count:
        raise ValueError('trace_pair_boundary_inventory')
    preparation = on['request']['preparation_intervals']
    for index in range(count):
        rows = on['substeps'][2*index:2*index+2]
        if any(row['control_index'] != index for row in rows):
            raise ValueError('trace_pair_interval_inventory')
        validate_interval(rows, configuration=on['request']['configuration'])
        generation = 2 if preparation and index >= preparation else 1
        if any(row['reset_generation'] != [generation] for row in rows):
            raise ValueError('trace_unexpected_reset_generation')
        compare_values(rows[-1]['state_after_physics_11'], on['boundary_states'][index]['state_11'])
        if index == 0 or (preparation and index == preparation):
            boundary = 'initial_boundary' if index == 0 else 'observed_start_boundary'
            compare_values(on[boundary]['state_11'], rows[0]['before']['state_11'])
        else:
            previous = on['substeps'][2 * index - 1]
            compare_values(previous['state_after_physics_11'], rows[0]['before']['state_11'])
            compare_values(previous['command']['actuator_speed_n'], rows[0]['before']['actuator_speed_n'])
            compare_values(previous['command']['telemetry']['step_token'], rows[0]['before']['telemetry']['step_token'], atol=0)
            before_time = np.asarray(previous['actuator_update']['end_time_s'])
            after_time = np.asarray(rows[0]['actuator_update']['end_time_s'])
            validate_clock_step(before_time, after_time)
    differences = {}
    for field in ('initial_boundary', 'observed_start_boundary', 'boundary_states'):
        if field == 'boundary_states' and (len(on[field]) != count or len(off[field]) != count):
            raise ValueError('trace_pair_boundary_inventory')
        differences.update(compare_values(on[field], off[field], path=field))
    return {'status': 'local_pair_checks_pass', 'atol_per_component': 1e-6,
            'compared_numeric_components': len(differences),
            'largest_component_differences': sorted(differences.items(), key=lambda item: item[1], reverse=True)[:12],
            'limitation': 'Pair equality does not certify server provenance or model benefit.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace-on', required=True, type=Path)
    parser.add_argument('--trace-off', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = validate_pair(json.loads(args.trace_on.read_text(encoding='utf-8')),
                               json.loads(args.trace_off.read_text(encoding='utf-8')))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'status': 'failed', 'reason': str(exc)}))
        raise SystemExit(1)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

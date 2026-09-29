"""Command-only input caching and continuous long-horizon v37 composition."""
import time

import numpy as np

from koopman.command_prediction_v37 import forecast_commands, validate_context
from workflows.actuator_replay_v28 import Float32PWMActuatorState
from workflows.control_seam_v23 import ControlKernel
from workflows.identification_prediction_v32 import valid_predictions


def _inputs(history, commands, origin_control):
    past = np.array(history, dtype=float, copy=True)
    drive = np.array(commands, dtype=float, copy=True)
    if (type(origin_control) is not int or origin_control < 0 or past.shape != (2*origin_control, 4)
            or not np.isfinite(past).all() or np.any(np.abs(past) > .95)):
        raise ValueError('formal_command_history')
    if (drive.ndim != 2 or drive.shape[1] != 4 or not 1 <= len(drive) <= 512
            or not np.isfinite(drive).all() or np.any(np.abs(drive) > .95)):
        raise ValueError('formal_planned_commands')
    return past, drive


def _check_time(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError('formal_prediction_budget')


def replay_planned_inputs(issued_control_history, planned_commands, configuration, context, *, origin_control, deadline=None):
    """Independent input sequence for a specified command plan, not a policy forecast.

    No future states, measured rotors or wrenches are accepted. Numerical equality
    with v37 is tested separately, including actual mass and masked topologies.
    """
    history, drive = _inputs(issued_control_history, planned_commands, origin_control)
    validate_context(configuration, context)
    kernel = ControlKernel(configuration)
    rotor = Float32PWMActuatorState(kernel.env._num_thrusters, tau=kernel.tau, dt=1/120,
                                    clock='float32_accumulated_v1')
    for command in history:
        _check_time(deadline)
        rotor.advance_pwm(kernel.command(command, pre_tam=True)['pwm'])
    origin_speed, origin_time = rotor.current(), rotor.elapsed_time
    scale = np.r_[[context.mass]*3, context.inertia]
    fields = {k: [] for k in ('pwm', 'rotor_speed', 'acceleration', 'applied_control', 'physics_time_s')}
    issued = drive.astype(np.float32)
    for command in issued:
        _check_time(deadline)
        allocation = kernel.command(command, pre_tam=True)
        for _ in range(2):
            _check_time(deadline)
            speed = rotor.advance_pwm(allocation['pwm'])
            wrench = kernel.B.numpy() @ (kernel.env.cfg.rotor_constant*np.abs(speed)*speed)
            fields['pwm'].append(allocation['pwm'].copy())
            fields['rotor_speed'].append(speed.copy())
            fields['acceleration'].append(wrench/scale)
            fields['applied_control'].append(allocation['virtual_control'].copy())
            fields['physics_time_s'].append(rotor.elapsed_time)
    return {k: np.asarray(v) for k, v in fields.items()} | dict(issued_commands=issued,
        origin_rotor_speed=origin_speed, origin_actuator_time_s=origin_time,
        future_inputs='specified_commands_and_own_rotor_recurrence', model_handoff=False)


def forecast_full_commands(initial_state, issued_control_history, planned_commands, configuration, context,
                           predictor, *, origin_control, deadline=None):
    """Up to512 commands in128-command calls, with own state and full history carried.

    Each block replays the entire command history from the same known-zero reset.
    This avoids a hidden float32 clock/rotor reset; no truth exists in this API.
    """
    history, drive = _inputs(issued_control_history, planned_commands, origin_control)
    x = np.array(initial_state, dtype=float, copy=True)
    if x.shape != (11,) or not valid_predictions(x[None])[0] or not callable(predictor):
        raise ValueError('formal_prediction_state')
    fields = {k: [] for k in ('predictions', 'pwm', 'rotor_speed', 'acceleration', 'applied_control',
                              'physics_time_s', 'issued_commands')}
    block_origins, failure = [], None
    for offset in range(0, len(drive), 128):
        _check_time(deadline)
        block_origins.append(origin_control+offset)
        block = forecast_commands(x, history, drive[offset:offset+128], configuration, context, predictor,
                                  origin_control=origin_control+offset, deadline=deadline)
        for key in fields:
            fields[key].append(block[key])
        if not block['complete']:
            failure = dict(block['failure'])
            failure['control_index'] += offset
            failure['completed_physics_ticks'] += 2*offset
            break
        x = block['predictions'][-1].copy()
        history = np.concatenate((history, np.repeat(block['issued_commands'], 2, axis=0)))
    result = {k: np.concatenate(v) for k, v in fields.items()}
    return result | dict(complete=failure is None, failure=failure, block_origins=block_origins,
        completed_control_intervals=len(result['predictions'])//2,
        future_inputs='planned_commands_and_own_rotor_recurrence', model_handoff=False)

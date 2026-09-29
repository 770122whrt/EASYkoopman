"""Prepared CPU rollout of the same v43 model with optional exact common prefix.

Only the known stateless compiled predictor uses this path. Other predictors or
numerical failures retain v45's scalar branch isolation. Fixed four-control
chunks return to Python deadline checks; process isolation remains required.
No candidate, model, objective, actuator clock or output field is removed.
"""
import math

import numpy as np
from numba import njit

from koopman.command_batch_v45 import forecast_prepared as reference_forecast
from koopman.command_state_v39 import _PredictionOrigin
from koopman.compiled_projected_v43 import _CompiledProjected, _step
from koopman.prepared_commands_v45 import PreparedCommands, validate_deadline, check_deadline
from koopman.prepared_projected_v40 import _context_key
from workflows.actuator_replay_v28 import Float32PWMActuatorState
from workflows.identification_prediction_v32 import valid_predictions


@njit(fastmath=False, nogil=True)
def _chunk(x, speed, clock, pwm, tau, dt, alpha_fixed, float_clock, wrench, scale,
           rotor, nonlinear, matrix, damping, inertia, cob, drag, buoyancy, net, linear, quadratic):
    count, controls, n = pwm.shape
    states = np.empty((count, 2*controls, 11))
    speeds = np.empty((count, 2*controls, n))
    inputs = np.empty((count, 2*controls, 6))
    times = np.empty(2*controls)
    threshold = np.float64(np.float32(.02))
    for control in range(controls):
        target = np.zeros((count, n))
        for i in range(count):
            for j in range(n):
                u = np.float64(pwm[i, control, j])
                if u >= threshold:
                    target[i, j] = -139*u**2 + 500*u + 8.28
                elif u <= -threshold:
                    target[i, j] = 161*u**2 + 517.86*u - 5.72
        for substep in range(2):
            if float_clock:
                next_clock = np.float64(np.float32(np.float32(clock) + np.float32(dt)))
                alpha = math.exp(-(next_clock-clock)/tau)
                clock = next_clock
            else:
                alpha = alpha_fixed
                clock += dt
            speed = alpha*speed + (1-alpha)*target
            force = rotor*np.abs(speed)*speed
            acceleration = np.empty((count, 6))
            for i in range(count):
                for axis in range(6):
                    total = 0.
                    for j in range(n):
                        total += wrench[axis, j]*force[i, j]
                    acceleration[i, axis] = total/scale[axis]
            x = _step(x, acceleration, nonlinear, matrix, damping, inertia, cob, drag,
                      buoyancy, net, linear, quadratic)
            for i in range(count):
                if (not np.isfinite(x[i]).all() or abs(x[i, 0]) > 100
                        or np.any(np.abs(x[i, 5:]) > 100)
                        or abs(math.sqrt(np.sum(x[i, 1:5]**2))-1) > 1e-3):
                    raise ValueError('compiled_prediction_invalid')
            tick = 2*control+substep
            states[:, tick] = x
            speeds[:, tick] = speed
            inputs[:, tick] = acceleration
            times[tick] = clock
    return states, speeds, inputs, times, x, speed, clock


def _parameters(predictor):
    b = predictor._base
    return (b._family == 'nonlinear', b._matrix, b._angular_damping, b._inertia,
            b._cob, float(b._drag), float(b._buoyancy_force),
            float(b._net_buoyancy_acceleration), b._linear, b._quadratic)


def warm_forecast(predictor):
    """Compile the owned-array signature outside request/actuator execution."""
    if type(predictor) is not _CompiledProjected:
        return
    x = np.zeros((1, 11)); x[:, 1] = 1.; x[:, 0] = 5.5
    _chunk(x, np.zeros((1, 1)), 0., np.zeros((1, 1, 1), dtype=np.float32),
           .1, 1/120, math.exp(-(1/120)/.1), True, np.zeros((6, 1)),
           np.ones(6), 1., *_parameters(predictor))


def forecast_compiled(origin, initial_state, prepared_commands, predictor, *,
                      indices=None, deadline=None, share_prefix=False):
    fallback = lambda: reference_forecast(origin, initial_state, prepared_commands, predictor,
                                          indices=indices, deadline=deadline)
    if type(predictor) is not _CompiledProjected:
        return fallback()
    if not isinstance(origin, _PredictionOrigin):
        raise ValueError('batch_causal_origin_required')
    validate_deadline(deadline); check_deadline(deadline)
    if type(prepared_commands) is not PreparedCommands:
        raise ValueError('prepared_commands_required')
    prepared_commands.check_origin(origin)
    if _context_key(origin._context) != predictor._base._key:
        return fallback()
    selection = np.arange(len(prepared_commands.requested_commands)) if indices is None else np.asarray(indices)
    if (selection.ndim != 1 or not 1 <= len(selection) <= 64 or selection.dtype.kind not in 'iu'
            or np.any(selection < 0) or np.any(selection >= len(prepared_commands.requested_commands))):
        raise ValueError('prepared_indices_invalid')
    initial = np.array(initial_state, dtype=float, copy=True)
    drive = np.array(prepared_commands.requested_commands[selection], dtype=float, copy=True)
    if (initial.shape != (11,) or not valid_predictions(initial[None])[0]
            or drive.ndim != 3 or drive.shape[2] != 4
            or not 1 <= drive.shape[0] <= 64 or not 1 <= drive.shape[1] <= 128
            or not np.isfinite(drive).all() or np.any(np.abs(drive) > .95)):
        raise ValueError('command_batch_input_invalid')
    estimator = origin._actuator
    if type(estimator) is not Float32PWMActuatorState:
        return fallback()
    if not _chunk.signatures:
        raise RuntimeError('compiled_forecast_not_prepared')
    count, horizon, _ = drive.shape
    initial_speed, initial_clock = estimator.current(), estimator.elapsed_time
    n = len(initial_speed)
    pwm = np.array(prepared_commands.pwm[selection], dtype=np.float32, copy=True, order='C')
    virtual = np.array(prepared_commands.virtual_control[selection], dtype=np.float32, copy=True)
    if pwm.shape != (count, horizon, n) or not np.isfinite(pwm).all() or np.any(np.abs(pwm) > 1):
        return fallback()
    context = origin._context
    scale = np.r_[[context.mass]*3, context.inertia]
    wrench = np.array(prepared_commands.wrench_matrix, dtype=float, copy=True, order='C')
    states = np.empty((count, 2*horizon, 11))
    speeds = np.empty((count, 2*horizon, n))
    inputs = np.empty((count, 2*horizon, 6))
    times = np.empty(2*horizon)
    prefix = 0
    if share_prefix and count > 1:
        # Exact command bytes, including signed zeros. Never share merely close
        # commands or a state computed by another request/model/history.
        while prefix < horizon and all(drive[i, prefix].tobytes() == drive[0, prefix].tobytes()
                                        for i in range(1, count)):
            prefix += 1
    args = (estimator.tau, estimator.dt, estimator.alpha,
            estimator.clock == 'float32_accumulated_v1', wrench, scale,
            prepared_commands.rotor_constant, *_parameters(predictor))
    def run(start, end, x, speed, clock, shared):
        for control in range(start, end, 4):
            check_deadline(deadline)
            stop = min(end, control+4)
            commands = np.array(pwm[:1 if shared else count, control:stop], copy=True, order='C')
            a, b, c, d, x, speed, clock = _chunk(x, speed, clock, commands, *args)
            check_deadline(deadline)
            states[:, 2*control:2*stop] = a
            speeds[:, 2*control:2*stop] = b
            inputs[:, 2*control:2*stop] = c
            times[2*control:2*stop] = d
        return x, speed, clock
    try:
        if prefix:
            x, speed, clock = run(0, prefix, initial[None].copy(), initial_speed[None].copy(), initial_clock, True)
            x = np.repeat(x, count, axis=0); speed = np.repeat(speed, count, axis=0)
        else:
            x = np.repeat(initial[None], count, axis=0)
            speed = np.repeat(initial_speed[None], count, axis=0); clock = initial_clock
        run(prefix, horizon, x, speed, clock, False)
    except (ValueError, FloatingPointError):
        # Known pure predictor only: rerun the reference to retain each failed
        # branch's exact partial record/reason. Work remains charged to deadline.
        check_deadline(deadline)
        return fallback()
    check_deadline(deadline)
    results = []
    for i in range(count):
        results.append(dict(complete=True, failure=None, completed_control_intervals=horizon,
            origin_control=origin.origin_control, origin_actuator_time_s=initial_clock,
            origin_rotor_speed=initial_speed.copy(), requested_commands=drive[i].copy(),
            issued_commands=drive[i].astype(np.float32), control_mask=np.array(origin._mask),
            applied_control=np.repeat(virtual[i], 2, axis=0), predictions=states[i].copy(),
            pwm=np.repeat(pwm[i], 2, axis=0), rotor_speed=speeds[i].copy(),
            acceleration=inputs[i].copy(), physics_time_s=times.copy(),
            input_contract='bounded4D_direct_preTAM_held_two_substeps',
            future_inputs='planned_commands_and_own_rotor_recurrence', model_handoff=False,
            actuator_origin='cached_acknowledged_physics_commands', evidence_level='local_contract_only'))
    check_deadline(deadline)
    return results

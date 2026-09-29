"""Bounded independent candidate forecasts sharing only batch computation.

Allocation uses owned v45 command results already checked by the optimizer.
Model and elementwise rotor recurrence keep v42 reduction and branch semantics.
Deadlines remain cooperative, not a replacement for runtime solver isolation.
"""
from copy import deepcopy
from dataclasses import replace

import numpy as np

from koopman.command_state_v39 import _PredictionOrigin
from koopman.prepared_commands_v45 import PreparedCommands, validate_deadline, check_deadline
from workflows.identification_prediction_v32 import valid_predictions


def forecast_prepared(origin, initial_state, prepared_commands, predictor, *, indices=None, deadline=None):
    """Return one v39-compatible result for each of 1..64 candidate sequences.

All candidates share a causal initial state/context and 1..128 control
intervals. The predictor must be stateless and row-independent. If one row
raises, scalar retries identify failed branches; surviving branches continue.
Nothing here can commit execution or modify the supplied origin.
"""
    if not isinstance(origin, _PredictionOrigin):
        raise ValueError('batch_causal_origin_required')
    validate_deadline(deadline)
    if type(prepared_commands) is not PreparedCommands:
        raise ValueError('prepared_commands_required')
    prepared_commands.check_origin(origin)
    selection = np.arange(len(prepared_commands.requested_commands)) if indices is None else np.asarray(indices)
    if (selection.ndim != 1 or not 1 <= len(selection) <= 64 or selection.dtype.kind not in 'iu'
            or np.any(selection < 0) or np.any(selection >= len(prepared_commands.requested_commands))):
        raise ValueError('prepared_indices_invalid')

    def check_time():
        check_deadline(deadline)

    check_time()
    initial = np.array(initial_state, dtype=float, copy=True)
    drive = np.array(prepared_commands.requested_commands[selection], dtype=float, copy=True)
    if (initial.shape != (11,) or not valid_predictions(initial[None])[0]
            or drive.ndim != 3 or drive.shape[2] != 4
            or not 1 <= drive.shape[0] <= 64 or not 1 <= drive.shape[1] <= 128
            or not np.isfinite(drive).all() or np.any(np.abs(drive) > .95) or not callable(predictor)):
        raise ValueError('command_batch_input_invalid')
    count, horizon, _ = drive.shape
    context = replace(origin._context)
    estimator = deepcopy(origin._actuator)
    initial_speed, initial_clock = estimator.current(), estimator.elapsed_time
    n = len(initial_speed)
    # Identical scalar clock/alpha for every branch; no clock averaging/reset.
    estimator._speed = np.tile(initial_speed, count)
    scale = np.r_[[context.mass]*3, context.inertia]
    x = np.repeat(initial[None], count, axis=0)
    alive = np.ones(count, dtype=bool)
    completed = np.zeros(count, dtype=int)
    issued_counts = np.zeros(count, dtype=int)
    failures = [None]*count
    shape = (count, 2*horizon)
    states = np.empty(shape+(11,))
    pwm_rows = np.empty(shape+(n,), dtype=np.float32)
    speeds = np.empty(shape+(n,))
    inputs = np.empty(shape+(6,))
    applied = np.empty(shape+(4,), dtype=np.float32)
    times = np.empty(shape)
    issued = np.empty((count, horizon, 4), dtype=np.float32)

    def fail(index, control, substep, exc):
        alive[index] = False
        failures[index] = dict(control_index=control, physics_substep=substep,
            completed_physics_ticks=int(completed[index]), exception=f'{type(exc).__name__}:{exc}')

    for control in range(horizon):
        check_time()
        if not alive.any():
            break
        pwm = np.zeros((count, n), dtype=np.float32)
        virtual = np.zeros((count, 4), dtype=np.float32)
        for i in np.flatnonzero(alive):
            check_time()
            try:
                command = drive[i, control].astype(np.float32)
                issued[i, control] = command
                issued_counts[i] += 1
                value = prepared_commands.pwm[selection[i], control]
                if (value.shape != (n,) or not np.isfinite(value).all() or np.any(np.abs(value) > 1)):
                    raise ValueError('direct_actuator_pwm_invalid')
                pwm[i], virtual[i] = value, prepared_commands.virtual_control[selection[i], control]
            except (ValueError, FloatingPointError) as exc:
                fail(i, control, 0, exc)
        for substep in range(2):
            check_time()
            ids = np.flatnonzero(alive)
            if not len(ids):
                break
            speed = estimator.advance_pwm(pwm.reshape(-1)).reshape(count, n)
            force = prepared_commands.rotor_constant*np.abs(speed)*speed
            # Keep the scalar dot's reduction order to avoid changing actuation.
            acceleration = np.stack([prepared_commands.wrench_matrix @ force[i] for i in ids])/scale
            following = np.empty((len(ids), 11))
            try:
                prediction = np.asarray(predictor(x[ids].copy(), acceleration.copy(), context), dtype=float)
                check_time()
                if prediction.shape != (len(ids), 11):
                    raise ValueError('command_prediction_invalid')
                following[:] = prediction
            except (ValueError, FloatingPointError):
                # A numerical/domain failure of one row must not poison others.
                for j, i in enumerate(ids):
                    check_time()
                    try:
                        single = np.asarray(predictor(x[i:i+1].copy(), acceleration[j:j+1].copy(), context), dtype=float)
                        check_time()
                        if single.shape != (1, 11):
                            raise ValueError('command_prediction_invalid')
                        following[j] = single[0]
                    except (ValueError, FloatingPointError) as exc:
                        fail(i, control, substep, exc)
                        following[j] = np.nan
            good = valid_predictions(following)
            for j, i in enumerate(ids):
                if not alive[i]:
                    continue
                if not good[j]:
                    fail(i, control, substep, ValueError('command_prediction_invalid'))
                    continue
                tick = int(completed[i])
                x[i] = following[j]
                states[i, tick] = x[i]
                pwm_rows[i, tick] = pwm[i]
                speeds[i, tick] = speed[i]
                inputs[i, tick] = acceleration[j]
                applied[i, tick] = virtual[i]
                times[i, tick] = estimator.elapsed_time
                completed[i] += 1
    check_time()
    results = []
    for i in range(count):
        end = int(completed[i])
        results.append(dict(complete=failures[i] is None, failure=failures[i],
            completed_control_intervals=end//2, origin_control=origin.origin_control,
            origin_actuator_time_s=initial_clock, origin_rotor_speed=initial_speed.copy(),
            requested_commands=drive[i].copy(), issued_commands=issued[i, :issued_counts[i]].copy(),
            control_mask=np.array(origin._mask), applied_control=applied[i, :end].copy(),
            predictions=states[i, :end].copy(), pwm=pwm_rows[i, :end].copy(),
            rotor_speed=speeds[i, :end].copy(), acceleration=inputs[i, :end].copy(),
            physics_time_s=times[i, :end].copy(), input_contract='bounded4D_direct_preTAM_held_two_substeps',
            future_inputs='planned_commands_and_own_rotor_recurrence', model_handoff=False,
            actuator_origin='cached_acknowledged_physics_commands', evidence_level='local_contract_only'))
    return results

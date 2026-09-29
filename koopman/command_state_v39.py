"""Causal actuator origins for the qualified v37 command-prediction contract.

Only confirmed, ordered physics commands advance the live state. A snapshot
owns a copy of the complete actuator recurrence; each forecast copies it again.
No prediction branch can be committed as execution or restore arbitrary rotor
telemetry. Callers must establish the actual zero reset and authenticate issued
commands; an episode label or counter is not evidence of physical execution.
"""
from copy import deepcopy
from dataclasses import dataclass, replace
import math
from threading import Lock
import time

import numpy as np

from easyuuv_nc.embodiments import CONTROL_CHANNELS
from koopman.command_prediction_v37 import validate_context
from workflows.actuator_replay_v28 import Float32PWMActuatorState
from workflows.control_seam_v23 import ControlKernel
from workflows.identification_prediction_v32 import valid_predictions


def _same_context(a, b):
    return all(np.array_equal(getattr(a, key), getattr(b, key)) for key in
               ('mass', 'inertia', 'cob', 'volume', 'drag_multiplier', 'rho', 'beta', 'gravity'))


def _command(value):
    command = np.array(value, dtype=float, copy=True)
    if command.shape != (4,) or not np.isfinite(command).all() or np.any(np.abs(command) > .95):
        raise ValueError('issued_command_invalid')
    return command.astype(np.float32)


class CausalCommandState:
    """Single live episode, bound to its admitted actual static mechanics.

    Record each command only after that physics substep was actually issued.
    If execution acknowledgement is lost, fail closed instead of guessing the
    missing command or reusing a candidate branch. Online reconfiguration and
    unknown rotor initialization have no admission path in this version.
    """
    channels = CONTROL_CHANNELS

    def __init__(self, configuration, context, *, episode_id, zero_rotor_reset_verified):
        if zero_rotor_reset_verified is not True:
            raise ValueError('command_zero_reset_required')
        if not isinstance(episode_id, str) or not episode_id.strip():
            raise ValueError('command_episode_invalid')
        m = validate_context(configuration, context)
        self._configuration = configuration
        self._context = replace(context)
        self._episode_id = episode_id
        self._mask = tuple(m['control_mask_4'])
        self._kernel = ControlKernel(configuration)
        self._actuator = Float32PWMActuatorState(self._kernel.env._num_thrusters,
            tau=self._kernel.tau, dt=1/120, clock='float32_accumulated_v1')
        self._physics_index = 0
        self._held_command = None
        self._lock = Lock()

    @property
    def physics_index(self):
        with self._lock:
            return self._physics_index

    def record_issued(self, command, *, physics_index, episode_id):
        """Advance exactly one acknowledged substep, never an optimizer trial."""
        command = _command(command)
        with self._lock:
            if (type(physics_index) is not int or physics_index != self._physics_index
                    or episode_id != self._episode_id):
                raise ValueError('issued_sequence_mismatch')
            if physics_index % 2 and not np.array_equal(command, self._held_command):
                raise ValueError('issued_hold_mismatch')
            # Commit only after allocation and recurrence finish successfully.
            following = deepcopy(self._actuator)
            following.advance_pwm(self._kernel.command(command, pre_tam=True)['pwm'])
            self._actuator = following
            self._held_command = command.copy() if physics_index % 2 == 0 else None
            self._physics_index += 1

    def snapshot(self, *, configuration, context, origin_control, episode_id):
        """Capture an even boundary and independently check the caller's context."""
        with self._lock:
            if (type(origin_control) is not int or origin_control < 0
                    or self._physics_index != 2*origin_control or episode_id != self._episode_id):
                raise ValueError('command_origin_mismatch')
            validate_context(configuration, context)
            if configuration != self._configuration or not _same_context(context, self._context):
                raise ValueError('command_context_mismatch')
            return _PredictionOrigin(self._configuration, replace(self._context),
                                     self._mask, origin_control, deepcopy(self._actuator))


@dataclass(frozen=True)
class _PredictionOrigin:
    _configuration: str
    _context: object
    _mask: tuple
    origin_control: int
    _actuator: object

    def forecast(self, initial_state, planned_commands, predictor, *, deadline=None):
        """Forecast 1..128 controls without modifying this origin or live state.

        Predictor must be stateless, as in v37. Deadline checks are cooperative;
        a blocking predictor cannot be preempted by this in-process interface.
        Solver isolation and runtime command arbitration remain separate work.
        """
        if deadline is not None and (isinstance(deadline, bool)
                or not isinstance(deadline, (int, float)) or not math.isfinite(deadline)):
            raise ValueError('command_deadline_invalid')

        def check_time():
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError('command_prediction_budget')

        check_time()
        x = np.array(initial_state, dtype=float, copy=True)
        drive = np.array(planned_commands, dtype=float, copy=True)
        if (x.shape != (11,) or not valid_predictions(x[None])[0]
                or drive.ndim != 2 or drive.shape[1] != 4 or not 1 <= len(drive) <= 128
                or not np.isfinite(drive).all() or np.any(np.abs(drive) > .95) or not callable(predictor)):
            raise ValueError('command_forecast_input_invalid')
        kernel = ControlKernel(self._configuration)
        estimator = deepcopy(self._actuator)
        context = replace(self._context)
        initial_speed, initial_clock = estimator.current(), estimator.elapsed_time
        scale = np.r_[[context.mass]*3, context.inertia]
        states, pwm_rows, speeds, inputs, applied, times, issued = [], [], [], [], [], [], []
        failure = None
        for control, request in enumerate(drive):
            check_time()
            substep = 0
            try:
                command = request.astype(np.float32)
                allocation = kernel.command(command, pre_tam=True)
                issued.append(command.copy())
                for substep in range(2):
                    check_time()
                    speed = estimator.advance_pwm(allocation['pwm'])
                    wrench = kernel.B.numpy() @ (kernel.env.cfg.rotor_constant*np.abs(speed)*speed)
                    acceleration = wrench/scale
                    following = np.asarray(predictor(x[None], acceleration[None], context), dtype=float)
                    check_time()
                    if following.shape != (1, 11) or not valid_predictions(following)[0]:
                        raise ValueError('command_prediction_invalid')
                    x = following[0].copy()
                    states.append(x.copy()); pwm_rows.append(allocation['pwm'].copy())
                    speeds.append(speed.copy()); inputs.append(acceleration.copy())
                    applied.append(allocation['virtual_control'].copy()); times.append(estimator.elapsed_time)
            except (ValueError, FloatingPointError) as exc:
                failure = dict(control_index=control, physics_substep=substep,
                    completed_physics_ticks=len(states), exception=f'{type(exc).__name__}:{exc}')
                break
        n = kernel.env._num_thrusters
        return dict(complete=failure is None, failure=failure, completed_control_intervals=len(states)//2,
            origin_control=self.origin_control, origin_actuator_time_s=initial_clock,
            origin_rotor_speed=initial_speed, requested_commands=drive,
            issued_commands=np.asarray(issued, dtype=np.float32).reshape(-1, 4),
            control_mask=np.array(self._mask), applied_control=np.asarray(applied, dtype=np.float32).reshape(-1, 4),
            predictions=np.asarray(states).reshape(-1, 11), pwm=np.asarray(pwm_rows, dtype=np.float32).reshape(-1, n),
            rotor_speed=np.asarray(speeds).reshape(-1, n), acceleration=np.asarray(inputs).reshape(-1, 6),
            physics_time_s=np.asarray(times), input_contract='bounded4D_direct_preTAM_held_two_substeps',
            future_inputs='planned_commands_and_own_rotor_recurrence', model_handoff=False,
            actuator_origin='cached_acknowledged_physics_commands', evidence_level='local_contract_only')

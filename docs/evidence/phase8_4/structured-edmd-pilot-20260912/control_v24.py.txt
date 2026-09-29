"""Opt-in direct pre-TAM contract for the fixed, single-environment pilot.

Commands are dimensionless roll/pitch/yaw/depth allocation coordinates. They
are not calibrated forces. All actuator and hull propagation remains external.
"""
import math
import numpy as np
import torch
from easyuuv_nc.thrust_allocation import allocate, control_channels_to_wrench

DIRECT_MODES = ('direct_pre_tam_v24', 'direct_sequence_replay_v24')


def _command(runtime, value, *, sequence=False):
    if runtime.num_envs != 1:
        raise ValueError('direct_single_environment_only')
    result = torch.as_tensor(value, dtype=torch.float32, device=runtime.device)
    expected = (1, 2, 4) if sequence else (1, 4)
    if result.shape != expected or not torch.isfinite(result).all() or torch.any(result.abs() > 1):
        raise ValueError('direct_command_invalid')
    return result.detach().clone()


def queue_sequence(runtime, commands):
    if getattr(runtime.cfg, 'control_input_mode', 'legacy_action') != 'direct_sequence_replay_v24':
        raise ValueError('direct_sequence_mode_required')
    if getattr(runtime, '_direct_pending_v24', None) is not None:
        raise ValueError('direct_sequence_already_pending')
    runtime._direct_pending_v24 = _command(runtime, commands, sequence=True)


def begin_interval(runtime, actions):
    mode = getattr(runtime.cfg, 'control_input_mode', 'legacy_action')
    if mode not in DIRECT_MODES:
        raise ValueError('direct_control_mode_invalid')
    command = _command(runtime, actions)
    if getattr(runtime, '_tune_gains_enabled', False):
        raise ValueError('direct_gain_tuning_unsupported')
    if getattr(runtime.cfg, 'decimation', 2) != 2:
        raise ValueError('direct_decimation_invalid')
    if getattr(runtime, '_direct_index_v24', 2) != 2:
        raise ValueError('direct_consume_count_incomplete')
    if mode == 'direct_sequence_replay_v24':
        sequence = getattr(runtime, '_direct_pending_v24', None)
        if sequence is None:
            raise ValueError('direct_sequence_missing')
        if not torch.equal(command, sequence[:, 0]):
            raise ValueError('direct_first_command_mismatch')
        runtime._direct_pending_v24 = None
    else:
        sequence = command[:, None, :].repeat(1, 2, 1)
    runtime._direct_sequence_v24 = sequence
    runtime._direct_index_v24 = 0


def direct_pwm(runtime):
    index = getattr(runtime, '_direct_index_v24', 2)
    if index >= 2 or not hasattr(runtime, '_direct_sequence_v24'):
        raise ValueError('direct_consume_count_exceeded')
    command = runtime._direct_sequence_v24[:, index]
    virtual = command * runtime._control_mask_4
    if runtime._use_config_alloc:
        wrench = control_channels_to_wrench(virtual * runtime._alloc_channel_sign)
        raw = allocate(runtime._alloc_B, wrench, mode=runtime._alloc_mode, weight=runtime._alloc_weight)
    else:
        roll, pitch, yaw, depth = virtual.unbind(-1)
        raw = torch.stack((-roll-pitch+depth, roll-pitch+depth, -roll+pitch+depth,
                           roll+pitch+depth, yaw, -yaw, -yaw, yaw), dim=-1)
    if not torch.isfinite(raw).all():
        raise ValueError('direct_allocation_nonfinite')
    pwm = torch.clamp(raw, -1, 1)
    runtime._last_pid_value = virtual.detach().clone()
    runtime._last_virtual_control_4 = virtual.detach().clone()
    runtime._last_motor_values_raw = raw.detach().clone()
    runtime._last_motor_values_clipped = pwm.detach().clone()
    runtime._last_motor_saturation_ratio = (raw.abs() > 1).float().mean(-1)
    runtime._last_motor_headroom = 1 - raw.abs().max(-1).values
    runtime._pid_value_add_buf = torch.zeros_like(virtual)
    runtime._pseudo_label_buf = torch.zeros_like(virtual)
    runtime._direct_index_v24 = index + 1
    return pwm


def reset_direct(runtime, env_ids):
    # This version deliberately rejects batched runtime before any command.
    if runtime.num_envs != 1:
        raise ValueError('direct_single_environment_only')
    ids = torch.as_tensor(env_ids).reshape(-1)
    if len(ids) == 0:
        return
    if len(ids) != 1 or int(ids[0]) != 0:
        raise ValueError('direct_reset_ids_invalid')
    runtime._direct_pending_v24 = None
    runtime._direct_index_v24 = 2
    runtime._direct_sequence_v24 = torch.zeros(1, 2, 4, device=runtime.device)


class ActuatorState:
    """Known-zero command-only rotor recurrence. No measured-state update API."""
    def __init__(self, count, *, tau, dt, clock='fixed_dt'):
        if (isinstance(count, bool) or not isinstance(count, int) or count < 1
                or not math.isfinite(tau) or not math.isfinite(dt) or tau <= 0 or dt <= 0):
            raise ValueError('direct_actuator_parameters_invalid')
        if clock not in ('fixed_dt', 'float32_accumulated_v1'):
            raise ValueError('direct_actuator_clock_invalid')
        self._speed = np.zeros(count)
        self.clock, self.dt, self.tau = clock, float(dt), float(tau)
        self.elapsed_time = 0.0
        self.alpha = math.exp(-dt/tau)

    def current(self):
        return self._speed.copy()

    def reset(self):
        self._speed.fill(0)
        self.elapsed_time = 0.0

    def advance_pwm(self, pwm):
        command = np.asarray(pwm, dtype=float)
        if command.shape != self._speed.shape or not np.isfinite(command).all() or np.any(np.abs(command) > 1):
            raise ValueError('direct_actuator_pwm_invalid')
        positive, negative = command >= .02, command <= -.02
        target = np.zeros_like(command)
        target[positive] = -139*command[positive]**2 + 500*command[positive] + 8.28
        target[negative] = 161*command[negative]**2 + 517.86*command[negative] - 5.72
        if self.clock == 'float32_accumulated_v1':
            # Reproduce the known runtime clock arithmetic, not a measured timestamp.
            next_time = float(np.float32(np.float32(self.elapsed_time) + np.float32(self.dt)))
            alpha = math.exp(-(next_time-self.elapsed_time)/self.tau)
            self.elapsed_time = next_time
        else:
            alpha = self.alpha
            self.elapsed_time += self.dt
        self._speed = alpha*self._speed + (1-alpha)*target
        return self.current()

"""Configuration-bound direct allocation for prediction, not the live controller.

The original ControlKernel supplies geometry and the fixed direct-seam contract.
Only constant matrix inversion and unused PID telemetry are removed. Configured
allocation retains the original float32 scalar einsum reduction, including WLS.
"""
from dataclasses import dataclass, field

import numpy as np
import torch

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from workflows.control_seam_v23 import ControlKernel


def _immutable(value):
    a = np.asarray(value, dtype=np.float32)
    return np.frombuffer(a.tobytes(), dtype=a.dtype).reshape(a.shape)


@dataclass(frozen=True, init=False)
class PreparedDirectAllocation:
    configuration: str
    wrench_matrix: np.ndarray = field(repr=False)
    rotor_constant: float
    _mask: np.ndarray = field(repr=False)
    _sign: np.ndarray = field(repr=False)
    _weights: object = field(repr=False)
    _inverse: object = field(repr=False)

    def __init__(self, configuration):
        if not isinstance(configuration, str) or configuration not in SUPPORTED_EMBODIMENTS:
            raise ValueError('prepared_allocation_configuration_invalid')
        kernel = ControlKernel(configuration)
        env = kernel.env
        # Fail closed if the source's diagnostic direct contract ever changes.
        if (env._depth_pid_output_scale != 1. or env._depth_integral_gain != 0.
                or env._depth_deadband_mode != 'off' or env._depth_invert_compensation
                or env._alloc_priority_mode != 'off' or env.ctrl_mismatch_mode != 'none'
                or not torch.all(env._action_channel_sign == 1)):
            raise ValueError('prepared_allocation_direct_contract_changed')
        weights, inverse = None, None
        if env._use_config_alloc:
            if env._alloc_mode not in ('pinv', 'wls'):
                raise ValueError('prepared_allocation_mode_invalid')
            matrix = kernel.B
            if env._alloc_mode == 'wls':
                weight = torch.ones(6, dtype=torch.float32) if env._alloc_weight is None else env._alloc_weight
                matrix = weight.unsqueeze(-1)*matrix
                weights = _immutable(weight.numpy())
            inverse = torch.linalg.pinv(matrix).detach().clone()
        for key, value in dict(configuration=configuration,
                wrench_matrix=_immutable(kernel.B.numpy()), rotor_constant=env.cfg.rotor_constant,
                _mask=_immutable(env._control_mask_4.numpy()[0]),
                _sign=_immutable(env._alloc_channel_sign.numpy()),
                _weights=weights, _inverse=inverse).items():
            object.__setattr__(self, key, value)

    def command(self, action, *, pre_tam=False):
        if pre_tam is not True:
            raise ValueError('prepared_allocation_direct_seam_only')
        command = np.array(action, dtype=np.float32, copy=True)
        if command.shape != (4,) or not np.isfinite(command).all() or np.any(np.abs(command) > 1):
            raise ValueError('kernel_command_invalid')
        virtual = np.clip(command, -1, 1)*self._mask
        if self._inverse is not None:
            signed = virtual*self._sign
            wrench = np.zeros((1, 6), dtype=np.float32)
            wrench[0, [3, 4, 5, 2]] = signed
            if self._weights is not None:
                wrench = wrench*self._weights
            # Keep shape (1, 6); a batched GEMM could change float32 rounding.
            raw = torch.einsum('nk,...k->...n', self._inverse, torch.from_numpy(wrench)).numpy()[0].copy()
        else:
            roll, pitch, yaw, depth = virtual
            raw = np.array([-roll-pitch+depth, roll-pitch+depth,
                            -roll+pitch+depth, roll+pitch+depth,
                            yaw, -yaw, -yaw, yaw], dtype=np.float32)
        return dict(virtual_control=virtual.copy(), pwm_raw=raw, pwm=np.clip(raw, -1, 1))

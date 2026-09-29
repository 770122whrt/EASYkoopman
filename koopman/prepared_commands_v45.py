"""Immutable, bounded command allocations shared by screening and forecasting.

Only identical float32 command bytes share a scalar v42 allocation. There is no
rotor state, trajectory state, cross-request cache or changed reduction order.
The original requested commands are owned separately from their applied mask.
"""
from dataclasses import dataclass, field
import numbers
import time

import numpy as np

from koopman.command_state_v39 import _PredictionOrigin
from koopman.command_prediction_v37 import validate_context
from koopman.prepared_allocation_v42 import PreparedDirectAllocation
from koopman.prepared_projected_v40 import _context_key


def validate_deadline(deadline):
    if deadline is not None and (isinstance(deadline,bool) or not isinstance(deadline,numbers.Real)
                                 or not np.isfinite(deadline)):
        raise ValueError('command_deadline_invalid')


def check_deadline(deadline):
    if deadline is not None and time.perf_counter() >= deadline:
        raise TimeoutError('command_prediction_budget')


def immutable(value, dtype=None):
    a=np.asarray(value,dtype=dtype)
    return np.frombuffer(a.tobytes(),dtype=a.dtype).reshape(a.shape)


@dataclass(frozen=True,init=False)
class PreparedCommands:
    configuration: str
    context_key: tuple
    requested_commands: np.ndarray = field(repr=False)
    virtual_control: np.ndarray = field(repr=False)
    pwm_raw: np.ndarray = field(repr=False)
    pwm: np.ndarray = field(repr=False)
    wrench_matrix: np.ndarray = field(repr=False)
    rotor_constant: float
    unique_command_count: int

    def __init__(self,origin,planned_commands,*,allocator=None,deadline=None):
        validate_deadline(deadline); check_deadline(deadline)
        if not isinstance(origin,_PredictionOrigin): raise ValueError('prepared_causal_origin_required')
        validate_context(origin._configuration,origin._context)
        drive=np.array(planned_commands,dtype=float,copy=True)
        if (drive.ndim!=3 or drive.shape[2]!=4 or not 1<=drive.shape[0]<=64
                or not 1<=drive.shape[1]<=128 or not np.isfinite(drive).all() or np.any(np.abs(drive)>.95)):
            raise ValueError('prepared_commands_invalid')
        if allocator is None: allocator=PreparedDirectAllocation(origin._configuration)
        if type(allocator) is not PreparedDirectAllocation or allocator.configuration!=origin._configuration:
            raise ValueError('prepared_allocation_configuration_mismatch')
        count,horizon,_=drive.shape; thrusters=allocator.wrench_matrix.shape[1]
        pwm=np.empty((count,horizon,thrusters),dtype=np.float32)
        raw=np.empty_like(pwm); virtual=np.empty((count,horizon,4),dtype=np.float32)
        cache={}
        for i in range(count):
            for j in range(horizon):
                check_deadline(deadline)
                command=drive[i,j].astype(np.float32); key=command.tobytes()
                if key not in cache:
                    cache[key]=allocator.command(command,pre_tam=True)
                result=cache[key]
                pwm[i,j],raw[i,j],virtual[i,j]=result['pwm'],result['pwm_raw'],result['virtual_control']
        if not all(np.isfinite(a).all() for a in (pwm,raw,virtual)) or np.any(np.abs(pwm)>1):
            raise ValueError('prepared_allocation_nonfinite_or_invalid')
        for name,value in dict(configuration=origin._configuration,context_key=_context_key(origin._context),
                requested_commands=immutable(drive),virtual_control=immutable(virtual),pwm_raw=immutable(raw),
                pwm=immutable(pwm),wrench_matrix=immutable(allocator.wrench_matrix),
                rotor_constant=allocator.rotor_constant,unique_command_count=len(cache)).items():
            object.__setattr__(self,name,value)
        check_deadline(deadline)

    def check_origin(self,origin):
        if (not isinstance(origin,_PredictionOrigin) or origin._configuration!=self.configuration
                or _context_key(origin._context)!=self.context_key):
            raise ValueError('prepared_origin_context_mismatch')

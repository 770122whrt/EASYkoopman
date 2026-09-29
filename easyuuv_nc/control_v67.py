"""Explicit 30Hz command hold: four unchanged 120Hz physics/actuator steps."""
import torch
from easyuuv_nc.control_v24 import _command
from easyuuv_nc.thrust_allocation import allocate,control_channels_to_wrench

def begin_interval(runtime, actions):
    mode = getattr(runtime.cfg, 'control_input_mode', 'legacy_action')
    if mode != 'direct_pre_tam_v24':
        raise ValueError('direct_control_mode_invalid')
    command = _command(runtime, actions)
    if getattr(runtime, '_tune_gains_enabled', False):
        raise ValueError('direct_gain_tuning_unsupported')
    if getattr(runtime.cfg, 'decimation', 2) != 4 or getattr(runtime.cfg, 'control_rate_hz_v67', None) != 30:
        raise ValueError('direct_decimation_invalid')
    if getattr(runtime, '_direct_index_v24', 4) != 4:
        raise ValueError('direct_consume_count_incomplete')
    if mode == 'direct_sequence_replay_v24':
        sequence = getattr(runtime, '_direct_pending_v24', None)
        if sequence is None:
            raise ValueError('direct_sequence_missing')
        if not torch.equal(command, sequence[:, 0]):
            raise ValueError('direct_first_command_mismatch')
        runtime._direct_pending_v24 = None
    else:
        sequence = command[:, None, :].repeat(1, 4, 1)
    runtime._direct_sequence_v24 = sequence
    runtime._direct_index_v24 = 0

def direct_pwm(runtime):
    index = getattr(runtime, '_direct_index_v24', 4)
    if index >= 4 or not hasattr(runtime, '_direct_sequence_v24'):
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
    runtime._direct_index_v24 = 4
    runtime._direct_sequence_v24 = torch.zeros(1, 4, 4, device=runtime.device)

def install_control_clock():
    """Opt-in process-local routing; original file and the 60Hz path stay intact."""
    from easyuuv_nc import control_v24
    originals={n:getattr(control_v24,n) for n in ('begin_interval','direct_pwm','reset_direct')}
    if any(getattr(f,'_rate30_route',False) for f in originals.values()):raise ValueError('rate30_already_installed')
    for name,new in [('begin_interval',begin_interval),('direct_pwm',direct_pwm),('reset_direct',reset_direct)]:
        old=originals[name]
        def route(runtime,*args,_old=old,_new=new,**kwargs):
            if getattr(runtime.cfg,'control_rate_hz_v67',None)==30:return _new(runtime,*args,**kwargs)
            return _old(runtime,*args,**kwargs)
        route._rate30_route=True
        setattr(control_v24,name,route)
    return originals

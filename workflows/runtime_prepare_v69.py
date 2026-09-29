"""Prepare existing pure math on private tensors; no env.step or actuator update.

Startup costs remain recorded. This does not relax the first controlled cycle
deadline. The caller must compare full actual reset snapshots before/after.
"""
import json
import time


def _scratch(value):
    import torch
    if isinstance(value,torch.Tensor):return value.detach().clone()
    if isinstance(value,tuple):return tuple(_scratch(x) for x in value)
    if isinstance(value,list):return [_scratch(x) for x in value]
    if isinstance(value,dict):return {k:_scratch(v) for k,v in value.items()}
    if value is None or type(value) in (float,int,bool,str):return value
    raise TypeError('unsupported_scratch_input')


def assert_unchanged(before,after):
    if json.dumps(before,sort_keys=True,allow_nan=False)!=json.dumps(after,sort_keys=True,allow_nan=False):
        raise ValueError('warmup_changed_runtime')


def warm_pure_calls(calls,*,synchronize,repeats=8):
    if type(repeats) is not int or not 1<=repeats<=64:raise ValueError('bounded_warmup_repeats')
    started=time.perf_counter();measurements=[]
    for name,function,args in calls:
        for i in range(repeats):
            private=_scratch(args)
            synchronize();begin=time.perf_counter()
            function(*private)
            synchronize()
            measurements.append(dict(name=name,repeat=i,seconds=time.perf_counter()-begin))
    return dict(physics_steps=0,calls=len(measurements),startup_seconds=time.perf_counter()-started,
                preparation='private_math_inputs_only',measurements=measurements)


def prepare_math(env):
    """Explicit pure functions only; never call stateful env/controller methods."""
    import torch
    from isaaclab_compat import quat_apply,quat_conjugate,math_utils
    from easyuuv_nc.env.easyuuv_env import _compute_rewards
    from easyuuv_nc.env.rigid_body_hydrodynamics import HydrodynamicForceModels
    data=env._robot.data;cfg=env.cfg
    q=data.root_quat_w.detach().clone()
    vector=torch.zeros((env.num_envs,3),device=env.device);vector[:,0]=1
    forces=torch.zeros((env.num_envs,env._num_thrusters,3),device=env.device);forces[...,0]=1
    hydro=HydrodynamicForceModels(env.num_envs,env.device)
    scales=tuple(float(getattr(cfg,k,0.)) for k in ('rew_scale_pos','rew_scale_ang','rew_scale_lin_vel',
        'rew_scale_ang_vel','rew_scale_actions','rew_scale_action_rate','rew_scale_action_jerk'))
    calls=[('quat_conjugate',quat_conjugate,(q,)),
        ('quat_apply_body',quat_apply,(q,vector)),
        ('quat_apply_thrusters',quat_apply,(env.thruster_quats,forces)),
        ('quat_error',math_utils.quat_error_magnitude,(env._goal,q)),
        ('buoyancy',hydro.calculate_buoyancy_forces,(q,float(cfg.water_rho),env.volumes,
            float(abs(env._gravity_magnitude)),env.com_to_cob_offsets)),
        ('drag',hydro.calculate_density_and_viscosity_forces,(q,data.root_lin_vel_w,data.root_ang_vel_w,
            env.inertia_tensors,env.inertia_tensors_mean,float(cfg.water_beta),float(cfg.water_rho),env.masses,vector)),
        ('reward',_compute_rewards,scales+(data.root_lin_vel_b,data.root_ang_vel_b,env.reset_terminated,
            data.root_pos_w,q,env._goal,vector,env._completed_envs,env._actions,env._actions,env._actions))]
    result=warm_pure_calls(calls,synchronize=lambda:torch.cuda.synchronize(env.device))
    result['allocation']=warm_allocation(env)
    result['startup_seconds']+=result['allocation']['startup_seconds']
    result['calls']+=result['allocation']['calls']
    return result


def warm_allocation(env, *, synchronize=None):
    """Warm the actual configured pinv/WLS shape without invoking any plant method."""
    if not env._use_config_alloc:
        return dict(physics_steps=0,calls=0,startup_seconds=0.,reason='legacy_no_matrix_allocation')
    import torch
    from easyuuv_nc.thrust_allocation import allocate,control_channels_to_wrench
    mode=env._alloc_mode
    def operation(matrix,command,sign,weight):
        return allocate(matrix,control_channels_to_wrench(command*sign),mode=mode,weight=weight)
    command=torch.zeros((env.num_envs,4),device=env.device);command[:,1]=.01
    sync=synchronize if synchronize is not None else lambda:torch.cuda.synchronize(env.device)
    return warm_pure_calls([('configured_allocation_'+mode,operation,
        (env._alloc_B,command,env._alloc_channel_sign,env._alloc_weight))],synchronize=sync)

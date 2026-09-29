"""CPU control-subsystem probes, not an Isaac environment or hull simulator.

Compile the actual default controller/PWM statements and actuator classes from
the checkout. No frozen source is edited and no Isaac module is impersonated.
"""
import ast
from functools import lru_cache
import math
from pathlib import Path
import sys
from types import MethodType, ModuleType, SimpleNamespace
import numpy as np
import torch

from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS, qualification_record
from easyuuv_nc.thrust_allocation import (ThrusterLayout, allocate, build_wrench_matrix,
    control_channels_to_wrench, dof_weight_vector)

ROOT=Path(__file__).resolve().parents[1]
ENV=ROOT/'easyuuv_nc/env/easyuuv_env.py'
THRUSTER=ROOT/'easyuuv_nc/env/thruster_dynamics.py'


@lru_cache(maxsize=1)
def _kernels():
    tree=ast.parse(ENV.read_text(encoding='utf8'))
    cfg=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='EasyUUVEnvCfg')
    names={'PID_PWM_value','PID_init_args','control_method','s_ratio','cascade_control',
           'self_adapt','attitude_error_mode','action_lim_vec','pseudo_error_driven','rotor_constant'}
    nodes=[n for n in cfg.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in names]
    values={};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(ENV),'exec'),values)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='EasyUUVEnv')
    methods={n.name:n for n in cls.body if isinstance(n,ast.FunctionDef)}
    ns={'torch':torch,'np':np,'math':math,'allocate':allocate,'control_channels_to_wrench':control_channels_to_wrench}
    exec(compile(ast.Module(body=[methods['_pid_control']],type_ignores=[]),str(ENV),'exec'),ns)
    body=methods['_compute_dynamics'].body
    start=next(i for i,n in enumerate(body) if ast.unparse(n).startswith('action_diff ='))
    end=next(i for i,n in enumerate(body) if ast.unparse(n)=='self.old_actions = actions.clone()')
    wrapper=ast.parse('def controller_step(self, actions):\n    pass').body[0]
    wrapper.body=body[start:end+1]+[ast.Return(value=ast.Name(id='motorValues',ctx=ast.Load()))]
    exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),str(ENV),'exec'),ns)
    start=next(i for i,n in enumerate(body) if ast.unparse(n)=='threshold = 0.02')
    pwm=ast.parse('def pwm_speed(motorValues):\n    motorValues = motorValues.clone()').body[0]
    pwm.body+=body[start:start+4]+[ast.Return(value=ast.Name(id='motorValues',ctx=ast.Load()))]
    exec(compile(ast.fix_missing_locations(ast.Module(body=[pwm],type_ignores=[])),str(ENV),'exec'),ns)
    # The unused legacy Euler helper references Isaac; the active geometry builder
    # implements its own RPY quaternion calculation. Drop only that import.
    dyn_tree=ast.parse(THRUSTER.read_text(encoding='utf8'))
    dyn_tree.body=[n for n in dyn_tree.body if not (isinstance(n,ast.ImportFrom) and n.module=='isaaclab_compat')]
    module=ModuleType('_control_seam_actual_thruster_v23');sys.modules[module.__name__]=module
    exec(compile(dyn_tree,str(THRUSTER),'exec'),module.__dict__)
    return {n:values[n] for n in names},ns,module


class ControlKernel:
    def __init__(self,configuration,*,dt=1/120):
        defaults,ns,dyn=_kernels()
        if not math.isfinite(dt) or dt<=0:raise ValueError('kernel_dt_invalid')
        cfg=EMBODIMENT_CONFIGS[configuration];topology=qualification_record(configuration)
        allocation=cfg.get('thrust_allocation')
        if allocation:
            layout=ThrusterLayout.from_specs(allocation['specs'])
        else:
            positions,orientations=dyn.get_thruster_com_and_orientations('cpu')
            layout=ThrusterLayout(positions*cfg.get('thruster_com_offset_scale',1),orientations,8)
        self.B=build_wrench_matrix(layout);self.dt=dt;self.tau=cfg['dyn_time_constant']
        self.env=SimpleNamespace(cfg=SimpleNamespace(**defaults),num_envs=1,_num_thrusters=layout.num_thrusters,
            device='cpu',ctrl_mismatch_mode='none',_depth_pid_output_scale=1.,_depth_integral_gain=0.,
            _depth_deadband_mode='off',_depth_invert_compensation=False,_alloc_priority_mode='off',
            _use_config_alloc=bool(allocation),_alloc_B=self.B,
            _alloc_mode=allocation['mode'] if allocation else 'legacy',
            _alloc_weight=dof_weight_vector(allocation['controllable_dofs']) if allocation else None,
            _alloc_channel_sign=torch.tensor([-1.,1.,-1.,1.]),
            _action_channel_sign=torch.ones(1,4),_control_mask_4=torch.tensor(topology['control_mask']).reshape(1,4),
            action_lim=torch.tensor(defaults['action_lim_vec']).reshape(1,4),
            PID_args=torch.tensor(defaults['PID_init_args']).reshape(1,4,3),
            old_actions=torch.zeros(1,4),actions_i=torch.zeros(1,4))
        self.env._pid_control=MethodType(ns['_pid_control'],self.env)
        self.controller_step=ns['controller_step'];self.pwm_speed=ns['pwm_speed']
        self.actuator=dyn.DynamicsFirstOrder(1,layout.num_thrusters,self.tau,'cpu')
        self.conversion=dyn.ConversionFunctionBasic(defaults['rotor_constant'])
        self.time=torch.zeros(1)

    def command(self,action,*,pre_tam=False):
        a=torch.as_tensor(action,dtype=torch.float32).reshape(1,4)
        if not torch.isfinite(a).all() or torch.any(a.abs()>1):raise ValueError('kernel_command_invalid')
        if pre_tam:
            # Diagnostic injection at the declared seam only; no runtime edit.
            saved=self.env.cfg.cascade_control;self.env.cfg.cascade_control=False
            try:pwm=self.env._pid_control(a,torch.zeros_like(a),torch.zeros_like(a))
            finally:self.env.cfg.cascade_control=saved
        else:pwm=self.controller_step(self.env,a)
        return {'virtual_control':self.env._last_virtual_control_4.numpy()[0].copy(),
                'pwm_raw':self.env._last_motor_values_raw.numpy()[0].copy(),'pwm':pwm.numpy()[0].copy()}

    def advance(self,pwm):
        speed_cmd=self.pwm_speed(torch.as_tensor(pwm,dtype=torch.float32).reshape(1,-1))
        self.time.add_(self.dt)
        speed=self.actuator.update(speed_cmd,self.time).clone()
        force=self.conversion.convert(speed)
        return {'speed_command':speed_cmd.numpy()[0].copy(),'speed':speed.numpy()[0].copy(),
                'wrench':(self.B@force[0]).numpy().copy()}


def estimate_speed(previous,pwm,*,tau,dt):
    """Independent command-driven estimate, no measured speed/wrench inputs."""
    previous=np.asarray(previous,dtype=float);pwm=np.asarray(pwm,dtype=float)
    if (previous.shape!=pwm.shape or not np.isfinite(previous).all() or not np.isfinite(pwm).all()
        or np.any(np.abs(pwm)>1) or not math.isfinite(tau) or not math.isfinite(dt) or tau<=0 or dt<=0):
        raise ValueError('actuator_estimate_invalid')
    speed=np.zeros_like(pwm);positive=pwm>=.02;negative=pwm<=-.02
    speed[positive]=-139*pwm[positive]**2+500*pwm[positive]+8.28
    speed[negative]=161*pwm[negative]**2+517.86*pwm[negative]-5.72
    alpha=math.exp(-dt/tau)
    return alpha*previous+(1-alpha)*speed


def mechanical_readback(runtime):
    """Keep local hydrodynamic parameters distinct from actual PhysX tensors."""
    from workflows.observation_trace import _copy
    try:
        view=runtime._robot.root_physx_view
        result={'declared_mass':_copy(runtime.masses),'declared_inertia':_copy(runtime.inertia_tensors),
            'physx_mass':_copy(view.get_masses()),'physx_inertia':_copy(view.get_inertias())}
        if any(not np.isfinite(np.asarray(v,dtype=float)).all() for v in result.values()):
            raise ValueError('nonfinite_physics_readback')
        return result
    except (AttributeError,TypeError,ValueError,RuntimeError) as exc:
        raise ValueError('mechanical_readback_unavailable') from exc

"""Exercise the real environment method seam without claiming Isaac physics."""
import ast
import importlib.util
from pathlib import Path
from types import MethodType
import numpy as np
import pytest
import torch
from workflows.control_seam_v23 import ControlKernel


def module():
    assert importlib.util.find_spec('easyuuv_nc.control_v24'), 'direct contract missing'
    from easyuuv_nc import control_v24
    return control_v24


def bind_pre(kernel, mode):
    m=module();e=kernel.env;e.cfg.control_input_mode=mode
    e._debug=False;e._tune_gains_enabled=False
    e._actions=torch.zeros(1,4);e._prev_action=torch.zeros(1,4);e._prev_prev_action=torch.zeros(1,4)
    tree=ast.parse((Path(__file__).resolve().parents[1]/'easyuuv_nc/env/easyuuv_env.py').read_text(encoding='utf8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='EasyUUVEnv')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_pre_physics_step')
    scope={'torch':torch};exec(compile(ast.Module(body=[method],type_ignores=[]),'real-pre-step','exec'),scope)
    e.pre=MethodType(scope['_pre_physics_step'],e)
    return m,e


@pytest.mark.parametrize('configuration',['base','long_body','heavy_moderate','asymmetric','uuv6','uuv6_angled','uuv4','uuv4_angled'])
def test_direct_seam_matches_existing_allocation_without_reinterpreting_pid(configuration):
    k=ControlKernel(configuration);m,e=bind_pre(k,'direct_pre_tam_v24')
    u=torch.tensor([[.05,-.04,.08,.2]])
    expected=ControlKernel(configuration).command(u,pre_tam=True)
    e.PID_args.fill_(99);e._depth_pid_output_scale=-13;e._depth_integral_gain=8
    e.pre(u)
    for _ in range(2):
        actual=k.command(u)
        np.testing.assert_allclose(actual['pwm'],expected['pwm'],atol=1e-7)
        np.testing.assert_allclose(actual['virtual_control'],u.numpy()[0]*e._control_mask_4.numpy()[0],atol=0)
    with pytest.raises(ValueError,match='consume_count'):
        k.command(u)


def test_ordered_replay_is_consumed_once_and_requires_matching_first_command():
    k=ControlKernel('uuv6');m,e=bind_pre(k,'direct_sequence_replay_v24')
    seq=torch.tensor([[[.1,.2,.1,.0],[-.1,0,.2,.1]]])
    m.queue_sequence(e,seq)
    with pytest.raises(ValueError,match='first_command'):
        e.pre(torch.zeros(1,4))
    e.pre(seq[:,0])
    for j in range(2):
        actual=k.command(seq[:,0])
        np.testing.assert_array_equal(actual['virtual_control'],seq[0,j].numpy())
    with pytest.raises(ValueError,match='sequence_missing'):
        e.pre(seq[:,0])


@pytest.mark.parametrize('bad',[1.01,float('nan'),float('inf')])
def test_invalid_direct_action_rejected_before_legacy_clipping(bad):
    k=ControlKernel('base');_,e=bind_pre(k,'direct_pre_tam_v24')
    u=torch.zeros(1,4);u[0,0]=bad
    with pytest.raises(ValueError,match='direct_command'):
        e.pre(u)
    assert not torch.any(e._actions)


def test_single_environment_reset_clears_pending_direct_schedule():
    k=ControlKernel('base');m,e=bind_pre(k,'direct_sequence_replay_v24')
    m.queue_sequence(e,torch.ones(1,2,4)*.1)
    m.reset_direct(e,torch.tensor([0]))
    with pytest.raises(ValueError,match='sequence_missing'):
        e.pre(torch.ones(1,4)*.1)


def test_unvalidated_batched_direct_mode_is_explicitly_rejected():
    k=ControlKernel('base');_,e=bind_pre(k,'direct_pre_tam_v24');e.num_envs=2
    with pytest.raises(ValueError,match='single_environment_only'):
        e.pre(torch.zeros(2,4))


def test_command_driven_actuator_matches_existing_real_kernels():
    m=module();k=ControlKernel('uuv6')
    estimator=m.ActuatorState(k.env._num_thrusters,tau=k.tau,dt=k.dt)
    for pwm in [np.array([0,.019,.02,-.02,.8,-.8]),np.zeros(6),np.ones(6)*.1]:
        actual=k.advance(pwm)['speed']
        np.testing.assert_allclose(estimator.advance_pwm(pwm),actual,atol=2e-5)
    estimator.reset();np.testing.assert_array_equal(estimator.current(),np.zeros(6))


def test_long_known_clock_estimator_matches_float32_runtime_without_speed_truth():
    m=module();k=ControlKernel('uuv6')
    estimator=m.ActuatorState(6,tau=k.tau,dt=k.dt,clock='float32_accumulated_v1')
    from workflows.pilot_control_v24 import commands
    request={'intervals':128,'seed':8421,'excitation':'prbs','amplitudes':[.04,.04,.08,.2],'hold_intervals':4,'configuration':'uuv6'}
    maximum=0
    for u in commands(request):
        for _ in range(2):
            pwm=k.command(u,pre_tam=True)['pwm']
            prediction=estimator.advance_pwm(pwm)
            actual=k.advance(pwm)['speed']
            maximum=max(maximum,float(np.max(np.abs(prediction-actual))))
    assert maximum<1e-3
    estimator.reset();assert estimator.elapsed_time==0

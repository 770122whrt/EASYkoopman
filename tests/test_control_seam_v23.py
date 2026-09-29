import importlib.util
from types import SimpleNamespace
import numpy as np
import pytest
import torch


def api():
    assert importlib.util.find_spec('workflows.control_seam_v23') is not None, 'control seam not implemented'
    from workflows import control_seam_v23
    return control_seam_v23


def test_real_controller_consumes_difference_once_and_keeps_last_command():
    k=api().ControlKernel('base')
    a=np.array([0.,0.,0.,.1])
    first=k.command(a);second=k.command(a)
    assert first['virtual_control'][3]>second['virtual_control'][3]>0
    np.testing.assert_allclose(second['virtual_control'][3], np.tanh(2*(.16/.6)*.1),rtol=2e-6)
    np.testing.assert_array_equal(k.env.old_actions.numpy()[0],a.astype(np.float32))


def test_force_allocator_output_is_currently_pwm_not_calibrated_thrust():
    base=api().ControlKernel('base');six=api().ControlKernel('uuv6')
    u=np.array([0.,0.,0.,.1])
    b=base.command(u,pre_tam=True);s=six.command(u,pre_tam=True)
    np.testing.assert_allclose(b['pwm'][:4],.1,atol=1e-7)
    np.testing.assert_allclose(s['pwm'][:4],.025,atol=1e-6)
    wb=base.advance(b['pwm']);ws=six.advance(s['pwm'])
    assert wb['wrench'][2]>5*ws['wrench'][2]


def test_legacy_reset_history_can_alias_same_recorded_input_and_proxy():
    records=[]
    for sign in [-1,1]:
        k=api().ControlKernel('base');k.env.old_actions[0,3]=sign*.1
        a=k.command(np.zeros(4));f=k.advance(a['pwm'])
        b=k.command(np.zeros(4));g=k.advance(b['pwm'])
        records.append((a,b,f,g))
    np.testing.assert_array_equal(records[0][1]['virtual_control'],np.zeros(4))
    np.testing.assert_array_equal(records[0][1]['virtual_control'],records[1][1]['virtual_control'])
    assert records[0][3]['wrench'][2]*records[1][3]['wrench'][2]<0


def test_independent_estimator_matches_real_lag_at_physics_dt():
    k=api().ControlKernel('uuv6');estimate=np.zeros(6)
    for pwm in [np.ones(6)*.1,np.ones(6)*-.1,np.zeros(6)]:
        actual=k.advance(pwm)
        estimate=api().estimate_speed(estimate,pwm,tau=.05,dt=1/120)
        np.testing.assert_allclose(estimate,actual['speed'],rtol=2e-6,atol=1e-5)


def test_masked_yaw_is_not_claimed_as_control_authority():
    k=api().ControlKernel('uuv4')
    result=k.command([0,0,.1,0],pre_tam=True)
    np.testing.assert_array_equal(result['virtual_control'],np.zeros(4))
    np.testing.assert_array_equal(result['pwm'],np.zeros(4))


def test_actual_physics_parameters_are_not_substituted_with_declared_values():
    runtime=SimpleNamespace(masses=torch.tensor([[99.]]),inertia_tensors=torch.tensor([[9.,9.,9.]]),
        _robot=SimpleNamespace(root_physx_view=SimpleNamespace(get_masses=lambda:torch.tensor([[2.]]),
            get_inertias=lambda:torch.eye(3).reshape(1,1,9))))
    result=api().mechanical_readback(runtime)
    assert result['physx_mass']==[[2.]] and result['declared_mass']==[[99.]]
    assert result['physx_inertia']==[[[1.,0.,0.,0.,1.,0.,0.,0.,1.]]]


def test_absent_physics_readback_fails_instead_of_guessing():
    with pytest.raises(ValueError,match='mechanical_readback_unavailable'):
        api().mechanical_readback(SimpleNamespace())

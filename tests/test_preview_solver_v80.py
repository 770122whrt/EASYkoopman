"""Numerical-interior and protocol contracts, not new hull simulations."""
import importlib
import numpy as np
import pytest
from test_control_separation_v79 import setup
from koopman.feedback_preview_v79 import audit_observed_pwm


def api(name):
    assert importlib.util.find_spec(name), 'v80 implementation missing'
    return importlib.import_module(name)


def test_planning_margin_is_stricter_than_observed_margin():
    mod=api('koopman.preview_solver_v80')
    c,m,d,_,origin,x=setup()
    from koopman.model_separation_v79 import make_predictor
    checker=mod.ExactChecker(d,make_predictor('nominal_physics',m,c),horizon=2)
    # base depth-only command maps to four equal raw PWM values.
    command=np.array([0,0,0,float(np.float32(.02))+2.5e-6])
    assert audit_observed_pwm(np.array([command[-1]]*4),np.array([command[-1]]*4))['accepted']
    result=checker.check(origin,x,np.tile(command,(2,1)),command,x[:5])
    assert not result['feasible'] and result['reason']=='planning_pwm_interior'
    command[-1]=float(np.float32(.02))+3.5e-6
    assert checker.check(origin,x,np.tile(command,(2,1)),command,x[:5])['feasible']


def test_only_deadzone_constraint_bounds_are_tightened():
    mod=api('koopman.preview_solver_v80')
    h,n=20,6
    lower=np.full(60*h+h*(4+2*n),-1.)
    expected=[]
    for k in range(h):
        ids=np.arange(60*h+k*(4+2*n)+4+n,60*h+(k+1)*(4+2*n))
        lower[ids]=2e-6;expected.extend(ids)
    tighter=mod.tighten_deadzone_bounds(lower,h,n)
    np.testing.assert_array_equal(np.flatnonzero(tighter!=lower),expected)
    assert np.all(tighter[expected]==4e-6)
    with pytest.raises(ValueError,match='constraint_layout'):
        mod.tighten_deadzone_bounds(lower[:-1],h,n)
    corrupted=lower.copy();corrupted[expected[0]]=0
    with pytest.raises(ValueError,match='constraint_layout'):
        mod.tighten_deadzone_bounds(corrupted,h,n)


def test_protocol_keeps_one_factor_and_rejects_feedback_preview():
    mod=api('workflows.protocol_v80')
    a=mod.case_spec('base','identified_physics',False,'pitch_pos')
    b=mod.case_spec('base','identified_physics',True,'pitch_pos')
    assert {k for k in a if a[k]!=b[k]}=={'preview_enabled'}
    assert a['controls']==60 and a['profile']=='depth4_h20'
    opposite=mod.case_spec('base','identified_physics',False,'pitch_neg')
    assert opposite['reference'][3]==-a['reference'][3]
    with pytest.raises(ValueError,match='feedback_preview'):
        mod.case_spec('base','feedback',True,'pitch_pos')


@pytest.mark.parametrize('configuration',['base','uuv4','long_body','uuv6'])
def test_backend_preview_matches_execution_allocation_without_consuming(configuration):
    mod=api('koopman.backend_gate_v80')
    from workflows.control_seam_v23 import ControlKernel
    kernel=ControlKernel(configuration);env=kernel.env
    before=env.old_actions.clone();command=np.array([.011,.033,0.,.042],dtype=np.float32)
    got=mod.backend_pwm(env,command)
    expected=kernel.command(command,pre_tam=True)
    np.testing.assert_array_equal(got['pwm_raw'],expected['pwm_raw'])
    np.testing.assert_array_equal(got['pwm'],expected['pwm'])
    np.testing.assert_array_equal(before.numpy(),env.old_actions.numpy())
    assert not hasattr(env,'_direct_index_v24')

from dataclasses import replace
import inspect
import numpy as np
import pytest
from koopman.projected_edmd_v24 import PhysicalContext
from koopman.physical_prediction_v29 import known_step
from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS
from workflows.workpoint_v27 import mechanics


def context(name='base'):
    m=mechanics(name)
    return PhysicalContext(m['mass_kg'],m['inertia_kg_m2'],m['cob_m'],m['volume_m3'],
        EMBODIMENT_CONFIGS[name]['drag_multiplier'],rho=m['water_density_kg_m3'])


def state():return np.array([5.5,1.,0.,0.,0.,0.,0.,0.,0.,0.,0.])
def physics(x,a,c):return known_step(x,a,c,angular_damping=float(np.float32(.05)),gyroscopic=True)


def run(commands,history=None,**overrides):
    from koopman.command_prediction_v36 import forecast_commands
    past=np.zeros((0,4)) if history is None else history
    args=dict(initial_state=state(),issued_control_history=past,planned_commands=commands,
        origin_control=len(past)//2,configuration='base',context=context(),predictor=physics)
    args.update(overrides)
    return forecast_commands(**args)


def test_branch_calls_and_input_arrays_are_independent():
    a=np.array([[0,0,0,.2],[0,0,0,-.1]]);b=np.array([[.1,-.1,.1,.2],[0,0,0,0.]])
    history=np.tile([0,0,0,.12],(4,1));original=history.copy();aa=a.copy();x=state();xx=x.copy()
    first=run(a,history,initial_state=x);other=run(b,history);again=run(a,history,initial_state=x)
    assert first['complete'] and other['complete'] and again['complete']
    for key in ('predictions','pwm','rotor_speed','acceleration','applied_control','physics_time_s'):
        np.testing.assert_array_equal(first[key],again[key])
    assert not np.array_equal(first['predictions'],other['predictions'])
    np.testing.assert_array_equal(history,original);np.testing.assert_array_equal(a,aa);np.testing.assert_array_equal(x,xx)


def test_held_command_has_two_different_actuator_substeps_and_immediate_effect():
    r=run(np.array([[0,0,0,.2]]))
    assert r['complete'] and r['predictions'].shape==(2,11) and r['rotor_speed'].shape==(2,8)
    np.testing.assert_array_equal(r['pwm'][0],r['pwm'][1])
    assert not np.array_equal(r['rotor_speed'][0],r['rotor_speed'][1])
    assert not np.array_equal(r['acceleration'][0],r['acceleration'][1])
    assert np.linalg.norm(r['predictions'][0,5:])>0
    assert r['origin_actuator_time_s']==0 and np.all(np.diff(r['physics_time_s'])>0)


def test_history_is_inherited_even_when_next_command_is_zero():
    history=np.tile([0,0,0,.2],(4,1));warm=run(np.zeros((1,4)),history);cold=run(np.zeros((1,4)))
    assert np.linalg.norm(warm['origin_rotor_speed'])>0
    assert np.linalg.norm(warm['acceleration'][0])>0 and not np.any(cold['acceleration'])
    assert warm['origin_actuator_time_s']>0


@pytest.mark.parametrize('history,origin',[(np.zeros((1,4)),0),(np.zeros((2,4)),0),(np.zeros((0,4)),1),(np.zeros((0,4)),True)])
def test_incomplete_history_or_inconsistent_origin_is_rejected(history,origin):
    with pytest.raises(ValueError,match='command_history'):run(np.zeros((1,4)),history,origin_control=origin)


def test_context_configuration_mismatch_is_rejected():
    with pytest.raises(ValueError,match='command_context'):run(np.zeros((1,4)),context=context('heavy_moderate'))
    for key in ('mass','volume','drag_multiplier','rho','beta','gravity'):
        c=context();bad=replace(c,**{key:getattr(c,key)*1.1})
        with pytest.raises(ValueError,match='command_context'):run(np.zeros((1,4)),context=bad)
    with pytest.raises(ValueError):run(np.zeros((1,4)),configuration='unknown')


def test_underactuated_axis_is_masked_before_pwm_and_history_replay():
    r=run(np.array([[0,0,.5,0.]]),configuration='uuv4',context=context('uuv4'))
    assert r['complete'] and r['control_mask'][2]==0 and r['rotor_speed'].shape==(2,4)
    assert not np.any(r['applied_control']) and not np.any(r['pwm']) and not np.any(r['acceleration'])


def test_invalid_state_future_commands_and_future_truth_are_rejected():
    from koopman.command_prediction_v36 import forecast_commands
    for bad in (np.full((1,4),np.nan),np.ones((1,4)),np.zeros((1,6)),np.zeros((0,4)),np.zeros((129,4))):
        with pytest.raises(ValueError):run(bad)
    for bad in (np.zeros(11),np.full(11,np.nan)):
        with pytest.raises(ValueError):run(np.zeros((1,4)),initial_state=bad)
    assert not any('truth' in k or 'measured' in k for k in inspect.signature(forecast_commands).parameters)
    with pytest.raises(TypeError):run(np.zeros((1,4)),future_truth=np.zeros((2,11)))


def test_partial_numerical_failure_never_returns_complete():
    calls=[]
    def bad(x,a,c):
        calls.append(1)
        return physics(x,a,c) if len(calls)==1 else np.full((1,11),np.nan)
    r=run(np.array([[0,0,0,.2],[0,0,0,.2]]),predictor=bad)
    assert not r['complete'] and r['predictions'].shape==(1,11)
    assert r['failure']['completed_physics_ticks']==1 and r['failure']['physics_substep']==1
    assert r['completed_control_intervals']==0

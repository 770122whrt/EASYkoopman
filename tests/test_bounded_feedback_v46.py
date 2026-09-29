"""Source-map equality, physically meaningful demand and bounded rejection."""
from dataclasses import replace
import time
import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from test_prepared_projected_v40 import context
from test_bounded_mpc_v44 import world_yaw
from workflows.control_seam_v23 import ControlKernel
from workflows.workpoint_v27 import _steady, ACCELERATION_TOLERANCE


@pytest.mark.parametrize('name',SUPPORTED_EMBODIMENTS)
def test_prepared_steady_map_retains_original_float32_curve_wrench_and_deadzone(name):
    from koopman.bounded_feedback_v46 import PreparedSteadyMap
    candidate=PreparedSteadyMap(name,context(name)); original=ControlKernel(name)
    drive=list(np.random.default_rng(460).uniform(-.95,.95,(30,4)))
    for value in (-.95,.95,0.,-.02,.02,np.nextafter(np.float32(.02),np.float32(0)),np.nextafter(np.float32(.02),np.float32(1))):
        for axis in range(4):
            u=np.zeros(4);u[axis]=value;drive.append(u)
    for u in drive:
        wrench,sent=_steady(original,u); got=candidate.evaluate(u)
        for key in ('virtual_control','pwm_raw','pwm'):
            np.testing.assert_allclose(got[key],sent[key],rtol=1e-12,atol=1e-12,err_msg=key)
        np.testing.assert_allclose(got['wrench'],wrench,rtol=1e-12,atol=1e-12)
    changed=candidate.evaluate([.01,-.02,.03,.12]);changed['wrench'][:]=99
    assert not np.any(candidate.evaluate([.01,-.02,.03,.12])['wrench']==99)


def initial():return np.array([5.5,1.,0,0,0,0,0,0,0,0,0])


@pytest.mark.parametrize('name',SUPPORTED_EMBODIMENTS)
def test_depth_feedback_direction_and_projected_vertical_force_are_correct(name):
    from koopman.bounded_feedback_v46 import feedback_demand,FeedbackConfig
    c=context(name);x=initial();x[1:5]=[np.cos(.15),np.sin(.15),0,0]
    ref=np.array([5.8,1.,0,0,0]);up_z=np.cos(.3)
    got=feedback_demand(x,ref,name,c,FeedbackConfig())
    assert got['desired_vertical_acceleration']>0
    force=got['target_wrench'][2]
    actual=(force*up_z+(c.rho*c.volume-c.mass)*c.gravity)/c.mass
    assert actual==pytest.approx(got['desired_vertical_acceleration'],abs=1e-12)
    x[0]=6.;assert feedback_demand(x,ref,name,c,FeedbackConfig())['desired_vertical_acceleration']<0
    x=initial();x[7]=.1;ref[0]=5.5
    assert feedback_demand(x,ref,name,c,FeedbackConfig())['desired_vertical_acceleration']<0


@pytest.mark.parametrize('name',['uuv4','uuv4_angled'])
@pytest.mark.parametrize('yaw',[-2.8,-.4,.7,2.9])
def test_reduced_attitude_demand_is_invariant_to_world_yaw(name,yaw):
    from koopman.bounded_feedback_v46 import feedback_demand,FeedbackConfig
    x=initial();x[1:5]=[.97,.12,-.09,.05];x[1:5]/=np.linalg.norm(x[1:5]);x[5:]=[.01,.02,.03,.04,.05,.7]
    y=x.copy();y[1:5]=world_yaw(x[1:5],yaw)
    ref=initial()[:5]
    a=feedback_demand(x,ref,name,context(name),FeedbackConfig())
    b=feedback_demand(y,ref,name,context(name),FeedbackConfig())
    for key in ('target_wrench','desired_angular_acceleration','desired_vertical_acceleration'):
        np.testing.assert_allclose(a[key],b[key],rtol=1e-12,atol=1e-12)
    assert a['target_wrench'][5]==b['target_wrench'][5]==0


def test_full_attitude_and_reference_are_respected_with_quaternion_sign_invariance():
    from koopman.bounded_feedback_v46 import feedback_demand,FeedbackConfig
    x=initial();x[1:5]=world_yaw(x[1:5],.4);ref=initial()[:5]; c=context('base'); cfg=FeedbackConfig()
    a=feedback_demand(x,ref,'base',c,cfg)
    assert a['desired_angular_acceleration'][2]<0
    x[1:5]*=-1
    b=feedback_demand(x,ref,'base',c,cfg)
    np.testing.assert_allclose(a['target_wrench'],b['target_wrench'],rtol=1e-12,atol=1e-12)
    ref[1:5]=x[1:5]
    assert np.max(np.abs(feedback_demand(x,ref,'base',c,cfg)['desired_angular_acceleration']))<1e-12


@pytest.mark.parametrize('name',SUPPORTED_EMBODIMENTS)
def test_bounded_inverse_accepts_reachable_nearby_target_only_after_physical_checks(name):
    from koopman.bounded_feedback_v46 import PreparedSteadyMap,FeedbackConfig
    m=PreparedSteadyMap(name,context(name))
    previous=np.array([.01,-.01,.02,.13])*m.mask
    desired=previous+np.array([.009,-.009,.009,.009])*m.mask
    target=m.evaluate(desired)['wrench']
    result=m.inverse(target,previous,previous-.01*m.mask,previous+.01*m.mask,FeedbackConfig(timeout_ms=2000.),deadline=time.perf_counter()+2)
    assert result['status']=='ready'
    u=result['command'];assert np.all(np.abs(u-previous)<=.01+1e-7)
    assert np.all(np.abs((m.evaluate(u)['wrench']-target)/m.scale)<=ACCELERATION_TOLERANCE)
    assert np.max(np.abs(m.evaluate(u)['pwm_raw']))<=.95


def make_policy(name='base',**cfg):
    from koopman.bounded_feedback_v46 import BoundedFeedback,FeedbackConfig
    from koopman.bounded_mpc_v44 import SupportDomain
    c=context(name);d=SupportDomain.diagnostic(name,c,'a'*64)
    return BoundedFeedback(d,c,config=FeedbackConfig(timeout_ms=2000.,**cfg),allow_diagnostic=True)


@pytest.mark.parametrize('name',SUPPORTED_EMBODIMENTS)
def test_startup_is_prepared_before_control_and_proposal_never_claims_actual_issue(name):
    policy=make_policy(name);x=initial();ref=x[:5].copy()
    assert policy.decide(x,ref,previous=None)['status']=='no_command'
    seed=policy.prepare_startup(x,ref)
    assert seed['status']=='prepared'
    result=policy.decide(x,ref,previous=None)
    assert result['status']=='ready' and result['startup_exception_requested'] is True
    assert result['runtime_eligible'] is False
    assert result['actual_history_advanced'] is False
    np.testing.assert_allclose(result['command'],seed['command'],rtol=1e-12,atol=1e-12)
    # A changed startup state/reference cannot borrow the precomputed solution.
    changed=x.copy();changed[0]+=.05
    assert policy.decide(changed,ref,previous=None)['status']=='no_command'


@pytest.mark.parametrize('bad',['state','reference','previous','unreachable','raw_saturation','timeout'])
def test_failure_has_no_command_and_does_not_relabel_achieved_wrench_as_target(bad,monkeypatch):
    p=make_policy();x=initial();ref=x[:5].copy();previous=np.zeros(4)
    if bad=='state':x[0]=1.
    if bad=='reference':ref[1:5]=0
    if bad=='previous':previous[0]=np.nan
    if bad=='unreachable':ref[0]=7.
    if bad=='raw_saturation':previous[:]=[.4,.4,0,.4]
    if bad=='timeout':
        p.config=replace(p.config,timeout_ms=5.)
        old=p.steady.evaluate
        def slow(u):time.sleep(.01);return old(u)
        monkeypatch.setattr(p.steady,'evaluate',slow)
    result=p.decide(x,ref,previous=previous)
    assert result['status']=='no_command' and result['command'] is None and result['reason']
    assert result['runtime_eligible'] is False and result['actual_history_advanced'] is False


def test_unverified_fit_domain_cannot_enter_normal_constructor():
    from koopman.bounded_feedback_v46 import BoundedFeedback
    from koopman.bounded_mpc_v44 import SupportDomain
    c=context('base');d=SupportDomain.diagnostic('base',c,'a'*64)
    with pytest.raises(ValueError):BoundedFeedback(d,c)
    with pytest.raises(ValueError):BoundedFeedback(d,context('heavy_moderate'),allow_diagnostic=True)


def test_startup_binding_accepts_equivalent_quaternion_signs():
    policy=make_policy();x=initial();ref=x[:5].copy();policy.prepare_startup(x,ref)
    x[1:5]*=-1;ref[1:5]*=-1
    assert policy.decide(x,ref,previous=None)['status']=='ready'


def test_swapped_prepared_configuration_cannot_be_used_with_old_domain():
    from koopman.bounded_feedback_v46 import PreparedSteadyMap
    policy=make_policy();policy.steady=PreparedSteadyMap('uuv6',context('uuv6'))
    result=policy.decide(initial(),initial()[:5],previous=np.zeros(4))
    assert result['status']=='no_command' and result['reason']=='policy_binding_changed'


@pytest.mark.parametrize('field,value',[('height_kp',0.),('height_kp',np.nan),('timeout_ms',0.),('iterations',99),('slew',-.01)])
def test_invalid_parameters_cannot_disable_contracts(field,value):
    from koopman.bounded_feedback_v46 import FeedbackConfig
    with pytest.raises(ValueError):FeedbackConfig(**{field:value})

"""Separate static inversion from honest, rate-limited tracking proposals."""
from dataclasses import replace
import time

import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from test_prepared_projected_v40 import context
from test_bounded_feedback_v46 import initial
from workflows.control_seam_v23 import ControlKernel
from workflows.workpoint_v27 import _steady, ACCELERATION_TOLERANCE


def mapping(name='base'):
    from koopman.bounded_feedback_v47 import PreparedTrackingMap
    return PreparedTrackingMap(name, context(name))


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
@pytest.mark.parametrize('depth', [-.13, .13])
def test_geometry_seed_reaches_known_static_target_from_zero_deadzone(name, depth):
    from koopman.bounded_feedback_v46 import FeedbackConfig
    m = mapping(name)
    expected, _ = _steady(ControlKernel(name), [0, 0, 0, depth])
    target = expected.copy()
    got = m.static_inverse(target, np.zeros(4), FeedbackConfig(), deadline=time.perf_counter()+2)
    assert got['status'] == 'ready', got
    actual, sent = _steady(ControlKernel(name), got['command'].copy())
    assert np.all(np.abs((actual-target)/m.scale) <= ACCELERATION_TOLERANCE)
    assert 1-np.max(np.abs(sent['pwm_raw'])) >= .05
    np.testing.assert_array_equal(target, expected)
    assert got['inspection']['physical_residual_accepted']


def limit(m, target, full, previous, lower=None, upper=None):
    from koopman.bounded_feedback_v47 import limit_tracking_command
    return limit_tracking_command(m, target, full, previous,
        -.95*m.mask if lower is None else lower,
        .95*m.mask if upper is None else upper, .01, deadline=time.perf_counter()+2)


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
def test_limited_command_is_legal_but_does_not_relabel_original_target(name):
    m = mapping(name); full = np.array([0., 0, 0, .18]); previous = np.array([0., 0, 0, .10])
    target = m.evaluate(full)['wrench']; original = target.copy()
    result = limit(m, target, full, previous)
    assert result['status'] == 'ready' and result['tracking_status'] == 'tracking_limited'
    assert result['static_inspection']['physical_residual_accepted']
    assert not result['inspection']['physical_residual_accepted']
    assert 'slew' in result['limitations'] and 0 < result['alpha'] < 1
    assert np.max(np.abs(result['command']-previous)) <= .01+1e-7
    wrench, _ = _steady(ControlKernel(name), result['command'].copy())
    np.testing.assert_allclose(result['inspection']['acceleration_error'], (wrench-target)/m.scale, rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(target, original)
    np.testing.assert_array_equal(result['requested_wrench'], original)
    assert not result['target_rewritten']


def test_internal_static_reference_can_exceed_fit_box_but_actual_command_cannot():
    m=mapping(); full=np.array([0.,0,0,.18]); old=np.array([0.,0,0,.149])
    upper=.95*m.mask;upper[3]=.15;target=m.evaluate(full)['wrench']
    got=limit(m,target,full,old,upper=upper)
    assert got['status']=='ready' and 'support' in got['limitations']
    assert not got['static_reference_in_support']
    assert got['command'][3] <= .15+1e-7
    assert got['static_command'][3] > .15
    assert got['tracking_status']=='tracking_limited'


def test_synthetic_command_sequence_crosses_deadzone_without_rate_violation():
    # Only command geometry is exercised; this is not a simulated hull rollout.
    m=mapping(); full=np.array([0.,0,0,.0301]);target=m.evaluate(full)['wrench']
    previous=np.zeros(4);records=[]
    for _ in range(5):
        got=limit(m,target,full,previous)
        assert got['status']=='ready'
        assert np.max(np.abs(got['command']-previous))<=.01+1e-7
        assert got['inspection']['minimum_deadzone_distance_pwm']>2e-6
        records.append(got);previous=got['command'].copy()
    assert records[0]['tracking_status']=='tracking_limited'
    assert any('deadzone_backoff' in r['limitations'] for r in records)
    assert records[-1]['tracking_status']=='target_attained'
    assert np.linalg.norm(records[-1]['inspection']['steady_wrench'])>0


def test_support_boundary_hold_is_explicitly_zero_progress_not_target_success():
    m=mapping();full=np.array([0.,0,0,.18]);old=np.array([0.,0,0,.15])
    upper=.95*m.mask;upper[3]=old[3]
    got=limit(m,m.evaluate(full)['wrench'],full,old,upper=upper)
    assert got['status']=='ready' and got['zero_progress']
    assert got['alpha']==0 and got['tracking_status']=='tracking_limited'
    assert 'support' in got['limitations']


def test_all_finite_backoffs_near_deadzone_can_reject_without_issuing_old_command():
    m=mapping();full=np.array([0.,0,0,.0301]);old=np.array([0.,0,0,.019997])
    upper=.95*m.mask;upper[3]=.02
    got=limit(m,m.evaluate(full)['wrench'],full,old,upper=upper)
    assert got['status']=='no_command' and got['command'] is None
    assert got['reason']=='no_admissible_limited_command'


@pytest.mark.parametrize('bad', ['full_residual','full_pwm','previous_outside','target_nan','masked_axis','deadline'])
def test_limiter_rejects_invalid_or_unqualified_inputs(bad):
    m=mapping('uuv4');full=np.array([0.,0,0,.18]);old=np.array([0.,0,0,.10])
    target=m.evaluate(full)['wrench'];lower=-.95*m.mask;upper=.95*m.mask
    if bad=='full_residual':target[2]+=50
    if bad=='full_pwm':full[:]=[.5,.5,0,.5];target=m.evaluate(full)['wrench']
    if bad=='previous_outside':upper[3]=.09
    if bad=='target_nan':target[0]=np.nan
    if bad=='masked_axis':old[2]=.01
    if bad=='deadline':
        from koopman.bounded_feedback_v47 import limit_tracking_command
        with pytest.raises(TimeoutError):
            limit_tracking_command(m,target,full,old,lower,upper,.01,deadline=time.perf_counter()-1)
        return
    got=limit(m,target,full,old,lower,upper)
    assert got['status']=='no_command' and got['command'] is None


def policy(name='base'):
    from koopman.bounded_feedback_v47 import TrackingFeedback
    from koopman.bounded_feedback_v46 import FeedbackConfig
    from koopman.bounded_mpc_v44 import SupportDomain
    c=context(name);d=SupportDomain.diagnostic(name,c,'a'*64)
    return TrackingFeedback(d,c,config=FeedbackConfig(timeout_ms=2000),allow_diagnostic=True)


def test_policy_reports_depth_tracking_limitation_without_mutating_actual_history():
    p=policy();x=initial();ref=x[:5].copy();ref[0]+=.05
    got=p.decide(x,ref,previous=np.zeros(4))
    assert got['status']=='ready', got
    assert got['tracking_status']=='tracking_limited'
    assert got['runtime_eligible'] is False and got['actual_history_advanced'] is False
    assert got['startup_exception_requested'] is False
    np.testing.assert_array_equal(got['demand']['target_wrench'],got['requested_wrench'])


def test_startup_still_requires_preparation_and_matching_reset_reference():
    p=policy('heavy_moderate');x=initial();ref=x[:5].copy()
    assert p.decide(x,ref,previous=None)['status']=='no_command'
    assert p.prepare_startup(x,ref)['status']=='prepared'
    x[1:5]*=-1;ref[1:5]*=-1
    got=p.decide(x,ref,previous=None)
    assert got['status']=='ready' and got['startup_exception_requested']
    assert got['tracking_status']=='target_attained' and not got['runtime_eligible']
    ref[0]+=.05
    assert p.decide(x,ref,previous=None)['status']=='no_command'


def test_timeout_returns_no_command_even_if_internal_calculation_eventually_succeeds(monkeypatch):
    p=policy();p.config=replace(p.config,timeout_ms=1)
    original=p.steady.evaluate
    def delayed(u):
        time.sleep(.005)
        return original(u)
    monkeypatch.setattr(p.steady,'evaluate',delayed)
    result=p.decide(initial(),initial()[:5],previous=np.zeros(4))
    assert result['status']=='no_command' and result['reason']=='timeout' and result['command'] is None


def test_policy_rejects_changed_geometry_binding():
    p=policy();p.steady=mapping('uuv6')
    got=p.decide(initial(),initial()[:5],previous=np.zeros(4))
    assert got['status']=='no_command' and got['reason']=='policy_binding_changed'


def test_unverified_domain_cannot_be_used_by_tracking_policy_without_diagnostic_opt_in():
    from koopman.bounded_feedback_v47 import TrackingFeedback
    from koopman.bounded_mpc_v44 import SupportDomain
    c=context('base');d=SupportDomain.diagnostic('base',c,'a'*64)
    with pytest.raises(ValueError,match='provenance'):
        TrackingFeedback(d,c)

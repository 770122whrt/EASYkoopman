import time
import numpy as np
import pytest
from test_prepared_projected_v40 import context
from koopman.bounded_mpc_v44 import SupportDomain
from koopman.bounded_feedback_v46 import FeedbackConfig
from koopman.cached_checks_v53 import CachedTrackingFeedback


@pytest.mark.parametrize('z,vz',[(5.490192890167236,-.013051971793174744),
                               (5.487166881561279,-.014804757200181484)])
def test_observed_static_residual_failure_becomes_explicit_bounded_tracking(z,vz):
    from koopman.inexact_tracking_v66 import InexactTrackingFeedback
    c=context('base');d=SupportDomain.diagnostic('base',c,'0'*64)
    cfg=FeedbackConfig(timeout_ms=1000)
    x=np.array([z,1,0,0,0,0,0,vz,0,0,0],float);ref=[5.48,1,0,0,0]
    old=CachedTrackingFeedback(d,c,config=cfg,allow_diagnostic=True).decide(x,ref,previous=np.zeros(4))
    assert old['reason']=='static_inverse_not_found'
    new=InexactTrackingFeedback(d,c,config=cfg,allow_diagnostic=True).decide(x,ref,previous=np.zeros(4))
    assert new['status']=='ready' and new['tracking_status']=='tracking_limited'
    assert new['inspection']['command_constraints_accepted']
    assert not new['static_inspection']['physical_residual_accepted']
    assert new['target_rewritten'] is False
    assert 'static_residual_unmet' in new['limitations']
    np.testing.assert_array_equal(new['requested_wrench'],old['requested_wrench'])
    assert np.max(np.abs(new['command']))<=cfg.slew+1e-7


def test_invalid_best_candidate_cannot_be_used(monkeypatch):
    from koopman.inexact_tracking_v66 import InexactTrackingMap
    from koopman.cached_checks_v53 import CachedTrackingMap
    c=context('base');m=InexactTrackingMap('base',c)
    answer=dict(status='no_command',reason='static_inverse_not_found',command=None,
                inspection=dict(command_constraints_accepted=False))
    monkeypatch.setattr(CachedTrackingMap,'static_inverse',lambda *a,**k:answer)
    assert m.static_inverse(np.zeros(6),np.zeros(4),FeedbackConfig(),deadline=time.perf_counter()+1)['status']=='no_command'


def test_timeout_is_never_reinterpreted(monkeypatch):
    from koopman.inexact_tracking_v66 import InexactTrackingMap
    from koopman.cached_checks_v53 import CachedTrackingMap
    def timeout(*a,**k):raise TimeoutError('deadline')
    monkeypatch.setattr(CachedTrackingMap,'static_inverse',timeout)
    with pytest.raises(TimeoutError):
        InexactTrackingMap('base',context('base')).static_inverse(np.zeros(6),np.zeros(4),FeedbackConfig(),deadline=time.perf_counter()+1)


@pytest.mark.parametrize('bad',[False,True])
def test_recovery_keeps_prefix_and_rejects_illegal_prefix(bad):
    from koopman.inexact_tracking_v66 import InexactRecoveryBaseline
    c=context('base');d=SupportDomain.diagnostic('base',c,'0'*64)
    b=InexactRecoveryBaseline(d,c,config=FeedbackConfig(timeout_ms=1000),allow_diagnostic=True)
    x=np.array([5.490192890167236,1,0,0,0,0,0,-.013051971793174744,0,0,0])
    prefix=np.zeros((8,4))
    if bad:prefix[3,0]=.2
    r=b.build(x,[5.48,1,0,0,0],np.zeros(4),prefix,horizon=20,deadline=time.perf_counter()+2)
    if bad:
        assert r['status']=='no_baseline' and r['commands'] is None
    else:
        assert r['status']=='ready'
        np.testing.assert_array_equal(r['commands'][:8],prefix)
        assert all('static_residual_unmet' in t['limitations'] for t in r['tracking'])
        assert not r['target_rewritten'] and not r['future_feedback_assumed']
        assert np.max(np.abs(np.diff(r['commands'],axis=0)))<=.01+1e-7


def test_exact_inverse_path_retains_original_feedback_result():
    from koopman.inexact_tracking_v66 import InexactTrackingFeedback
    c=context('base');d=SupportDomain.diagnostic('base',c,'0'*64)
    cfg=FeedbackConfig(timeout_ms=1000)
    x=np.array([5.5,1,0,0,0,0,0,0,0,0,0]);ref=[5.48,1,0,0,0]
    old=CachedTrackingFeedback(d,c,config=cfg,allow_diagnostic=True).decide(x,ref,previous=np.zeros(4))
    new=InexactTrackingFeedback(d,c,config=cfg,allow_diagnostic=True).decide(x,ref,previous=np.zeros(4))
    assert old['status']==new['status']=='ready'
    np.testing.assert_array_equal(old['command'],new['command'])
    np.testing.assert_array_equal(old['requested_wrench'],new['requested_wrench'])
    assert old['limitations']==new['limitations']


def test_inexact_candidate_cannot_be_worse_than_legal_hold():
    from koopman.inexact_tracking_v66 import InexactTrackingMap,_score
    m=InexactTrackingMap('base',context('base'));old=np.zeros(4)
    r=m.static_inverse(np.array([0,0,.571123855781849,0,0,0]),old,FeedbackConfig(timeout_ms=1000),deadline=time.perf_counter()+2)
    assert r['status']=='ready'
    hold=m.inspect(old,[0,0,.571123855781849,0,0,0],-.95*m.mask,.95*m.mask)
    assert _score(r['inspection'])<=_score(hold)


@pytest.mark.parametrize('tamper',[None,'residual','target','command','status','zero','missing'])
def test_feedback_audit_recomputes_residual_truth(tamper):
    from koopman.inexact_tracking_v66 import InexactTrackingFeedback
    from workflows.validate_tracking_v66 import validate_tracking_audit
    from koopman.diagnostics_v23 import json_safe
    c=context('base');d=SupportDomain.diagnostic('base',c,'0'*64)
    fb=InexactTrackingFeedback(d,c,config=FeedbackConfig(timeout_ms=1000),allow_diagnostic=True)
    x=np.array([5.490192890167236,1,0,0,0,0,0,-.013051971793174744,0,0,0]);ref=[5.48,1,0,0,0]
    fb.physics_index=lambda:2
    r=fb.decide(x,ref,previous=np.zeros(4))
    # A preceding confirmed interval supplies the actual previous command.
    data=dict(case=dict(reference=ref,controller='mpc'),intervals=[dict(decision=dict(packet=dict(command=[0]*4))),
        dict(decision=dict(packet=dict(command=r['command'])))],substeps=[{}, {},dict(before=dict(state_11=[x]))],
        inexact_feedback_audit=json_safe(fb.audit),arbitration_audit=[dict(method='choose',physics_index=2,result=dict(status='fallback'))])
    if tamper=='residual':data['inexact_feedback_audit'][0]['result']['static_inspection']['physical_residual_accepted']=True
    if tamper=='target':data['inexact_feedback_audit'][0]['result']['requested_wrench'][2]+=1
    if tamper=='command':data['inexact_feedback_audit'][0]['result']['command'][3]+=.1
    if tamper=='zero':data['inexact_feedback_audit'][0]['result']['zero_progress']=False
    if tamper=='missing':data['arbitration_audit'].append(dict(method='choose',physics_index=0,result=dict(status='fallback')))
    if tamper=='status':data['inexact_feedback_audit'][0]['result']['tracking_status']='target_attained'
    if tamper:
        with pytest.raises(ValueError):validate_tracking_audit(data,d,c)
    else:
        got=validate_tracking_audit(data,d,c)
        assert got['static_residual_unmet']==1 and got['tracking_limited']==1

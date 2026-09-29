import copy
import numpy as np
import pytest


def fixture_scores():
    from workflows.sparse_evaluation_v30 import policy
    from workflows.identification_protocol_v29 import cases
    result=[]
    for q in [q for q in cases() if q['role']=='validation']:
        for h in policy()['conditional_horizons']:
            for f,scope,error in [('persistence','none',.1),('known_physics','none',.0004)]+[(f,s,e) for f,e in [('nonlinear',.0005),('linear',.01)] for s in ('pooled','local','heldout')]:
                result.append({'run_id':q['run_id'],'configuration':q['configuration'],'family':f,'scope':scope,
                    'mode':'conditional_projected','horizon_control_intervals':h,'origins':193-h,
                    'complete_aggregate':True,'failed_origins':0,'endpoint_rmse':[error]*4,'path_rmse':[error]*4})
    return result


def test_pilot_gate_requires_all_cases_and_catches_a_bad_configuration():
    from workflows.sparse_evaluation_v30 import conditional_gate
    scores=fixture_scores();assert conditional_gate(scores)['pass']
    altered=copy.deepcopy(scores)
    target=next(r for r in altered if r['family']=='nonlinear' and r['scope']=='heldout' and r['horizon_control_intervals']==60)
    target['endpoint_rmse']=[1]*4
    assert not conditional_gate(altered)['pass']
    with pytest.raises(ValueError,match='sparse_score_inventory'):conditional_gate(scores[:-1])
    with pytest.raises(ValueError,match='sparse_score_duplicate'):conditional_gate(scores+[scores[0]])


def test_a_failed_required_origin_cannot_receive_a_finite_average():
    from workflows.sparse_evaluation_v30 import conditional_gate
    scores=fixture_scores();r=next(r for r in scores if r['family']=='nonlinear' and r['scope']=='pooled')
    r.update(complete_aggregate=False,failed_origins=1,endpoint_rmse=None,path_rmse=None)
    assert not conditional_gate(scores)['pass']
    r['endpoint_rmse']=[0]*4
    with pytest.raises(ValueError,match='sparse_score_failure_semantics'):conditional_gate(scores)


def test_policy_short_prefix_survives_a_later_failure_without_relabelling_long_prefix():
    from workflows.sparse_evaluation_v30 import score_policy_prefix
    x=np.tile([5.5,1,0,0,0,0,0,0,0,0,0],(50,1))
    forecast={'complete':False,'failure':{'completed_physics_ticks':50},'predictions':x.copy()}
    assert score_policy_prefix(x,forecast,20)['complete_aggregate']
    assert not score_policy_prefix(x,forecast,60)['complete_aggregate']


def test_lift_decoder_restores_body_velocity_from_world_observable():
    from workflows.sparse_evaluation_v30 import decode_lift
    from koopman.sparse_world_edmd_v30 import lift
    from koopman.projected_edmd_v24 import PhysicalContext
    c=PhysicalContext(1,[1,1,1],[0,0,0],1/997,0)
    x=np.array([[5.5,2**-.5,0,0,2**-.5,.1,.2,.3,.2,0,.1]])
    y=decode_lift(lift(x,c,'nonlinear'))
    np.testing.assert_allclose(y[:,5:],x[:,5:],atol=1e-12)
    assert abs(np.dot(y[0,1:5],x[0,1:5]))==pytest.approx(1)


def test_policy_gate_requires_both_origins_and_rejects_required_failure():
    from workflows.sparse_evaluation_v30 import policy_gate
    scores=[dict(r,mode='policy_self_recurrence',origin_control=o) for r in fixture_scores()
            if r['scope']!='local' and r['horizon_control_intervals']!=1 for o in (128,176)]
    assert policy_gate(scores)['pass']
    with pytest.raises(ValueError,match='sparse_score_inventory'):policy_gate(scores[:-1])
    r=next(r for r in scores if r['family']=='nonlinear')
    r.update(complete_aggregate=False,failed_origins=1,endpoint_rmse=None,path_rmse=None)
    assert not policy_gate(scores)['pass']


def test_unprojected_identity_motion_has_correct_origins_and_exact_readout():
    from types import SimpleNamespace
    from workflows.sparse_evaluation_v30 import unprojected_rollout
    from koopman.sparse_world_edmd_v30 import core_matrix
    from koopman.projected_edmd_v24 import PhysicalContext
    c=PhysicalContext(1,[1,1,1],[0,0,0],1/997,0)
    x=np.tile([5.5,1,0,0,0,.1,0,0,0,0,0],(641,1))
    model=SimpleNamespace(family='nonlinear',matrix=core_matrix('nonlinear',np.zeros(6),np.ones(6),.05),angular_damping=.05)
    r=unprojected_rollout(x,np.zeros((640,6)),model,c,60)
    assert r['origins']==133 and r['complete_aggregate'] and not r['feature_reprojection']
    assert max(r['endpoint_rmse'])<1e-7
def test_decode_nonfinite_lift_does_not_hide_failure():
    from workflows.sparse_evaluation_v30 import decode_lift
    f=np.zeros((1,53));f[:,0]=5.5;f[:,1:10]=np.eye(3).reshape(1,9);f[:,-1]=np.inf
    assert not np.isfinite(decode_lift(f)).all()

import copy
import numpy as np
import pytest
from koopman.projected_edmd_v24 import PhysicalContext,rotation
from koopman.sparse_world_edmd_v30 import core_matrix,feature_names,lift
from workflows.identify_sparse_world_v30 import SparseModel


def neutral():return PhysicalContext(1.,[1.,1.,1.],[0.,0.,0.],1/997,0.)
def state():return np.array([[5.5,1,0,0,0,0,0,0,0,0,0]],dtype=float)
def reference():return SparseModel('nonlinear',core_matrix('nonlinear',np.zeros(6),np.ones(6),.05),np.zeros(6),np.ones(6),.05,{})


def test_learned_height_output_is_used_instead_of_analytic_pose():
    from koopman.state_projection_v34 import projected_step
    x=state();ref=reference();A=ref.matrix.copy();A[-1,0]=.1
    y=projected_step(x,np.zeros((1,6)),neutral(),ref,A)
    assert y[0,0]==pytest.approx(5.6)
    assert ref(x,np.zeros((1,6)),neutral())[0,0]==5.5


def test_learned_rotation_changes_body_coordinates_without_changing_world_velocity():
    from koopman.state_projection_v34 import projected_step
    ref=reference();A=ref.matrix.copy();A[:,1:10]=0
    R=np.array([[0,-1,0],[1,0,0],[0,0,1]],dtype=float);A[-1,1:10]=R.reshape(-1)
    x=state();x[0,5]=1.;y=projected_step(x,np.zeros((1,6)),neutral(),ref,A)
    np.testing.assert_allclose(rotation(y[:,1:5])[0],R,atol=1e-12)
    np.testing.assert_allclose(y[0,5:8],[0,-1,0],atol=1e-12)


def test_same_step_heave_and_roll_input_effects_survive_projection():
    from koopman.state_projection_v34 import projected_step
    ref=reference();a=np.array([[0,0,1,1,0,0]],dtype=float)
    y=projected_step(state(),a,neutral(),ref,ref.matrix)
    assert y[0,0]-5.5==pytest.approx(1/120**2,abs=1e-14)
    assert np.linalg.norm(y[0,2:5])>1e-5


def test_nonphysical_auxiliary_drag_is_not_carried_into_next_step():
    from koopman.state_projection_v34 import projected_step
    ref=reference();A=ref.matrix.copy();j=feature_names('nonlinear').index('angular_quadratic_0');A[-1,j]=1e6
    x=state();a=np.zeros((1,6));y=projected_step(x,a,neutral(),ref,A);z=projected_step(y,a,neutral(),ref,A)
    np.testing.assert_allclose(z,x,atol=1e-12)
    assert lift(y,neutral(),'nonlinear')[0,j]==0


def test_rotation_readout_is_proper_and_singular_readout_is_invalid():
    from koopman.state_projection_v34 import projected_step
    ref=reference();A=ref.matrix.copy();A[:,1:10]=0;A[-1,1:10]=np.diag([-1,1,1]).reshape(-1)
    y=projected_step(state(),np.zeros((1,6)),neutral(),ref,A)
    assert np.linalg.det(rotation(y[:,1:5])[0])==pytest.approx(1)
    A[-1,1:10]=0;y=projected_step(state(),np.zeros((1,6)),neutral(),ref,A)
    assert not np.isfinite(y).all()


def test_predictor_rejects_malformed_inputs():
    from koopman.state_projection_v34 import projected_step
    ref=reference()
    for a in (np.zeros((1,4)),np.full((1,6),np.nan)):
        with pytest.raises(ValueError):projected_step(state(),a,neutral(),ref,ref.matrix)


def test_loader_binds_parent_parameters_and_readonly_matrix():
    from types import SimpleNamespace
    from workflows.identification_protocol_v29 import cases
    from workflows.identify_sparse_world_v30 import fit_model
    from workflows.controlled_lift_v33 import fit_lift_matrix
    from koopman.state_projection_v34 import from_record
    x=np.repeat(state(),641,axis=0);a=np.zeros((640,6));c=neutral()
    episodes=[SimpleNamespace(case=q,states=x,acceleration=a,context=c,acceptance={'training_eligible':True},
        source_commit='a'*40,trace_sha256='b'*64) for q in cases() if q['role']=='fit' and q['configuration']=='base']
    parent,_=fit_model(episodes,'nonlinear',['base']);parent['model_id']='fixture'
    record,_=fit_lift_matrix(episodes,parent);record['parent_sha256']='c'*64
    model=from_record(record,parent,'c'*64)
    assert not model.matrix.flags.writeable
    np.testing.assert_allclose(model(state(),np.zeros((1,6)),c),state(),atol=1e-12)
    bad=copy.deepcopy(record);bad['damping'][0]=1.
    with pytest.raises(ValueError,match='state_projection_parent'):from_record(bad,parent,'c'*64)
    with pytest.raises(ValueError,match='state_projection_parent'):from_record(record,parent,'d'*64)


def fixture_scores():
    from workflows.identification_protocol_v29 import cases
    candidates=[];baselines=[]
    for q in cases():
        if q['role']!='fit':continue
        for h in (1,20,60,128,320):
            r={'run_id':q['run_id'],'configuration':q['configuration'],'role':'fit_diagnostic',
               'horizon_control_intervals':h,'origins':1 if h==320 else 193-h,'failed_origins':0,
               'complete_aggregate':True,'endpoint_rmse':[.1]*4,'path_rmse':[.1]*4}
            for scope in ('pooled','heldout'):
                candidates.append(dict(r,scope=scope,family='nonlinear_v34',mode='full_state_projected'))
                for family,value in [('linear',.5),('nonlinear',.1)]:
                    baselines.append(dict(r,scope=scope,family=family,mode='projected',endpoint_rmse=[value]*4,path_rmse=[value]*4))
            for family,value in [('persistence',1.),('known_physics',.01)]:
                baselines.append(dict(r,scope='none',family=family,mode='projected',endpoint_rmse=[value]*4,path_rmse=[value]*4))
    return candidates,baselines


def test_fit_screen_checks_catalog_and_passes_fixed_improvement():
    from workflows.state_projection_v34 import fit_screen
    candidates,baselines=fixture_scores();r=fit_screen(candidates,baselines)
    assert r['pass'] and len(r['gates'])==12 and not r['independent_validation'] and not r['model_handoff']
    for incomplete in (candidates[:-1],candidates+[candidates[0]]):
        with pytest.raises(ValueError):fit_screen(incomplete,baselines)


def test_one_failed_origin_cannot_be_hidden_by_other_predictions():
    from workflows.state_projection_v34 import fit_screen
    candidates,baselines=fixture_scores();candidates[-1].update(complete_aggregate=False,failed_origins=1,endpoint_rmse=None,path_rmse=None)
    assert not fit_screen(candidates,baselines)['pass']


def test_zero_error_tie_does_not_claim_gain_over_linear():
    from workflows.state_projection_v34 import fit_screen
    candidates,baselines=fixture_scores()
    for r in candidates+baselines:r.update(endpoint_rmse=[0.]*4,path_rmse=[0.]*4)
    result=fit_screen(candidates,baselines)
    assert not result['pass'] and all(r['over_linear_macro']==1. for r in result['gates'])

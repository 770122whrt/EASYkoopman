import numpy as np
import pytest
from koopman.projected_edmd_v24 import PhysicalContext
from koopman.sparse_world_edmd_v30 import core_matrix, input_effect, lift


def neutral():
    return PhysicalContext(1.,[1.,1.,1.],[0.,0.,0.],1/997,0.)


def state():
    return np.array([[5.5,1,0,0,0,0,0,0,0,0,0]],dtype=float)


def model():
    from workflows.identify_sparse_world_v30 import SparseModel
    return SparseModel('nonlinear',core_matrix('nonlinear',np.zeros(6),np.ones(6),.05),np.zeros(6),np.ones(6),.05,{})


def test_zero_input_has_no_lifted_effect_even_with_drift():
    from koopman.controlled_lift_v33 import full_step_input_effect
    x=state();x[:,5:]=[.1,-.2,.3,.4,-.5,.6]
    np.testing.assert_array_equal(full_step_input_effect(x,np.zeros((1,6)),neutral(),model()),np.zeros((1,53)))


def test_heave_control_changes_height_in_the_same_physics_step():
    from koopman.controlled_lift_v33 import full_step_input_effect
    a=np.array([[0,0,1,0,0,0]],dtype=float);m=model();c=neutral();x=state()
    effect=full_step_input_effect(x,a,c,m)
    assert effect[0,0]==pytest.approx(1/120**2,abs=1e-14)
    assert input_effect(x,a,c,'nonlinear',.05)[0,0]==0
    assert effect[0,12]==pytest.approx(1/120)


def test_roll_control_changes_orientation_without_future_truth():
    from koopman.controlled_lift_v33 import full_step_input_effect
    effect=full_step_input_effect(state(),np.array([[0,0,0,1,0,0]],dtype=float),neutral(),model())
    assert np.linalg.norm(effect[:,1:10])>1e-5
    assert effect[0,13]==pytest.approx((1-.05/120)/120)


def test_input_effect_matches_full_step_counterfactual_and_accepts_tilted_state():
    from koopman.controlled_lift_v33 import full_step_input_effect
    x=state();x[0,1:5]=[.96,.12,-.08,.2];x[:,1:5]/=np.linalg.norm(x[:,1:5]);x[:,5:]=[.2,-.1,.3,.4,-.2,.1]
    c=PhysicalContext(22.7,[.37,.97,1.19],[.03,.02,.05],.0227,1.)
    a=np.array([[.1,.2,-.3,-.4,.2,.1]]);m=model()
    expected=lift(m(x,a,c),c,'nonlinear')-lift(m(x,np.zeros_like(a),c),c,'nonlinear')
    np.testing.assert_allclose(full_step_input_effect(x,a,c,m),expected,atol=1e-12)


def test_full_step_preserves_latent_state_instead_of_silently_relifting():
    from koopman.controlled_lift_v33 import latent_step
    x=state();m=model();z=lift(x,neutral(),'nonlinear');matrix=m.matrix.copy();matrix[0,0]=1.1
    y,prediction=latent_step(z,x,np.zeros((1,6)),neutral(),m,matrix,'corrected')
    assert y[0,0]==pytest.approx(6.05)
    assert prediction[0,0]==pytest.approx(6.05)
    assert m(x,np.zeros((1,6)),neutral())[0,0]==5.5


def test_input_rejects_wrong_shape_and_nonfinite_values():
    from koopman.controlled_lift_v33 import full_step_input_effect
    for a in (np.zeros((1,4)),np.full((1,6),np.nan)):
        with pytest.raises(ValueError):full_step_input_effect(state(),a,neutral(),model())


def test_complete_rollout_failure_has_no_survivor_average():
    from workflows.controlled_lift_v33 import full_rollout
    x=np.repeat(state(),641,axis=0);m=model();matrix=m.matrix.copy();matrix[0,0]=2.
    result=full_rollout(x,np.zeros((640,6)),m,neutral(),matrix,'corrected',20)
    assert result['origins']==173 and result['failed_origins']==173
    assert set(result['first_failure_physics_tick'])=={5}
    assert result['endpoint_rmse'] is None and result['path_rmse'] is None


def test_old_rollout_path_reproduces_frozen_diagnostic():
    from workflows.controlled_lift_v33 import full_rollout
    from workflows.sparse_evaluation_v32 import unprojected_rollout
    x=np.repeat(state(),641,axis=0);a=np.zeros((640,6));m=model()
    old=unprojected_rollout(x,a,m,neutral(),20)
    new=full_rollout(x,a,m,neutral(),m.matrix,'old',20)
    for key in ('complete_aggregate','failed_origins','first_failure_physics_tick','endpoint_rmse','path_rmse'):
        assert new[key]==old[key]


def test_refit_preserves_velocity_parameters_and_rejects_wrong_role():
    from types import SimpleNamespace
    from workflows.identify_sparse_world_v30 import fit_model
    from workflows.identification_protocol_v29 import cases
    from workflows.controlled_lift_v33 import fit_lift_matrix
    x=np.repeat(state(),641,axis=0);a=np.zeros((640,6));c=neutral()
    episodes=[SimpleNamespace(case=q,states=x,acceleration=a,context=c,acceptance={'training_eligible':True},
        source_commit='a'*40,trace_sha256='b'*64) for q in cases() if q['role']=='fit' and q['configuration']=='base']
    parent,_=fit_model(episodes,'nonlinear',['base']);parent['model_id']='fixture'
    record,matrix=fit_lift_matrix(episodes,parent)
    np.testing.assert_array_equal(matrix[:,10:16],np.asarray(parent['matrix'])[:,10:16])
    assert record['damping']==parent['damping'] and record['quadratic']==parent['quadratic']
    episodes[0].case={**episodes[0].case,'role':'validation'}
    with pytest.raises(ValueError,match='controlled_lift_fit_identity'):fit_lift_matrix(episodes,parent)

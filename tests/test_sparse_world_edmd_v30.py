import numpy as np
import pytest
from koopman.projected_edmd_v24 import PhysicalContext


def test_box_ridge_recovers_coefficients_and_rejects_negative_damping():
    from koopman.sparse_world_edmd_v30 import box_ridge
    x=np.array([[1,0],[0,1],[1,1],[-1,1]],dtype=float)
    coefficient,audit=box_ridge(x,x@np.array([.2,1.3]),np.ones(4),[0,0],[20,2],[0,1],ridge=1e-10)
    np.testing.assert_allclose(coefficient,[.2,1.3],atol=1e-7)
    coefficient,audit=box_ridge(x,-x[:,0],np.ones(4),[0,0],[20,2],[0,1],ridge=1e-10)
    assert coefficient[0]==pytest.approx(0,abs=1e-8) and np.min(coefficient)>=0


def test_unexcited_coefficient_retains_prior_and_is_marked_unidentified():
    from koopman.sparse_world_edmd_v30 import box_ridge
    coefficient,audit=box_ridge(np.zeros((8,2)),np.zeros(8),np.ones(8),[0,0],[20,2],[0,1])
    np.testing.assert_array_equal(coefficient,[0,1])
    assert audit['identified_columns']==[]


def test_physical_prior_velocity_rows_match_known_comparator_and_ignore_absolute_height():
    from koopman.sparse_world_edmd_v30 import core_matrix,predict_projected,feature_names
    from koopman.physical_prediction_v29 import known_step
    c=PhysicalContext(22.701,[.37,.97,1.19],[.03,.02,.05],.022747843530591776,1.)
    x=np.array([[5.5,.99,.05,-.04,.08,.12,-.02,.04,.2,-.3,.1]],dtype=float);x[:,1:5]/=np.linalg.norm(x[:,1:5],axis=1)[:,None]
    a=np.array([[.02,.01,1.,.1,-.2,.3]])
    matrix=core_matrix('nonlinear',np.zeros(6),np.ones(6),.05)
    y=predict_projected(x,a,c,matrix,'nonlinear',.05)
    reference=known_step(x,a,c,angular_damping=.05,gyroscopic=True)
    np.testing.assert_allclose(y,reference,atol=1e-12)
    shifted=x.copy();shifted[:,0]+=50
    z=predict_projected(shifted,a,c,matrix,'nonlinear',.05)
    np.testing.assert_allclose(y[:,1:],z[:,1:],atol=1e-12)
    assert len(feature_names('nonlinear'))==53 and len(feature_names('linear'))==41
    assert not matrix[0,10:16].any()


def test_known_input_effect_has_no_future_state_or_rotor_argument():
    from koopman.sparse_world_edmd_v30 import input_effect,lift
    c=PhysicalContext(1,[1,1,1],[0,0,0],1/997,0)
    x=np.array([[5.5,1,0,0,0,0,0,0,0,0,0]],dtype=float);a=np.array([[1,2,3,4,5,6]],dtype=float)
    effect=input_effect(x,a,c,'nonlinear',.05)
    np.testing.assert_allclose(effect[:,10:13],a[:,:3]/120)
    np.testing.assert_allclose(effect[:,13:16],a[:,3:]/120*(1-.05/120))
    assert not effect[:,:10].any()

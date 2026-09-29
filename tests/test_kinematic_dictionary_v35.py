import copy
from types import SimpleNamespace
import numpy as np
import pytest
from koopman.projected_edmd_v24 import PhysicalContext,rotation
from koopman.sparse_world_edmd_v30 import core_matrix,lift as old_lift
from workflows.identify_sparse_world_v30 import SparseModel,fit_model
from workflows.identification_protocol_v29 import cases


def neutral():return PhysicalContext(1.,[1.,1.,1.],[0.,0.,0.],1/997,0.)
def state():return np.array([[5.5,1,0,0,0,0,0,0,0,0,0]],dtype=float)
def reference():return SparseModel('nonlinear',core_matrix('nonlinear',np.zeros(6),np.ones(6),.05),np.zeros(6),np.ones(6),.05,{})


def test_new_dictionary_resolves_the_missing_rotation_omega_interaction():
    from koopman.kinematic_dictionary_v35 import lift
    x=np.repeat(state(),4,0);x[2:,1]=np.cos(.25/2);x[2:,2]=np.sin(.25/2);x[[1,3],10]=.2
    z=lift(x,neutral());np.testing.assert_array_equal(z[:,:53],old_lift(x,neutral(),'nonlinear'))
    delta=z[3]-z[2]-z[1]+z[0]
    assert np.max(abs(delta[:53]))==0
    assert np.linalg.norm(delta[53:])==pytest.approx(.04986989335409109)
    assert np.all(z[:,52]==1)


def test_state_readout_uses_kinematic_columns_and_preserves_world_velocity():
    from koopman.kinematic_dictionary_v35 import projected_step
    ref=reference();K=np.vstack([ref.matrix[:,:16],np.zeros((9,16))]);K[53:,1:10]=np.eye(9)/120
    x=state();x[0,5]=1;x[0,10]=.2;y=projected_step(x,np.zeros((1,6)),neutral(),ref,K)
    # q and -q describe the same rotation; test direction in R, not quaternion sign.
    assert rotation(y[:,1:5])[0,1,0]>0
    np.testing.assert_allclose(np.einsum('nij,nj->ni',rotation(y[:,1:5]),y[:,5:8]),[[1,0,0]],atol=1e-12)


def test_full_step_input_map_is_unchanged_and_zero_input_is_exact():
    from koopman.kinematic_dictionary_v35 import projected_step
    ref=reference();K=np.vstack([ref.matrix[:,:16],np.zeros((9,16))]);x=state()
    np.testing.assert_allclose(projected_step(x,np.zeros((1,6)),neutral(),ref,K),x,atol=1e-12)
    a=np.array([[0,0,1,1,0,0]],dtype=float);y=projected_step(x,a,neutral(),ref,K)
    assert y[0,0]-x[0,0]==pytest.approx(1/120**2,abs=1e-14)
    assert abs(y[0,2])>1e-5
    for wrong in (np.zeros((1,4)),np.full((1,6),np.nan)):
        with pytest.raises(ValueError):projected_step(x,wrong,neutral(),ref,K)


def fixture_episodes():
    x=np.repeat(state(),641,axis=0);a=np.zeros((640,6));c=neutral()
    return [SimpleNamespace(case=q,states=x,acceleration=a,context=c,acceptance={'training_eligible':True},
        source_commit='a'*40,trace_sha256='b'*64) for q in cases() if q['role']=='fit' and q['configuration']=='base']


def test_fit_binds_roles_and_parameters_and_fixes_all_velocity_columns():
    from workflows.kinematic_dictionary_v35 import fit_readout,from_record
    episodes=fixture_episodes();parent,_=fit_model(episodes,'nonlinear',['base']);parent['model_id']='fixture'
    record=fit_readout(episodes,parent,'c'*64);model=from_record(record,parent,'c'*64)
    assert not model.matrix.flags.writeable and model.matrix.shape==(62,16)
    np.testing.assert_array_equal(model.matrix[:53,10:16],np.array(parent['matrix'])[:,10:16])
    np.testing.assert_array_equal(model.matrix[53:,10:16],0.)
    np.testing.assert_allclose(model(state(),np.zeros((1,6)),neutral()),state(),atol=1e-12)
    changed=copy.deepcopy(record);changed['matrix'][53][10]=.1
    with pytest.raises(ValueError):from_record(changed,parent,'c'*64)
    with pytest.raises(ValueError):from_record(record,parent,'d'*64)
    changed=copy.deepcopy(record);changed['quadratic'][0]=.9
    with pytest.raises(ValueError):from_record(changed,parent,'c'*64)


def test_validation_or_missing_fit_episode_cannot_enter_fit():
    from workflows.kinematic_dictionary_v35 import fit_readout
    episodes=fixture_episodes();parent,_=fit_model(episodes,'nonlinear',['base']);parent['model_id']='fixture'
    with pytest.raises(ValueError):fit_readout(episodes[:-1],parent,'c'*64)
    changed=copy.deepcopy(episodes);changed[0].case['role']='validation'
    with pytest.raises(ValueError):fit_readout(changed,parent,'c'*64)

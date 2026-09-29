"""New learned readout must differ from D/Q while preserving causal geometry."""
import copy
from dataclasses import replace
import importlib
import numpy as np
import pytest
from test_prepared_projected_v40 import context, model, states
from workflows.identify_sparse_world_v30 import _expected
from koopman.sparse_world_edmd_v30 import feature_names, lift, input_effect


def api():
    assert importlib.util.find_spec('koopman.learned_velocity_v81')
    return importlib.import_module('koopman.learned_velocity_v81')


def record():
    m=model(); configs=['base']; names=feature_names('nonlinear')
    prior=dict(schema='sparse-world-edmd-v30', family='nonlinear', configurations=configs,
        fit_source='a'*40, fit_episode_hashes={k:'b'*64 for k in _expected(configs)},
        feature_names=names,matrix=m.matrix.tolist(),damping=m.damping.tolist(),
        quadratic=m.quadratic.tolist(),angular_damping=m.angular_damping,
        audit={'training_role':'fit','full_lift_operator':True})
    return api().seal_record(dict(schema='projected-controlled-edmd-velocity-v81',
        family='nonlinear',feature_names=names, velocity_matrix=m.matrix[:,10:16].tolist(),
        physical_prior=prior, ridge=.001, feature_mean=[0.]*len(names),feature_scale=[1.]*len(names),
        audit={'training_role':'fit','fit_episodes':3,'startup_weight':1/3,
               'analytic_pose':True,'full_latent_closure_claim':False}))


def test_learning_changes_control_readout_outside_dq_subspace():
    a=api();r=record();c=context();x=states(4);u=np.zeros((4,6))
    p=a.prepare_learned(r,c); altered=copy.deepcopy(r);altered['velocity_matrix'][-1][0]+=.03
    altered=a.seal_record(altered);q=a.prepare_learned(altered,c)
    assert np.max(np.abs(p(x,u,c)-q(x,u,c)))>.02
    assert a.dq_subspace_distance(altered)>0.02
    assert q._symbolic_base._matrix[-1,10]==altered['velocity_matrix'][-1][0]


def test_hash_role_inventory_and_context_fail_closed():
    a=api();r=record();c=context();x=states(1)
    bad=copy.deepcopy(r);bad['velocity_matrix'][-1][0]+=.1
    with pytest.raises(ValueError,match='hash'):a.prepare_learned(bad,c)
    bad=copy.deepcopy(r);bad['audit']['training_role']='test';bad=a.seal_record(bad)
    with pytest.raises(ValueError,match='record'):a.prepare_learned(bad,c)
    bad=copy.deepcopy(r);bad['physical_prior']['fit_episode_hashes']['test_episode']='d'*64;bad=a.seal_record(bad)
    with pytest.raises(ValueError):a.prepare_learned(bad,c)
    p=a.prepare_learned(r,c)
    with pytest.raises(ValueError,match='context'):p(x,np.zeros((1,6)),replace(c,mass=c.mass+1))


def test_physical_target_has_no_spurious_residual_and_pose_is_normalized():
    a=api();r=record();c=context();x=states(9);u=np.random.default_rng(18).normal(size=(9,6))
    p=a.prepare_learned(r,c);y=p(x,u,c)
    target=a.velocity_target(x,y,u,c,p._symbolic_base._angular_damping)
    np.testing.assert_allclose(target,lift(x,c,'nonlinear')@np.asarray(r['velocity_matrix']),atol=1e-12)
    np.testing.assert_allclose(np.linalg.norm(y[:,1:5],axis=1),1,atol=1e-14)


def test_physical_center_ridge_learns_nonphysical_feature_and_keeps_zero_residual():
    a=api();rng=np.random.default_rng(2);features=rng.normal(size=(600,53));features[:,-1]=1
    prior=np.zeros((53,6));weights=np.ones(600);target=features@prior
    fitted,stats=a.fit_readout(features,target,weights,prior,.001)
    np.testing.assert_allclose(fitted,prior,atol=1e-15)
    target[:,0]+=.2*features[:,0]
    learned,_=a.fit_readout(features,target,weights,prior,.001)
    assert learned[0,0]>.19
    assert np.sqrt(np.mean((features@learned-target)**2))<.001


def test_attitude_error_normalizes_ground_truth_quaternion():
    from workflows.fit_learned_velocity_v81 import errors
    x=np.array([[5.5,1.,0,0,0,0,0,0,0,0,0]])
    y=x.copy();y[:,1]=-.99999
    assert errors(x,y)['attitude_rmse_rad']==0

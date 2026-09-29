import importlib.util
import numpy as np
import pytest
from koopman.so3_v21 import so3_exp_v21


def module():
    assert importlib.util.find_spec('koopman.projected_edmd_v24'), 'EDMD operator missing'
    from koopman import projected_edmd_v24
    return projected_edmd_v24


def context():
    return module().PhysicalContext(20.,[.4,.8,1.],[0,0,.01],.02,1.,997.,.001306,9.81)


def states(n=3):
    x=np.zeros((n,11));x[:,0]=1.5;x[:,1]=1
    return x


def test_features_have_fixed_width_and_correct_gravity_frame():
    m=module();c=context();x=states();x[1,1:5]=so3_exp_v21([0,np.pi/2,0]);x[:,5]=.2
    linear=m.observable(x,c,'linear');nonlinear=m.observable(x,c,'nonlinear')
    assert linear.shape==(3,25) and nonlinear.shape==(3,58)
    np.testing.assert_array_equal(nonlinear[:,:25],linear)
    # Net buoyancy points along worldup expressed in the currentbody frame.
    buoyancy_ratio=(997*.02/20-1)*9.81
    np.testing.assert_allclose(linear[0,13:16],[0,0,buoyancy_ratio],atol=1e-12)
    np.testing.assert_allclose(linear[1,13:16],[-buoyancy_ratio,0,0],atol=1e-12)


def test_quadratic_drag_is_dissipative_and_gyro_transport_are_explicit():
    m=module();x=states(1);x[0,5:11]=[.2,-.3,.4,.1,.2,-.1]
    f=m.observable(x,context(),'nonlinear')[0]
    assert np.all(f[25:31]*x[0,5:11]<0)
    np.testing.assert_allclose(f[31:34],np.cross(x[0,8:],x[0,5:8]))


def test_operator_fits_all_observables_and_exact_fixed_mean_ridge_objective():
    m=module();rng=np.random.default_rng(81)
    a=rng.normal(size=(80,25));b=a+rng.normal(size=a.shape)*.05;u=rng.normal(size=(80,6))
    op=m.fit_operator(a,b,u)
    z=(a-op.mean)/op.scale;v=(u-op.input_mean)/op.input_scale
    design=np.column_stack((z,v));target=(b-a)/op.scale
    expected=np.linalg.solve(design.T@design/len(a)+.001*np.eye(31),design.T@(target-target.mean(0))/len(a))
    np.testing.assert_allclose(op.coefficient,expected,atol=1e-12)
    predicted=op.advance_lift(z,u)
    np.testing.assert_allclose(predicted,z+target.mean(0)+design@expected,atol=1e-12)
    assert predicted.shape==a.shape and op.audit['target_observables']==25
    with pytest.raises(ValueError):op.mean[0]=4


def test_known_pose_step_uses_current_body_twist_without_future_pose():
    m=module();x=states(1);x[0,1:5]=so3_exp_v21([0,np.pi/2,0]);x[0,5]=2
    predicted=m.known_pose_step(x,np.ones((1,6))*9,.1)
    assert predicted[0,0]==pytest.approx(1.3)
    np.testing.assert_allclose(predicted[0,1:5],x[0,1:5])
    np.testing.assert_array_equal(predicted[0,5:],np.ones(6)*9)


def test_lift_decode_roundtrip_and_degenerate_columns_are_rejected_per_row():
    m=module();x=states();x[1,1:5]=so3_exp_v21([.3,-.4,.6])
    f=m.observable(x,context(),'nonlinear');y=m.decode(f)
    np.testing.assert_allclose(np.abs(np.sum(x[:,1:5]*y[:,1:5],axis=1)),1,atol=1e-12)
    f[2,1:7]=0;bad=m.decode(f)
    assert np.isfinite(bad[:2]).all() and not np.isfinite(bad[2]).all()


def test_fit_nonfinite_is_rejected():
    with pytest.raises(ValueError,match='operator_fit_invalid'):
        module().fit_operator(np.full((3,25),np.nan),np.zeros((3,25)),np.zeros((3,6)))

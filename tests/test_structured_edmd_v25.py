import importlib.util
import numpy as np
import pytest
from koopman.projected_edmd_v24 import PhysicalContext,observable
from workflows.evaluate_projected_edmd_v24 import rollout


def module():
    assert importlib.util.find_spec('koopman.structured_edmd_v25')
    from koopman import structured_edmd_v25
    return structured_edmd_v25


def context():return PhysicalContext(20,[.4,.8,1],[0,0,.01],.02,1)


def states(n):
    rng=np.random.default_rng(94);x=np.zeros((n,11));x[:,1]=1;x[:,0]=1.5;x[:,5:]=rng.normal(size=(n,6))*.1
    return x


def test_known_kick_preserves_pose_and_has_exact_body_input_units():
    m=module();x=states(4);a=np.arange(24).reshape(4,6)
    y=m.input_kick(x,a)
    np.testing.assert_array_equal(y[:,:5],x[:,:5])
    np.testing.assert_allclose(y[:,5:]-x[:,5:],a/120,atol=1e-15)
    with pytest.raises(ValueError,match='known_input_invalid'):m.input_kick(x,np.full((4,6),np.nan))


def test_state_operator_fits_exact_mean_ridge_without_any_input_coefficients():
    m=module();rng=np.random.default_rng(33);a=rng.normal(size=(90,25));b=a+rng.normal(size=a.shape)*.02
    op=m.fit_state_operator(a,b);z=(a-op.mean)/op.scale;target=(b-a)/op.scale
    expected=np.linalg.solve(z.T@z/90+.001*np.eye(25),z.T@(target-target.mean(0))/90)
    assert op.coefficient.shape==(25,25)
    np.testing.assert_allclose(op.coefficient,expected,atol=1e-12)
    with pytest.raises(ValueError):op.mean[0]=3


def test_unexcited_training_cannot_create_arbitrary_Fx_to_vz_cross_gain():
    m=module();x=states(90);c=context();phi=observable(x,c,'nonlinear')
    drift=m.fit_state_operator(phi,phi);op=drift.bind(c,'nonlinear');z=(phi[:4]-op.mean)/op.scale
    baseline=op.advance_lift(z,np.zeros((4,6)))*op.scale+op.mean
    for channel in range(6):
        u=np.zeros((4,6));u[:,channel]=.2
        kicked=op.advance_lift(z,u)*op.scale+op.mean
        expected=np.zeros((4,6));expected[:,channel]=.2/120
        np.testing.assert_allclose(kicked[:,7:13]-baseline[:,7:13],expected,atol=1e-14)


def test_known_input_removal_leaves_pure_static_state_training_target():
    m=module();x=states(12);u=np.ones((12,6))*.4;c=context()
    y=m.input_kick(x,u);a,b=m.remove_known_input(x,y,u,c,'nonlinear')
    np.testing.assert_allclose(b,a,atol=1e-14)


def test_projected_structured_rollout_uses_preset_input_and_current_twist():
    m=module();x=states(30);x[:,5:]=0;c=context();phi=observable(x,c,'linear')
    op=m.fit_state_operator(phi,phi).bind(c,'linear')
    result=rollout(x[:9],np.tile([1,0,0,0,0,0],(8,1)),op,'linear',c,'projected',4)
    assert result['complete_aggregate']
    np.testing.assert_allclose(result['final_predictions'][0][5:],[8/120,0,0,0,0,0],atol=1e-12)


def test_state_operator_rejects_nonfinite_and_misaligned_targets():
    m=module()
    with pytest.raises(ValueError,match='operator_fit_invalid'):m.fit_state_operator(np.ones((3,25)),np.zeros((4,25)))
    with pytest.raises(ValueError,match='operator_fit_invalid'):m.fit_state_operator(np.full((3,25),np.nan),np.zeros((3,25)))


def test_unprojected_degenerate_row_does_not_poison_other_origins():
    m=module();x=states(20);c=context();phi=observable(x,c,'nonlinear')
    op=m.fit_state_operator(phi,phi).bind(c,'nonlinear');bad=phi[:2].copy();bad[1,1:7]=0
    result=op.advance_lift((bad-op.mean)/op.scale,np.zeros((2,6)))
    assert np.isfinite(result[0]).all() and not np.isfinite(result[1]).all()

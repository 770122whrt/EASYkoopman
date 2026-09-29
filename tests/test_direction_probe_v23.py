"""Analytic contracts for non-promoting direction probes."""
import importlib.util
import numpy as np
import pytest

from koopman.so3_v21 import apply_increment_target_v21, so3_exp_v21
from koopman.metrics_v21 import RolloutEpisodeV21, rollout_episode_v21, OFFICIAL_ROLLOUT_POLICY_V21


def module():
    assert importlib.util.find_spec('koopman.direction_probe_v23') is not None, 'direction probe not implemented'
    from koopman import direction_probe_v23
    return direction_probe_v23


def state():
    x = np.zeros(11); x[0] = 1.5; x[1] = 1
    return x


def test_kinematics_rotates_body_velocity_to_world_z_and_preserves_velocity_heads():
    c = np.zeros((10, 22)); c[:, 0] = np.arange(10)
    m = module().DirectionProbe(c, dt=.1, kinematic_pose=True)
    x = state(); x[1:5] = so3_exp_v21([0, np.pi/2, 0]); x[5] = 2; x[8:11] = [.2, .3, .4]
    dx = m.predict_increment(x, np.zeros(4), np.zeros(4))
    assert dx[0] == pytest.approx(-.2)
    np.testing.assert_array_equal(dx[1:7], np.arange(1, 7))
    np.testing.assert_allclose(dx[7:], [.02, .03, .04])
    np.testing.assert_array_equal(c[:, 0], np.arange(10))


def test_body_right_rotation_is_not_world_left_rotation():
    m = module().DirectionProbe(np.zeros((10,22)), dt=.1, kinematic_pose=True)
    x = state(); x[1:5] = so3_exp_v21([0, 0, np.pi/2]); x[8] = np.pi
    actual = apply_increment_target_v21(x, m.predict_increment(x,np.zeros(4),np.zeros(4)))
    # qz(pi/2) * qx(pi/10), Hamilton body-right composition.
    c, s = np.cos(np.pi/20), np.sin(np.pi/20)
    np.testing.assert_allclose(actual[1:5], np.sqrt(.5)*np.array([c,s,s,c]), atol=1e-12)


def test_fixed_origin_rollout_does_not_teacher_force_future_states():
    states = np.tile(state(), (5,1)); states[0,7] = 2; states[1:,0] = 70
    ep = RolloutEpisodeV21('analytic','uuv6',states,np.zeros((5,4)),np.zeros((5,4)),states.copy(),.2,.1,(1,1,1,1))
    m = module().DirectionProbe(np.zeros((10,22)), dt=.1, kinematic_pose=True)
    trace = rollout_episode_v21(m,ep,start=0,steps=5,policy=OFFICIAL_ROLLOUT_POLICY_V21)
    assert trace.status == 'success'
    np.testing.assert_allclose(trace.predictions[:,0], 1.5+.2*np.arange(1,6))


def test_ridge_matches_normal_equation_and_returns_rank_diagnostics():
    rng=np.random.default_rng(13); x=rng.normal(size=(80,22)); x[:,0]=1
    y=rng.normal(size=(80,10)); ridge=.03
    c,audit=module().fit_probe_coefficients(x,y,ridge=ridge)
    expected=np.linalg.solve(x.T@x+ridge*np.eye(22),x.T@y).T
    np.testing.assert_allclose(c,expected,atol=1e-12)
    assert audit['design_rank']==22


def test_batch_matches_single_and_unlearned_increment_equals_persistence():
    m=module().DirectionProbe(np.zeros((10,22)),dt=.1)
    xs=np.tile(state(),(3,1)); u=np.ones((3,4))
    np.testing.assert_array_equal(m.predict_increment(xs,u,u),np.zeros((3,10)))
    k=module().DirectionProbe(np.ones((10,22))*.001,dt=.1,kinematic_pose=True)
    np.testing.assert_allclose(k.predict_increment(xs,u,u),np.array([k.predict_increment(x,a,a) for x,a in zip(xs,u)]))


@pytest.mark.parametrize('dt',[0,-.1,float('nan')])
def test_invalid_clock_rejected(dt):
    with pytest.raises(ValueError,match='probe_dt_invalid'):
        module().DirectionProbe(np.zeros((10,22)),dt=dt)


def test_failed_rollout_is_not_removed_from_macro():
    result=module().complete_macro([{'status':'success','metrics':{'depth_rmse':.1}}, {'status':'failed','metrics':None}])
    assert result['success_count']==1 and result['episode_count']==2
    assert result['macro_metrics'] is None

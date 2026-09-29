import numpy as np
from koopman.projected_edmd_v24 import PhysicalContext,rotation


def neutral():return PhysicalContext(1,[1,1,1],[0,0,0],1/997,0.)


def test_force_free_rotating_body_preserves_world_linear_velocity():
    from koopman.physical_prediction_v29 import known_step
    x=np.array([[5.5,1,0,0,0,1,0,0,0,0,1]],dtype=float)
    y=known_step(x,np.zeros((1,6)),neutral(),angular_damping=0.,gyroscopic=True)
    np.testing.assert_allclose(rotation(y[:,1:5])[0]@y[0,5:8],[1,0,0],atol=1e-12)
    assert y[0,6]<0 and abs(np.linalg.norm(y[0,1:5])-1)<1e-12


def test_known_input_updates_pose_using_predicted_velocity_and_height_is_invariant():
    from koopman.physical_prediction_v29 import known_step
    x=np.array([[5.5,1,0,0,0,0,0,0,0,0,0]],dtype=float);a=np.array([[0,0,1,0,0,0]],dtype=float)
    y=known_step(x,a,neutral(),angular_damping=0.,gyroscopic=True)
    np.testing.assert_allclose(y[0,[0,7]],[5.5+1/120**2,1/120])
    other=x.copy();other[:,0]+=40
    z=known_step(other,a,neutral(),angular_damping=0.,gyroscopic=True)
    np.testing.assert_allclose(y[:,1:],z[:,1:]);np.testing.assert_allclose(z[:,0]-y[:,0],40)

import itertools
import numpy as np
import pytest


def corners():
    return np.array(list(itertools.product((-.5,.5),(-.5,.5),(-.25,.25))))


def test_actual_box_clearance_accounts_for_rotation():
    from workflows.free_water_runtime_v26 import clearance
    assert clearance(corners(), [0,0,1.5,0,0,0,1], 0) == pytest.approx(1.25)
    q=[0,np.sqrt(.5),0,np.sqrt(.5)]
    assert clearance(corners(), [0,0,1.5,*q], 0) == pytest.approx(1.)


@pytest.mark.parametrize('points,pose,ground',[(np.zeros((0,3)),[0,0,1,0,0,0,1],0),
    (corners(),[0,0,1,0,0,0,0],0),(corners(),[0,0,1,0,0,0,1],float('nan'))])
def test_incomplete_geometry_rejected(points,pose,ground):
    from workflows.free_water_runtime_v26 import clearance
    with pytest.raises(ValueError,match='clearance_geometry'):
        clearance(points,pose,ground)


def test_minimum_over_before_and_after_is_used():
    from workflows.free_water_runtime_v26 import step_clearance
    row={'before':{'backend':{'transform_actor_world_xyzw':[[0,0,1.5,0,0,0,1]]}},
         'backend_after_physics':{'transform_actor_world_xyzw':[[0,0,.3,0,0,0,1]]}}
    assert step_clearance(row,{'body_local_corners_m':corners().tolist(),'ground_world_z_m':0}) == pytest.approx(.05)

import copy

import numpy as np
import pytest

from koopman.projected_edmd_v24 import PhysicalContext


def trace():
    backend = dict(mass_kg=[[20.]], inertia_9=[[1.,0,0,0,2.,0,0,0,3.]],
                   com_local_pose_xyzw=[[0.,0,0,0,0,0,1.]])
    return dict(geometry={'body_physics_attributes': {
        'physxRigidBody:linearDamping': 0., 'physxRigidBody:angularDamping': float(np.float32(.05)),
        'physxRigidBody:enableGyroscopicForces': 'True'}},
        substeps=[dict(before={'backend': copy.deepcopy(backend)}, command={'backend': copy.deepcopy(backend)},
                       backend_after_physics=copy.deepcopy(backend)) for _ in range(2)])


def test_every_backend_readback_and_integration_attributes_remain_bound():
    from workflows.projected_adapter_v38 import validate_prediction_backend
    c = PhysicalContext(20., [1.,2.,3.], [0.,0.,0.], .02, 1.)
    validate_prediction_backend(trace(), c)
    for key, value in [('mass_kg', [[21.]]), ('inertia_9', [[1,0,0,0,2,0,0,0,4]]),
                       ('com_local_pose_xyzw', [[.1,0,0,0,0,0,1]])]:
        bad = trace()
        bad['substeps'][-1]['backend_after_physics'][key] = value
        with pytest.raises((ValueError, AssertionError)):
            validate_prediction_backend(bad, c)
    for key, value in [('physxRigidBody:linearDamping', .1), ('physxRigidBody:angularDamping', 0.),
                       ('physxRigidBody:enableGyroscopicForces', 'False')]:
        bad = trace()
        bad['geometry']['body_physics_attributes'][key] = value
        with pytest.raises(ValueError):
            validate_prediction_backend(bad, c)

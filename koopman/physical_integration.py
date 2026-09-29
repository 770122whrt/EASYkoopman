"""Known-physics comparator with predicted-velocity pose integration.

This is a discrete approximation, not the proprietary deployed GPU solver and
not a learned Koopman model. Reference integration order: NVIDIA PhysX
physx/source/lowleveldynamics/src/DyBodyCoreIntegrator.h (public main, 2026-09-13).
The actual runtime damping/gyro attributes must be passed from accepted data.
"""
import numpy as np
from koopman.physics_context import rotation,known_pose_step
from koopman.physical_terms import validate_states


def advance_old_frame_velocity(states,next_nu,dt=1/120):
    """Advance pose and then express predicted world velocity in the new body frame."""
    x=validate_states(states);nu=np.asarray(next_nu,dtype=float)
    if nu.shape!=(len(x),6) or not np.isfinite(nu).all():raise ValueError('physical_prediction_velocity')
    temporary=x.copy();temporary[:,5:]=nu
    y=known_pose_step(temporary,nu,dt)
    old_r=rotation(x[:,1:5]);new_r=rotation(y[:,1:5])
    transform=np.einsum('nji,njk->nik',new_r,old_r)
    y[:,5:8]=np.einsum('nij,nj->ni',transform,nu[:,:3])
    y[:,8:]=np.einsum('nij,nj->ni',transform,nu[:,3:])
    return y

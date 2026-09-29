"""Known-physics comparator with predicted-velocity pose integration.

This is a discrete approximation, not the proprietary deployed GPU solver and
not a learned Koopman model. Reference integration order: NVIDIA PhysX
physx/source/lowleveldynamics/src/DyBodyCoreIntegrator.h (public main, 2026-09-13).
The actual runtime damping/gyro attributes must be passed from accepted data.
"""
import numpy as np
from koopman.projected_edmd_v24 import rotation,known_pose_step
from koopman.physical_terms_v26 import state_terms,validate_states


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


def known_step(states,acceleration,context,*,angular_damping,gyroscopic):
    x=validate_states(states);a=np.asarray(acceleration,dtype=float)
    if (a.shape!=(len(x),6) or not np.isfinite(a).all() or not np.isfinite(angular_damping)
            or angular_damping<0 or type(gyroscopic) is not bool):raise ValueError('physical_prediction_parameters')
    terms=state_terms(x,context)
    # Frame transport is handled by exact rotation of the predicted velocity,
    # so it must not be added again as -omega cross v in this old-frame update.
    rate=a+np.c_[terms['net_buoyancy'],terms['restoring']]
    rate+=terms['linear_drag']+terms['quadratic_drag']
    if gyroscopic:rate[:,3:]+=terms['gyro']
    nu=x[:,5:]+rate/120
    nu[:,3:]*=max(1-angular_damping/120,0.)
    return advance_old_frame_velocity(x,nu)

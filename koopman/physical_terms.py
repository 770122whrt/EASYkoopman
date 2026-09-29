"""Continuous body-frame terms of the declared, still-water rigid-body model.

These expressions match the force source, not an exact discrete PhysX solver.
Backend damping, contacts, flows and hidden solver state are not invented.
"""
import numpy as np
from koopman.physics_context import PhysicalContext,rotation


def valid_predictions(x):
    """Finite forecast rows with the original magnitude and quaternion checks."""
    return (np.isfinite(x).all(axis=1)&(np.abs(x[:,0])<=100)
            &np.all(np.abs(x[:,5:])<=100,axis=1)
            &(np.abs(np.linalg.norm(x[:,1:5],axis=1)-1)<=1e-3))


def validate_states(states):
    x=np.asarray(states,dtype=float)
    if (x.ndim!=2 or x.shape[1]!=11 or not np.isfinite(x).all()
            or np.any(np.abs(np.linalg.norm(x[:,1:5],axis=1)-1)>1e-3)):
        raise ValueError('physical_state_invalid')
    return x


def state_terms(states,context):
    x=validate_states(states)
    if not isinstance(context,PhysicalContext):raise ValueError('physical_context_invalid')
    c=context;r=rotation(x[:,1:5]);v=x[:,5:8];w=x[:,8:]
    radii=np.sqrt(np.maximum(3/(2*c.mass)*(np.roll(c.inertia,1)+np.roll(c.inertia,-1)-c.inertia),1e-9))
    mean=radii.mean();rj=np.roll(radii,1);rk=np.roll(radii,-1)
    up=r[:,2,:]
    linear=np.concatenate((-6*c.beta*np.pi*mean/c.mass*v,-8*c.beta*np.pi*mean**3/c.inertia*w),axis=1)*c.drag_multiplier
    quadratic=np.concatenate((-2*c.rho*rj*rk/c.mass*np.abs(v)*v,
                              -.5*c.rho*radii*(rj**4+rk**4)/c.inertia*np.abs(w)*w),axis=1)*c.drag_multiplier
    return {'net_buoyancy':(c.rho*c.volume/c.mass-1)*c.gravity*up,
            'restoring':np.cross(c.cob,c.rho*c.volume*c.gravity*up)/c.inertia,
            'linear_drag':linear,'quadratic_drag':quadratic,
            'transport':-np.cross(w,v),'gyro':-np.cross(w,c.inertia*w)/c.inertia}

"""Physical context and pose geometry shared by the frozen predictors."""
from dataclasses import dataclass
import numpy as np
@dataclass(frozen=True)
class PhysicalContext:
    mass: float
    inertia: object
    cob: object
    volume: float
    drag_multiplier: float
    rho: float = 997.0
    beta: float = .001306
    gravity: float = 9.81

    def __post_init__(self):
        for name in ('inertia', 'cob'):
            value = np.array(getattr(self, name), dtype=float, copy=True)
            if value.shape != (3,) or not np.isfinite(value).all():
                raise ValueError('physical_context_invalid')
            value.setflags(write=False)
            object.__setattr__(self, name, value)
        values = [self.mass, self.volume, self.rho, self.beta, self.gravity]
        if not np.isfinite(values).all() or min(values) <= 0 or np.any(self.inertia <= 0):
            raise ValueError('physical_context_invalid')
        if not np.isfinite(self.drag_multiplier) or self.drag_multiplier < 0:
            raise ValueError('physical_context_invalid')

def rotation(q):
    """Vectorized body-to-world rotation, quaternion order wxyz."""
    q = np.asarray(q, dtype=float)
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    w, x, y, z = np.moveaxis(q, -1, 0)
    return np.stack((1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y),
                     2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x),
                     2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)), axis=-1).reshape(q.shape[:-1]+(3,3))

def known_pose_step(states, next_nu, dt):
    """Advance pose with current body twist; replace velocity with EDMD output."""
    x = np.asarray(states, dtype=float); y = x.copy()
    y[:,0] += dt*np.einsum('ni,ni->n', rotation(x[:,1:5])[:,2,:], x[:,5:8])
    theta = dt*x[:,8:11]; norm = np.linalg.norm(theta,axis=1,keepdims=True)
    dq = np.concatenate((np.cos(norm/2), .5*np.sinc(norm/(2*np.pi))*theta),axis=1)
    q = x[:,1:5]; a=q[:,:1]; b=q[:,1:]; c=dq[:,:1]; d=dq[:,1:]
    result = np.concatenate((a*c-np.sum(b*d,axis=1,keepdims=True), a*d+c*b+np.cross(b,d)),axis=1)
    y[:,1:5] = result/np.linalg.norm(result,axis=1,keepdims=True)
    y[:,5:11] = next_nu
    return y

def _readonly(value):
    result=np.array(value,dtype=float,copy=True); result.setflags(write=False)
    return result

"""Fixed pilot EDMD dictionaries and operators; projection is explicitly hybrid.

No fitting or scoring executes on import. Physical context is known simulator
metadata, while every observable increment coefficient is learned from fit rows.
"""
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


def observable(states, context, dictionary):
    x = np.asarray(states, dtype=float)
    if x.ndim != 2 or x.shape[1] != 11 or dictionary not in ('linear', 'nonlinear'):
        raise ValueError('observable_input_invalid')
    c = context; r = rotation(x[:, 1:5]); v = x[:, 5:8]; w = x[:, 8:11]
    r6 = np.concatenate((r[:, :, 0], r[:, :, 1]), axis=1)
    up = r[:, 2, :]
    radii = np.sqrt(np.maximum(3/(2*c.mass)*(np.roll(c.inertia,1)+np.roll(c.inertia,-1)-c.inertia), 1e-9))
    mean_radius = radii.mean()
    buoyancy = c.rho*c.volume*c.gravity*up
    linear_drag = np.concatenate(((-6*c.beta*np.pi*mean_radius/c.mass)*v,
                                  (-8*c.beta*np.pi*mean_radius**3/c.inertia)*w), axis=1)*c.drag_multiplier
    linear = np.concatenate((x[:, :1], r6, v, w,
                             (c.rho*c.volume/c.mass-1)*c.gravity*up,
                             np.cross(c.cob, buoyancy)/c.inertia,
                             linear_drag), axis=1)
    if dictionary == 'linear':
        return linear
    rj = np.roll(radii,1); rk = np.roll(radii,-1)
    quadratic = np.concatenate(((-2*c.rho*rj*rk/c.mass)*np.abs(v)*v,
                                (-.5*c.rho*radii*(rj**4+rk**4)/c.inertia)*np.abs(w)*w), axis=1)*c.drag_multiplier
    return np.concatenate((linear, quadratic, np.cross(w,v),
                           np.cross(w,c.inertia*w)/c.inertia,
                           (r6[:,:,None]*w[:,None,:]).reshape(len(x),18),
                           r[:,2,:]*v), axis=1)


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


def decode(features):
    """Decode each R6 independently; a degenerate row remains invalid."""
    f = np.asarray(features,dtype=float)
    y = np.full((len(f),11),np.nan)
    a=f[:,1:4]; b=f[:,4:7]; na=np.linalg.norm(a,axis=1)
    valid=np.isfinite(f[:,:13]).all(axis=1)&(na>1e-10)
    first=np.zeros_like(a); first[valid]=a[valid]/na[valid,None]
    second=b-np.sum(first*b,axis=1,keepdims=True)*first
    nb=np.linalg.norm(second,axis=1); valid &= nb>1e-10
    second[valid]/=nb[valid,None]
    if np.any(valid):
        mats=np.stack((first[valid],second[valid],np.cross(first[valid],second[valid])),axis=2)
        # Symmetric quaternion extraction remains stable at rotations near pi.
        r=mats; k=np.empty((len(r),4,4))
        k[:,0,0]=np.trace(r,axis1=1,axis2=2)
        for i in range(3):k[:,i+1,i+1]=2*r[:,i,i]-k[:,0,0]
        k[:,0,1]=k[:,1,0]=r[:,2,1]-r[:,1,2]
        k[:,0,2]=k[:,2,0]=r[:,0,2]-r[:,2,0]
        k[:,0,3]=k[:,3,0]=r[:,1,0]-r[:,0,1]
        k[:,1,2]=k[:,2,1]=r[:,0,1]+r[:,1,0]
        k[:,1,3]=k[:,3,1]=r[:,0,2]+r[:,2,0]
        k[:,2,3]=k[:,3,2]=r[:,1,2]+r[:,2,1]
        quaternion=np.linalg.eigh(k)[1][:,:,-1]
        y[valid,0]=f[valid,0]; y[valid,1:5]=quaternion; y[valid,5:11]=f[valid,7:13]
    return y


def _readonly(value):
    result=np.array(value,dtype=float,copy=True); result.setflags(write=False)
    return result


@dataclass(frozen=True)
class Operator:
    mean: np.ndarray
    scale: np.ndarray
    input_mean: np.ndarray
    input_scale: np.ndarray
    bias: np.ndarray
    coefficient: np.ndarray
    audit: dict

    def advance_lift(self, z, inputs):
        design=np.concatenate((z,(inputs-self.input_mean)/self.input_scale),axis=1)
        return z+self.bias+design@self.coefficient


def fit_operator(current, following, inputs):
    a=np.asarray(current,dtype=float); b=np.asarray(following,dtype=float); u=np.asarray(inputs,dtype=float)
    if (a.ndim!=2 or a.shape!=b.shape or u.ndim!=2 or len(a)!=len(u) or len(a)<2
            or not a.shape[1] or not u.shape[1]
            or not all(np.isfinite(v).all() for v in (a,b,u))):
        raise ValueError('operator_fit_invalid')
    mean=a.mean(0); scale=np.maximum(a.std(0),1e-6)
    input_mean=u.mean(0); input_scale=np.maximum(u.std(0),1e-6)
    design=np.concatenate(((a-mean)/scale,(u-input_mean)/input_scale),axis=1)
    target=(b-a)/scale; bias=target.mean(0)
    left,singular,right=np.linalg.svd(design,full_matrices=False)
    smallest=singular[-1]**2/len(a) if len(singular)==design.shape[1] else 0.
    condition=(singular[0]**2/len(a)+.001)/(smallest+.001)
    if not np.isfinite(condition) or condition>1e8:
        raise ValueError('operator_condition_invalid')
    coefficient=(right.T*(singular/(singular**2+len(a)*.001)))@(left.T@(target-bias))
    residual=target-bias-design@coefficient
    audit={'fit_rows':len(a),'target_observables':a.shape[1],'inputs':u.shape[1],
           'rank':int(np.sum(singular>singular[0]*max(design.shape)*np.finfo(float).eps)),
           'singular_values':singular.tolist(),'regularized_condition':float(condition),
           'mean_ridge':.001,'standardized_increment_fit_rmse':np.sqrt(np.mean(residual**2,axis=0)).tolist()}
    return Operator(*map(_readonly,(mean,scale,input_mean,input_scale,bias,coefficient)),audit)

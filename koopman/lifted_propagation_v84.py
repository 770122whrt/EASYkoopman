"""Nonlinear lifting, fixed-context linear latent propagation, explicit input lift.

Offline research candidate: no implicit state re-lifting and no claim of QP,
global stability, or control admission. The quaternion chart is local to identity.
"""
from dataclasses import dataclass
import hashlib
import json
import numpy as np
from koopman.physical_terms_v26 import validate_states
from koopman.prepared_projected_v40 import _context_key, _immutable

CHART_ANGLE_LIMIT=.6
SCHEMA='nonlinear-lift-linear-propagation-v84'


def coordinates(states):
    x=validate_states(states);q=x[:,1:5]/np.linalg.norm(x[:,1:5],axis=1,keepdims=True)
    if np.any(2*np.arccos(np.clip(abs(q[:,0]),0,1))>CHART_ANGLE_LIMIT):
        raise ValueError('lifted_chart_outside')
    return np.c_[x[:,0]-5.5,q[:,1:]/q[:,:1],x[:,5:]]


def decode(xi):
    t=np.asarray(xi,dtype=float)
    if t.ndim!=2 or t.shape[1]!=10 or not np.isfinite(t).all():
        raise ValueError('lifted_decode_input')
    if np.any(2*np.arctan(np.linalg.norm(t[:,1:4],axis=1))>CHART_ANGLE_LIMIT):
        raise ValueError('lifted_chart_outside')
    q=np.c_[np.ones(len(t)),t[:,1:4]];q/=np.linalg.norm(q,axis=1,keepdims=True)
    return np.c_[t[:,0]+5.5,q,t[:,4:]]


def feature_names():
    raw=['height_offset','chart_x','chart_y','chart_z','v_x','v_y','v_z','w_x','w_y','w_z']
    return (raw+[n+'_square' for n in raw[1:]]+[n+'_signed_square' for n in raw[4:]]
            +['w_xy','w_yz','w_zx']+[f'chart_{i}_w_{j}' for i in range(3) for j in range(3)]+['constant'])


def lift(states):
    t=coordinates(states);w=t[:,7:10]
    return np.c_[t,t[:,1:]**2,t[:,4:]*abs(t[:,4:]),w[:,0]*w[:,1],w[:,1]*w[:,2],
                 w[:,2]*w[:,0],(t[:,1:4,None]*w[:,None,:]).reshape(len(t),9),np.ones(len(t))]


def input_lift(acceleration):
    a=np.asarray(acceleration,dtype=float)
    if a.ndim!=2 or a.shape[1]!=6 or not np.isfinite(a).all():
        raise ValueError('lifted_input_invalid')
    return np.c_[a,a*a]


def descriptors(context):
    _context_key(context);c=context
    return np.r_[1/c.mass,1/c.inertia,c.rho*c.volume/c.mass-1,
                 c.cob*(c.rho*c.volume*c.gravity)/c.inertia,c.drag_multiplier]


def seal(record):
    result=dict(record);result.pop('content_sha256',None)
    result['content_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return result


def fit_lifted(states,following,acceleration,contexts,weights,*,ridge):
    """Fit observable increments around identity, with source-only RMS scaling.

    Height is retained in readout but excluded from increment regressors: exact
    height-translation equivariance in the declared uniform, still-water task.
    Context-modulated coefficients are shared across all source configurations.
    """
    z=lift(states);next_z=lift(following);u=input_lift(acceleration)
    w=np.asarray(weights,dtype=float);n,d=z.shape
    if (next_z.shape!=z.shape or len(u)!=n or len(contexts)!=n or w.shape!=(n,)
            or not np.isfinite(w).all() or np.any(w<=0) or n<2
            or isinstance(ridge,bool) or not np.isfinite(ridge) or not 0<ridge<=.1):
        raise ValueError('lifted_fit_input')
    wn=w/w.sum()
    # Cache fixed descriptors rather than recompute them for all episode rows.
    cache={};ps=[]
    for c in contexts:
        key=_context_key(c)
        if key not in cache:cache[key]=descriptors(c)
        ps.append(cache[key])
    p=np.asarray(ps);pm=wn@p;pscale=np.maximum(np.sqrt(wn@((p-pm)**2)),1e-6)
    varying=np.ptp(p,axis=0)>1e-10
    q=np.c_[np.ones(n),(p-pm)/pscale*varying]
    base=np.c_[z[:,1:],u]
    design=(q[:,:,None]*base[:,None,:]).reshape(n,-1)
    scale=np.maximum(np.sqrt(wn@(design*design)),1e-6)
    a=design/scale
    target=next_z-z
    output_scale=np.maximum(np.sqrt(wn@(z*z)),1e-6)
    gram=a.T@(wn[:,None]*a)
    rhs=a.T@(wn[:,None]*(target/output_scale))
    coefficient=np.linalg.solve(gram+ridge*np.eye(gram.shape[0]),rhs)
    coefficient=coefficient*output_scale[None,:]/scale[:,None]
    coefficient[:,-1]=0.  # exact constant preservation
    predicted=z+design@coefficient
    return seal(dict(schema=SCHEMA,feature_names=feature_names(),ridge=ridge,
        chart_angle_limit=CHART_ANGLE_LIMIT,dt=1/120,input_features='a_and_a_squared',
        coefficients=coefficient.reshape(q.shape[1],base.shape[1],d).tolist(),
        context_mean=pm.tolist(),context_scale=pscale.tolist(),context_varying=varying.tolist(),
        training_rows=n,training_configurations=len(cache),
        fit_array_sha256=hashlib.sha256(z.tobytes()+next_z.tobytes()+u.tobytes()+p.tobytes()+w.tobytes()).hexdigest(),
        audit=dict(training_only_scaling=True,latent_relift_inside_horizon=False,
                   analytic_pose_step=False,height_increment_regressor=False,
                   training_lift_rmse=np.sqrt(wn@((predicted-next_z)**2)).tolist(),
                   design_dimension=a.shape[1],inactive_design_columns=int(np.sum(np.ptp(design,axis=0)==0)),
                   control_admitted=False)))


@dataclass(frozen=True)
class PreparedLifted:
    A: object
    B: object
    context: object

    def __post_init__(self):
        d=len(feature_names());a=np.asarray(self.A);b=np.asarray(self.B)
        if a.shape!=(d,d) or b.shape!=(d,12) or not np.isfinite(a).all() or not np.isfinite(b).all():
            raise ValueError('lifted_matrix_shape')
        object.__setattr__(self,'A',_immutable(a));object.__setattr__(self,'B',_immutable(b))
        object.__setattr__(self,'_key',_context_key(self.context))

    def step(self,z,acceleration,context):
        if _context_key(context)!=self._key:raise ValueError('lifted_context_mismatch')
        value=np.asarray(z,dtype=float);u=input_lift(acceleration)
        if value.ndim!=2 or value.shape!=(len(u),len(feature_names())) or not np.isfinite(value).all():
            raise ValueError('lifted_latent_invalid')
        result=value@self.A.T+u@self.B.T
        if not np.isfinite(result).all():raise ValueError('lifted_latent_nonfinite')
        return result

    def symbolic_step(self,z,acceleration):
        import casadi as ca
        return ca.DM(self.A)@z+ca.DM(self.B)@ca.vertcat(acceleration,acceleration**2)


def prepare_lifted(record,context):
    if record.get('content_sha256')!=seal(record)['content_sha256']:
        raise ValueError('lifted_record_hash')
    if (record.get('schema')!=SCHEMA or record.get('feature_names')!=feature_names()
            or record.get('chart_angle_limit')!=CHART_ANGLE_LIMIT or record.get('dt')!=1/120
            or record.get('input_features')!='a_and_a_squared'):
        raise ValueError('lifted_record_schema')
    mean=np.asarray(record['context_mean']);scale=np.asarray(record['context_scale'])
    varying=np.asarray(record['context_varying'],dtype=bool)
    if mean.shape!=(9,) or scale.shape!=(9,) or varying.shape!=(9,) or np.any(scale<=0):
        raise ValueError('lifted_context_record')
    p=np.r_[1,(descriptors(context)-mean)/scale*varying]
    d=len(feature_names());coef=np.asarray(record['coefficients'],dtype=float)
    if coef.shape!=(10,d-1+12,d) or not np.isfinite(coef).all():raise ValueError('lifted_coefficients')
    mapping=np.einsum('p,pij->ij',p,coef)
    A=np.eye(d);A[:,1:]+=mapping[:d-1].T;B=mapping[d-1:].T
    if np.max(abs(A[-1]-np.eye(d)[-1]))>1e-12 or np.any(B[-1]):
        raise ValueError('lifted_constant_constraint')
    return PreparedLifted(A,B,context)

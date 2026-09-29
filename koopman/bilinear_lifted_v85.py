"""Bounded bilinear extension of v84: z+ = (A(p)+sum a_i N_i)z+B(p)phi(a).

The same 38 observables and a/a-squared inputs are retained. Only 216
context-independent state/input interactions are added; N is not a general
context-conditioned operator. Height and constant are excluded as interaction
regressors to preserve height translation and avoid duplicating B*a. This is
an offline candidate, with no stability, generalization, or control claims.
"""
from dataclasses import dataclass
import hashlib
import numpy as np
from koopman.lifted_propagation_v84 import (
    coordinates,decode,lift,feature_names,input_lift,descriptors,seal,
    PreparedLifted,CHART_ANGLE_LIMIT)
from koopman.prepared_projected_v40 import _context_key,_immutable

SCHEMA='nonlinear-lift-bilinear-propagation-v85'


def fit_bilinear(states,following,acceleration,contexts,weights,*,ridge):
    z=lift(states);next_z=lift(following);u=input_lift(acceleration)
    w=np.asarray(weights,dtype=float);n,d=z.shape
    if (next_z.shape!=z.shape or len(u)!=n or len(contexts)!=n or w.shape!=(n,)
            or not np.isfinite(w).all() or np.any(w<=0) or n<2
            or isinstance(ridge,bool) or not np.isfinite(ridge) or not 0<ridge<=.1):
        raise ValueError('bilinear_fit_input')
    wn=w/w.sum();cache={};ps=[]
    for context in contexts:
        key=_context_key(context)
        if key not in cache:cache[key]=descriptors(context)
        ps.append(cache[key])
    p=np.asarray(ps);pm=wn@p;pscale=np.maximum(np.sqrt(wn@((p-pm)**2)),1e-6)
    varying=np.ptp(p,axis=0)>1e-10;q=np.c_[np.ones(n),(p-pm)/pscale*varying]
    base=np.c_[z[:,1:],u]
    core=(q[:,:,None]*base[:,None,:]).reshape(n,-1)
    interactions=(u[:,:6,None]*z[:,None,1:-1]).reshape(n,-1)
    design=np.c_[core,interactions]
    scale=np.maximum(np.sqrt(wn@(design*design)),1e-6);a=design/scale
    target=next_z-z
    # Match v84's independent-output ridge convention; output scaling cancels
    # algebraically after inverse scaling and does not change output weighting.
    output_scale=np.maximum(np.sqrt(wn@(z*z)),1e-6)
    gram=a.T@(wn[:,None]*a);rhs=a.T@(wn[:,None]*(target/output_scale))
    coefficient=np.linalg.solve(gram+ridge*np.eye(gram.shape[0]),rhs)
    coefficient=coefficient*output_scale[None,:]/scale[:,None]
    coefficient[:,-1]=0.
    predicted=z+design@coefficient
    return seal(dict(schema=SCHEMA,feature_names=feature_names(),ridge=ridge,
        chart_angle_limit=CHART_ANGLE_LIMIT,dt=1/120,input_features='a_and_a_squared',
        coefficients=coefficient[:core.shape[1]].reshape(q.shape[1],base.shape[1],d).tolist(),
        interaction_coefficients=coefficient[core.shape[1]:].reshape(6,d-2,d).tolist(),
        context_mean=pm.tolist(),context_scale=pscale.tolist(),context_varying=varying.tolist(),
        training_rows=n,training_configurations=len(cache),
        fit_array_sha256=hashlib.sha256(z.tobytes()+next_z.tobytes()+u.tobytes()+p.tobytes()+w.tobytes()).hexdigest(),
        audit=dict(training_only_scaling=True,latent_relift_inside_horizon=False,
            analytic_pose_step=False,height_increment_regressor=False,
            context_modulated_interactions=False,interaction_columns=interactions.shape[1],
            interaction_regressor_indices=list(range(1,d-1)),
            training_lift_rmse=np.sqrt(wn@((predicted-next_z)**2)).tolist(),
            design_dimension=design.shape[1],inactive_design_columns=int(np.sum(np.ptp(design,axis=0)==0)),
            control_admitted=False)))


@dataclass(frozen=True)
class PreparedBilinear(PreparedLifted):
    N: object

    def __post_init__(self):
        super().__post_init__();d=len(feature_names());n=np.asarray(self.N,dtype=float)
        if n.shape!=(6,d,d) or not np.isfinite(n).all():raise ValueError('bilinear_matrix_shape')
        object.__setattr__(self,'N',_immutable(n))

    def step(self,z,acceleration,context):
        result=super().step(z,acceleration,context)
        result+=np.einsum('bi,ijk,bk->bj',np.asarray(acceleration,dtype=float),self.N,np.asarray(z,dtype=float))
        if not np.isfinite(result).all():raise ValueError('bilinear_latent_nonfinite')
        return result

    def symbolic_step(self,z,acceleration):
        import casadi as ca
        result=super().symbolic_step(z,acceleration)
        for i in range(6):result+=acceleration[i]*(ca.DM(self.N[i])@z)
        return result


def prepare_bilinear(record,context):
    if record.get('content_sha256')!=seal(record)['content_sha256']:
        raise ValueError('bilinear_record_hash')
    d=len(feature_names())
    if (record.get('schema')!=SCHEMA or record.get('feature_names')!=feature_names()
            or record.get('chart_angle_limit')!=CHART_ANGLE_LIMIT or record.get('dt')!=1/120
            or record.get('input_features')!='a_and_a_squared'
            or record.get('audit',{}).get('context_modulated_interactions') is not False
            or record['audit'].get('interaction_regressor_indices')!=list(range(1,d-1))):
        raise ValueError('bilinear_record_schema')
    mean=np.asarray(record['context_mean']);scale=np.asarray(record['context_scale'])
    varying=np.asarray(record['context_varying'],dtype=bool)
    if (mean.shape!=(9,) or scale.shape!=(9,) or varying.shape!=(9,)
            or not np.isfinite(mean).all() or not np.isfinite(scale).all() or np.any(scale<=0)):
        raise ValueError('bilinear_context_record')
    p=np.r_[1,(descriptors(context)-mean)/scale*varying]
    coef=np.asarray(record['coefficients'],dtype=float);inter=np.asarray(record['interaction_coefficients'],dtype=float)
    if (coef.shape!=(10,d-1+12,d) or inter.shape!=(6,d-2,d)
            or not np.isfinite(coef).all() or not np.isfinite(inter).all()):
        raise ValueError('bilinear_coefficients')
    mapping=np.einsum('p,pij->ij',p,coef)
    A=np.eye(d);A[:,1:]+=mapping[:d-1].T;B=mapping[d-1:].T
    N=np.zeros((6,d,d));N[:,:,1:-1]=inter.transpose(0,2,1)
    if np.max(abs(A[-1]-np.eye(d)[-1]))>1e-12 or np.any(B[-1]) or np.any(N[:,-1]):
        raise ValueError('bilinear_constant_constraint')
    return PreparedBilinear(A=A,B=B,context=context,N=N)

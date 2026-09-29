"""Projected controlled EDMD with a genuinely learned six-column velocity map.

Known pose kinematics and the actuator/input map are retained. This is neither
an unconstrained full-latent rollout nor a v30/v38-admitted artifact. Model
records bind the fit-only physical center and learned map with a content hash.
"""
from dataclasses import dataclass, replace
import copy
import hashlib
import json
import numpy as np
from koopman.projected_edmd_v24 import rotation
from koopman.prepared_projected_v40 import prepare_projected, _immutable
from koopman.sparse_world_edmd_v30 import feature_names, input_effect, core_matrix
from workflows.identify_sparse_world_v30 import from_record


def seal_record(record):
    result=copy.deepcopy(record);result.pop('content_sha256',None)
    result['content_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return result


def validate_record(record, *, expected_sha256=None):
    if (record.get('content_sha256')!=seal_record(record)['content_sha256']
            or expected_sha256 is not None and record['content_sha256']!=expected_sha256):
        raise ValueError('learned_velocity_hash')
    if (record.get('schema')!='projected-controlled-edmd-velocity-v81'
            or record.get('family')!='nonlinear'
            or record.get('feature_names')!=feature_names('nonlinear')
            or record.get('ridge') not in (.001,.1)
            or record.get('audit',{}).get('training_role')!='fit'
            or record['audit'].get('analytic_pose') is not True
            or record['audit'].get('full_latent_closure_claim') is not False):
        raise ValueError('learned_velocity_record')
    prior=from_record(record['physical_prior'])
    k=np.asarray(record['velocity_matrix'],dtype=float)
    mean=np.asarray(record['feature_mean'],dtype=float);scale=np.asarray(record['feature_scale'],dtype=float)
    if (k.shape!=(53,6) or mean.shape!=(53,) or scale.shape!=(53,)
            or not all(np.isfinite(v).all() for v in (k,mean,scale)) or np.any(scale<=0)
            or record['audit'].get('fit_episodes')!=len(record['physical_prior']['fit_episode_hashes'])
            or record['audit'].get('startup_weight')!=1/3):
        raise ValueError('learned_velocity_record')
    return prior,k


@dataclass(frozen=True)
class LearnedVelocity:
    _symbolic_base: object
    content_sha256: str
    model_kind: str='learned_projected_edmd_velocity_v81'

    def __call__(self,states,acceleration,context):
        return self._symbolic_base(states,acceleration,context)


def prepare_learned(record,context,*,expected_sha256=None):
    prior,k=validate_record(record,expected_sha256=expected_sha256)
    base=prepare_projected(prior,context)
    matrix=base._matrix.copy();matrix[:,10:16]=k
    return LearnedVelocity(replace(base,_matrix=_immutable(matrix)),record['content_sha256'])


def velocity_target(states,following,acceleration,context,angular_damping):
    """Fixed observables at t+1 minus the identical known input contribution.

The next angular velocity remains on its rotation axis under our analytic
pose step, so it equals the pre-pose angular vector (tested independently).
"""
    following=np.asarray(following,dtype=float)
    world=np.einsum('nij,nj->ni',rotation(following[:,1:5]),following[:,5:8])
    return np.c_[world,following[:,8:]]-input_effect(states,acceleration,context,
                                                    'nonlinear',angular_damping)[:,10:16]


def fit_readout(features,target,weights,physical_prior,ridge):
    a=np.asarray(features,dtype=float);y=np.asarray(target,dtype=float)
    w=np.asarray(weights,dtype=float);prior=np.asarray(physical_prior,dtype=float)
    if (a.ndim!=2 or a.shape[1]!=53 or y.shape!=(len(a),6) or w.shape!=(len(a),)
            or prior.shape!=(53,6) or ridge not in (.001,.1) or np.any(w<=0)
            or not all(np.isfinite(v).all() for v in (a,y,w,prior))
            or not np.all(a[:,-1]==1)):
        raise ValueError('learned_velocity_fit_input')
    wn=w/w.sum();mean=wn@a;scale=np.maximum(np.sqrt(wn@((a-mean)**2)),1e-6)
    z=(a-mean)/scale;residual=y-a@prior;bias=wn@residual
    coefficient=np.linalg.solve(z.T@(wn[:,None]*z)+ridge*np.eye(53),
                                z.T@(wn[:,None]*(residual-bias)))
    increment=coefficient/scale[:,None]
    increment[-1,:]+=bias-mean@increment
    fitted=prior+increment
    return fitted,dict(feature_mean=mean.tolist(),feature_scale=scale.tolist(),
        weighted_velocity_rmse=np.sqrt(wn@((a@fitted-y)**2)).tolist(),
        physical_prior_weighted_velocity_rmse=np.sqrt(wn@((a@prior-y)**2)).tolist(),
        centered_feature_rank=int(np.linalg.matrix_rank(z)),
        learned_increment_frobenius=float(np.linalg.norm(increment)))


def dq_subspace_distance(record):
    """Unbounded affine D/Q projection: nonzero means no D/Q can represent K."""
    prior,k=validate_record(record);ad=prior.angular_damping
    center=core_matrix('nonlinear',np.zeros(6),np.zeros(6),ad)[:,10:16]
    directions=[]
    for j in range(12):
        d=np.zeros(6);q=np.zeros(6)
        (d if j<6 else q)[j%6]=1
        directions.append((core_matrix('nonlinear',d,q,ad)[:,10:16]-center).ravel())
    basis=np.stack(directions,axis=1);delta=(k-center).ravel()
    return float(np.linalg.norm(delta-basis@np.linalg.lstsq(basis,delta,rcond=None)[0]))

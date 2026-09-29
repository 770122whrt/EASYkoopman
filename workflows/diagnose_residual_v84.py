"""Read-only single-origin error attribution of all 18 frozen v81 residuals.

No fitting, optimizer, rollout, or physics. Historical fit-role data are reused
as development data under the recorded pooled/LOCO split, not new blind tests.
"""
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from koopman.learned_velocity_v81 import validate_record, velocity_target
from koopman.sparse_world_edmd_v30 import feature_names, lift
from workflows.identify_sparse_world_v30 import load_fit_cache

ROOT=Path(__file__).resolve().parents[1]
MODELS=ROOT/'docs/evidence/phase9/learned-velocity-v81-20260926/normalized-quaternion'
OUT=ROOT/'docs/evidence/phase9/residual-attribution-v84-20260927'
GROUPS={'height_rotation':(0,10),'velocity':(10,16),'axis_velocity':(16,25),
        'linear_quadratic_drag':(25,34),'angular_quadratic_drag':(34,37),
        'buoyancy':(37,40),'restoring':(40,43),'gyro':(43,46),
        'linear_world_drag':(46,49),'linear_angular_drag':(49,52),'constant':(52,53)}


def decompose(error, parts, weights):
    """Allocate exact per-axis MSE delta, explicitly retaining group cross terms.

Group allocations sum to total delta but are not causal Shapley values. Removing
one group is a separate single-step intervention and does not sum across groups.
"""
    e=np.asarray(error,dtype=float);w=np.asarray(weights,dtype=float)
    if (e.ndim!=2 or not parts or w.shape!=(len(e),) or np.any(w<=0)
            or not np.isfinite(e).all() or not np.isfinite(w).all()
            or any(np.shape(v)!=e.shape or not np.isfinite(v).all() for v in parts.values())):
        raise ValueError('attribution_input')
    w=w/w.sum();avg=lambda v: w@v
    r=sum(parts.values());learned=e-r
    physical=avg(e*e);residual=avg(learned*learned)
    square=avg(r*r);dot=avg(e*r);delta=residual-physical
    identity=square-2*dot
    groups={}
    for name,g in parts.items():
        groups[name]={'correction_rms':np.sqrt(avg(g*g)).tolist(),
            'correction_mean':avg(g).tolist(), 'error_dot_correction':avg(e*g).tolist(),
            'allocated_delta_mse':avg(g*r-2*e*g).tolist(),
            'remove_group_delta_mse':avg((learned+g)**2-learned**2).tolist()}
    denom=np.sqrt(physical*square)
    alignment=np.divide(dot,denom,out=np.zeros_like(dot),where=denom>0)
    return {'rows':len(e),'physical_rmse':np.sqrt(physical).tolist(),
        'residual_rmse':np.sqrt(residual).tolist(),'correction_rms':np.sqrt(square).tolist(),
        'error_dot_correction':dot.tolist(),'alignment':alignment.tolist(),
        'delta_mse':delta.tolist(), 'correction_square':square.tolist(),
        'identity_max_abs':float(np.max(np.abs(delta-identity))),
        'fraction_rows_worse_per_axis':avg((learned*learned>e*e).astype(float)).tolist(),
        'groups':groups}


def source_activation(phi,mean,scale,source_std):
    p=np.asarray(phi,dtype=float);m=np.asarray(mean);s=np.asarray(scale)
    z=(p-m)/s
    # Constant columns may have ~1e-14 summation noise in saved feature_mean.
    changed=np.where((np.asarray(source_std)==0)&(np.max(abs(p-m),axis=0)>1e-10))[0]
    return {'max_abs_z':np.max(abs(z),axis=0).tolist(),
        'rms_z':np.sqrt(np.mean(z*z,axis=0)).tolist(),
        'fraction_abs_z_gt_5':np.mean(abs(z)>5,axis=0).tolist(),
        'source_constant_changed_columns':changed.tolist()}


def main():
    start=time.monotonic();episodes=load_fit_cache(ROOT)
    configs=list(dict.fromkeys(e.case['configuration'] for e in episodes))
    features=[lift(e.states[:-1],e.context,'nonlinear') for e in episodes]
    weights=np.r_[np.full(256,1/3),np.ones(384)]
    output={'scope':'frozen_same_origin_single_step_velocity_attribution',
        'new_fits':0,'new_solves':0,'new_physics':0,'axis_names':['world_vx','world_vy','world_vz','body_wx','body_wy','body_wz'],
        'axis_units':['m/s']*3+['rad/s']*3,
        'weighting':'first 256 transitions weight 1/3, final 384 weight 1; axis-wise only, no mixed-unit scalar objective',
        'feature_names':feature_names('nonlinear'), 'folds':[],
        'limits':['No new observations; all source episodes were historical fit-role development data.',
                  'True state origin and identical recorded actuator acceleration at every step; no multi-step rollout.',
                  'Group allocations include cross terms; group removal is a diagnostic single-step intervention, not a new fitted model.',
                  'Large standardized activation without nonzero coefficient contribution is not an error cause.']}
    for fold in ['pooled']+['loco_'+c for c in configs]:
        for ridge in (.001,.1):
            path=MODELS/(fold+f'__learned_{ridge:g}.json')
            raw=path.read_bytes();rec=json.loads(raw);prior,k=validate_record(rec)
            train_ids=[i for i,e in enumerate(episodes) if e.case['configuration'] in rec['physical_prior']['configurations']]
            actual={episodes[i].case['run_id']:episodes[i].trace_sha256 for i in train_ids}
            if actual!=rec['physical_prior']['fit_episode_hashes']:raise ValueError('fit_episode_hash_mismatch')
            targets=[velocity_target(e.states[:-1],e.states[1:],e.acceleration,e.context,rec['physical_prior']['angular_damping']) for e in episodes]
            train_phi=np.concatenate([features[i] for i in train_ids]);train_y=np.concatenate([targets[i] for i in train_ids]);train_w=np.tile(weights,len(train_ids))
            source_hash=hashlib.sha256(train_phi.tobytes()+train_y.tobytes()+train_w.tobytes()).hexdigest()
            if source_hash!=rec['audit']['fit_feature_target_sha256']:raise ValueError('fit_array_hash_mismatch')
            wn=train_w/train_w.sum();mean=wn@train_phi
            std=np.sqrt(wn@((train_phi-mean)**2));scale=np.maximum(std,1e-6)
            np.testing.assert_allclose(mean,rec['feature_mean'],rtol=1e-12,atol=1e-12)
            np.testing.assert_allclose(scale,rec['feature_scale'],rtol=1e-12,atol=1e-12)
            # Use source ptp to identify true constants independently of mean roundoff.
            std[np.ptp(train_phi,axis=0)==0]=0
            delta=k-prior.matrix[:,10:16]
            rows=[]
            selections=[('training_aggregate',train_ids)]
            selections += [(c,[i for i,e in enumerate(episodes) if e.case['configuration']==c]) for c in configs]
            for cfg,ids in selections:
                phi=np.concatenate([features[i] for i in ids]);target=np.concatenate([targets[i] for i in ids]);w=np.tile(weights,len(ids))
                ep=target-phi@prior.matrix[:,10:16]
                parts={g:phi[:,a:b]@delta[a:b] for g,(a,b) in GROUPS.items()}
                stat=decompose(ep,parts,w)
                np.testing.assert_allclose(sum(parts.values()),phi@delta,rtol=1e-9,atol=1e-14)
                if cfg=='training_aggregate':np.testing.assert_allclose(stat['residual_rmse'],rec['audit']['weighted_velocity_rmse'],rtol=1e-10,atol=1e-12)
                centered={g:(phi[:,a:b]-mean[a:b])@delta[a:b] for g,(a,b) in GROUPS.items()}
                centered['source_mean_bias']=np.tile(mean@delta,(len(phi),1))
                center_stat=decompose(ep,centered,w)
                np.testing.assert_allclose(center_stat['delta_mse'],stat['delta_mse'],atol=1e-15,rtol=1e-8)
                stat['centered_groups']=center_stat['groups']
                stat['configuration']=cfg;stat['role']='training' if cfg=='training_aggregate' or all(i in train_ids for i in ids) else 'heldout_configuration'
                stat['source_activation']=source_activation(phi,mean,scale,std)
                stat['feature_centered_correction_rms']= (np.sqrt((w/w.sum())@((phi-mean)**2))[:,None]*abs(delta)).tolist()
                rows.append(stat)
            output['folds'].append({'fold':fold,'ridge':ridge,'model_sha256':hashlib.sha256(raw).hexdigest(),
                'fit_feature_target_sha256_verified':source_hash,'fit_episode_hashes_verified':actual,
                'source_scale':scale.tolist(),'source_std':std.tolist(),'delta_matrix':delta.tolist(),'results':rows})
            if time.monotonic()-start>300:raise TimeoutError('attribution_five_minute_bound')
    output['elapsed_seconds']=time.monotonic()-start
    output['max_identity_residual']=max(r['identity_max_abs'] for f in output['folds'] for r in f['results'])
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'result.json').open('x',encoding='utf8') as f:json.dump(output,f,indent=2,allow_nan=False)
    print(json.dumps({'fold_models':len(output['folds']),'rows':sum(len(f['results']) for f in output['folds']),
        'seconds':output['elapsed_seconds'],'max_identity_residual':output['max_identity_residual']}))


if __name__=='__main__':main()

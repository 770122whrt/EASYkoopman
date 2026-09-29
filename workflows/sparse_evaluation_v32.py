"""Frozen pilot comparison policy; missing/failed cases cannot become averages."""
import numpy as np
from workflows.identification_protocol_v32 import cases
from workflows.evaluate_projected_edmd_v24 import squared_errors
from workflows.identification_prediction_v32 import valid_predictions
from koopman.projected_edmd_v24 import decode,rotation
from koopman.sparse_world_edmd_v30 import lift,input_effect


def policy():
    return {'version':'sparse-world-v32-repaired-policy-evaluation-v1','role':'validation',
        'conditional_horizons':[1,20,60,128],'primary_accuracy_horizons':[20,60,128],
        'start_control':128,'conditional_scopes':['pooled','local','heldout'],
        'policy_origins':[128,176],'policy_horizons':[20,60,128],'policy_maximum_horizon':128,
        'full_episode_control_horizon':320,'primary_scopes':['pooled','heldout'],
        'denominator_floor':[.001,.001,.001,.001],
        'conditional_limits':{'macro':.95,'each_configuration_macro':1.05,'each_configuration_group':1.25,
            'over_linear_macro':.95,'each_configuration_over_linear':1.05},
        'policy_each_configuration_macro_max':1.05,
        'numerical_prediction_limits':{'absolute_z':100.,'absolute_velocity_component':100.,'quaternion_norm_tolerance':.001},
        'unprojected':'nonlinear pooled and heldout; diagnostic only; no spectral stability claim',
        'known_physics':'reported separately; noninferiority to persistence is not learned benefit over physics',
        'allowed_claim':'bounded new-episode exact-eight-catalog pilot; per-model LOCO training exclusion, not researcher-unseen platforms',
        'model_handoff':False,'test_access':False}


def _catalog():return {q['run_id']:q for q in cases() if q['role']=='validation'}


def _metric_record(r):
    if type(r.get('complete_aggregate')) is not bool:raise ValueError('sparse_score_failure_semantics')
    if r['complete_aggregate']:
        if r.get('failed_origins',0)!=0:raise ValueError('sparse_score_failure_semantics')
        for key in ('endpoint_rmse','path_rmse'):
            a=np.asarray(r[key],dtype=float)
            if a.shape!=(4,) or not np.isfinite(a).all() or np.any(a<0):raise ValueError('sparse_score_failure_semantics')
    elif r.get('failed_origins',1)<1 or r['endpoint_rmse'] is not None or r['path_rmse'] is not None:
        raise ValueError('sparse_score_failure_semantics')


def _conditional_index(scores):
    catalog=_catalog();p=policy();index={}
    allowed=[('persistence','none'),('known_physics','none')]+[(f,s) for f in ('nonlinear','linear') for s in p['conditional_scopes']]
    expected={(q,f,s,h) for q in catalog for f,s in allowed for h in p['conditional_horizons']}
    for r in scores:
        key=(r['run_id'],r['family'],r['scope'],r['horizon_control_intervals'])
        if key in index:raise ValueError('sparse_score_duplicate')
        q=catalog.get(r['run_id'])
        if (key not in expected or q is None or r['configuration']!=q['configuration']
                or r['mode']!='conditional_projected' or r['origins']!=193-r['horizon_control_intervals']):
            raise ValueError('sparse_score_inventory')
        _metric_record(r)
        if not 0<=r['failed_origins']<=r['origins']:raise ValueError('sparse_score_failure_semantics')
        index[key]=r
    if set(index)!=expected:raise ValueError('sparse_score_inventory')
    return index


def _ratio(a,b):
    if a<=1e-15 and b<=1e-15:return 1.
    return float(a/max(b,1e-15))


def conditional_gate(scores):
    index=_conditional_index(scores);p=policy();catalog=_catalog();configs=list(dict.fromkeys(q['configuration'] for q in catalog.values()))
    required=[r for r in scores if r['family']=='nonlinear' and r['scope'] in p['primary_scopes']]
    complete=all(r['complete_aggregate'] for r in required);gates=[];limits=p['conditional_limits']
    for scope in p['primary_scopes']:
        for h in p['primary_accuracy_horizons']:
            for metric in ('endpoint_rmse','path_rmse'):
                rows=[(index[(q,'nonlinear',scope,h)],index[(q,'linear',scope,h)],index[(q,'persistence','none',h)]) for q in catalog]
                result={'scope':scope,'horizon':h,'metric':metric,'pass':False}
                if all(r['complete_aggregate'] for triple in rows for r in triple):
                    candidate=np.asarray([t[0][metric] for t in rows]);linear=np.asarray([t[1][metric] for t in rows])
                    denominator=np.maximum([t[2][metric] for t in rows],p['denominator_floor'])
                    candidate/=denominator;linear/=denominator
                    config_values={c:candidate[[q['configuration']==c for q in catalog.values()]].mean(0) for c in configs}
                    config_ratios={c:_ratio(float(v.mean()),float(linear[[q['configuration']==c for q in catalog.values()]].mean())) for c,v in config_values.items()}
                    macro=float(candidate.mean());relative=_ratio(macro,float(linear.mean()))
                    passed=(macro<=limits['macro'] and all(v.mean()<=limits['each_configuration_macro'] and max(v)<=limits['each_configuration_group'] for v in config_values.values())
                        and relative<=limits['over_linear_macro'] and max(config_ratios.values())<=limits['each_configuration_over_linear'])
                    result.update(normalized_macro=macro,per_configuration_groups={c:v.tolist() for c,v in config_values.items()},
                        over_linear_macro=relative,per_configuration_over_linear=config_ratios,pass_=bool(passed))
                    result['pass']=result.pop('pass_')
                gates.append(result)
    return {'pass':bool(complete and all(r['pass'] for r in gates)),'primary_all_complete':complete,
        'primary_expected_records':len(required),'gates':gates,'model_handoff':False}


def score_policy_prefix(reference,forecast,horizon):
    steps=2*horizon;prediction=np.asarray(forecast['predictions'],dtype=float);truth=np.asarray(reference,dtype=float)
    complete=len(prediction)>=steps and len(truth)>=steps
    if complete:
        complete=bool(prediction.shape[1:]==(11,) and truth.shape[1:]==(11,) and valid_predictions(prediction[:steps]).all())
    error=squared_errors(truth[:steps],prediction[:steps]) if complete else None
    return {'horizon_control_intervals':horizon,'complete_aggregate':complete,'failed_origins':0 if complete else 1,
        'endpoint_rmse':np.sqrt(error[-1]).tolist() if complete else None,
        'path_rmse':np.sqrt(error.mean(0)).tolist() if complete else None,
        'forecast_failure':forecast['failure'],'later_failure_outside_this_prefix':bool(complete and not forecast['complete'])}


def policy_gate(scores):
    catalog=_catalog();p=policy();index={}
    allowed=[('persistence','none'),('known_physics','none')]+[(f,s) for f in ('nonlinear','linear') for s in p['primary_scopes']]
    expected={(q,f,s,o,h) for q in catalog for f,s in allowed for o in p['policy_origins'] for h in p['policy_horizons']}
    for r in scores:
        key=(r['run_id'],r['family'],r['scope'],r['origin_control'],r['horizon_control_intervals'])
        if key in index:raise ValueError('sparse_score_duplicate')
        if key not in expected or r['configuration']!=catalog[r['run_id']]['configuration'] or r['mode']!='policy_self_recurrence':
            raise ValueError('sparse_score_inventory')
        _metric_record(r);index[key]=r
    if set(index)!=expected:raise ValueError('sparse_score_inventory')
    primary=[r for r in scores if r['family']=='nonlinear'];complete=all(r['complete_aggregate'] for r in primary);gates=[]
    for scope in p['primary_scopes']:
        for h in p['policy_horizons']:
            for metric in ('endpoint_rmse','path_rmse'):
                values={};available=True
                for q,case in catalog.items():
                    for origin in p['policy_origins']:
                        candidate=index[(q,'nonlinear',scope,origin,h)];base=index[(q,'persistence','none',origin,h)]
                        if not candidate['complete_aggregate'] or not base['complete_aggregate']:available=False;continue
                        values.setdefault(case['configuration'],[]).append(np.asarray(candidate[metric])/np.maximum(base[metric],p['denominator_floor']))
                means={c:float(np.mean(a)) for c,a in values.items()}
                gates.append({'scope':scope,'horizon':h,'metric':metric,'configuration_macros':means,
                    'pass':bool(available and max(means.values(),default=np.inf)<=p['policy_each_configuration_macro_max'])})
    return {'pass':bool(complete and all(g['pass'] for g in gates)),'primary_all_complete':complete,'gates':gates,'model_handoff':False}


def decode_lift(features):
    f=np.asarray(features,dtype=float);y=np.full((len(f),11),np.nan)
    good=np.isfinite(f).all(1)
    if not np.any(good):return y
    ids=np.flatnonzero(good);matrices=f[ids,1:10].reshape(-1,3,3)
    u,s,vh=np.linalg.svd(matrices);valid=s[:,-1]>1e-10
    u=u[valid];vh=vh[valid];ids=ids[valid]
    if not len(ids):return y
    correction=np.ones((len(ids),3));correction[:,-1]=np.linalg.det(u@vh)
    r=(u*correction[:,None,:])@vh
    minimal=np.c_[f[ids,0],r[:,:,0],r[:,:,1],f[ids,10:16]]
    states=decode(minimal);states[:,5:8]=np.einsum('nji,nj->ni',r,f[ids,10:13]);y[ids]=states
    return y


def unprojected_rollout(states,acceleration,model,context,horizon):
    x=np.asarray(states,dtype=float);u=np.asarray(acceleration,dtype=float);steps=2*horizon
    origins=np.arange(256,len(u)-steps+1,2)
    if len(x)!=len(u)+1 or not len(origins):raise ValueError('sparse_unprojected_contract')
    prediction=x[origins].copy();latent=lift(prediction,context,model.family)
    alive=np.ones(len(origins),dtype=bool);failure=np.full(len(origins),-1,dtype=int);summed=np.zeros((len(origins),4));endpoint=np.zeros_like(summed);exceptions=[]
    for tick in range(steps):
        ids=np.flatnonzero(alive)
        if not len(ids):break
        try:
            with np.errstate(over='ignore',invalid='ignore',divide='ignore'):
                following=latent[ids]@model.matrix+input_effect(prediction[ids],u[origins[ids]+tick],context,model.family,model.angular_damping)
            new=decode_lift(following);good=valid_predictions(new)
        except (ValueError,FloatingPointError,np.linalg.LinAlgError) as exc:
            exceptions.append({'tick':tick+1,'error':f'{type(exc).__name__}:{exc}'})
            good=np.zeros(len(ids),dtype=bool)
        bad=ids[~good]
        alive[bad]=False;failure[bad]=tick+1;ids=ids[good]
        if len(ids):
            latent[ids]=following[good];prediction[ids]=new[good]
            error=squared_errors(x[origins[ids]+tick+1],prediction[ids]);summed[ids]+=error;endpoint[ids]=error
    complete=bool(alive.all())
    return {'horizon_control_intervals':horizon,'origins':len(origins),'failed_origins':int(np.sum(~alive)),
        'first_failure_physics_tick':failure.tolist(),'complete_aggregate':complete,'exceptions':exceptions,
        'endpoint_rmse':np.sqrt(endpoint.mean(0)).tolist() if complete else None,
        'path_rmse':np.sqrt(summed.mean(0)/steps).tolist() if complete else None,
        'full_matrix_spectral_radius':float(np.max(np.abs(np.linalg.eigvals(model.matrix)))),
        'feature_reprojection':False,'pose_decode':'nearest_rotation_readout_only; latent features not reset'}

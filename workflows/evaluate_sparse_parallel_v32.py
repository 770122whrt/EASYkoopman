"""Execution-only parallel resume of the frozen v32 scientific evaluation.

Four independent episode workers; original prediction/score primitives and
model/data identities are unchanged. Original partial outputs remain intact.
"""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import json,time,sys,hashlib
from pathlib import Path
from dataclasses import asdict
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
from workflows.evaluate_sparse_world_v32 import dump
from workflows.validation_release_v32 import read,sha,validate_freeze
from workflows.identification_protocol_v32 import cases,pulse
from workflows.identification_adapter_v32 import load_episode
from workflows.identification_prediction_v32 import conditional_rollout,policy_forecast
from workflows.identify_sparse_world_v30 import from_record
from workflows.sparse_evaluation_v32 import policy,conditional_gate,policy_gate,score_policy_prefix,unprojected_rollout
from workflows.formal_evidence_v25 import verify_raw
from koopman.physical_prediction_v29 import known_step

def cached_forecast(directory,q,family,scope,origin):
    name=q['run_id']+'__'+family+'__'+scope+'__'+str(origin)
    p=Path(directory)/(name+'.npz');meta=p.with_suffix('.json')
    if not p.is_file() or not meta.is_file():return None
    r=read(meta)
    if (r['run_id']!=q['run_id'] or r['configuration']!=q['configuration'] or r['role']!='validation'
        or r['family']!=family or r['scope']!=scope or r['origin_control']!=origin or sha(p)!=r['forecast_sha256']):
        raise ValueError('parallel_forecast_checkpoint_identity')
    with np.load(p,allow_pickle=False) as data:
        result={k:r[k] for k in ('complete','failure','origin_actuator_time_s','future_inputs')}
        result.update(predictions=data['predictions'].copy(),commands=data['commands'].copy())
    x=result['predictions'];u=result['commands']
    if (x.ndim!=2 or x.shape[1]!=11 or u.ndim!=2 or u.shape[1]!=4 or len(x)>256 or len(u)>128
        or not np.isfinite(x).all() or not np.isfinite(u).all()
        or (result['complete'] and (len(x)!=256 or len(u)!=128))):raise ValueError('parallel_checkpoint_shape')
    result['reused_forecast_path']=str(p)
    return result

def parity_task(task):
    root=Path(task['root']);family=task['family'];scope=task['scope'];q=cases()[0];origin=128
    fit=root/'source/results/phase8.4-sparse-world-pilot-v30-20260913';evidence=root/'docs/evidence/phase8_4/server-validation-20260913-r19/validation'
    accepted=read(evidence/'acceptance.json')
    e=load_episode(evidence/'raw/validation'/q['run_id']/'trace.json',q,accepted['source_commit'],accepted['trace_sha256'][q['run_id']],root)
    prior=cached_forecast(fit/'independent-validation-v32/forecasts',q,family,scope,origin)
    if prior is None:raise ValueError('parity_checkpoint_required')
    if family=='persistence':predict=lambda x,a,c:x
    elif family=='known_physics':predict=lambda x,a,c:known_step(x,a,c,angular_damping=float(np.float32(.05)),gyroscopic=True)
    else:predict=from_record(read(fit/'models'/(family+'__'+(scope if scope=='pooled' else scope+'-'+q['configuration'])+'.json')))
    fresh=policy_forecast(e.states[2*origin],e.arrays['issued_control'][:2*origin],pulse(q)[origin:origin+2],q['configuration'],e.context,predict)
    if not fresh['complete']:raise ValueError('parity_forecast_failed')
    xerr=float(np.max(np.abs(fresh['predictions']-prior['predictions'][:4])))
    uerr=float(np.max(np.abs(fresh['commands']-prior['commands'][:2])))
    if xerr>1e-12 or uerr>1e-12:raise ValueError('parallel_numeric_parity')
    return {'family':family,'scope':scope,'physics_ticks':4,'maximum_state_difference':xerr,'maximum_command_difference':uerr}

def work(task):
    root=Path(task['root']);q=task['case'];deadline=task['deadline'];started=time.monotonic()
    package=root/'docs/evidence/phase8_4/validation-package-20260913-r19'
    fit=root/'source/results/phase8.4-sparse-world-pilot-v30-20260913'
    f=read(package/'validation-freeze.json')
    models={name:from_record(read(fit/'models'/(name+'.json'))) for name in f['models']}
    evidence=root/'docs/evidence/phase8_4/server-validation-20260913-r19/validation'
    accepted=read(evidence/'acceptance.json');raw=evidence/'raw'
    out=fit/'independent-validation-v32-parallel'/'cases'/q['run_id'];out.mkdir(exist_ok=False)
    (out/'episodes').mkdir();(out/'forecasts').mkdir()
    conditional=[];full=[];latent=[];self_scores=[];cache={}
    def check():
        if time.monotonic()>=deadline:raise TimeoutError('v32_shared_analysis_budget')
    def physics(x,a,c):return known_step(x,a,c,angular_damping=float(np.float32(.05)),gyroscopic=True)
    def forecast_or_cache(*args,**kwargs):
        origin=len(args[1])//2
        prior=cached_forecast(fit/'independent-validation-v32/forecasts',q,family,scope,origin)
        return prior if prior is not None else policy_forecast(*args,**kwargs)
    check();e=load_episode(raw/'validation'/q['run_id']/'trace.json',q,accepted['source_commit'],accepted['trace_sha256'][q['run_id']],root)
    trace=read(raw/'validation'/q['run_id']/'trace.json');attrs=trace['geometry']['body_physics_attributes']
    if (float(attrs['physxRigidBody:linearDamping'])!=0 or float(attrs['physxRigidBody:angularDamping'])!=float(np.float32(.05))
        or attrs['physxRigidBody:enableGyroscopicForces']!='True'):raise ValueError('validation_backend_changed')
    for row in trace['substeps']:
        for b in (row['before']['backend'],row['command']['backend'],row['backend_after_physics']):
            np.testing.assert_allclose(np.asarray(b['inertia_9']).reshape(3,3),np.diag(e.context.inertia),rtol=0,atol=1e-8)
            np.testing.assert_allclose(b['com_local_pose_xyzw'],[[0,0,0,0,0,0,1]],rtol=0,atol=1e-8)
    p=out/'episodes'/(q['run_id']+'.npz');np.savez_compressed(p,**e.arrays,acceleration=e.acceleration)
    dump(p.with_suffix('.json'),{'case':q,'context':asdict(e.context),'trace_sha256':e.trace_sha256,'source_commit':e.source_commit,'acceptance':e.acceptance,'arrays_sha256':sha(p)})
    cache[q['run_id']]=sha(p)
    predictors=[('persistence','none',lambda x,a,c:x),('known_physics','none',physics)]
    predictors += [(family,scope,models[family+'__'+(scope if scope=='pooled' else scope+'-'+q['configuration'])]) for family in ('nonlinear','linear') for scope in ('pooled','local','heldout')]
    for family,scope,predict in predictors:
        base={'run_id':q['run_id'],'configuration':q['configuration'],'family':family,'scope':scope,'role':'validation'}
        for h in policy()['conditional_horizons']:
            check();score=conditional_rollout(e.states,e.acceleration,predict,e.context,h)
            conditional.append(dict(base,mode='conditional_projected',**score))
            if family=='nonlinear' and scope in ('pooled','heldout'):
                check();score=unprojected_rollout(e.states,e.acceleration,predict,e.context,h)
                latent.append(dict(base,mode='unprojected',**score))
        if scope=='local':continue
        check();score=conditional_rollout(e.states,e.acceleration,predict,e.context,320,start_control=0)
        full.append(dict(base,mode='full_episode_conditional',**score))
        external=pulse(q)
        for origin in policy()['policy_origins']:
            check();forecast=forecast_or_cache(e.states[2*origin],e.arrays['issued_control'][:2*origin],external[origin:origin+128],q['configuration'],e.context,predict,deadline=deadline)
            name=q['run_id']+'__'+family+'__'+scope+'__'+str(origin)
            p=out/'forecasts'/(name+'.npz')
            if forecast.get('reused_forecast_path'):p=Path(forecast['reused_forecast_path'])
            else:np.savez_compressed(p,predictions=forecast['predictions'],commands=forecast['commands'])
            dump(out/'forecasts'/(name+'.json'),dict(base,origin_control=origin,forecast_sha256=sha(p),**{k:v for k,v in forecast.items() if k not in ('predictions','commands')}))
            for h in policy()['policy_horizons']:
                score=score_policy_prefix(e.states[2*origin+1:],forecast,h)
                self_scores.append(dict(base,mode='policy_self_recurrence',origin_control=origin,**score))
    for name,values in [('conditional',conditional),('full-episode',full),('unprojected',latent),('policy',self_scores)]:dump(out/(name+'.json'),values)
    print(json.dumps({'validation_scored':q['run_id'],'conditional':len(conditional),'policy':len(self_scores),'elapsed_s':time.monotonic()-started}),flush=True)
    return {'run_id':q['run_id'],'conditional':conditional,'full_episode':full,'unprojected':latent,'policy':self_scores,'cache':cache,'seconds':time.monotonic()-started}

def run(root):
    root=Path(root);fit=root/'source/results/phase8.4-sparse-world-pilot-v30-20260913'
    package=root/'docs/evidence/phase8_4/validation-package-20260913-r19'
    f=read(package/'validation-freeze.json');validate_freeze(f)
    for name,h in f['evaluation_source_sha256'].items():
        if sha(root/name)!=h:raise ValueError('frozen_evaluation_source_changed:'+name)
    for name,h in read(fit/'analysis-source.json')['files_sha256'].items():
        if sha(root/name)!=h:raise ValueError('frozen_fit_source_changed:'+name)
    for name,h in f['models'].items():
        if sha(fit/'models'/(name+'.json'))!=h:raise ValueError('frozen_model_changed:'+name)
    evidence=root/'docs/evidence/phase8_4/server-validation-20260913-r19/validation';accepted=read(evidence/'acceptance.json')
    qs=cases()
    if (accepted['status']!='identification_source_runtime_inventory_pullback_accepted' or accepted['stage']!='validation'
        or accepted['source_commit']!=read(package/'package.json')['source_commit']
        or accepted['training_eligible'] is not False or set(accepted['trace_sha256'])!={q['run_id'] for q in qs}):raise ValueError('parallel_validation_inventory')
    verify_raw(evidence/'raw',read(evidence/'raw/inventory.json'))
    execution=read(fit/'v32-parallel-execution-freeze.json')
    if (sha(Path(__file__))!=execution['parallel_source_sha256'] or execution['workers']!=4
        or execution['scientific_validation_freeze_sha256']!=sha(package/'validation-freeze.json')):raise ValueError('parallel_execution_source_changed')
    for name,h in execution['prior_output_sha256'].items():
        if sha(fit/name)!=h:raise ValueError('parallel_prior_output_changed')
    out=fit/'independent-validation-v32-parallel';out.mkdir(exist_ok=False);(out/'cases').mkdir()
    ledger=root/'docs/evidence/phase8_4/identification-fit-20260913-r17/analysis-budget.json';budget=read(ledger)
    reserve=3600-budget['charged_seconds']
    if reserve<120:raise ValueError('parallel_budget_exhausted')
    attempt={'stage':'v32_parallel_same_algorithm_resume','status':'reserved','charged_seconds':reserve,'workers':4}
    budget['attempts'].append(attempt);budget['charged_seconds']+=reserve;dump(ledger,budget)
    started=time.monotonic();deadline=started+reserve-60;results={}
    status={'status':'running','refits':0,'test_access':False,'model_handoff':False,'workers':4,'execution_only_amendment':True}
    try:
        with ProcessPoolExecutor(max_workers=4) as pool:
            jobs={pool.submit(work,{'root':str(root),'case':q,'deadline':deadline}):q['run_id'] for q in qs}
            for job in as_completed(jobs):
                r=job.result();results[r['run_id']]=r
                print(json.dumps({'completed_case':r['run_id'],'completed_cases':len(results),'seconds':r['seconds'],'wall_seconds':time.monotonic()-started}),flush=True)
                dump(out/'completed-cases.json',{'completed':list(results),'total':16})
        ordered=[results[q['run_id']] for q in qs]
        joined={key:[r for item in ordered for r in item[key]] for key in ('conditional','full_episode','unprojected','policy')}
        for key,values in joined.items():dump(out/(key.replace('_','-')+'.json'),values)
        c=conditional_gate(joined['conditional']);p=policy_gate(joined['policy'])
        status.update(status='bounded_pilot_go' if c['pass'] and p['pass'] else 'NO_SELECTION',conditional_gate=c,policy_gate=p,
            counts={k:len(v) for k,v in joined.items()},validation_acceptance_sha256=sha(evidence/'acceptance.json'),
            validation_freeze_sha256=sha(package/'validation-freeze.json'),execution_freeze_sha256=sha(fit/'v32-parallel-execution-freeze.json'),
            caveat='Projected finite approximation; no full-operator stability, MPC handoff or learned increment over known physics inferred.')
        attempt['status']='completed'
    except BaseException as exc:
        status.update(status='incomplete',exception=f'{type(exc).__name__}:{exc}',completed_cases=list(results));raise
    finally:
        elapsed=time.monotonic()-started;budget['charged_seconds']+=elapsed-reserve;attempt['charged_seconds']=elapsed;dump(ledger,budget)
        status['seconds']=elapsed;dump(out/'status.json',status)
    print(json.dumps(status))

if __name__=='__main__':run(Path.cwd())

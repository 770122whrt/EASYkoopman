"""One-shot frozen validation; no fitting and no future truth in policy forecasts."""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('MKL_NUM_THREADS','1')
import json,time,hashlib
from pathlib import Path
from dataclasses import asdict
import numpy as np
from workflows.validation_release_v30 import read,sha,validate_freeze
from workflows.identification_protocol_v29 import cases,pulse
from workflows.identification_adapter_v29 import load_episode
from workflows.identification_prediction_v29 import conditional_rollout,policy_forecast
from workflows.identify_sparse_world_v30 import from_record
from workflows.sparse_evaluation_v30 import policy,conditional_gate,policy_gate,score_policy_prefix,unprojected_rollout
from workflows.formal_evidence_v25 import verify_raw
from koopman.physical_prediction_v29 import known_step

def dump(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False,default=lambda a:a.tolist())+'\n',encoding='utf8')

def run(root):
    root=Path(root);package=root/'docs/evidence/phase8_4/validation-package-20260913-r18'
    fit=root/'source/results/phase8.4-sparse-world-pilot-v30-20260913'
    f=read(package/'validation-freeze.json');validate_freeze(f)
    for name,h in f['evaluation_source_sha256'].items():
        if sha(root/name)!=h:raise ValueError('evaluation_source_changed:'+name)
    for name,h in read(fit/'analysis-source.json')['files_sha256'].items():
        if sha(root/name)!=h:raise ValueError('fit_source_changed:'+name)
    if sha(fit/'analysis-source.json')!=f['analysis_source_sha256']:raise ValueError('analysis_identity')
    models={}
    for name,h in f['models'].items():
        p=fit/'models'/(name+'.json')
        if sha(p)!=h:raise ValueError('evaluation_model_changed:'+name)
        models[name]=from_record(read(p))
    evidence=root/'docs/evidence/phase8_4/server-validation-20260913-r18/validation'
    accepted=read(evidence/'acceptance.json');raw=evidence/'raw'
    qs=[q for q in cases() if q['role']=='validation']
    if (accepted['status']!='identification_source_runtime_inventory_pullback_accepted' or accepted['stage']!='validation'
        or accepted['source_commit']!=read(package/'package.json')['source_commit']
        or set(accepted['trace_sha256'])!={q['run_id'] for q in qs}
        or accepted['training_eligible'] is not False):raise ValueError('validation_inventory')
    verify_raw(raw,read(raw/'inventory.json'))
    out=fit/'independent-validation';out.mkdir(exist_ok=False);(out/'episodes').mkdir();(out/'forecasts').mkdir()
    ledger=root/'docs/evidence/phase8_4/identification-fit-20260913-r17/analysis-budget.json'
    budget=read(ledger);reserve=3600-budget['charged_seconds']
    if reserve<30:raise ValueError('evaluation_budget_exhausted')
    attempt={'stage':'v30_independent_validation_adaptation_and_all_scores','status':'reserved','charged_seconds':reserve}
    budget['attempts'].append(attempt);budget['charged_seconds']+=reserve;dump(ledger,budget)
    started=time.monotonic();deadline=started+reserve-5
    conditional=[];full=[];latent=[];self_scores=[];cache={};status={'status':'running','refits':0,'test_access':False,'model_handoff':False}
    def check():
        if time.monotonic()>=deadline:raise TimeoutError('v30_shared_analysis_budget')
    def physics(x,a,c):return known_step(x,a,c,angular_damping=float(np.float32(.05)),gyroscopic=True)
    try:
        for q in qs:
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
                    check();forecast=policy_forecast(e.states[2*origin],e.arrays['issued_control'][:2*origin],external[origin:origin+128],q['configuration'],e.context,predict,deadline=deadline)
                    name=q['run_id']+'__'+family+'__'+scope+'__'+str(origin)
                    p=out/'forecasts'/(name+'.npz');np.savez_compressed(p,predictions=forecast['predictions'],commands=forecast['commands'])
                    dump(p.with_suffix('.json'),dict(base,origin_control=origin,forecast_sha256=sha(p),**{k:v for k,v in forecast.items() if k not in ('predictions','commands')}))
                    for h in policy()['policy_horizons']:
                        score=score_policy_prefix(e.states[2*origin+1:],forecast,h)
                        self_scores.append(dict(base,mode='policy_self_recurrence',origin_control=origin,**score))
            for name,values in [('conditional',conditional),('full-episode',full),('unprojected',latent),('policy',self_scores)]:dump(out/(name+'.json'),values)
            print(json.dumps({'validation_scored':q['run_id'],'conditional':len(conditional),'policy':len(self_scores),'elapsed_s':time.monotonic()-started}),flush=True)
        c=conditional_gate(conditional);p=policy_gate(self_scores)
        status.update(status='bounded_pilot_go' if c['pass'] and p['pass'] else 'NO_SELECTION',conditional_gate=c,policy_gate=p,
            counts={'conditional':len(conditional),'full_episode':len(full),'unprojected':len(latent),'policy':len(self_scores)},
            validation_acceptance_sha256=sha(evidence/'acceptance.json'),validation_freeze_sha256=sha(package/'validation-freeze.json'),episode_arrays_sha256=cache,
            caveat='Projected finite approximation; full A spectrum and unprojected failures reported separately; no MPC handoff or known-physics learning increment inferred.')
        attempt['status']='completed'
    except BaseException as exc:
        status.update(status='incomplete',exception=f'{type(exc).__name__}:{exc}');raise
    finally:
        for name,values in [('conditional',conditional),('full-episode',full),('unprojected',latent),('policy',self_scores)]:dump(out/(name+'.json'),values)
        elapsed=time.monotonic()-started;budget['charged_seconds']+=elapsed-reserve;attempt['charged_seconds']=elapsed
        dump(ledger,budget);status['seconds']=elapsed;dump(out/'status.json',status)
    print(json.dumps(status))

if __name__=='__main__':run(Path.cwd())

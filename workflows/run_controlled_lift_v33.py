"""One frozen local fit-only timing repair assay; no server or validation access."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import json,hashlib,time
from pathlib import Path
import numpy as np
from workflows.identify_sparse_world_v30 import load_fit_cache,from_record
from workflows.controlled_lift_v33 import fit_lift_matrix,full_rollout
from workflows.identification_prediction_v32 import conditional_rollout
from koopman.physical_prediction_v29 import known_step


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')


def run(root):
    root=Path(root);out=root/'source/results/phase8.4-controlled-lift-v33-20260913';freeze=read(out/'freeze.json')
    if (out/'status.json').exists() or (out/'models').exists():raise ValueError('v33_one_shot_already_started')
    for name,h in freeze['source_sha256'].items():
        if sha(root/name)!=h:raise ValueError('v33_source_changed:'+name)
    old=root/'source/results/phase8.4-sparse-world-pilot-v30-20260913'
    for name,h in freeze['parent_models_sha256'].items():
        if sha(old/'models'/(name+'.json'))!=h:raise ValueError('v33_parent_model_changed')
    if sha(root/freeze['fit_inventory_path'])!=freeze['fit_inventory_sha256']:raise ValueError('v33_fit_inventory_changed')
    (out/'models').mkdir();(out/'cases').mkdir()
    budget=read(out/'budget.json');reserve=freeze['fit_analysis_limit_seconds']
    attempt={'stage':'frozen_nine_matrix_refits_and_1440_fit_scores','status':'reserved','charged_seconds':reserve}
    budget['fit_analysis_attempts'].append(attempt);budget['fit_analysis_charged_seconds']+=reserve;dump(out/'budget.json',budget)
    started=time.monotonic();deadline=started+reserve-10
    status={'status':'running','role':'fit_diagnostic','independent_validation':False,'new_server_runs':0,'model_handoff':False,'test_access':False}
    all_scores=[];fits={}
    def check():
        if time.monotonic()>=deadline:raise TimeoutError('v33_fixed_fit_analysis_limit')
    try:
        episodes=load_fit_cache(root)
        parents={name:read(old/'models'/(name+'.json')) for name in freeze['parent_models_sha256']}
        reference={name:from_record(r) for name,r in parents.items()}
        for name in freeze['refit_models']:
            check();p=parents[name];subset=[e for e in episodes if e.case['configuration'] in p['configurations']]
            record,matrix=fit_lift_matrix(subset,p);record['parent_sha256']=freeze['parent_models_sha256'][name]
            record['experiment_freeze_sha256']=sha(out/'freeze.json');dump(out/'models'/(name+'.json'),record)
            fits[name]=matrix
        for e in episodes:
            records=[];cfg=e.case['configuration'];base={'run_id':e.case['run_id'],'configuration':cfg,'role':'fit_diagnostic'}
            paths=[]
            for scope in ('pooled','heldout'):
                suffix=scope if scope=='pooled' else scope+'-'+cfg;name='nonlinear__'+suffix;ref=reference[name]
                for mode,input_mode,matrix in [('old_full','old',ref.matrix),('changed_input_only','corrected',ref.matrix),('refit_full','corrected',fits[name])]:
                    paths.append(('nonlinear',scope,mode,ref,matrix,input_mode))
                paths.append(('nonlinear',scope,'projected',ref,None,None))
                paths.append(('linear',scope,'projected',reference['linear__'+suffix],None,None))
            physics=lambda x,a,c:known_step(x,a,c,angular_damping=float(np.float32(.05)),gyroscopic=True)
            paths.extend([('known_physics','none','projected',physics,None,None),('persistence','none','projected',lambda x,a,c:x,None,None)])
            for family,scope,mode,predict,matrix,input_mode in paths:
                for horizon in (1,20,60,128,320):
                    check();start=0 if horizon==320 else 128
                    if matrix is None:score=conditional_rollout(e.states,e.acceleration,predict,e.context,horizon,start_control=start)
                    else:score=full_rollout(e.states,e.acceleration,predict,e.context,matrix,input_mode,horizon,start_control=start)
                    records.append(dict(base,family=family,scope=scope,mode=mode,**score))
            dump(out/'cases'/(e.case['run_id']+'.json'),records);all_scores.extend(records)
            print(json.dumps({'case':e.case['run_id'],'completed_cases':len(all_scores)//60,'scores':len(all_scores),'seconds':time.monotonic()-started}),flush=True)
        if len(fits)!=9 or len(all_scores)!=1440:raise ValueError('v33_result_inventory')
        dump(out/'scores.json',all_scores)
        summary=[]
        for family,scope,mode,horizon in dict.fromkeys((r['family'],r['scope'],r['mode'],r['horizon_control_intervals']) for r in all_scores):
            rows=[r for r in all_scores if (r['family'],r['scope'],r['mode'],r['horizon_control_intervals'])==(family,scope,mode,horizon)]
            complete=all(r['complete_aggregate'] for r in rows)
            ticks=[n for r in rows for n in r.get('first_failure_physics_tick',[]) if n>0]
            summary.append({'family':family,'scope':scope,'mode':mode,'horizon':horizon,'records':len(rows),
                'complete_records':sum(r['complete_aggregate'] for r in rows),'failed_origins':sum(r['failed_origins'] for r in rows),
                'first_failure_range':([min(ticks),max(ticks)] if ticks else None),
                'mean_endpoint':np.mean([r['endpoint_rmse'] for r in rows],0).tolist() if complete else None,
                'mean_path':np.mean([r['path_rmse'] for r in rows],0).tolist() if complete else None})
        dump(out/'summary.json',summary)
        required=[r for r in all_scores if r['mode']=='refit_full']
        all_complete=all(r['complete_aggregate'] for r in required)
        status.update(status='fit_diagnostic_complete',new_matrices=len(fits),new_velocity_parameter_fits=0,scores=len(all_scores),
            refit_full_complete_records=sum(r['complete_aggregate'] for r in required),refit_full_records=len(required),
            hypothesis='timing_refit_removes_fit_instability_only' if all_complete else 'input_timing_correction_insufficient',
            next_evidence_admitted=False,reason='No independent validation or unique learned benefit established by fit diagnostics.')
        attempt['status']='completed'
    except BaseException as exc:
        attempt['status']='failed';status.update(status='incomplete',exception=f'{type(exc).__name__}:{exc}',scores=len(all_scores));raise
    finally:
        elapsed=time.monotonic()-started;attempt['charged_seconds']=elapsed;budget['fit_analysis_charged_seconds']+=elapsed-reserve
        dump(out/'budget.json',budget);status['seconds']=elapsed;dump(out/'status.json',status)
    print(json.dumps(status),flush=True)


if __name__=='__main__':run(Path.cwd())

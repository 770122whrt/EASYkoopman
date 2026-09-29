"""Frozen240score fit-only screen for the full-state projected candidate."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import json,time,hashlib
from pathlib import Path
import numpy as np
from koopman.state_projection_v34 import from_record
from workflows.identify_sparse_world_v30 import load_fit_cache
from workflows.identification_prediction_v32 import conditional_rollout
from workflows.state_projection_v34 import fit_screen


def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,value):Path(p).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')


def run(root):
    root=Path(root);out=root/'source/results/phase8.4-state-projection-v34-20260913';freeze=read(out/'freeze.json')
    if (out/'status.json').exists() or (out/'cases').exists():raise ValueError('v34_one_shot_already_started')
    for name,h in freeze['source_sha256'].items():
        if sha(root/name)!=h:raise ValueError('v34_source_changed:'+name)
    for name,h in freeze['input_sha256'].items():
        if sha(root/name)!=h:raise ValueError('v34_input_changed:'+name)
    out.joinpath('cases').mkdir();budget=read(out/'budget.json');reserve=freeze['analysis_limit_seconds']
    attempt={'stage':'fixed240fit_scores_and_screen','status':'reserved','charged_seconds':reserve}
    budget['analysis_attempts'].append(attempt);budget['analysis_charged_seconds']+=reserve;dump(out/'budget.json',budget)
    started=time.monotonic();deadline=started+reserve-10;records=[]
    status={'status':'running','role':'fit_diagnostic','new_fits':0,'new_server_runs':0,'independent_validation':False,'model_handoff':False,'test_access':False}
    def check():
        if time.monotonic()>=deadline:raise TimeoutError('v34_analysis_limit')
    try:
        episodes=load_fit_cache(root);models={}
        old=root/'source/results/phase8.4-sparse-world-pilot-v30-20260913/models';v33=root/'source/results/phase8.4-controlled-lift-v33-20260913'
        for name in freeze['model_names']:
            parent=old/(name+'.json');models[name]=from_record(read(v33/'models'/(name+'.json')),read(parent),sha(parent))
        baseline=read(v33/'scores.json')
        for e in episodes:
            rows=[]
            for scope in ('pooled','heldout'):
                name='nonlinear__'+(scope if scope=='pooled' else scope+'-'+e.case['configuration'])
                for horizon in (1,20,60,128,320):
                    check();score=conditional_rollout(e.states,e.acceleration,models[name],e.context,horizon,start_control=0 if horizon==320 else 128)
                    rows.append(dict(run_id=e.case['run_id'],configuration=e.case['configuration'],role='fit_diagnostic',
                        family='nonlinear_v34',scope=scope,mode='full_state_projected',model_id=name,**score))
            records.extend(rows);dump(out/'cases'/(e.case['run_id']+'.json'),rows)
            print(json.dumps({'case':e.case['run_id'],'completed_cases':len(records)//10,'scores':len(records),'seconds':time.monotonic()-started}),flush=True)
        if len(records)!=240:raise ValueError('v34_score_inventory')
        dump(out/'scores.json',records);gate=fit_screen(records,baseline);summary=[]
        for scope in ('pooled','heldout'):
            for horizon in (1,20,60,128,320):
                rows=[r for r in records if r['scope']==scope and r['horizon_control_intervals']==horizon]
                complete=all(r['complete_aggregate'] for r in rows)
                summary.append({'scope':scope,'horizon':horizon,'records':len(rows),'complete_records':sum(r['complete_aggregate'] for r in rows),
                    'failed_origins':sum(r['failed_origins'] for r in rows),
                    'mean_endpoint':np.mean([r['endpoint_rmse'] for r in rows],0).tolist() if complete else None,
                    'mean_path':np.mean([r['path_rmse'] for r in rows],0).tolist() if complete else None})
        dump(out/'summary.json',summary);status.update(status='fit_screen_go' if gate['pass'] else 'fit_screen_no_go',
            gate=gate,complete_scores=sum(r['complete_aggregate'] for r in records),scores=len(records),
            caveat='Fit-only screening; no independent benefit, full-operator stability or MPC handoff inferred.')
        attempt['status']='completed'
    except BaseException as exc:
        status.update(status='incomplete',exception=f'{type(exc).__name__}:{exc}',scores=len(records));attempt['status']='failed';raise
    finally:
        elapsed=time.monotonic()-started;attempt['charged_seconds']=elapsed;budget['analysis_charged_seconds']+=elapsed-reserve
        dump(out/'budget.json',budget);status['seconds']=elapsed;dump(out/'status.json',status)
    print(json.dumps(status),flush=True)


if __name__=='__main__':run(Path.cwd())

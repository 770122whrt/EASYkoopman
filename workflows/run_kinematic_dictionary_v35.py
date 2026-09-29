"""One frozen nine-readout fit and240score diagnostic, without server access."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import time
from pathlib import Path
import numpy as np
from workflows.run_state_projection_v34 import read,sha,dump
from workflows.kinematic_dictionary_v35 import fit_readout,from_record,fit_screen
from workflows.identify_sparse_world_v30 import load_fit_cache
from workflows.identification_prediction_v32 import conditional_rollout


def run(root):
    root=Path(root);out=root/'source/results/phase8.4-kinematic-dictionary-v35-20260913';freeze=read(out/'freeze.json')
    if (out/'status.json').exists() or (out/'models').exists():raise ValueError('v35_one_shot_already_started')
    for name,h in {**freeze['source_sha256'],**freeze['input_sha256']}.items():
        if sha(root/name)!=h:raise ValueError('v35_bound_file_changed:'+name)
    out.joinpath('models').mkdir();out.joinpath('cases').mkdir();budget=read(out/'budget.json');reserve=freeze['analysis_limit_seconds']
    attempt={'stage':'nine_pose_readout_fits_and240fit_scores','status':'reserved','charged_seconds':reserve}
    budget['analysis_attempts'].append(attempt);budget['analysis_charged_seconds']+=reserve;dump(out/'budget.json',budget)
    started=time.monotonic();deadline=started+reserve-10;records=[]
    status={'status':'running','role':'fit_diagnostic','new_pose_readout_fits':0,'new_velocity_parameter_fits':0,
        'new_server_runs':0,'independent_validation':False,'model_handoff':False,'test_access':False}
    def check():
        if time.monotonic()>=deadline:raise TimeoutError('v35_analysis_limit')
    try:
        episodes=load_fit_cache(root);models={};old=root/'source/results/phase8.4-sparse-world-pilot-v30-20260913/models'
        for name in freeze['model_names']:
            check();p=old/(name+'.json');parent=read(p)
            selected=[e for e in episodes if e.case['configuration'] in parent['configurations']]
            record=fit_readout(selected,parent,sha(p));record['model_id']=name
            dump(out/'models'/(name+'.json'),record);models[name]=from_record(record,parent,sha(p))
            status['new_pose_readout_fits']+=1
        baseline=read(root/'source/results/phase8.4-controlled-lift-v33-20260913/scores.json')
        for e in episodes:
            rows=[]
            for scope in ('pooled','heldout'):
                name='nonlinear__'+(scope if scope=='pooled' else scope+'-'+e.case['configuration'])
                for horizon in (1,20,60,128,320):
                    check();score=conditional_rollout(e.states,e.acceleration,models[name],e.context,horizon,start_control=0 if horizon==320 else 128)
                    rows.append(dict(run_id=e.case['run_id'],configuration=e.case['configuration'],role='fit_diagnostic',
                        family='nonlinear_v35',scope=scope,mode='kinematic_state_projected',model_id=name,**score))
            records.extend(rows);dump(out/'cases'/(e.case['run_id']+'.json'),rows)
            import json
            print(json.dumps({'case':e.case['run_id'],'completed_cases':len(records)//10,'scores':len(records),'seconds':time.monotonic()-started}),flush=True)
        if len(records)!=240:raise ValueError('v35_score_inventory')
        dump(out/'scores.json',records);gate=fit_screen(records,baseline);summary=[]
        for scope in ('pooled','heldout'):
            for h in (1,20,60,128,320):
                rows=[r for r in records if r['scope']==scope and r['horizon_control_intervals']==h];complete=all(r['complete_aggregate'] for r in rows)
                summary.append({'scope':scope,'horizon':h,'records':len(rows),'complete_records':sum(r['complete_aggregate'] for r in rows),
                    'failed_origins':sum(r['failed_origins'] for r in rows),
                    'mean_endpoint':np.mean([r['endpoint_rmse'] for r in rows],0).tolist() if complete else None,
                    'mean_path':np.mean([r['path_rmse'] for r in rows],0).tolist() if complete else None})
        dump(out/'summary.json',summary);status.update(status='fit_screen_go' if gate['pass'] else 'fit_screen_no_go',
            gate=gate,scores=len(records),complete_scores=sum(r['complete_aggregate'] for r in records));attempt['status']='completed'
    except BaseException as exc:
        status.update(status='incomplete',exception=f'{type(exc).__name__}:{exc}',scores=len(records));attempt['status']='failed';raise
    finally:
        elapsed=time.monotonic()-started;attempt['charged_seconds']=elapsed;budget['analysis_charged_seconds']+=elapsed-reserve
        dump(out/'budget.json',budget);status['seconds']=elapsed;dump(out/'status.json',status)
    print(json.dumps({'status':status['status'],'complete_scores':status['complete_scores'],'gates_passed':sum(g['pass'] for g in gate['gates']),
        'seconds':elapsed}),flush=True)


if __name__=='__main__':run(Path.cwd())

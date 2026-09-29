"""Bounded, source-frozen v25 formal evaluation; validation gates precede test."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from workflows.formal_contract_v25 import proposal,analysis_policy,authorize,digest,validate_stage,EXPERIMENT
from workflows.formal_models_v25 import model_specs,reconstruct,fit_one,load_operator,training_matrices,json_value
from workflows.formal_metrics_v25 import gate_report,bootstrap_report
from workflows.formal_evidence_v25 import recheck_stage,sha_file,cases_for_stage
from workflows.evaluate_projected_edmd_v24 import rollout


def write_new(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as output:
        json.dump(value,output,indent=2,allow_nan=False,default=json_value)


def check_approval(approval):
    if approval.get('decision')!='approved':raise ValueError('formal_d23_not_approved')
    for case in proposal()['entries']:
        authorize(proposal(),analysis_policy(),approval,approval['source_commit'],case['run_id'])


def source_binding():
    from workflows.collect_koopman_v21_identification import _repository_commit
    root=Path(__file__).resolve().parents[1];commit=_repository_commit()
    manifest=json.loads((root/'SOURCE_MANIFEST.json').read_text())
    for name,sha in manifest['files_sha256'].items():
        if sha_file(root/name)!=sha:raise ValueError('formal_evaluator_source_changed')
    return commit,manifest


def remaining_seconds(budget):
    charged=budget.get('charged_seconds',0)
    if not np.isfinite(charged) or charged<0 or charged>=3600:raise ValueError('formal_analysis_time_budget')
    return 3600-charged


def _equal(a,b,reason):
    a=np.asarray(a);b=np.asarray(b)
    if a.shape!=b.shape or not np.isfinite(a).all() or not np.allclose(a,b,rtol=1e-10,atol=1e-12):
        raise ValueError('formal_audit_'+reason)


def audit_score(record,states):
    horizon=record['horizon_control_intervals'];origins=np.arange(0,len(states)-2*horizon,2)
    _equal(record['origin_control_indices'],origins//2,'origins')
    if record['origins']!=len(origins):raise ValueError('formal_audit_origin_count')
    failures=np.asarray(record['first_failure_physics_tick'])
    if failures.shape!=(len(origins),) or np.any((failures!=-1)&((failures<1)|(failures>2*horizon))):
        raise ValueError('formal_audit_failure_indices')
    if record['failed_origins']!=int(np.sum(failures!=-1)):raise ValueError('formal_audit_failure_count')
    if not record['complete_aggregate']:
        if not record['failed_origins'] or any(record[k] is not None for k in
                ('endpoint_rmse','path_rmse','per_origin_endpoint_squared_error','per_origin_path_mean_squared_error','final_predictions')):
            raise ValueError('formal_audit_failed_aggregate')
        return
    if record['failed_origins']:raise ValueError('formal_audit_complete_failure')
    endpoint=np.asarray(record['per_origin_endpoint_squared_error']);path=np.asarray(record['per_origin_path_mean_squared_error'])
    if endpoint.shape!=(len(origins),4) or path.shape!=endpoint.shape or np.any(endpoint<0) or np.any(path<0):
        raise ValueError('formal_audit_squared_error_shape')
    _equal(record['endpoint_rmse'],np.sqrt(endpoint.mean(0)),'endpoint_average')
    _equal(record['path_rmse'],np.sqrt(path.mean(0)),'path_average')
    prediction=np.asarray(record['final_predictions']);reference=states[origins+2*horizon]
    if prediction.shape!=reference.shape:raise ValueError('formal_audit_prediction_shape')
    qa=reference[:,1:5]/np.linalg.norm(reference[:,1:5],axis=1,keepdims=True)
    qb=prediction[:,1:5]/np.linalg.norm(prediction[:,1:5],axis=1,keepdims=True)
    angular=(2*np.arccos(np.clip(np.abs(np.sum(qa*qb,axis=1)),0,1)))**2
    direct=np.column_stack(((reference[:,0]-prediction[:,0])**2,angular,
                            ((reference[:,5:8]-prediction[:,5:8])**2).mean(1),
                            ((reference[:,8:11]-prediction[:,8:11])**2).mean(1)))
    _equal(endpoint,direct,'endpoint_predictions')


def _artifact_path(name,output,evidence):
    from workflows.formal_evidence_v25 import _safe_name
    if not _safe_name(name):raise ValueError('formal_freeze_path')
    if name.startswith('collection/'):
        pieces=name.split('/')
        if len(pieces)!=3 or pieces[-1]!='trace.json':raise ValueError('formal_freeze_path')
        cases={case['run_id']:case for case in proposal()['entries']};case=cases.get(pieces[1])
        if case is None or case['role']=='test':raise ValueError('formal_freeze_data_role')
        stage='preflight' if case['role']=='preflight' else 'fit-validation'
        return evidence/stage/'raw/results'/name
    return output/name


def verify_freeze(output,evidence,approval,evaluator_commit):
    path=output/'pre-test-freeze.json'
    if not path.is_file():raise ValueError('formal_freeze_missing')
    freeze=json.loads(path.read_text());source=approval['source_commit']
    case=next(c for c in proposal()['entries'] if c['role']=='test')
    validate_stage(case,freeze,source,digest(proposal()))
    if freeze.get('evaluator_commit')!=evaluator_commit:raise ValueError('formal_freeze_evaluator')
    for name,sha in freeze['artifact_sha256'].items():
        artifact=_artifact_path(name,output,evidence)
        if not artifact.is_file() or artifact.is_symlink() or sha_file(artifact)!=sha:raise ValueError('formal_freeze_artifact_changed')
    decision=json.loads((output/freeze['validation_summary']).read_text())
    if (decision.get('status')!='validation_gates_passed' or decision.get('test_accessed') is not False
            or decision.get('decision')!='GO' or decision.get('source_commit')!=source
            or decision.get('evaluator_commit')!=evaluator_commit
            or decision.get('role_protocol_sha256')!=digest(proposal())
            or decision.get('analysis_policy_sha256')!=digest(analysis_policy())):raise ValueError('formal_freeze_decision')
    audit=json.loads((output/freeze['audit_report']).read_text())
    if audit.get('status')!='arithmetic_roles_and_source_passed' or audit.get('models')!=68:raise ValueError('formal_freeze_audit')
    for spec in model_specs():
        record=json.loads((output/freeze['frozen_models'][spec['model_id']]).read_text())
        if (record.get('source_commit')!=source or record.get('evaluator_commit')!=evaluator_commit
                or record.get('training_role')!='fit' or record.get('status')!='fit_complete'
                or record.get('model_id')!=spec['model_id'] or record.get('role_protocol_sha256')!=digest(proposal())
                or record.get('analysis_policy_sha256')!=digest(analysis_policy())):raise ValueError('formal_freeze_model_binding')
        load_operator(spec['family'],record['operator'])
    return freeze


def _load_episodes(evidence,stage,approval):
    accepted=recheck_stage(evidence/stage,stage,approval);result=[]
    hashes={c['run_id']:c['trace_sha256'] for c in accepted['cases']}
    for case in cases_for_stage(stage):
        path=evidence/stage/'raw/results/collection'/case['run_id']/'trace.json'
        result.append(reconstruct(json.loads(path.read_text()),case,approval['source_commit'],hashes[case['run_id']]))
    return result


def _score(spec,operator,episodes):
    result=[];dictionary=spec['family'].split('_')[0]
    for episode in episodes:
        if episode.case['configuration'] not in spec['evaluation_configurations']:continue
        active=operator.bind(episode.context,dictionary) if spec['family'].endswith('_fixed') else operator
        modes=['projected','unprojected_lift'] if dictionary=='nonlinear' else ['projected']
        for mode in modes:
            for horizon in analysis_policy()['horizons_control']:
                score=rollout(episode.states,episode.acceleration,active,dictionary,episode.context,mode,horizon)
                score.update(model_id=spec['model_id'],family=spec['family'],scope=spec['scope'],mode=mode,
                             run_id=episode.case['run_id'],configuration=episode.case['configuration'],seed=episode.case['seed'])
                result.append(score)
    return result


def _compact(record):
    return {name:record[name] for name in ('model_id','family','scope','mode','run_id','configuration','seed',
            'horizon_control_intervals','origins','failed_origins','complete_aggregate','endpoint_rmse','path_rmse')}


def _audit_artifacts(output,stage,models,score_index,fit,episodes):
    for record in models:
        if record['status']!='fit_complete':raise ValueError('formal_audit_incomplete_fit')
        spec=next(s for s in model_specs() if s['model_id']==record['model_id'])
        selected=[e for e in fit if e.case['configuration'] in spec['fit_configurations']]
        a,b,u,ordered=training_matrices(spec,selected);op=load_operator(spec['family'],record['operator'])
        if record['fit_episode_hashes']!={e.case['run_id']:e.trace_sha256 for e in ordered}:raise ValueError('formal_audit_training_roles')
        if record['fit_matrix_sha256']!=hashlib.sha256(a.tobytes()+b.tobytes()+u.tobytes()).hexdigest():raise ValueError('formal_audit_fit_matrix')
        _equal(op.mean,a.mean(0),'fit_mean');_equal(op.scale,np.maximum(a.std(0),1e-6),'fit_scale')
        if spec['family'].endswith('_free'):
            _equal(op.input_mean,u.mean(0),'input_mean');_equal(op.input_scale,np.maximum(u.std(0),1e-6),'input_scale')
    states={e.case['run_id']:e.states for e in episodes};compact=[];total=0
    for entry in score_index:
        path=output/entry['path']
        if sha_file(path)!=entry['sha256']:raise ValueError('formal_audit_score_file')
        records=json.loads(path.read_text())
        if len(records)!=entry['records']:raise ValueError('formal_audit_score_inventory')
        for record in records:
            if record['run_id'] not in states:raise ValueError('formal_audit_score_role')
            audit_score(record,states[record['run_id']]);compact.append(_compact(record));total+=1
    return compact,{'status':'arithmetic_roles_and_source_passed','models':len(models),'score_records':total,
                    'role':stage,'scope':'independent saved arithmetic and fit-role checks; not independent researcher review'}


def _worker(request):
    output=Path(request['output']);evidence=Path(request['evidence']);stage=request['stage']
    approval=json.loads(Path(request['approval']).read_text());check_approval(approval)
    evaluator,manifest=source_binding()
    if evaluator!=request['evaluator_commit']:raise ValueError('formal_worker_source')
    if stage=='validation' and (evidence/'test').exists():raise ValueError('formal_test_access_before_freeze')
    if stage=='test':verify_freeze(output,evidence,approval,evaluator)
    recheck_stage(evidence/'preflight','preflight',approval)
    pair=_load_episodes(evidence,'fit-validation',approval);fit=[e for e in pair if e.case['role']=='fit']
    episodes=[e for e in pair if e.case['role']=='validation'] if stage=='validation' else _load_episodes(evidence,'test',approval)
    binding={'source_commit':approval['source_commit'],'evaluator_commit':evaluator,'role_protocol_sha256':digest(proposal()),
             'analysis_policy_sha256':digest(analysis_policy()),'approval_sha256':digest(approval)}
    write_new(output/stage/'analysis-binding.json',dict(binding,role=stage,source_manifest_sha256=digest(manifest),
              primary_scope_interpretation='all local/pooled/heldout primary complete; heldout and pooled accuracy gates',
              episode_hashes={e.case['run_id']:e.trace_sha256 for e in fit+episodes}))
    models=[];score_index=[];fit_failures=[]
    for spec in model_specs():
        if stage=='validation':
            selected=[e for e in fit if e.case['configuration'] in spec['fit_configurations']]
            try:record,operator=fit_one(spec,selected)
            except ValueError as exc:
                record=dict(spec,training_role='fit',status='fit_failed',reason=str(exc));operator=None;fit_failures.append(record)
            record.update(binding);write_new(output/'models'/(spec['model_id']+'.json'),record)
        else:
            record=json.loads((output/'models'/(spec['model_id']+'.json')).read_text());operator=load_operator(spec['family'],record['operator'])
        models.append(record)
        if operator is not None:
            scores=_score(spec,operator,episodes);path=output/stage/'scores'/(spec['model_id']+'.json');write_new(path,scores)
            score_index.append({'path':path.relative_to(output).as_posix(),'sha256':sha_file(path),'records':len(scores)})
        if sum(p.stat().st_size for base in (output,evidence) for p in base.rglob('*') if p.is_file())>=4*1024**3:
            raise ValueError('formal_analysis_disk_budget')
        print(json.dumps({'stage':stage,'model_id':spec['model_id'],'status':record['status']}),flush=True)
    persistence=[]
    for episode in episodes:
        for horizon in analysis_policy()['horizons_control']:
            score=rollout(episode.states,episode.acceleration,None,None,None,'persistence',horizon)
            score.update(model_id='persistence',family='persistence',scope='none',mode='persistence',run_id=episode.case['run_id'],
                         configuration=episode.case['configuration'],seed=episode.case['seed']);persistence.append(score)
    path=output/stage/'scores/persistence.json';write_new(path,persistence)
    score_index.append({'path':path.relative_to(output).as_posix(),'sha256':sha_file(path),'records':len(persistence)})
    write_new(output/stage/'scores-index.json',score_index)
    if fit_failures:
        decision=dict(binding,status='validation_gates_failed',decision='NO_GO',fit_failures=fit_failures,test_accessed=False,model_handoff=False)
        write_new(output/stage/'decision.json',decision)
        write_new(output/'selection.json',dict(binding,selection_status='no_selection',reason='incomplete_fixed_fit_grid',
                  test_accessed=False,model_handoff=False))
        return decision
    compact,audit=_audit_artifacts(output,stage,models,score_index,fit,episodes)
    decision=gate_report(compact,stage);decision.update(binding,test_accessed=stage=='test',
        status=('validation_gates_passed' if decision['decision']=='GO' else 'validation_gates_failed') if stage=='validation' else 'test_evaluation_complete')
    write_new(output/stage/'compact-scores.json',compact);write_new(output/stage/'audit.json',dict(audit,**binding))
    write_new(output/stage/'decision.json',decision)
    if stage=='validation' and decision['decision']=='GO':
        paths=[p for d in (output/'models',output/'validation') for p in d.rglob('*') if p.is_file()]
        artifacts={p.relative_to(output).as_posix():sha_file(p) for p in paths}
        for part in ('preflight','fit-validation'):
            for case in cases_for_stage(part):
                name='collection/'+case['run_id']+'/trace.json';artifacts[name]=sha_file(evidence/part/'raw/results'/name)
        freeze=dict(binding,status='validation_and_models_frozen',configurations=proposal()['configurations'],fit_count=68,
                    test_accessed=False,artifact_sha256=artifacts,frozen_models={r['model_id']:'models/'+r['model_id']+'.json' for r in models},
                    validation_summary='validation/decision.json',audit_report='validation/audit.json')
        write_new(output/'pre-test-freeze.json',freeze);verify_freeze(output,evidence,approval,evaluator)
    elif stage=='validation':
        write_new(output/'selection.json',dict(binding,selection_status='no_selection',reason='validation_gate_failure',test_accessed=False,model_handoff=False))
    if stage=='test':
        write_new(output/'test/uncertainty.json',bootstrap_report(compact,'test'))
        write_new(output/'selection.json',dict(binding,selection_status='prediction_candidate' if decision['decision']=='GO' else 'no_selection',
                  candidate='nonlinear_fixed__pooled' if decision['decision']=='GO' else None,model_handoff=False,
                  reason='independent_closeout_and_interface_handoff_still_required',test_accessed=True))
    print(json.dumps({'stage':stage,'decision':decision['decision'],'score_records':len(compact),'model_handoff':False}),flush=True)
    return decision


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['validation','test'],required=True)
    parser.add_argument('--evidence',type=Path,required=True);parser.add_argument('--approval',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    approval=json.loads(args.approval.read_text());check_approval(approval);evaluator,_=source_binding()
    output=args.output.resolve();evidence=args.evidence.resolve()
    if output.name!=EXPERIMENT or output.parent.name!='results' or output.parent.parent.name!='source':raise ValueError('formal_output_root')
    if (output/args.stage).exists():raise ValueError('formal_analysis_stage_already_attempted')
    if args.stage=='test':verify_freeze(output,evidence,approval,evaluator)
    budget_path=output/'analysis-budget.json'
    budget=json.loads(budget_path.read_text()) if budget_path.exists() else {'charged_seconds':0.,'attempts':[]}
    remaining=remaining_seconds(budget)
    request={'stage':args.stage,'evidence':str(evidence),'approval':str(args.approval.resolve()),'output':str(output),'evaluator_commit':evaluator}
    request_path=output/(args.stage+'-worker-request.json');write_new(request_path,request)
    attempt={'stage':args.stage,'reserved_seconds':remaining,'status':'reserved'};budget['attempts'].append(attempt)
    charged_before=budget['charged_seconds'];budget['charged_seconds']+=remaining
    budget_path.write_text(json.dumps(budget,indent=2))
    command=[sys.executable,'-X','utf8','-B','-c',
             'import json,sys;from pathlib import Path;from workflows.evaluate_formal_v25 import _worker;_worker(json.loads(Path(sys.argv[1]).read_text()))',str(request_path)]
    started=time.monotonic()
    try:
        with (output/(args.stage+'-worker.log')).open('x',encoding='utf8') as log:
            result=subprocess.run(command,cwd=Path(__file__).resolve().parents[1],stdout=log,stderr=subprocess.STDOUT,timeout=remaining,check=False)
        attempt.update(status='exited',exit_code=result.returncode)
        if result.returncode:raise RuntimeError('formal_analysis_worker_failed')
    except subprocess.TimeoutExpired:
        attempt.update(status='timed_out');raise
    finally:
        elapsed=time.monotonic()-started;budget['charged_seconds']=charged_before+elapsed;attempt['charged_seconds']=elapsed
        budget_path.write_text(json.dumps(budget,indent=2))
    print(json.dumps({'stage':args.stage,'native_exit':result.returncode,'charged_seconds':budget['charged_seconds']}))


if __name__=='__main__':main()

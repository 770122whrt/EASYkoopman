"""Train once on four admitted traces; evaluate separate roles without refitting."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from koopman.disturbance_lifted_v86 import fit,prepare
from koopman.lifted_propagation_v84 import seal
from workflows.disturbance_data_v86 import context,frozen_physics,load_episode,verify_manifest,PHYSICAL_SHA256
from workflows.protocol_v86 import cases,protocol,RIDGE
from workflows.fit_learned_velocity_v81 import errors


def write_new(path,value):
    with Path(path).open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def train(data,manifest,output):
    if Path(output).exists():raise FileExistsError(output)
    sha=verify_manifest(manifest)
    episodes=[load_episode(Path(data)/q['run_id'],sha) for q in cases() if q['role']=='train']
    if [e['case'] for e in episodes]!=[q for q in cases() if q['role']=='train']:
        raise ValueError('v86_training_inventory')
    if len({e['trace_sha256'] for e in episodes})!=4:raise ValueError('v86_duplicate_training')
    prior,physical=frozen_physics()
    record=fit(np.concatenate([e['states'][:-1] for e in episodes]),
        np.concatenate([e['states'][1:] for e in episodes]),
        np.concatenate([e['inputs'] for e in episodes]),context(),physical,ridge=RIDGE)
    record.update(physical_prior=prior,physical_file_sha256=PHYSICAL_SHA256,protocol=protocol(),
        collection_manifest_sha256=sha,fit_episode_hashes={e['case']['run_id']:e['trace_sha256'] for e in episodes})
    record=seal(record);write_new(output,record)
    return record


def load_record(path):
    record=json.loads(Path(path).read_text(encoding='utf8'))
    if record.get('content_sha256')!=seal(record)['content_sha256']:raise ValueError('v86_model_hash')
    prior,physical=frozen_physics()
    if (record['physical_prior']!=prior or record['physical_file_sha256']!=PHYSICAL_SHA256
            or record['protocol']!=protocol() or record['lifted']['ridge']!=RIDGE
            or record['lifted']['training_rows']!=2560
            or len(set(record['fit_episode_hashes'].values()))!=4
            or set(record['fit_episode_hashes'])!={q['run_id'] for q in cases() if q['role']=='train'}):
        raise ValueError('v86_frozen_model_contract')
    for kind in ('koopman','hybrid'):prepare(record,context(),physical,kind=kind)
    return record,physical


def evaluate(data,manifest,model,role,output):
    if Path(output).exists():raise FileExistsError(output)
    if role not in ('validation','test'):raise ValueError('v86_evaluation_role')
    sha=verify_manifest(manifest);record,physical=load_record(model)
    if record['collection_manifest_sha256']!=sha:raise ValueError('v86_collection_changed')
    episodes=[load_episode(Path(data)/q['run_id'],sha) for q in cases() if q['role']==role]
    if [e['case'] for e in episodes]!=[q for q in cases() if q['role']==role]:raise ValueError('v86_evaluation_inventory')
    if (len({e['trace_sha256'] for e in episodes})!=len(episodes)
            or set(record['fit_episode_hashes'].values()) & {e['trace_sha256'] for e in episodes}):
        raise ValueError('v86_training_evaluation_overlap')
    rows=[];c=context()
    builders={'physics':physical,**{k:prepare(record,c,physical,kind=k) for k in ('koopman','hybrid')}}
    for e in episodes:
        for name,p in builders.items():
            for start in protocol()['prediction_origins']:
                x=e['states'][start:start+1].copy();trajectory=[];failure=None
                try:
                    step=p.start_forecast(x,c) if hasattr(p,'start_forecast') else p
                    for u in e['inputs'][start:start+80]:
                        x=step(x,u[None],c)
                        if (not np.isfinite(x).all() or not 3.5<=x[0,0]<=7.5
                                or np.linalg.norm(x[0,5:8])>1.5 or np.linalg.norm(x[0,8:])>3):
                            raise ValueError('prediction_envelope')
                        trajectory.append(x[0].copy())
                except (ValueError,FloatingPointError) as exc:failure=str(exc)
                metric=errors(trajectory,e['states'][start+1:start+81]) if len(trajectory)==80 else None
                rows.append(dict(model=name,episode=e['case']['run_id'],origin=start,complete=len(trajectory)==80,
                    failure=failure,metrics=metric,source_trace_sha256=e['trace_sha256']))
    gates={}
    for name in builders:
        r=[r for r in rows if r['model']==name]
        passed=all(q['complete'] and q['metrics']['z_rmse_m']<=.002 and q['metrics']['attitude_rmse_rad']<=.004 for q in r)
        gates[name]=dict(prediction_passed=passed,windows=len(r),failures=sum(not q['complete'] for q in r))
    result=dict(schema='v86-prediction-evaluation',role=role,model_sha256=hashlib.sha256(Path(model).read_bytes()).hexdigest(),
        rows=rows,gates=gates,model_fits=0,closed_loop_admitted=False,physical_recalibrated=False,
        inputs='causal actuator replay from past executed and future prescribed commands; no future state or rotor truth',
        generalization='same base and disturbance, independent trajectories only')
    write_new(output,result);return result


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('train','validation','test'))
    p.add_argument('--data',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--model',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.action=='train':train(a.data,a.manifest,a.output)
    else:
        if a.model is None:p.error('--model is required for evaluation')
        evaluate(a.data,a.manifest,a.model,a.action,a.output)


if __name__=='__main__':main()

"""One frozen fit on diverse train episodes; no validation/test refitting."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from koopman.disturbance_lifted_v86 import fit,prepare
from koopman.lifted_propagation_v84 import seal,coordinates
from workflows.disturbance_data_v87 import context,frozen_physics,load_episode,verify_manifest,PHYSICAL_SHA256
from workflows.protocol_v87 import cases,protocol,RIDGE
from workflows.fit_disturbance_v86 import write_new
from workflows.fit_learned_velocity_v81 import errors


def training_arrays(episodes):
    if [e['case'] for e in episodes]!=[q for q in cases() if q['role']=='train']:
        raise ValueError('v87_training_inventory')
    if len({e['trace_sha256'] for e in episodes})!=16:raise ValueError('v87_duplicate_training')
    parts=[(e,0 if i==0 else 256) for i,e in enumerate(episodes)]
    return (np.concatenate([e['states'][start:-1] for e,start in parts]),
            np.concatenate([e['states'][start+1:] for e,start in parts]),
            np.concatenate([e['inputs'][start:] for e,start in parts]))


def train(data,manifest,output):
    if Path(output).exists():raise FileExistsError(output)
    sha=verify_manifest(manifest)
    episodes=[load_episode(Path(data)/q['run_id'],sha) for q in cases() if q['role']=='train']
    x,y,u=training_arrays(episodes);prior,physical=frozen_physics()
    record=fit(x,y,u,context(),physical,ridge=RIDGE)
    record.update(physical_prior=prior,physical_file_sha256=PHYSICAL_SHA256,protocol=protocol(),
        collection_manifest_sha256=sha,fit_episode_hashes={e['case']['run_id']:e['trace_sha256'] for e in episodes},
        training_range=dict(state_min=x.min(0).tolist(),state_max=x.max(0).tolist(),
            max_linear_speed=float(np.max(np.linalg.norm(x[:,5:8],axis=1))),
            max_angular_speed=float(np.max(np.linalg.norm(x[:,8:],axis=1)))))
    record=seal(record);write_new(output,record);return record


def load_record(path):
    record=json.loads(Path(path).read_text(encoding='utf8'))
    if record.get('content_sha256')!=seal(record)['content_sha256']:raise ValueError('v87_model_hash')
    prior,physical=frozen_physics()
    if (record['physical_prior']!=prior or record['physical_file_sha256']!=PHYSICAL_SHA256
            or record['protocol']!=protocol() or record['lifted']['ridge']!=RIDGE
            or record['lifted']['training_rows']!=16640
            or len(set(record['fit_episode_hashes'].values()))!=16
            or set(record['fit_episode_hashes'])!={q['run_id'] for q in cases() if q['role']=='train'}):
        raise ValueError('v87_frozen_model_contract')
    for kind in ('koopman','hybrid'):prepare(record,context(),physical,kind=kind)
    return record,physical


def evaluate(data,manifest,model,role,output):
    if Path(output).exists():raise FileExistsError(output)
    if role not in ('validation','test'):raise ValueError('v87_evaluation_role')
    sha=verify_manifest(manifest);record,physical=load_record(model)
    if record['collection_manifest_sha256']!=sha:raise ValueError('v87_collection_changed')
    episodes=[load_episode(Path(data)/q['run_id'],sha) for q in cases() if q['role']==role]
    if [e['case'] for e in episodes]!=[q for q in cases() if q['role']==role]:raise ValueError('v87_evaluation_inventory')
    hashes={e['trace_sha256'] for e in episodes}
    if len(hashes)!=4 or set(record['fit_episode_hashes'].values()) & hashes:raise ValueError('v87_training_evaluation_overlap')
    rows=[];ranges=[];c=context()
    builders={'physics':physical,**{k:prepare(record,c,physical,kind=k) for k in ('koopman','hybrid')}}
    for e in episodes:
        states=e['states'];lo=np.asarray(record['training_range']['state_min']);hi=np.asarray(record['training_range']['state_max'])
        ranges.append(dict(episode=e['case']['run_id'],
            max_linear_speed=float(np.max(np.linalg.norm(states[:,5:8],axis=1))),
            max_angular_speed=float(np.max(np.linalg.norm(states[:,8:],axis=1))),
            velocity_outside_train_box_fraction=float(np.mean(np.any((states[:,5:]<lo[5:])|(states[:,5:]>hi[5:]),axis=1)))))
        for name,p in builders.items():
            for start in protocol()['prediction_origins']:
                x=states[start:start+1].copy();trajectory=[];failure=None
                try:
                    step=p.start_forecast(x,c) if hasattr(p,'start_forecast') else p
                    for u in e['inputs'][start:start+80]:
                        x=step(x,u[None],c);coordinates(x)
                        if (not np.isfinite(x).all() or not 3.5<=x[0,0]<=7.5
                                or np.linalg.norm(x[0,5:8])>1.5 or np.linalg.norm(x[0,8:])>3):
                            raise ValueError('prediction_envelope')
                        trajectory.append(x[0].copy())
                except (ValueError,FloatingPointError) as exc:failure=str(exc)
                metric=errors(trajectory,states[start+1:start+81]) if len(trajectory)==80 else None
                rows.append(dict(model=name,episode=e['case']['run_id'],origin=start,complete=len(trajectory)==80,
                    failure=failure,metrics=metric,source_trace_sha256=e['trace_sha256']))
    gates={}
    for name in builders:
        r=[r for r in rows if r['model']==name]
        good=[q['complete'] and q['metrics']['z_rmse_m']<=.002 and q['metrics']['attitude_rmse_rad']<=.004 for q in r]
        gates[name]=dict(prediction_passed=all(good),windows=len(r),passed_windows=sum(good),failures=sum(not q['complete'] for q in r))
    result=dict(schema='v87-prediction-evaluation',role=role,model_sha256=hashlib.sha256(Path(model).read_bytes()).hexdigest(),
        source_manifest_sha256=sha,source_trace_hashes=sorted(hashes),rows=rows,gates=gates,ranges=ranges,
        model_fits=0,closed_loop_admitted=False,physical_recalibrated=False,
        inputs='causal actuator replay from executed and future prescribed commands; no future state or rotor truth',
        generalization='same base and disturbance, independent seeds and waveform parameters; seen input families')
    write_new(output,result);return result


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('train','validation','test'))
    p.add_argument('--data',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--model',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.action=='train':train(a.data,a.manifest,a.output)
    else:
        if a.model is None:p.error('--model required')
        evaluate(a.data,a.manifest,a.model,a.action,a.output)

if __name__=='__main__':main()

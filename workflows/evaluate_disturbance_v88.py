"""No-fit, no-hidden-input forecast evaluation of frozen v87 models on fresh matrix."""
import argparse
from pathlib import Path
import numpy as np
from koopman.disturbance_lifted_v86 import prepare
from koopman.lifted_propagation_v84 import coordinates
from workflows.disturbance_data_v88 import context,frozen_model,load_episode,verify_manifest,MODEL_SHA256
from workflows.protocol_v88 import cases,protocol,LEVELS
from workflows.fit_disturbance_v86 import write_new
from workflows.fit_learned_velocity_v81 import errors


def evaluate(data,manifest,model,role,output):
    if Path(output).exists():raise FileExistsError(output)
    if role not in ('validation','test'):raise ValueError('v88_evaluation_role')
    sha=verify_manifest(manifest);record,physical=frozen_model(model)
    if record['collection_manifest_sha256']==sha:raise ValueError('v88_old_collection_manifest')
    episodes=[load_episode(Path(data)/q['run_id'],sha) for q in cases() if q['role']==role]
    if [e['case'] for e in episodes]!=[q for q in cases() if q['role']==role]:raise ValueError('v88_evaluation_inventory')
    hashes={e['trace_sha256'] for e in episodes}
    if len(hashes)!=12 or set(record['fit_episode_hashes'].values()) & hashes:raise ValueError('v88_training_evaluation_overlap')
    rows=[];ranges=[];c=context()
    builders={'physics':physical,**{k:prepare(record,c,physical,kind=k) for k in ('koopman','hybrid')}}
    for e in episodes:
        states=e['states'];lo=np.asarray(record['training_range']['state_min']);hi=np.asarray(record['training_range']['state_max'])
        ranges.append(dict(episode=e['case']['run_id'],fraction=e['case']['hidden_drag_fraction'],
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
                rows.append(dict(model=name,episode=e['case']['run_id'],fraction=e['case']['hidden_drag_fraction'],origin=start,complete=len(trajectory)==80,
                    failure=failure,metrics=metric,source_trace_sha256=e['trace_sha256']))
    gates={}
    for fraction in LEVELS:
        level={}
        for name in builders:
            selected=[r for r in rows if r['model']==name and r['fraction']==fraction]
            good=[q['complete'] and q['metrics']['z_rmse_m']<=protocol()['max_depth_rmse_m']
                  and q['metrics']['attitude_rmse_rad']<=protocol()['max_attitude_rmse_rad'] for q in selected]
            level[name]=dict(prediction_passed=all(good),windows=len(selected),passed_windows=sum(good),
                failures=sum(not q['complete'] for q in selected))
        gates[str(fraction)]=level
    result=dict(schema='v88-prediction-evaluation',role=role,model_sha256=MODEL_SHA256,training_manifest_sha256=record['collection_manifest_sha256'],
        source_manifest_sha256=sha,source_trace_hashes=sorted(hashes),rows=rows,gates=gates,ranges=ranges,
        model_fits=0,closed_loop_admitted=False,physical_recalibrated=False,
        inputs='causal actuator replay from executed and future prescribed commands; no future state or rotor truth',
        generalization='same base, unseen disturbance strengths 0/0.1/0.3 versus training 0.2; independent role seeds; seen input families')
    write_new(output,result);return result



def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True);p.add_argument('--role',choices=('validation','test'),required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    evaluate(a.data,a.manifest,a.model,a.role,a.output)


if __name__=='__main__':main()

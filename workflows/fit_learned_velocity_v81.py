"""Bounded fit-only retrospective pooled/LOCO evaluation, no simulator or control.

Two predeclared ridge values are retained, not selected on the held-out folds.
Future recorded actuator-derived acceleration is exogenous replay input here;
no future state is fed back into a multi-step forecast.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from koopman.learned_velocity_v81 import (fit_readout, velocity_target, seal_record,
    prepare_learned, dq_subspace_distance)
from koopman.sparse_world_edmd_v30 import lift, feature_names, core_matrix
from koopman.prepared_projected_v40 import prepare_projected
from workflows.identify_sparse_world_v30 import load_fit_cache, fit_model, SparseModel

RIDGES=(.001,.1)
ORIGINS=(256,384,512)
HORIZONS=(1,80,128)


def fit_candidates(episodes,configurations):
    prior,physical=fit_model(episodes,'nonlinear',configurations)
    a=[];b=[];weights=[]
    for e in episodes:
        a.append(lift(e.states[:-1],e.context,'nonlinear'))
        b.append(velocity_target(e.states[:-1],e.states[1:],e.acceleration,
                                 e.context,physical.angular_damping))
        weights.append(np.r_[np.full(256,1/3),np.ones(384)])
    a=np.concatenate(a);b=np.concatenate(b);weights=np.concatenate(weights)
    records=[]
    for ridge in RIDGES:
        matrix,stats=fit_readout(a,b,weights,physical.matrix[:,10:16],ridge)
        record=dict(schema='projected-controlled-edmd-velocity-v81',family='nonlinear',
            feature_names=feature_names('nonlinear'),velocity_matrix=matrix.tolist(),
            physical_prior=prior,ridge=ridge,feature_mean=stats.pop('feature_mean'),
            feature_scale=stats.pop('feature_scale'),audit=dict(training_role='fit',
                fit_episodes=len(episodes),startup_weight=1/3,analytic_pose=True,
                full_latent_closure_claim=False,training_physics_rows=len(a),
                fit_feature_target_sha256=hashlib.sha256(a.tobytes()+b.tobytes()+weights.tobytes()).hexdigest(),
                **stats))
        records.append(seal_record(record))
    return prior,physical,records


def errors(prediction,truth):
    p=np.asarray(prediction);t=np.asarray(truth)
    pq=p[:,1:5]/np.linalg.norm(p[:,1:5],axis=1,keepdims=True)
    tq=t[:,1:5]/np.linalg.norm(t[:,1:5],axis=1,keepdims=True)
    angle=2*np.arccos(np.clip(np.abs(np.sum(pq*tq,axis=1)),0,1))
    return dict(z_rmse_m=float(np.sqrt(np.mean((p[:,0]-t[:,0])**2))),
        attitude_rmse_rad=float(np.sqrt(np.mean(angle**2))),
        velocity_6_rmse=np.sqrt(np.mean((p[:,5:]-t[:,5:])**2,axis=0)).tolist(),
        linear_velocity_rmse_m_s=float(np.sqrt(np.mean((p[:,5:8]-t[:,5:8])**2))),
        angular_velocity_rmse_rad_s=float(np.sqrt(np.mean((p[:,8:]-t[:,8:])**2))))


def evaluate(episodes,physical,records):
    rows=[]
    nominal=SparseModel('nonlinear',core_matrix('nonlinear',np.zeros(6),np.ones(6),
        physical.angular_damping),np.zeros(6),np.ones(6),physical.angular_damping,{})
    for e in episodes:
        predictors={'nominal_physics':prepare_projected(nominal,e.context),
                    'same_data_identified_physics':prepare_projected(physical,e.context),
                    'state_persistence':lambda x,u,c:x.copy()}
        predictors.update({f'learned_ridge_{r["ridge"]:g}':prepare_learned(r,e.context) for r in records})
        for name,predictor in predictors.items():
            # Each origin is an independent rollout. Batch only the arithmetic.
            active=np.ones(len(ORIGINS),dtype=bool);x=e.states[list(ORIGINS)].copy()
            trajectories=[[] for _ in ORIGINS];reasons=[None]*len(ORIGINS)
            for tick in range(max(HORIZONS)):
                for j,start in enumerate(ORIGINS):
                    if not active[j]:continue
                    try:
                        y=predictor(x[j:j+1],e.acceleration[start+tick:start+tick+1],e.context)[0]
                        if (not np.isfinite(y).all() or not 3.5<=y[0]<=7.5
                                or np.linalg.norm(y[5:8])>1.5 or np.linalg.norm(y[8:])>3):
                            raise ValueError('forecast_state_envelope')
                        trajectories[j].append(y.copy());x[j]=y
                    except (ValueError,FloatingPointError,OverflowError) as exc:
                        active[j]=False;reasons[j]=str(exc)
            for j,start in enumerate(ORIGINS):
                for horizon in HORIZONS:
                    complete=len(trajectories[j])>=horizon
                    rows.append(dict(configuration=e.case['configuration'],episode=e.case['run_id'],
                        source_trace_sha256=e.trace_sha256,origin=start,horizon_physics=horizon,
                        model=name,complete=complete,completed_physics=min(horizon,len(trajectories[j])),
                        failure=None if complete else reasons[j],
                        metrics=errors(trajectories[j][:horizon],e.states[start+1:start+horizon+1]) if complete else None))
    return rows


def aggregate(rows):
    result=[]
    for model in sorted({r['model'] for r in rows}):
        for h in HORIZONS:
            group=[r for r in rows if r['model']==model and r['horizon_physics']==h]
            complete=[r for r in group if r['complete']]
            metrics={}
            if complete:
                for key in complete[0]['metrics']:
                    # Equal-weight RMS across equal-length windows.
                    values=np.asarray([r['metrics'][key] for r in complete])
                    value=np.sqrt(np.mean(values*values,axis=0))
                    metrics[key]=value.tolist()
            result.append(dict(model=model,horizon_physics=h,total=len(group),
                complete=len(complete),failed=len(group)-len(complete),
                complete_window_metrics=metrics,metrics_exclude_failures_explicitly=True))
    return result


def run(root,output,*,maximum_seconds=900,maximum_bytes=128*1024**2):
    started=time.monotonic();output=Path(output)
    if output.exists():raise FileExistsError('learned_v81_output_exists')
    output.mkdir(parents=True)
    def write(name,data):
        payload=(json.dumps(data,indent=2,allow_nan=False)+'\n').encode()
        if sum(p.stat().st_size for p in output.glob('**/*') if p.is_file())+len(payload)>maximum_bytes:
            raise RuntimeError('learned_v81_byte_budget')
        (output/name).write_bytes(payload)
    episodes=load_fit_cache(root);configs=list(dict.fromkeys(e.case['configuration'] for e in episodes))
    protocol=dict(schema='phase9-learned-velocity-v81-protocol',ridge_candidates=list(RIDGES),
        configurations=configs,training_only_role='fit',evaluation='retrospective_LOCO_on_historical_fit_episodes',
        pooled_is_resubstitution=True,blind_test=False,closed_loop=False,
        origins=list(ORIGINS),horizons_physics=list(HORIZONS),startup_training_weight=1/3,
        same_data_physical_center_refit_per_fold=True,heldout_scaling_or_support_used=False,
        forecast_input='recorded_causal_actuator_derived_acceleration; no future state feedback',
        candidate_selection='none; retain both fixed candidates and every failure',
        maximum_seconds=maximum_seconds,maximum_bytes=maximum_bytes,
        failure_envelope={'z_m':[3.5,7.5],'linear_speed_m_s':1.5,'angular_speed_rad_s':3})
    write('protocol.json',protocol);summaries=[];all_loco=[]
    for heldout in [None]+configs:
        if time.monotonic()-started>maximum_seconds:raise RuntimeError('learned_v81_time_budget')
        key='pooled' if heldout is None else 'loco_'+heldout
        training=episodes if heldout is None else [e for e in episodes if e.case['configuration']!=heldout]
        evaluation=episodes if heldout is None else [e for e in episodes if e.case['configuration']==heldout]
        trained_configs=[c for c in configs if c!=heldout]
        begin=time.monotonic();prior,physical,records=fit_candidates(training,trained_configs)
        write(key+'__physical.json',prior)
        for r in records:write(key+f'__learned_{r["ridge"]:g}.json',r)
        rows=evaluate(evaluation,physical,records)
        report=dict(fold=key,heldout_configuration=heldout,training_configurations=trained_configs,
            training_episodes=len(training),evaluation_episodes=len(evaluation),seconds=time.monotonic()-begin,
            model_dq_subspace_distance={str(r['ridge']):dq_subspace_distance(r) for r in records},
            model_content_sha256={str(r['ridge']):r['content_sha256'] for r in records},
            summary=aggregate(rows),rows=rows)
        write(key+'__evaluation.json',report);summaries.append({k:v for k,v in report.items() if k!='rows'})
        if heldout is not None:all_loco+=rows
        print(json.dumps({'fold':key,'seconds':report['seconds'],'dq_distance':report['model_dq_subspace_distance']}),flush=True)
    final=dict(schema='phase9-learned-velocity-v81-offline-report',protocol=protocol,
        status='completed_retrospective_prediction_only',elapsed_seconds=time.monotonic()-started,
        model_fits=18,physical_prior_fits=9,folds=summaries,loco_summary=aggregate(all_loco),
        closed_loop_benefit_established=False,blind_generalization_established=False)
    write('report.json',final)
    return final


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path('.'))
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    run(args.root,args.output)

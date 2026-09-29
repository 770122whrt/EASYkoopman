"""Four-family retrospective comparison; frozen baselines, new Rc and LK fits.

Only body dynamics are evaluated here, with recorded actuator-derived inputs.
No future true state enters a free rollout; no controller or physics is run.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from koopman import lifted_propagation_v84 as lk
from koopman.compact_residual_v84 import fit_compact,make_record,prepare_compact
from koopman.learned_velocity_v81 import prepare_learned,velocity_target,validate_record
from koopman.sparse_world_edmd_v30 import lift
from koopman.prepared_projected_v40 import prepare_projected
from workflows.identify_sparse_world_v30 import load_fit_cache,from_record,fit_model
from workflows.fit_learned_velocity_v81 import ORIGINS,HORIZONS,RIDGES,errors,aggregate

GATE={'horizon_physics':80,'max_window_z_rmse_m':.002,'max_window_attitude_rmse_rad':.004}


def forecast(predictor,initial,inputs,context,*,relift=False):
    x=np.asarray(initial,dtype=float).reshape(1,11).copy();trajectory=[];failure=None;drift=0.
    latent=lk.lift(x) if isinstance(predictor,lk.PreparedLifted) else None
    for u in np.asarray(inputs):
        try:
            if latent is not None:
                latent=predictor.step(latent,u[None],context)
                y=lk.decode(latent[:,:10])
                rebuilt=lk.lift(y);drift=max(drift,float(np.max(abs(rebuilt-latent))))
                if relift:latent=rebuilt
            else:y=predictor(x,u[None],context)
            if (not np.isfinite(y).all() or not 3.5<=y[0,0]<=7.5
                    or np.linalg.norm(y[0,5:8])>1.5 or np.linalg.norm(y[0,8:])>3):
                raise ValueError('forecast_state_envelope')
            # Same local task-region check for all model families, not silent projection.
            lk.coordinates(y)
            trajectory.append(y[0].copy());x=y
        except (ValueError,FloatingPointError,OverflowError) as exc:
            failure=str(exc);break
    return dict(trajectory=trajectory,failure=failure,latent_consistency_max=drift)


def prediction_gate(rows):
    selected=[r for r in rows if r['horizon_physics']==80]
    complete=[r for r in selected if r['complete']]
    mz=max((r['metrics']['z_rmse_m'] for r in complete),default=None)
    ma=max((r['metrics']['attitude_rmse_rad'] for r in complete),default=None)
    ok=bool(selected) and len(complete)==len(selected) and mz<=.002 and ma<=.004
    return dict(eligible_body_prediction=ok,windows=len(selected),failures=len(selected)-len(complete),
                max_z_rmse_m=mz,max_attitude_rmse_rad=ma,closed_loop_admitted=False)


def evaluate(episodes,builders):
    rows=[]
    for e in episodes:
        for name,builder in builders.items():
            p=builder(e.context)
            for start in ORIGINS:
                result=forecast(p,e.states[start],e.acceleration[start:start+max(HORIZONS)],e.context,
                                relift=name.endswith('_relift_diagnostic'))
                trajectory=result['trajectory']
                for h in HORIZONS:
                    complete=len(trajectory)>=h
                    rows.append(dict(configuration=e.case['configuration'],episode=e.case['run_id'],
                        source_trace_sha256=e.trace_sha256,origin=start,horizon_physics=h,model=name,
                        complete=complete,completed_physics=min(h,len(trajectory)),
                        failure=None if complete else result['failure'],
                        latent_consistency_max_over_attempted_horizon=result['latent_consistency_max'],
                        metrics=errors(trajectory[:h],e.states[start+1:start+h+1]) if complete else None))
    return rows


def train_new(episodes,prior,*,check_deadline=lambda:None):
    physical=from_record(prior);features=[];target=[];x=[];y=[];u=[];contexts=[];weights=[]
    for e in episodes:
        x.append(e.states[:-1]);y.append(e.states[1:]);u.append(e.acceleration)
        contexts.extend([e.context]*640)
        features.append(lift(e.states[:-1],e.context,'nonlinear'))
        target.append(velocity_target(e.states[:-1],e.states[1:],e.acceleration,e.context,physical.angular_damping))
        weights.append(np.r_[np.full(256,1/3),np.ones(384)])
    f=np.concatenate(features);target=np.concatenate(target);w=np.concatenate(weights)
    x=np.concatenate(x);y=np.concatenate(y);u=np.concatenate(u)
    source={e.case['run_id']:e.trace_sha256 for e in episodes}
    assert source==prior['fit_episode_hashes']
    checksum=hashlib.sha256(f.tobytes()+target.tobytes()+w.tobytes()).hexdigest()
    records={}
    for ridge in RIDGES:
        check_deadline()
        k,stats=fit_compact(f,target,w,physical.matrix[:,10:16],ridge)
        records[f'Rc_{ridge:g}']=make_record(prior,k,stats,ridge=ridge,
                    extra_audit={'fit_feature_target_sha256':checksum})
        r=lk.fit_lifted(x,y,u,contexts,w,ridge=ridge)
        r['fit_episode_hashes']=source;r['fit_source']=episodes[0].source_commit
        r['training_configuration_names']=prior['configurations']
        records[f'LK_{ridge:g}']=lk.seal(r)
    return records


def new_builders(records):
    return {name:(lambda c,r=r:prepare_compact(r,c)) if name.startswith('Rc_')
            else (lambda c,r=r:lk.prepare_lifted(r,c)) for name,r in records.items()}


def run(root,output,*,maximum_seconds=1200,include_source_dev=True):
    root=Path(root);output=Path(output);started=time.monotonic()
    if output.exists():raise FileExistsError('v84_output_exists')
    output.mkdir(parents=True)
    def check():
        if time.monotonic()-started>maximum_seconds:raise RuntimeError('v84_time_limit')
    def write(name,data):
        check();payload=(json.dumps(data,indent=2,allow_nan=False)+'\n').encode()
        if sum(p.stat().st_size for p in output.rglob('*') if p.is_file())+len(payload)>256*1024**2:
            raise RuntimeError('v84_output_limit')
        (output/name).write_bytes(payload)
    protocol=dict(schema='four-family-offline-comparison-v84',families=['P','R53','Rc','LK'],
        ridges=list(RIDGES),origins=list(ORIGINS),horizons=list(HORIZONS),new_gate=GATE,
        gate_rationale='2mm depth / 4mrad attitude finite-horizon RMS budget; frozen before model fitting; not historical threshold',
        maximum_seconds=maximum_seconds,maximum_bytes=256*1024**2,physics_runs=0,solver_runs=0,
        local_chart_angle_limit=lk.CHART_ANGLE_LIMIT,chart_applied_to_all_families=True,
        inputs='recorded_actuator_derived_body_acceleration; conditional body prediction only',
        blind_test=False,evaluation='historical fit pooled resubstitution and retrospective LOCO',
        model_selection='none; retain both fixed ridges and failures',
        source_dev='hold alphabetically last source configuration out of each outer source fold' if include_source_dev else None,
        source_dev_not_used_to_select_candidates=True,heldout_data_used_in_scaling=False,
        LK_features=lk.feature_names(),LK_inputs='a_and_a_squared',LK_height_translation_equivariant=True,
        propagation_diagnostic='same fitted LK A/B, per-step re-lifting toggled only in marked rows',
        control_admission='requires independent causal-command rollout, NumPy/CasADi and solver validation after this gate',
        implementation_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__),root/'koopman/lifted_propagation_v84.py',root/'koopman/compact_residual_v84.py']})
    write('protocol.json',protocol)
    episodes=load_fit_cache(root);configs=list(dict.fromkeys(e.case['configuration'] for e in episodes))
    frozen=root/'docs/evidence/phase9/learned-velocity-v81-20260926/normalized-quaternion'
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    summaries=[];all_loco=[];csv_rows=[]
    for heldout in [None]+configs:
        check();begin=time.monotonic();key='pooled' if heldout is None else 'loco_'+heldout
        train=[e for e in episodes if e.case['configuration']!=heldout]
        selected=episodes if heldout is None else [e for e in episodes if e.case['configuration']==heldout]
        prior=read(frozen/(key+'__physical.json'));physical=from_record(prior)
        assert {e.case['run_id']:e.trace_sha256 for e in train}==prior['fit_episode_hashes']
        builders={'P':lambda c,p=physical:prepare_projected(p,c),'persistence':lambda c:lambda x,u,c:x.copy()}
        for ridge in RIDGES:
            r=read(frozen/(key+f'__learned_{ridge:g}.json'));validate_record(r)
            assert r['physical_prior']==prior
            builders[f'R53_{ridge:g}']=lambda c,r=r:prepare_learned(r,c)
        records=train_new(train,prior,check_deadline=check);builders.update(new_builders(records))
        for name,r in records.items():
            write(key+'__'+name+'.json',r)
            if name.startswith('LK_'):
                builders[name+'_relift_diagnostic']=lambda c,r=r:lk.prepare_lifted(r,c)
        rows=evaluate(selected,builders);check()
        dev=None
        if include_source_dev:
            source_configs=sorted({e.case['configuration'] for e in train});dev_cfg=source_configs[-1]
            dev_train=[e for e in train if e.case['configuration']!=dev_cfg]
            dev_eval=[e for e in train if e.case['configuration']==dev_cfg]
            dev_prior,_=fit_model(dev_train,'nonlinear',source_configs[:-1])
            dev_records=train_new(dev_train,dev_prior,check_deadline=check)
            for name,r in dev_records.items():write(key+'__source_dev__'+name+'.json',r)
            dev_rows=evaluate(dev_eval,new_builders(dev_records))
            dev=dict(heldout_source_configuration=dev_cfg,training_configurations=source_configs[:-1],
                target_outer_configuration_never_used=heldout,summary=aggregate(dev_rows),rows=dev_rows)
        grouped={name:[r for r in rows if r['model']==name] for name in builders}
        summary=aggregate(rows)
        report=dict(fold=key,evaluation_configurations=[e.case['configuration'] for e in selected[::3]],
            training_configurations=prior['configurations'],new_model_fits=len(records)+(4 if dev else 0),
            seconds=time.monotonic()-begin,summary=summary,rows=rows,source_development=dev,
            gates={name:prediction_gate(group) for name,group in grouped.items()})
        write(key+'__evaluation.json',report)
        summaries.append({k:v for k,v in report.items() if k not in ('rows','source_development')})
        if heldout is not None:all_loco.extend(rows)
        for item in summary:
            row={k:v for k,v in item.items() if k!='complete_window_metrics'}
            row.update(fold=key,**{k:v for k,v in item['complete_window_metrics'].items() if not isinstance(v,list)})
            csv_rows.append(row)
        print(json.dumps(dict(fold=key,seconds=round(report['seconds'],2),gates=report['gates'])),flush=True)
    final=dict(status='completed_retrospective_body_prediction',elapsed_seconds=time.monotonic()-started,
        new_model_fits=sum(f['new_model_fits'] for f in summaries),protocol=protocol,folds=summaries,
        loco_summary=aggregate(all_loco),control_benefit_established=False,blind_generalization_established=False)
    write('report.json',final)
    fields=list(dict.fromkeys(k for r in csv_rows for k in r))
    with (output/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(csv_rows)
    return final


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path('.').resolve())
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--without-source-dev',action='store_true')
    args=parser.parse_args();run(args.root,args.output,include_source_dev=not args.without_source_dev)

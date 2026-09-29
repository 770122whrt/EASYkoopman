"""Bounded source-only calibration of the separately authorized bilinear family.

All outer data are historical development data, not blind testing. Outer target
rows never enter the selection function; selection is persisted before refit and
outer evaluation. Original v84 candidates and negative results are preserved.
"""
import json
import hashlib
from pathlib import Path
import time
import numpy as np
from koopman import bilinear_lifted_v85 as lk
from workflows.calibrate_lifted_v84 import GRID, source_split, choose_ridge
from workflows.compare_models_v84 import evaluate, prediction_gate, GATE
from workflows.fit_learned_velocity_v81 import ORIGINS,HORIZONS,aggregate
from workflows.identify_sparse_world_v30 import load_fit_cache

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidence/phase9/bilinear-calibration-v85-20260927'


def fit(episodes,ridge):
    x=np.concatenate([e.states[:-1] for e in episodes]);y=np.concatenate([e.states[1:] for e in episodes])
    u=np.concatenate([e.acceleration for e in episodes]);contexts=[e.context for e in episodes for _ in range(640)]
    w=np.tile(np.r_[np.full(256,1/3),np.ones(384)],len(episodes))
    r=lk.fit_bilinear(x,y,u,contexts,w,ridge=ridge)
    r.update(fit_episode_hashes={e.case['run_id']:e.trace_sha256 for e in episodes},
        fit_source=episodes[0].source_commit,training_configuration_names=sorted({e.case['configuration'] for e in episodes}),
        calibration_scope='source_only_ridge_same_dictionary_with_shared_state_input_interactions')
    return lk.seal(r)


def run():
    start=time.monotonic();maximum_seconds=600;maximum_bytes=128*1024**2
    OUT.mkdir(parents=True,exist_ok=False)
    def check():
        if time.monotonic()-start>maximum_seconds:raise TimeoutError('calibration_600_second_limit')
    def write(name,value):
        payload=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
        if sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())+len(payload)>maximum_bytes:raise RuntimeError('calibration_128_mib_limit')
        with (OUT/name).open('xb') as f:f.write(payload)
    def safe_choice(r):
        # An all-failed candidate retains an explicit undefined score in JSON.
        if isinstance(r,dict):return {k:safe_choice(v) for k,v in r.items()}
        if isinstance(r,list):return [safe_choice(v) for v in r]
        if isinstance(r,float) and not np.isfinite(r):return None
        return r
    sources=[Path(__file__),ROOT/'koopman/bilinear_lifted_v85.py',ROOT/'koopman/lifted_propagation_v84.py',ROOT/'workflows/calibrate_lifted_v84.py',ROOT/'workflows/compare_models_v84.py']
    protocol={'schema':'source-only-bilinear-ridge-calibration-v85','ridge_grid':list(GRID),
        'maximum_seconds':maximum_seconds,'maximum_bytes':maximum_bytes,'gate':GATE,
        'selection':'lexicographic: number of failed 80-step windows; maximum over complete windows of z_RMSE/.002 + attitude_RMSE/.004; larger ridge on exact ties',
        'source_development':'alphabetically last outer source configuration, excluded from inner fitting',
        'outer_target_used_for_selection':False,'blind_test':False,
        'dictionary_changed':False,'input_features_changed':False,'propagation_changed':True,'interaction_features':'shared a_i*z_j; no height or constant',
        'user_authorized':'2026-09-27 bilinear extension as distinct comparison',
        'fixed_AB_comparator':'docs/evidence/phase9/lifted-calibration-v84-20260927/report.json',
        'origins':list(ORIGINS),'horizons':list(HORIZONS), 'solver_runs':0,'physics_runs':0,
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    write('protocol.json',protocol)  # Freeze rule and budget before any fit.
    episodes=load_fit_cache(ROOT);configs=list(dict.fromkeys(e.case['configuration'] for e in episodes))
    folds=[];loco_rows=[]
    for heldout in [None]+configs:
        check();begin=time.monotonic();key='pooled' if heldout is None else 'loco_'+heldout
        source,inner,dev=source_split(configs,heldout)
        inner_episodes=[e for e in episodes if e.case['configuration'] in inner]
        development=[e for e in episodes if e.case['configuration']==dev]
        dev_rows={}
        for ridge in GRID:
            check();r=fit(inner_episodes,ridge);check()
            prefix=key+f'__dev_{ridge:g}'
            write(prefix+'__model.json',r)
            rows=evaluate(development,{f'BLK_{ridge:g}':lambda c,r=r:lk.prepare_bilinear(r,c)})
            check();write(prefix+'__evaluation.json',{'rows':rows,'summary':aggregate(rows),'gate':prediction_gate(rows)})
            dev_rows[ridge]=rows
        choice=choose_ridge(dev_rows)
        selection={'fold':key,'source_configurations':source,'inner_training_configurations':inner,
            'development_configuration':dev,'outer_target_configuration':heldout,
            'inner_fit_episode_hashes':{e.case['run_id']:e.trace_sha256 for e in inner_episodes},
            'development_episode_hashes':{e.case['run_id']:e.trace_sha256 for e in development},
            'choice':safe_choice(choice),'selected_before_outer_evaluation':True}
        write(key+'__selection.json',selection)
        check();outer_source=[e for e in episodes if e.case['configuration'] in source]
        selected=fit(outer_source,choice['ridge']);check();write(key+'__selected_model.json',selected)
        target=episodes if heldout is None else [e for e in episodes if e.case['configuration']==heldout]
        builders={'BLK_calibrated':lambda c,r=selected:lk.prepare_bilinear(r,c)}
        if heldout is None:builders['BLK_calibrated_relift_diagnostic']=lambda c,r=selected:lk.prepare_bilinear(r,c)
        rows=evaluate(target,builders);check()
        gates={name:prediction_gate([r for r in rows if r['model']==name]) for name in builders}
        report={'fold':key,'ridge':choice['ridge'],'source_selection':selection,'gates':gates,
            'summary':aggregate(rows),'rows':rows,'seconds':time.monotonic()-begin,
            'outer_episode_hashes':{e.case['run_id']:e.trace_sha256 for e in target}}
        write(key+'__evaluation.json',report)
        folds.append({k:v for k,v in report.items() if k not in ('rows','source_selection','outer_episode_hashes')})
        if heldout is not None:loco_rows.extend(rows)
        print(json.dumps({'fold':key,'ridge':choice['ridge'],'seconds':report['seconds'],'gates':gates}),flush=True)
    result={'status':'completed_source_only_retrospective_calibration','protocol':protocol,
        'elapsed_seconds':time.monotonic()-start,'model_fits':len(folds)*(len(GRID)+1),
        'folds':folds,'loco_summary':aggregate(loco_rows),'closed_loop_admitted':False,
        'bounds':'Historical-data development only; no blind generalization or control benefit established.'}
    write('report.json',result)


if __name__=='__main__':run()

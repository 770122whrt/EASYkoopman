"""Recheck downloaded raw data and frozen predictions without fitting."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[3]))
from workflows.disturbance_data_v87 import verify_manifest,load_episode
from workflows.fit_disturbance_v87 import evaluate,write_new
from workflows.protocol_v87 import cases

root=HERE/'server'
manifest=HERE/'release-r1/manifest.json'
sha=verify_manifest(manifest)
rows=[]
for q in cases():
    try:
        e=load_episode(root/'data'/q['run_id'],sha)
        remote=json.loads((root/'data'/q['run_id']/'acceptance.json').read_text())
        if remote['trace_sha256']!=e['trace_sha256']:raise ValueError('trace_hash_changed')
        rows.append(dict(case=q['run_id'],accepted=True,trace_sha256=e['trace_sha256']))
    except Exception as exc:
        rows.append(dict(case=q['run_id'],accepted=False,error=type(exc).__name__+':'+str(exc)))
parity={}
for role in ('validation','test'):
    try:
        local=evaluate(root/'data',manifest,root/'model.json',role,HERE/'local'/(role+'-replay.json'))
        remote=json.loads((root/(role+'.json')).read_text())
        if local['gates']!=remote['gates']:raise ValueError('prediction_gate_changed')
        if len(local['rows'])!=len(remote['rows']):raise ValueError('prediction_rows_changed')
        worst=0.
        for a,b in zip(local['rows'],remote['rows']):
            for key in ('model','episode','origin','complete','failure','source_trace_sha256'):
                if a[key]!=b[key]:raise ValueError('prediction_identity_changed:'+key)
            if a['metrics'] is None or b['metrics'] is None:
                if a['metrics']!=b['metrics']:raise ValueError('prediction_failure_changed')
                continue
            for key in a['metrics']:
                worst=max(worst,float(np.max(np.abs(np.asarray(a['metrics'][key])-np.asarray(b['metrics'][key])))))
        parity[role]=dict(accepted=worst<=1e-7,max_metric_abs_error=worst)
    except Exception as exc:
        parity[role]=dict(accepted=False,error=type(exc).__name__+':'+str(exc))
result=dict(source_manifest_sha256=sha,model_sha256=hashlib.sha256((root/'model.json').read_bytes()).hexdigest(),
    data=rows,prediction_parity=parity,model_fits=0,closed_loop_runs=0,
    accepted=all(r['accepted'] for r in rows) and all(r['accepted'] for r in parity.values()))
write_new(HERE/'local/pullback-validation.json',result)
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['accepted'] else 1)

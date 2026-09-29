"""One independent raw replay per role; frozen forecast parity, no fitting."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[3]))
from workflows.disturbance_data_v88 import verify_manifest,MODEL_PATH
from workflows.evaluate_disturbance_v88 import evaluate,write_new
from workflows.protocol_v88 import cases
root=HERE/'server';manifest=HERE/'release-r1/manifest.json';sha=verify_manifest(manifest)
rows=[];parity={}
for role in ('validation','test'):
    try:
        # evaluate calls strict load_episode on every complete raw trajectory;
        # avoid redundantly re-running that same expensive raw validator twice.
        local=evaluate(root/'data',manifest,HERE.parents[3]/MODEL_PATH,role,HERE/'local'/(role+'-replay.json'))
        remote=json.loads((root/(role+'.json')).read_text())
        if local['gates']!=remote['gates']:raise ValueError('prediction_gate_changed')
        if len(local['rows'])!=len(remote['rows']):raise ValueError('prediction_rows_changed')
        worst=0.
        for a,b in zip(local['rows'],remote['rows']):
            for key in ('model','episode','fraction','origin','complete','failure','source_trace_sha256'):
                if a[key]!=b[key]:raise ValueError('prediction_identity_changed:'+key)
            if a['metrics'] is None or b['metrics'] is None:
                if a['metrics']!=b['metrics']:raise ValueError('prediction_failure_changed')
                continue
            for key in a['metrics']:
                worst=max(worst,float(np.max(np.abs(np.asarray(a['metrics'][key])-np.asarray(b['metrics'][key])))))
        for q in cases():
            if q['role']!=role:continue
            hashes={x['source_trace_sha256'] for x in local['rows'] if x['episode']==q['run_id']}
            acceptance=json.loads((root/'data'/q['run_id']/'acceptance.json').read_text())
            digest=hashlib.sha256((root/'data'/q['run_id']/'trace.json.gz').read_bytes()).hexdigest()
            if hashes!={digest} or acceptance['trace_sha256']!=digest:raise ValueError('trace_hash_changed')
            rows.append(dict(case=q['run_id'],accepted=True,trace_sha256=digest))
        parity[role]=dict(accepted=worst<=1e-7,max_metric_abs_error=worst)
    except Exception as exc:parity[role]=dict(accepted=False,error=type(exc).__name__+':'+str(exc))
result=dict(source_manifest_sha256=sha,model_sha256=hashlib.sha256((HERE.parents[3]/MODEL_PATH).read_bytes()).hexdigest(),
    data=rows,prediction_parity=parity,model_fits=0,closed_loop_runs=0,
    accepted=len(rows)==24 and all(r['accepted'] for r in rows) and all(r['accepted'] for r in parity.values()))
write_new(HERE/'local/pullback-validation.json',result)
print(json.dumps(result,indent=2));raise SystemExit(0 if result['accepted'] else 1)

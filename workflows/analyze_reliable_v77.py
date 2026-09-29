"""Summarize all attempts, keeping failures outside full-task benefit metrics."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np


def summarize(root, previous):
    rows=[]
    for path in sorted(root.glob('*/summary.json')):
        data=json.loads(path.read_text());case=data['case'];cfg=case['configuration']
        old=previous/(cfg+'-pitch-feedback-'+('r1' if cfg=='base' else 'r3'))
        reference=json.loads((old/'summary.json').read_text())
        trace=path.with_name('trace.json.gz')
        raw=json.loads(gzip.decompress(trace.read_bytes()))
        audits=raw.get('solve_audit',[])
        accepted=path.with_name('acceptance.json').exists()
        row=dict(name=path.parent.name,**case,accepted=accepted,status=data['status'],
            reason=data.get('exception'),physics_steps=data['physical_steps'],
            trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest(),
            source_manifest_sha256=data['source_manifest_sha256'],
            baseline_path=str(old),baseline_score=reference['metrics']['normalized_tracking_score'],
            statuses=dict(Counter(a['status'] for a in audits)),
            solver_statuses=dict(Counter(a.get('solver',{}).get('return_status','none') for a in audits)),
            warm_starts=sum(a.get('warm_start_used',False) for a in audits),
            physical_initializations=sum(a.get('initialization_kind')=='physical_target_ramp' for a in audits),
            feedback_unavailable=sum(a.get('baseline_reference')=='previous_hold_feedback_unavailable' for a in audits))
        observed=[a for a in audits if a.get('worker_pid') is not None]
        row['single_thread_environment_observed']=bool(observed) and all(
            a.get('worker_threads')=={'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
            for a in observed)
        residuals=[a['constraint_violation'] for a in audits if a.get('constraint_violation') is not None]
        if residuals:row['max_internal_constraint_violation']=max(residuals)
        for field in ('elapsed_seconds','worker_cpu_seconds'):
            values=[a[field] for a in audits if a.get(field) is not None]
            if values:row[field]=dict(median=float(np.median(values)),maximum=max(values),total=sum(values))
        if accepted:
            result=json.loads(path.with_name('acceptance.json').read_text())
            assert result['trace_sha256']==row['trace_sha256']
            assert result['physics_steps']==240
            row['metrics']=data['metrics']
            row['improvement_percent']=100*(1-data['metrics']['normalized_tracking_score']/row['baseline_score'])
            row['submetric_improvement_percent']={k:100*(1-data['metrics'][k]/reference['metrics'][k])
                for k in ('depth_rmse_m','attitude_rmse_rad')}
        rows.append(row)
    exits=[json.loads(p.read_text()) for p in root.glob('*.exit.json')]
    return dict(schema='v77-all-attempts',cases=rows,
        starts=sum('workflows.collect_reliable_v77' in x['command'] for x in exits),
        native_wall_seconds=sum(x['seconds'] for x in exits),
        complete=sum(x['accepted'] for x in rows),
        limitations=['two-second single-seed development task','frozen v76 feedback references outside base repeat',
            'predeclared profile ablations are development evidence, not independent tests','projected model equivalent to identified physics'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--previous',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=summarize(a.root,a.previous)
    a.output.write_text(json.dumps(r,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in r.items() if k!='cases'}))
    for row in r['cases']:
        print(row['name'],row['accepted'],row.get('improvement_percent'),row['reason'])

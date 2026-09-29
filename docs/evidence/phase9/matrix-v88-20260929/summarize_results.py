"""All fixed cells, including failures; reporting only, no fit or selection."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[3]))
from workflows.protocol_v88 import cases,protocol,LEVELS
from workflows.disturbance_data_v88 import MODEL_SHA256
r=HERE/'server';manifest_sha=hashlib.sha256((HERE/'release-r1/manifest.json').read_bytes()).hexdigest()
support_sha=hashlib.sha256((HERE/'support.json').read_bytes()).hexdigest()
result=dict(model_sha256=MODEL_SHA256,source_manifest_sha256=manifest_sha,support_sha256=support_sha,
            model_fits=0,closed_loop_runs=0,levels={})
reports={role:json.loads((r/(role+'.json')).read_text()) for role in ('validation','test')}
solver=json.loads((r/'solver.json').read_text())
for report in [*reports.values(),solver]:
    assert report['source_manifest_sha256']==manifest_sha and report['model_sha256']==MODEL_SHA256
    assert report['model_fits']==0
assert solver['support_sha256']==support_sha
assert len(solver['rows'])==36
closed=all(v==dict(process_stopped=True,io_threads_stopped=True) for v in solver['worker_close'].values())
assert set(solver['worker_close'])=={'physics','koopman','hybrid'}
assert not set(reports['validation']['source_trace_hashes'])&set(reports['test']['source_trace_hashes'])
for fraction in LEVELS:
    level={}
    for role,report in reports.items():
        arms={}
        for arm in ('physics','koopman','hybrid'):
            rows=[x for x in report['rows'] if x['fraction']==fraction and x['model']==arm]
            expected={(q['run_id'],o) for q in cases() if q['role']==role and q['hidden_drag_fraction']==fraction for o in protocol()['prediction_origins']}
            assert len(rows)==16 and {(x['episode'],x['origin']) for x in rows}==expected
            passed=[x['complete'] and x['metrics']['z_rmse_m']<=.002 and x['metrics']['attitude_rmse_rad']<=.004 for x in rows]
            metrics={key:dict(pooled_rmse=float(np.sqrt(np.mean([x['metrics'][key]**2 for x in rows]))) if all(x['complete'] for x in rows) else None,
                worst_rmse=max(x['metrics'][key] for x in rows) if all(x['complete'] for x in rows) else None)
                for key in ('z_rmse_m','attitude_rmse_rad','linear_velocity_rmse_m_s','angular_velocity_rmse_rad_s')}
            arms[arm]=dict(windows=len(rows),passed_windows=sum(passed),passed=all(passed),metrics=metrics)
            assert report['gates'][str(fraction)][arm]['passed_windows']==sum(passed)
        level[role]=arms
    level['solver']={}
    for arm in ('physics','koopman','hybrid'):
        rows=[x for x in solver['rows'] if x['fraction']==fraction and x['model']==arm]
        expected={(q['run_id'],o) for q in cases() if q['role']=='validation' and q['hidden_drag_fraction']==fraction and q['excitation'] in ('prbs','chirp') for o in protocol()['solver_origins']}
        assert len(rows)==4 and {(x['episode'],x['origin']) for x in rows}==expected
        good=[x.get('candidate_check',{}).get('feasible') is True and x.get('parent_check',{}).get('feasible') is True and x['passed'] and x.get('numpy_symbolic_max_error',float('inf'))<=1e-5 for x in rows]
        level['solver'][arm]=dict(cases=4,passed=sum(good),all_passed=all(good) and closed,
            old_support_accepted=sum(x['old_support']['rejection'] is None for x in rows),
            new_support_accepted=sum(x['new_support']['rejection'] is None for x in rows),
            failures=[dict(episode=x['episode'],origin=x['origin'],failure=x.get('failure'),
                worker_reason=x.get('solve',{}).get('worker_reason'),
                candidate_check=x.get('candidate_check'),parent_check=x.get('parent_check')) for x,g in zip(rows,good) if not g])
    level['closed_loop_eligible']=all(level[role][arm]['passed'] for role in ('validation','test') for arm in ('physics','koopman','hybrid')) and all(x['all_passed'] for x in level['solver'].values())
    result['levels'][str(fraction)]=level
result['solver_distinct_initial_states']=len({np.asarray(x['initial_state']).tobytes() for x in solver['rows']})
result['all_workers_closed']=closed
with (HERE/'summary.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2,allow_nan=False)
print(json.dumps(result,indent=2))

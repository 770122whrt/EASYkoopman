"""Descriptive aggregation of every fixed window; no model selection or refit."""
import json
from pathlib import Path
import numpy as np

root=Path(__file__).resolve().parent
result={}
for role in ('validation','test'):
    report=json.loads((root/'server'/(role+'.json')).read_text())
    arms={}
    for kind in ('physics','koopman','hybrid'):
        rows=[r for r in report['rows'] if r['model']==kind]
        complete=all(r['complete'] for r in rows)
        metrics={}
        for key in ('z_rmse_m','attitude_rmse_rad','linear_velocity_rmse_m_s','angular_velocity_rmse_rad_s'):
            metrics[key]=dict(pooled_rmse=float(np.sqrt(np.mean([r['metrics'][key]**2 for r in rows]))) if complete else None,
                worst_rmse=max(r['metrics'][key] for r in rows) if complete else None)
        arms[kind]=dict(**report['gates'][kind],metrics=metrics,failed_windows=[dict(
            episode=r['episode'],origin=r['origin'],failure=r['failure'],metrics=r['metrics'])
            for r in rows if not r['complete'] or r['metrics']['z_rmse_m']>.002 or r['metrics']['attitude_rmse_rad']>.004])
    result[role]=dict(arms=arms,ranges=report['ranges'])
solver=json.loads((root/'server/solver.json').read_text())
result['solver']=dict(distinct_origins=solver['distinct_origins'],arms={kind:dict(passed=arm['passed'],
    rows=[dict(episode=r['episode'],origin=r['origin'],passed=r['passed'],failure=r.get('failure'),
        numpy_symbolic_max_error=r.get('numpy_symbolic_max_error'),
        solver=r.get('solve',{}).get('solver'),candidate_check=r.get('candidate_check'),
        parent_check=r.get('parent_check'),selected_reference=r.get('selected_reference')) for r in arm['rows']])
    for kind,arm in solver['arms'].items()})
result['training_range']=json.loads((root/'server/model.json').read_text())['training_range']
with (root/'summary.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2,allow_nan=False)
print(json.dumps(result,indent=2,allow_nan=False))

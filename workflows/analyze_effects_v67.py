"""Offline physical/causal replay and descriptive metrics from real traces."""
import argparse,json,gzip,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--release-root',type=Path,required=True);p.add_argument('--case',required=True);args=p.parse_args()
sys.path.insert(0,str(args.release_root))
import numpy as np
from workflows.runtime_assets_v56 import load_assets,AssetLocation
from workflows.collect_runtime_v59 import HANDOFF_SHA
import koopman, workflows
for package in (koopman, workflows):
    package.__path__ = [str(Path(__file__).resolve().parents[1]/package.__name__), *list(package.__path__)]
from workflows.validate_effects_v67 import validate_execution
from koopman.control_objective_v44 import tracking_terms,control_mask
addon=Path(__file__).resolve().parents[1]
case=next(x for x in json.loads((addon/'protocol.json').read_text())['cases'] if x['case_id']==args.case)
folder=addon/'results'/case['case_id']
with gzip.open(folder/'output/diagnostic.json.gz','rt') as f:data=json.load(f)
assert data['case']==case and data['status']=='diagnostic_returned' and not data.get('exception')
assert not data['cleanup_errors'] and data['cleanup_completed']['environment'] and data['cleanup_completed']['simulation_app']
if case['controller']=='mpc':assert data['worker_closed']=={'process_stopped':True,'io_threads_stopped':True}
a=load_assets(AssetLocation(str(args.release_root),'.','assets/v38/inputs',HANDOFF_SHA),model_key=case['model_key'])
verified=validate_execution(data,case,a.domains[case['configuration']],a.context(case['configuration']))
from workflows.validate_tracking_v67 import validate_tracking_audit
inexact_audit=validate_tracking_audit(data,a.domains[case['configuration']],a.context(case['configuration']))
rows=data['substeps'];x=np.array([r['state_after_physics_11'][0] for r in rows]);terms=tracking_terms(x,case['reference'],control_mask(case['configuration']))
u=np.array([r['decision']['packet']['command'] for r in data['intervals']])
w=np.array([r['command']['telemetry']['applied_wrench_6'][0] for r in rows])
sources=[r['decision']['packet']['source'] for r in data['intervals']]
score=terms['depth']/.02**2+terms['attitude']/.04**2
result=dict(status='physical_and_causal_replay_passed',case=case,validation=verified,
 inexact_feedback_validation=inexact_audit,metrics=dict(normalized_tracking_score=float(np.mean(score)),depth_rmse_m=float(np.sqrt(np.mean(terms['depth']))),
 attitude_rmse_rad=float(np.sqrt(np.mean(terms['attitude']))),depth_iae_m_s=float(np.sum(np.sqrt(terms['depth']))/120),
 attitude_iae_rad_s=float(np.sum(np.sqrt(terms['attitude']))/120),
 command_variation=float(np.linalg.norm(np.diff(u,axis=0),axis=1).sum()),
 applied_force_squared_N2_s=float(np.sum(w[:,:3]**2)/120),applied_torque_squared_Nm2_s=float(np.sum(w[:,3:]**2)/120),
 mpc_command_controls=sources.count('mpc'),fallback_controls=sources.count('fallback'),committed_prefix_controls=sources.count('committed_prefix'),
 mpc_activations=data['runtime_final']['stats']['mpc_activations']),timing=data['cycle_summary'],
 runtime_stats=data['runtime_final']['stats'],outside_cycle_worker_wait_s=data['outside_cycle_worker_wait_s'],physical_steps=len(rows),runtime_qualified=False,unique_koopman_advantage_proven=False)
with (folder/'analysis.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
print(json.dumps(result))

"""Repeat a stopped runtime solve outside Isaac with unchanged solver settings."""
import argparse,gzip,hashlib,json,time
from pathlib import Path
import numpy as np
from workflows.runtime_assets_v56 import AssetLocation,load_assets,read
from workflows.identify_sparse_world_v30 import from_record
from koopman.prepared_projected_v40 import prepare_projected
from koopman.physical_control_v76 import PhysicalPredictor
from koopman.command_state_v39 import CausalCommandState
from koopman.continuous_mpc_v76 import ContinuousMPC
from koopman.control_objective_v44 import state_features,control_mask
from workflows.continuous_replay_v76 import plain


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--assets',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--configuration',help='Restrict additional diagnosis to one configuration')
    p.add_argument('--controller');p.add_argument('--shift-previous',action='store_true')
    a=p.parse_args();a.output.mkdir(exist_ok=False)
    assets=load_assets(AssetLocation(a.assets,'.','assets/v38/inputs',
        '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    frozen=from_record(read(assets.model_path));rows=[]
    for path in sorted(a.root.glob('*-r3/trace.json.gz')):
        raw=path.read_bytes();d=json.loads(gzip.decompress(raw))
        if d['status']!='failed' or not d.get('solve_audit'):continue
        if a.configuration and d['case']['configuration']!=a.configuration:continue
        if a.controller and d['case']['controller']!=a.controller:continue
        original=d['solve_audit'][-1]
        if original['reason'] not in ('solver_timeout','no_exact_feasible_solution_found'):continue
        cfg=d['case']['configuration'];kind=d['case']['controller'];c=assets.context(cfg)
        live=CausalCommandState(cfg,c,episode_id='stopped',zero_rotor_reset_verified=True)
        for i,r in enumerate(d['substeps']):
            live.record_issued(r['command']['telemetry']['virtual_control_4'][0],physics_index=i,episode_id='stopped')
        count=len(d['substeps']);assert count==original['physics_index']
        origin=live.snapshot(configuration=cfg,context=c,origin_control=count//2,episode_id='stopped')
        x=np.asarray(d['substeps'][-1]['state_after_physics_11'][0])
        previous=d['substeps'][-1]['command']['telemetry']['virtual_control_4'][0]
        base=np.tile(d['feedback_audit'][-1]['result']['command'],(10,1))
        predictor=prepare_projected(frozen,c) if kind=='projected_koopman' else PhysicalPredictor(frozen,c)
        solver=ContinuousMPC(assets.domains[cfg],predictor,horizon=10,solve_seconds=30.)
        baseline_forecast=origin.forecast(x,np.repeat(base,2,axis=0),predictor)
        features=state_features(baseline_forecast['predictions'],control_mask(cfg));domain=assets.domains[cfg]
        bad=np.argwhere((features<domain.state_lower-1e-12)|(features>domain.state_upper+1e-12))
        feature_names=['z','up_body_x','up_body_y','up_body_z','vx','vy','vz','wx','wy','wz','angle_from_identity']
        violations=[dict(physics_offset=int(i),feature=feature_names[j],value=float(features[i,j]),
                        lower=float(domain.state_lower[j]),upper=float(domain.state_upper[j])) for i,j in bad]
        if a.shift_previous:
            last=np.asarray(d['solve_audit'][-2]['commands'])
            base=np.vstack([last[1:],last[-1]])
        cpu=time.process_time()
        result=solver.solve(origin=origin,initial_state=x,baseline=base,previous=previous,reference=d['case']['reference'])
        used=time.process_time()-cpu
        if not a.shift_previous and original['baseline_cost'] is not None:
            np.testing.assert_allclose(result['baseline_cost'],original['baseline_cost'],atol=1e-12,rtol=1e-9)
        row=dict(case=path.parent.name,source_trace_sha256=hashlib.sha256(raw).hexdigest(),
            original_solver=original['solver'],original_elapsed_seconds=original['elapsed_seconds'],
            isolated_cpu_seconds=used,new_physics_steps=0,model_fits=0,
            initial_guess='previous_plan_shifted' if a.shift_previous else 'current_feedback_held',
            original_held_feedback_violations=violations,**result)
        (a.output/(path.parent.name+'.json')).write_text(json.dumps(plain(row),indent=2,allow_nan=False))
        compact={k:v for k,v in row.items() if k not in ('commands','predictions')};rows.append(compact)
        print(json.dumps(plain(compact)),flush=True)
    (a.output/'summary.json').write_text(json.dumps(plain(rows),indent=2,allow_nan=False))


if __name__=='__main__':main()

"""Six isolated NLP checks at fresh validation origins, before any closed loop."""
import argparse
import json
from pathlib import Path
import numpy as np
from workflows.disturbance_data_v86 import load_episode,verify_manifest
from workflows.protocol_v86 import cases,case_spec
from workflows.fit_disturbance_v86 import write_new


def run(data,manifest,model,model_sha,assets_path,output):
    import torch
    torch.set_num_threads(1)
    from workflows.runtime_assets_v56 import AssetLocation,load_assets
    from koopman.command_state_v39 import CausalCommandState
    from koopman.preview_solver_v86 import load_model,verify_support,make_predictor,create_solver,KINDS
    from koopman.continuous_prediction_v76 import SymbolicPlant
    from koopman.diagnostics_v23 import json_safe
    assets=load_assets(AssetLocation(assets_path,'.','assets/v38/inputs',
        '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    loaded=load_model(model,model_sha);verify_support(loaded,assets)
    sha=verify_manifest(manifest);c=assets.context('base');d=assets.domains['base'];arms={}
    episodes=[load_episode(Path(data)/q['run_id'],sha) for q in cases() if q['role']=='validation']
    if loaded.record['collection_manifest_sha256']!=sha:raise ValueError('v86_solver_collection')
    for kind in KINDS:
        rows=[];solver=None
        try:
            solver=create_solver(d,c,kind,learned_model=model,learned_sha256=model_sha)
            predictor=make_predictor(kind,loaded,c);plant=SymbolicPlant(predictor,'base')
            for e in episodes:
                item=dict(episode=e['case']['run_id'],passed=False);rows.append(item)
                try:
                    live=CausalCommandState('base',c,episode_id='v86-validation',zero_rotor_reset_verified=True)
                    start=256
                    for i,u in enumerate(e['commands'][:start]):live.record_issued(u,physics_index=i,episode_id='v86-validation')
                    origin=live.snapshot(configuration='base',context=c,origin_control=start//2,episode_id='v86-validation')
                    x=e['states'][start];old=e['commands'][start-1];plan=e['commands'][start:start+80:4]
                    exact=origin.forecast(x,np.repeat(plan,2,axis=0),predictor)
                    symbolic=plant.forecast(origin,x,plan)
                    if not exact['complete']:raise ValueError('v86_numpy_forecast_incomplete')
                    delta=float(np.max(abs(exact['predictions']-symbolic['predictions'])))
                    item['numpy_symbolic_max_error']=delta
                    if delta>1e-5:raise ValueError('v86_symbolic_parity')
                    answer=solver.solve(origin=origin,initial_state=x,baseline=np.tile(old,(20,1)),previous=old,
                                        reference=np.asarray(case_spec('base',kind,True,'pitch_pos')['reference']))
                    item['solve']=answer
                    if answer.get('commands') is None:raise ValueError('v86_no_plan')
                    checked=solver.checker.check(origin,x,answer['commands'],old,
                        np.asarray(case_spec('base',kind,True,'pitch_pos')['reference']))
                    item['parent_check']={k:v for k,v in checked.items() if k!='predictions'}
                    item['passed']=bool(checked['feasible'] and answer.get('candidate_commands') is not None
                                        and live.physics_index==start)
                except (ValueError,RuntimeError,FloatingPointError) as exc:item['failure']=str(exc)
        finally:
            closed=solver.close() if solver is not None else None
        arms[kind]=dict(passed=len(rows)==2 and all(r['passed'] for r in rows)
            and closed=={'process_stopped':True,'io_threads_stopped':True},rows=rows,worker_close=closed)
    report=dict(schema='v86-offline-solver-validation',model_sha256=model_sha,arms=arms,
        physics_runs=0,model_fits=0,control_benefit_established=False,real_time_qualified=False)
    write_new(output,json_safe(report));return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('data','manifest','model','model-sha','assets','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();run(a.data,a.manifest,a.model,a.model_sha,a.assets,a.output)

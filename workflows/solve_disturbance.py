"""Paired 3-level/3-model offline solver checks under one frozen training envelope."""
import argparse
import hashlib
from pathlib import Path
import numpy as np
from workflows.disturbance_data import write_new,execution_provenance
from workflows.disturbance_protocol import get_protocol

SPEC=get_protocol("v88")
cases,protocol=SPEC.cases,SPEC.protocol


def assess_answer(checker,origin,state,old,reference,answer):
    def check(commands):
        if commands is None:return dict(feasible=False,reason='unavailable')
        return {k:v for k,v in checker.check(origin,state,commands,old,reference).items() if k!='predictions'}
    parent=check(answer.get('commands'));candidate=check(answer.get('candidate_commands'))
    return dict(parent_check=parent,candidate_check=candidate,passed=bool(parent['feasible'] and candidate['feasible']))


def run(data,manifest,model,assets_path,support,support_sha,output,*,source_archive=None):
    import torch
    torch.set_num_threads(1)
    from workflows.runtime_assets import AssetLocation,load_assets
    from workflows.disturbance_data import load_episode,verify_manifest
    from workflows.control_task import reference as task_reference
    from koopman.training_support import load_domain,MODEL_SHA
    from koopman.command_state import CausalCommandState
    from koopman.control_solver import load_model,verify_support,make_predictor,create_solver,KINDS
    from koopman.symbolic_prediction import SymbolicPlant
    from koopman.control_objective import state_features,control_mask
    from koopman.diagnostics import json_safe
    if Path(output).exists():raise FileExistsError(output)
    assets=load_assets(AssetLocation(assets_path,'.','assets/v38/inputs',
        '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    loaded=load_model(model,MODEL_SHA);verify_support(loaded,assets)
    sha=verify_manifest(manifest,source_archive=source_archive);c=assets.context('base');old_domain=assets.domains['base']
    domain=load_domain(support,support_sha,old_domain,model)
    episodes=[load_episode(Path(data)/q['run_id'],sha) for q in cases()
              if q['role']=='validation' and q['excitation'] in ('prbs','chirp')]
    requests=[(e,start) for e in episodes for start in protocol()['solver_origins']]
    if len(requests)!=12:raise ValueError('v88_solver_inventory')
    rows=[];closes={}
    labels=['depth','up_x','up_y','up_z','vx','vy','vz','wx','wy','wz','angle']
    def screen(d,x):
        v=state_features(x[None],control_mask('base'))[0]
        bad=np.flatnonzero((v<d.state_lower-1e-12)|(v>d.state_upper+1e-12))
        return dict(rejection=d.check_states(x[None]),violations=[dict(feature=labels[i],value=v[i],
                    lower=d.state_lower[i],upper=d.state_upper[i]) for i in bad])
    for kind in KINDS:
        solver=None
        try:
            solver=create_solver(domain,c,kind,learned_model=model,learned_sha256=MODEL_SHA)
            predictor=make_predictor(kind,loaded,c);plant=SymbolicPlant(predictor,'base')
            for e,start in requests:
                x=e['states'][start]
                item=dict(model=kind,episode=e['case']['run_id'],fraction=e['case']['hidden_drag_fraction'],
                    origin=start,initial_state=x,source_trace_sha256=e['trace_sha256'],passed=False,
                    old_support=screen(old_domain,x),new_support=screen(domain,x));rows.append(item)
                try:
                    live=CausalCommandState('base',c,episode_id='v88-validation',zero_rotor_reset_verified=True)
                    for i,u in enumerate(e['commands'][:start]):live.record_issued(u,physics_index=i,episode_id='v88-validation')
                    origin=live.snapshot(configuration='base',context=c,origin_control=start//2,episode_id='v88-validation')
                    old=e['commands'][start-1];plan=e['commands'][start:start+80:4]
                    exact=origin.forecast(x,np.repeat(plan,2,axis=0),predictor)
                    symbolic=plant.forecast(origin,x,plan)
                    if not exact['complete']:raise ValueError('v88_numpy_forecast_incomplete')
                    delta=float(np.max(abs(exact['predictions']-symbolic['predictions'])))
                    item['numpy_symbolic_max_error']=delta
                    if delta>1e-5:raise ValueError('v88_symbolic_parity')
                    reference=np.asarray(task_reference('pitch_pos'))
                    answer=solver.solve(origin=origin,initial_state=x,baseline=np.tile(old,(20,1)),previous=old,reference=reference)
                    item['solve']=answer
                    item.update(assess_answer(solver.checker,origin,x,old,reference,answer))
                    item['passed']=bool(item['passed'] and live.physics_index==start)
                    if answer.get('commands') is None:item['failure']='v88_no_plan'
                except (ValueError,RuntimeError,FloatingPointError) as exc:item['failure']=str(exc)
                print(f"V88_SOLVE {kind} {e['case']['run_id']} {start} passed={item['passed']} reason={item.get('failure')}",flush=True)
        finally:closes[kind]=solver.close() if solver is not None else None
    report=dict(schema='v88-offline-solver-validation',model_sha256=MODEL_SHA,
        source_manifest_sha256=sha,support_sha256=support_sha,support_identity=domain.identity,
        rows=rows,worker_close=closes,model_fits=0,physics_runs=0,real_time_qualified=False)
    report.update(execution_provenance(manifest,source_archive))
    write_new(output,json_safe(report));return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('data','manifest','model','assets','support','support-sha','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--source-archive',type=Path)
    a=p.parse_args();run(a.data,a.manifest,a.model,a.assets,a.support,a.support_sha,a.output,source_archive=a.source_archive)

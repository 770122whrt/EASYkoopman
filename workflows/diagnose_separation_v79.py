"""Bounded local-only diagnosis using authenticated fit domains/v78 traces.

Preview receives current/past data only. The separate accuracy probe deliberately
uses recorded future commands as OFFLINE conditioning, never online controller
inputs. No optimizer, model fit, sensor simulation or new physics is run here.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from koopman.bounded_mpc_v44 import load_fit_domains
from koopman.command_state_v39 import CausalCommandState
from koopman.bounded_feedback_v46 import FeedbackConfig
from koopman.inexact_tracking_v66 import InexactTrackingFeedback
from koopman.feedback_preview_v79 import ExactChecker, feedback_preview, audit_selection
from koopman.model_separation_v79 import make_predictor, full_lift_probe
from koopman.control_objective_v44 import ObjectiveWeights
from workflows.identify_sparse_world_v30 import from_record
from workflows.runtime_assets_v56 import LoadedAssets

MODEL = 'source/results/phase8.4-sparse-world-pilot-v30-20260913/models/nonlinear__pooled.json'
SHA = '9704fbb8cc0a40ebc74f3f4d2727cba0f52a0b4221ec6e71d4f5526d98a088f4'
REPORT = 'docs/evidence/phase9/common-profile-v78-20260924/common-report.json'
KINDS = ('nominal_physics', 'identified_physics', 'structured_projected')


def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))


def plain(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    return value


def prepare(root):
    path=root/MODEL; payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=SHA: raise ValueError('model_identity')
    domains=load_fit_domains(root,path)
    return from_record(json.loads(payload)), LoadedAssets(None,{},'nonlinear__pooled',path,SHA,domains)


def recorded_origin(data,index,context):
    episode='v79-offline:'+data['case']['configuration']
    initial=data['reset_record']['snapshot']
    if np.max(np.abs(initial['actuator_speed_n']))>1e-8: raise ValueError('zero_rotor_reset')
    live=CausalCommandState(data['case']['configuration'],context,episode_id=episode,zero_rotor_reset_verified=True)
    for i,row in enumerate(data['substeps'][:index]):
        live.record_issued(row['command']['telemetry']['virtual_control_4'][0],physics_index=i,episode_id=episode)
    return live,live.snapshot(configuration=data['case']['configuration'],context=context,origin_control=index//2,episode_id=episode)


def errors(predicted,actual):
    p=np.asarray(predicted); a=np.asarray(actual)
    q=p[:,1:5]/np.linalg.norm(p[:,1:5],axis=1,keepdims=True)
    r=a[:,1:5]/np.linalg.norm(a[:,1:5],axis=1,keepdims=True)
    angle=2*np.arccos(np.clip(np.abs(np.sum(q*r,axis=1)),0,1))
    return dict(z_rmse_m=float(np.sqrt(np.mean((p[:,0]-a[:,0])**2))),
                attitude_rmse_rad=float(np.sqrt(np.mean(angle**2))),
                body_velocity_rmse=float(np.sqrt(np.mean((p[:,5:]-a[:,5:])**2))))


def diagnose(root,*,wall_limit_s=300):
    start=time.perf_counter(); fitted,assets=prepare(root); source=read(root/REPORT)
    output=dict(schema='local-control-model-separation-v79/1',physics_runs=0,model_fits=0,
                continuous_solves=0,closed_loop_benefit_claimed=False,model_sha256=SHA,
                scope='development_recorded_states_only',preview=[],model_probe=[],historical_selection=[])
    for row in source['main_rows']:
        if time.perf_counter()-start>wall_limit_s: raise TimeoutError('diagnostic_wall_budget')
        path=root/row['path'];payload=(path/'trace.json.gz').read_bytes()
        if hashlib.sha256(payload).hexdigest()!=row['trace_sha256']:raise ValueError('trace_identity')
        data=json.loads(gzip.decompress(payload));cfg=row['configuration'];context=assets.context(cfg)
        domain=assets.domains[cfg];reference=np.asarray(data['case']['reference'])
        for index in (4,80,160):
            if time.perf_counter()-start>wall_limit_s:raise TimeoutError('diagnostic_wall_budget')
            live,origin=recorded_origin(data,index,context)
            state=np.asarray(data['substeps'][index]['before']['state_11'][0])
            old=np.asarray(data['substeps'][index-1]['command']['telemetry']['virtual_control_4'][0])
            if row['controller']=='feedback':
                forecasts={}
                for kind in KINDS:
                    predictor=make_predictor(kind,fitted,context)
                    checker=ExactChecker(domain,predictor,horizon=20,weights=ObjectiveWeights(depth=4.))
                    feedback=InexactTrackingFeedback(domain,context,config=FeedbackConfig(slew=.02,timeout_ms=2000.))
                    current=feedback.decide(state,reference,previous=old)
                    hold=np.tile(current['command'] if current['status']=='ready' else old,(20,1))
                    held=checker.check(origin,state,hold,old,reference)
                    preview=feedback_preview(origin,state,old,reference,feedback,checker,timeout_s=15.)
                    delta=None if not held['feasible'] or preview['status']!='ready' else held['cost']-preview['cost']
                    output['preview'].append(dict(configuration=cfg,physics_index=index,kind=kind,
                        trace_sha256=row['trace_sha256'],hold_feasible=held['feasible'],hold_cost=held['cost'],
                        hold_reason=held['reason'],preview={k:v for k,v in preview.items() if k not in ('commands','predictions')},
                        predicted_cost_decrease=delta))
                    # Diagnostic only: same recorded future commands for every model.
                    commands=np.asarray([s['command']['telemetry']['virtual_control_4'][0] for s in data['substeps'][index:index+80:4]])
                    forecasts[kind]=origin.forecast(state,np.repeat(commands,2,axis=0),predictor)
                assert live.physics_index==index
                nominal=forecasts['nominal_physics']; identified=forecasts['identified_physics']; projected=forecasts['structured_projected']
                actual=np.asarray([s['state_after_physics_11'][0] for s in data['substeps'][index:index+80]])
                if not all(f['complete'] for f in forecasts.values()):raise ValueError('structured_forecast_failure')
                probe=full_lift_probe(fitted,context,state,projected['acceleration'])
                output['model_probe'].append(dict(configuration=cfg,physics_index=index,
                    recorded_future_commands_for_offline_diagnosis_only=True,
                    identified_projected_max_abs=float(np.max(np.abs(identified['predictions']-projected['predictions']))),
                    model_errors={k:errors(f['predictions'],actual) for k,f in forecasts.items()},
                    full_lift={k:v for k,v in probe.items() if k!='predictions'},
                    full_lift_completed_steps=len(probe['predictions']),
                    full_lift_error=errors(probe['predictions'],actual) if probe['complete'] else None))
            else:
                kind='nominal_physics' if row['controller']=='nominal_physics' else 'structured_projected'
                checker=ExactChecker(domain,make_predictor(kind,fitted,context),horizon=20,weights=ObjectiveWeights(depth=4.))
                decision=next(a for a in data['solve_audit'] if a['physics_index']==index)
                fb=next(a['result'] for a in data['feedback_audit'] if a['physics_index']==index)
                plans={'held':np.tile(fb['command'] if fb['status']=='ready' else old,(20,1)),
                       'selected':np.asarray(decision['commands'])}
                prior=next((a for a in data['solve_audit'] if a['physics_index']==index-4),None)
                if prior is not None:plans['warm']=np.vstack([prior['commands'][1:],prior['commands'][-1]])
                audited=audit_selection(checker,origin,state,old,reference,plans,decision['commands'],required=tuple(plans))
                output['historical_selection'].append(dict(configuration=cfg,kind=kind,physics_index=index,
                    original_status=decision['status'],audit=audited,
                    scope='known_held_warm_selected_only; unrecorded_discarded_worker_not_reconstructible'))
            assert live.physics_index==index
    output['elapsed_seconds']=time.perf_counter()-start
    return output


def boundary_diagnostics(root):
    from koopman.prepared_allocation_v42 import PreparedDirectAllocation
    from koopman.feedback_preview_v79 import audit_observed_pwm
    from workflows.feedback_inverse_v28 import MINIMUM_DEADZONE_DISTANCE
    rows=[];threshold=float(np.float32(.02))
    for row in read(root/REPORT)['main_rows']:
        if row['controller']=='feedback':continue
        payload=(root/row['path']/'trace.json.gz').read_bytes()
        if hashlib.sha256(payload).hexdigest()!=row['trace_sha256']:raise ValueError('trace_identity')
        data=json.loads(gzip.decompress(payload));allocator=PreparedDirectAllocation(row['configuration'])
        local=[];observed=[];receipts=[]
        for i,step in enumerate(data['substeps']):
            check=audit_observed_pwm(step['command']['_last_motor_values_raw'][0],step['command']['telemetry']['motor_pwm_n'][0])
            if not check['accepted']:receipts.append(dict(physics_index=i,**check))
        for step in data['substeps'][::4]:
            local.append(allocator.command(step['command']['telemetry']['virtual_control_4'][0],pre_tam=True)['pwm_raw'])
            observed.append(step['command']['_last_motor_values_raw'][0])
        local=np.asarray(local,dtype=float);observed=np.asarray(observed)
        margin=lambda a:np.abs(np.abs(a)-threshold)
        branch=lambda a:np.where(a>=threshold,1,np.where(a<=-threshold,-1,0))
        allplans=np.asarray([allocator.command(u,pre_tam=True)['pwm_raw']
            for a in data['solve_audit'] for u in a['commands']],dtype=float)
        rows.append(dict(configuration=row['configuration'],controller=row['controller'],
            trace_sha256=row['trace_sha256'],observed_local_max_pwm_difference=float(np.max(abs(local-observed))),
            actual_commands_deadzone_branch_changes=int(np.sum(branch(local)!=branch(observed))),
            actual_min_local_margin=float(margin(local).min()),actual_min_recorded_margin=float(margin(observed).min()),
            observed_receipt_rejections=receipts,
            planned_min_local_margin=float(margin(allplans).min()),
            planned_local_margin_rejections=int(np.sum(np.min(margin(allplans),axis=1)<=MINIMUM_DEADZONE_DISTANCE))))
    return dict(schema='v79-platform-pwm-boundary/1',physics_runs=0,model_fits=0,
        original_required_margin=MINIMUM_DEADZONE_DISTANCE,original_gate_unchanged=True,rows=rows,
        conclusion='CPU/backend margin discrepancy; actual receipt gate added; no threshold relaxed')


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--boundary-only',action='store_true');a=p.parse_args()
    if a.output.exists():raise ValueError('output_exists')
    root=Path(__file__).resolve().parents[1]
    result=boundary_diagnostics(root) if a.boundary_only else diagnose(root)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(plain(result),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(output=str(a.output),preview_rows=len(result.get('preview',[])),probe_rows=len(result.get('model_probe',[])),
                         selection_rows=len(result.get('historical_selection',[])),elapsed_seconds=result.get('elapsed_seconds'))))


if __name__=='__main__':main()

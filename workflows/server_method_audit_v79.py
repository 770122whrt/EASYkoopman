"""Bounded real-worker/allocator diagnostic; no Isaac physics or model fitting.

Matched preview on/off at the same recorded causal origin. This tests solver
integration, not closed-loop tracking benefit. Old raw receipts remain intact.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
import torch

from koopman.command_state_v39 import CausalCommandState
from koopman.preview_mpc_v79 import create_solver
from koopman.feedback_preview_v79 import audit_observed_pwm
from koopman.control_objective_v44 import ObjectiveWeights
from koopman.bounded_feedback_v46 import FeedbackConfig
from koopman.inexact_tracking_v66 import InexactTrackingFeedback
from koopman.prepared_allocation_v42 import PreparedDirectAllocation
from workflows.control_seam_v23 import ControlKernel
from workflows.runtime_assets_v56 import AssetLocation, load_assets, read
from workflows.identify_sparse_world_v30 import from_record
from workflows.validate_preview_decision_v79 import audit_decision
from easyuuv_nc.thrust_allocation import allocate, control_channels_to_wrench


def plain(v):
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,np.generic):return v.item()
    if isinstance(v,dict):return {k:plain(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)):return [plain(x) for x in v]
    return v


def origin_at(data,index,context):
    cfg=data['case']['configuration'];episode='v79-server-diagnostic:'+cfg
    if np.max(np.abs(data['reset_record']['snapshot']['actuator_speed_n']))>1e-8:
        raise ValueError('nonzero_rotor_reset')
    live=CausalCommandState(cfg,context,episode_id=episode,zero_rotor_reset_verified=True)
    for i,row in enumerate(data['substeps'][:index]):
        live.record_issued(row['command']['telemetry']['virtual_control_4'][0],physics_index=i,episode_id=episode)
    return live,live.snapshot(configuration=cfg,context=context,origin_control=index//2,episode_id=episode)


def pwm_check(data):
    cfg=data['case']['configuration'];cpu=PreparedDirectAllocation(cfg);kernel=ControlKernel(cfg)
    e=kernel.env;device='cuda';deltas=[];recorded_deltas=[];rejections=[]
    if e._use_config_alloc:
        b=kernel.B.to(device);weight=None if e._alloc_weight is None else e._alloc_weight.to(device)
        sign=e._alloc_channel_sign.to(device);mask=e._control_mask_4.to(device)
    for i,step in enumerate(data['substeps']):
        cmd=step['command'];observed=np.asarray(cmd['_last_motor_values_raw'][0])
        check=audit_observed_pwm(observed,cmd['telemetry']['motor_pwm_n'][0])
        if not check['accepted']:rejections.append(dict(physics_index=i,**check))
        if i%4:continue
        u=cmd['telemetry']['virtual_control_4'][0]
        raw=cpu.command(u,pre_tam=True)['pwm_raw']
        if e._use_config_alloc:
            t=torch.tensor(u,dtype=torch.float32,device=device).reshape(1,4)*mask
            gpu=allocate(b,control_channels_to_wrench(t*sign),e._alloc_mode,weight).cpu().numpy()[0]
        else:
            r,p,y,z=torch.tensor(u,dtype=torch.float32,device=device)
            gpu=torch.stack([-r-p+z,r-p+z,-r+p+z,r+p+z,y,-y,-y,y]).cpu().numpy()
        deltas.append(float(np.max(np.abs(raw-gpu))))
        recorded_deltas.append(float(np.max(np.abs(gpu.astype(float)-observed))))
    return dict(configuration=cfg,controller=data['case']['controller'],
        max_cpu_gpu_pwm_difference=max(deltas),max_gpu_recorded_pwm_difference=max(recorded_deltas),
        observed_rejections=rejections,scope='recorded_commands_only_not_global_roundoff_bound')


def main():
    p=argparse.ArgumentParser();p.add_argument('--assets',required=True)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('output_exists')
    a.output.mkdir(parents=True);torch.set_num_threads(1);started=time.monotonic()
    result=dict(schema='server-method-audit-v79/1',physics_runs=0,model_fits=0,
        closed_loop_benefit_claimed=False,model_representation_benefit_claimed=False,
        pid=os.getpid(),python=sys.version,torch=torch.__version__,numpy=np.__version__,
        gpu=torch.cuda.get_device_name(0),pwm=[],solves=[],status='started')
    def save():
        result['wall_seconds']=time.monotonic()-started
        (a.output/'diagnostic.json').write_text(json.dumps(plain(result),indent=2,allow_nan=False))
    save()
    try:
        assets=load_assets(AssetLocation(a.assets,'.','assets/v38/inputs',
            '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
        fitted=from_record(read(assets.model_path));result['model_sha256']=assets.model_sha256
        import casadi
        result['casadi']=casadi.__version__
        rows=read(a.inputs/'traces.json');feedbacks={}
        for row in rows:
            payload=(a.inputs/row['file']).read_bytes()
            if hashlib.sha256(payload).hexdigest()!=row['sha256']:raise ValueError('trace_identity')
            data=json.loads(gzip.decompress(payload))
            if data['case']['configuration']!=row['configuration'] or data['case']['controller']!=row['controller']:
                raise ValueError('trace_case_binding')
            if row['controller']=='feedback':feedbacks[row['configuration']]=(row,data)
            else:result['pwm'].append(dict(trace_sha256=row['sha256'],**pwm_check(data)))
        save()
        for cfg in ('base','uuv4'):
            row,data=feedbacks[cfg];context=assets.context(cfg);domain=assets.domains[cfg];index=4
            state=np.asarray(data['substeps'][index]['before']['state_11'][0]);ref=np.asarray(data['case']['reference'])
            old=np.asarray(data['substeps'][index-1]['command']['telemetry']['virtual_control_4'][0])
            def factory():return InexactTrackingFeedback(domain,context,config=FeedbackConfig(slew=.02,timeout_ms=2000.))
            current=factory().decide(state,ref,previous=old)
            if current['status']!='ready':raise ValueError('current_feedback_not_ready')
            for enabled in (False,True):
                if time.monotonic()-started>450:raise TimeoutError('diagnostic_remaining_budget')
                live,origin=origin_at(data,index,context);solver=None
                entry=dict(configuration=cfg,physics_index=index,preview_enabled=enabled,
                    kind='identified_physics',trace_sha256=row['sha256'],new_physics_steps=0)
                result['solves'].append(entry)
                try:
                    solver=create_solver(domain,fitted,context,'identified_physics',horizon=20,
                        weights=ObjectiveWeights(depth=4.),preview_enabled=enabled)
                    entry['model_identity']=solver.model_identity
                    decision=solver.solve(origin=origin,initial_state=state,
                        baseline=np.tile(current['command'],(20,1)),previous=old,reference=ref,
                        physical_target=current.get('static_command'))
                    entry['decision']=decision
                    if not decision['exact_feasible']:raise ValueError('no_accepted_solver_plan:'+str(decision['reason']))
                    entry['independent_audit']=audit_decision(checker=solver.checker,origin=origin,
                        state=state,previous=old,reference=ref,feedback_result=current,
                        prior_decision=None,decision=decision,feedback_factory=factory)
                    if not entry['independent_audit']['accepted']:raise ValueError('independent_selection_rejected')
                    if live.physics_index!=index:raise ValueError('future_history_leak')
                finally:
                    if solver is not None:entry['worker_cleanup']=solver.close()
                    save()
                if entry['worker_cleanup']!={'process_stopped':True,'io_threads_stopped':True}:
                    raise ValueError('worker_not_cleaned')
                print(json.dumps(dict(configuration=cfg,preview_enabled=enabled,status=decision['status'],cost=decision['cost'])),flush=True)
        result['status']='diagnostic_completed_not_closed_loop_admission'
    except BaseException as exc:
        result.update(status='failed',exception=type(exc).__name__+':'+str(exc));raise
    finally:save()


if __name__=='__main__':main()

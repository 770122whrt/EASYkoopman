"""Frozen8fit-origin interface equivalence; no model fitting or simulation."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import json,time
from pathlib import Path
import numpy as np
from workflows.run_state_projection_v34 import read,sha,dump
from workflows.identify_sparse_world_v30 import load_fit_cache,from_record
from workflows.identification_protocol_v29 import pulse
from workflows.identification_prediction_v32 import policy_forecast
from workflows.control_seam_v23 import ControlKernel
from workflows.actuator_replay_v28 import Float32PWMActuatorState
from koopman.command_prediction_v37 import forecast_commands


def direct_inputs(history,commands,configuration,context):
    """Independently replay the existing policy's actuator-loop statements."""
    k=ControlKernel(configuration);rotor=Float32PWMActuatorState(k.env._num_thrusters,tau=k.tau,dt=1/120,clock='float32_accumulated_v1')
    for u in history:rotor.advance_pwm(k.command(u,pre_tam=True)['pwm'])
    rows={key:[] for key in ('pwm','rotor_speed','acceleration','applied_control','physics_time_s')}
    scale=np.r_[[context.mass]*3,context.inertia]
    for u in commands:
        sent=k.command(u,pre_tam=True)
        for _ in range(2):
            speed=rotor.advance_pwm(sent['pwm']);force=k.env.cfg.rotor_constant*np.abs(speed)*speed
            values={'pwm':sent['pwm'],'rotor_speed':speed,'acceleration':(k.B.numpy()@force)/scale,
                'applied_control':sent['virtual_control'],'physics_time_s':rotor.elapsed_time}
            for key,value in values.items():rows[key].append(value)
    return {key:np.asarray(value) for key,value in rows.items()}


def run(root):
    root=Path(root);out=root/'docs/evidence/phase8_4/command-prediction-v37-20260913';freeze=read(out/'freeze.json')
    if (out/'status.json').exists() or (out/'cases').exists():raise ValueError('v37_one_shot_already_started')
    for name,h in {**freeze['source_sha256'],**freeze['input_sha256']}.items():
        if sha(root/name)!=h:raise ValueError('v37_bound_file_changed:'+name)
    out.joinpath('cases').mkdir();budget=read(out/'budget.json');started=time.monotonic()
    reserve=freeze['diagnostic_limit_seconds']-budget['charged_seconds'];deadline=started+reserve-5
    attempt={'stage':'eight_fit_origins_and_branch_isolation','status':'reserved','charged_seconds':reserve}
    budget['attempts'].append(attempt);budget['charged_seconds']+=reserve;dump(out/'budget.json',budget)
    reports=[];status={'status':'running','new_fits':0,'new_server_runs':0,'independent_validation':False,'model_handoff':False}
    try:
        episodes=[e for e in load_fit_cache(root) if e.case['excitation']=='prbs'];assert len(episodes)==8
        for e in episodes:
            cfg=e.case['configuration'];p=root/'source/results/phase8.4-sparse-world-pilot-v30-20260913/models'/('nonlinear__heldout-'+cfg+'.json')
            model=from_record(read(p));history=e.arrays['issued_control'][:256].copy();x=e.states[256].copy()
            old=policy_forecast(x,history,pulse(e.case)[128:132],cfg,e.context,model,deadline=deadline)
            if not old['complete'] or old['predictions'].shape!=(8,11):raise ValueError('v37_old_path_incomplete')
            new=forecast_commands(x,history,old['commands'],cfg,e.context,model,origin_control=128,deadline=deadline)
            if not new['complete']:raise ValueError('v37_new_path_incomplete')
            inputs=direct_inputs(history,old['commands'],cfg,e.context)
            differences={'state':float(np.max(np.abs(new['predictions']-old['predictions'])))}
            for key,value in inputs.items():differences[key]=float(np.max(np.abs(new[key]-value)))
            if max(differences.values())>1e-12:raise ValueError('v37_old_new_difference')
            np.testing.assert_array_equal(new['issued_commands'],old['commands'])
            for key in ('pwm','applied_control'):np.testing.assert_array_equal(new[key],inputs[key])
            if new['origin_actuator_time_s']!=old['origin_actuator_time_s']:raise ValueError('v37_clock_mismatch')
            alternatives=[]
            for sign in (-1,1):
                branch=old['commands'].copy();branch[:,3]=np.clip(branch[:,3]+sign*.01,-.95,.95)
                r=forecast_commands(x,history,branch,cfg,e.context,model,origin_control=128,deadline=deadline)
                if not r['complete']:raise ValueError('v37_branch_incomplete')
                alternatives.append({'depth_command_offset':sign*.01,'complete':r['complete'],
                    'state_difference_from_original_max':float(np.max(np.abs(r['predictions']-new['predictions'])))})
            repeated=forecast_commands(x,history,old['commands'],cfg,e.context,model,origin_control=128,deadline=deadline)
            for key in ('predictions','rotor_speed','physics_time_s','acceleration','pwm','applied_control'):
                np.testing.assert_array_equal(new[key],repeated[key])
            np.testing.assert_array_equal(new['applied_control'][:,np.asarray(new['control_mask'])==0],0.)
            arrays=out/'cases'/(e.case['run_id']+'.npz')
            np.savez_compressed(arrays,reference_states=old['predictions'],reference_commands=old['commands'],
                **{key:new[key] for key in ('predictions','issued_commands','pwm','rotor_speed','acceleration','applied_control','physics_time_s','origin_rotor_speed')})
            result={'case':e.case,'role':'fit_interface_diagnostic','origin_control':128,'control_intervals':4,
                'parent_sha256':sha(p),'trace_sha256':e.trace_sha256,'arrays_sha256':sha(arrays),
                'maximum_differences':differences,'repeat_branch_exact':True,'masked_axis_zero':True,
                'origin_actuator_time_s':new['origin_actuator_time_s'],'alternatives':alternatives}
            dump(arrays.with_suffix('.json'),result);reports.append(result)
            print(json.dumps({'configuration':cfg,'completed':len(reports),'state_max_difference':differences['state'],'seconds':time.monotonic()-started}),flush=True)
        status.update(status='interface_equivalence_passed',cases=8,reference_physics_ticks=64,
            predictions_per_case_including_two_branches_and_repeat=32,repeat_branch_exact=True,
            maximum_differences={key:max(r['maximum_differences'][key] for r in reports) for key in reports[0]['maximum_differences']},
            caveat='Source/fit interface equivalence only; not fresh prediction benefit or a closed-loop control gate.')
        attempt['status']='completed'
    except BaseException as exc:
        status.update(status='failed',exception=f'{type(exc).__name__}:{exc}',completed_cases=len(reports));attempt['status']='failed';raise
    finally:
        elapsed=time.monotonic()-started;attempt['charged_seconds']=elapsed;budget['charged_seconds']+=elapsed-reserve
        dump(out/'budget.json',budget);status['seconds']=elapsed;dump(out/'status.json',status)
    print(json.dumps(status),flush=True)


if __name__=='__main__':run(Path.cwd())

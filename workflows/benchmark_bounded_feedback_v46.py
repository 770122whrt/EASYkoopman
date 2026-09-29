"""Fixed fit-only fallback usability, timing and original-source cross-check."""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


def load_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    helper=load_file('feedback_assay_helper',root/'workflows/benchmark_command_state_v39.py')
    old=root/'docs/evidence/phase9/prepared-commands-v45-pilot-20260920'
    prior=helper.read(old/'protocol.json');previous=helper.read(old/'result.json')
    assert previous['local_gate']=='GO' and previous['protocol_sha256']==helper.sha(old/'protocol.json')
    assert all(helper.sha(root/name)==digest for name,digest in prior['sources'].items())
    handoff_path=root/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    assert helper.sha(handoff_path)==prior['handoff_sha256']
    handoff=helper.read(handoff_path);frozen=Path(handoff['frozen_source_directory'])
    modules=['koopman/command_state_v39.py','koopman/prepared_projected_v40.py',
        'koopman/prepared_allocation_v42.py','koopman/command_batch_v42.py','koopman/control_objective_v44.py',
        'koopman/bounded_mpc_v44.py','koopman/prepared_commands_v45.py','koopman/bounded_feedback_v46.py']
    sources=modules+['tests/test_bounded_feedback_v46.py','workflows/benchmark_bounded_feedback_v46.py']
    protocol=dict(schema='bounded-feedback-v46-fit-only-v1',configurations=handoff['configurations'],
        model_for_fit_support='nonlinear__pooled',requests_per_configuration=[
            dict(label='hold-o0',origin=0,z=5.5),dict(label='hold-o64',origin=64,z=5.5),
            dict(label='hold-o128',origin=128,z=5.5),dict(label='depth-minus-o128',origin=128,z=5.45),
            dict(label='depth-plus-o128',origin=128,z=5.55)],reference_quaternion=[1.,0.,0.,0.],
        warmups=1,repetitions=3,internal_ms=10.,complete_limit_ms=1000/60,
        gains=dict(height_kp=1.,vertical_kd=2.,attitude_kp=9.,angular_kd=6.),
        inverse_iterations=4,jacobian_step=.001,line_search_fractions=[1.,.5,.25],
        slew=.01,minimum_pwm_headroom=.05,minimum_deadzone_distance=2e-6,
        physical_residual_limit=[.025,.025,.025,.1,.1,.1],
        source_cross_check='original_ControlKernel_steady_outside_control_timer_all_ready_samples',
        maximum_seconds=180,output_limit_bytes=32*1024**2,processes=1,compute_threads=1,
        gate='all_120_measured_requests_ready_and_total_ms<=16.67_and_original_source_validation',
        formal_test_access=False,new_fits=0,new_server_runs=0,
        sources={name:helper.sha(root/name) for name in sources},prior_result_sha256=helper.sha(old/'result.json'),
        handoff_sha256=helper.sha(handoff_path))
    if args.output.exists():raise FileExistsError('feedback_assay_output_exists')
    args.output.mkdir(parents=True);helper.dump(args.output/'protocol.json',protocol)
    for name in sources:
        target=args.output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write((root/name).read_bytes())
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):os.environ[key]='1'
    sys.path.insert(0,str(frozen));started=time.perf_counter();rows=[];error=None;status='failed'
    def budget():
        if time.perf_counter()-started>=180:raise TimeoutError('fallback_assay_budget')
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        from workflows.projected_release_v38 import verify_bundle
        from workflows.identify_sparse_world_v30 import load_fit_cache
        from workflows.control_seam_v23 import ControlKernel
        from workflows.workpoint_v27 import _steady,ACCELERATION_TOLERANCE
        from workflows.feedback_inverse_v28 import deadzone_distance,MINIMUM_DEADZONE_DISTANCE
        verify_bundle(frozen,frozen.parent/'inputs',handoff['source_commit'])
        loaded={Path(name).stem:load_file(name[:-3].replace('/','.'),root/name) for name in modules}
        core=loaded['bounded_feedback_v46'];support=loaded['bounded_mpc_v44']
        entry=handoff['eligible_models'][protocol['model_for_fit_support']]
        assert helper.sha(frozen/entry['path'])==entry['sha256']
        domains=support.load_fit_domains(root,frozen/entry['path'])
        episodes=[e for e in load_fit_cache(root) if e.case['excitation']=='prbs']
        assert len(episodes)==8 and all(e.case['role']=='fit' for e in episodes)
        for e in episodes:
            budget();name=e.case['configuration'];tick=time.perf_counter()
            policy=core.BoundedFeedback(domains[name],e.context)
            seed=policy.prepare_startup(e.states[0].copy(),np.array([5.5,1.,0.,0.,0.]))
            preparation_ms=1000*(time.perf_counter()-tick)
            original=ControlKernel(name);scale=np.r_[[e.context.mass]*3,e.context.inertia]
            for request in protocol['requests_per_configuration']:
                origin=request['origin'];state=e.states[2*origin].copy()
                ref=np.array([request['z'],1.,0.,0.,0.])
                past=None if origin==0 else e.arrays['issued_control'][2*origin-1].copy()
                def call():
                    budget();tick=time.perf_counter()
                    value=policy.decide(state.copy(),ref.copy(),previous=None if past is None else past.copy())
                    encoded=json.dumps(value,default=lambda a:a.tolist(),allow_nan=False)
                    packet=json.loads(encoded);ms=1000*(time.perf_counter()-tick)
                    return dict(total_ms=ms,packet=packet,passes=bool(packet['status']=='ready' and ms<=1000/60))
                def check(sample):
                    t=time.perf_counter();p=sample['packet']
                    assert p['runtime_eligible'] is False and p['actual_history_advanced'] is False
                    if p['status']!='ready':
                        assert p['command'] is None and p['reason']
                        return dict(checked_ready=False,seconds=time.perf_counter()-t)
                    command=np.asarray(p['command'],dtype=float)
                    assert np.all(np.abs(command)<=.95) and np.all(np.abs(command*(1-policy.steady.mask))<=1e-7)
                    assert np.all(command>=domains[name].command_lower-1e-7) and np.all(command<=domains[name].command_upper+1e-7)
                    if past is not None:assert np.all(np.abs(command-past)<=.01+1e-7)
                    else:assert p['startup_exception_requested'] is True
                    wrench,sent=_steady(original,command);target=np.asarray(p['demand']['target_wrench'])
                    error=(wrench-target)/scale
                    assert np.all(np.abs(error)<=ACCELERATION_TOLERANCE)
                    assert 1-np.max(np.abs(sent['pwm_raw']))>=.05
                    assert deadzone_distance(sent['pwm_raw'])>MINIMUM_DEADZONE_DISTANCE
                    maximum=0.
                    for key,value in [('steady_wrench',wrench),('acceleration_error',error),('pwm_raw',sent['pwm_raw'])]:
                        np.testing.assert_allclose(p['inspection'][key],value,rtol=1e-12,atol=1e-12)
                        maximum=max(maximum,float(np.max(np.abs(np.asarray(p['inspection'][key])-value))))
                    return dict(checked_ready=True,maximum_difference=maximum,seconds=time.perf_counter()-t)
                warm=call();warm['source_check']=check(warm);samples=[]
                for repeat in range(3):
                    sample=call();sample['source_check']=check(sample);samples.append(sample)
                rows.append(dict(configuration=name,episode_id=e.case['run_id'],role='fit',trace_sha256=e.trace_sha256,
                    request=request,state=state.tolist(),reference=ref.tolist(),previous=None if past is None else past.tolist(),
                    support_id=domains[name].identity,prepare_before_ready_ms=preparation_ms,seed_status=seed['status'],
                    warmup=warm,samples=samples))
            helper.dump(args.output/f'{name}.json',rows[-5:])
            print(json.dumps(dict(configuration=name,requests=[dict(label=r['request']['label'],
                passes=sum(s['passes'] for s in r['samples']),reasons=[s['packet']['reason'] for s in r['samples']]) for r in rows[-5:]])),flush=True)
        budget();verify_bundle(frozen,frozen.parent/'inputs',handoff['source_commit'])
        assert all(helper.sha(root/name)==digest for name,digest in protocol['sources'].items())
        status='local_fallback_assay_complete'
    except Exception as exc:error=f'{type(exc).__name__}:{exc}'
    samples=[s for row in rows for s in row['samples']];complete=status=='local_fallback_assay_complete' and len(rows)==40
    go=complete and all(s['passes'] for s in samples)
    result=dict(status=status,error=error,seconds=time.perf_counter()-started,rows=rows,
        created_at=datetime.datetime.now().astimezone().isoformat(),protocol_sha256=helper.sha(args.output/'protocol.json'),
        measured_requests=len(samples),ready=sum(s['packet']['status']=='ready' for s in samples),
        complete_budget_passes=sum(s['passes'] for s in samples),local_gate='GO' if go else 'NO_GO',
        controller_promoted=False,actual_startup_permission_implemented=False,
        limitations=['fit_states_only_not_closed_loop','few_timing_samples','startup_proposals_not_actual_issuance',
                     'cooperative_timeout_not_isolation','actual_once_only_startup_and_runtime_arbiter_missing'])
    helper.dump(args.output/'result.json',result)
    if sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())>protocol['output_limit_bytes']:
        raise RuntimeError('fallback_assay_output_budget')
    print(json.dumps(dict(status=status,seconds=result['seconds'],local_gate=result['local_gate'],ready=result['ready'],error=error)),flush=True)
    if not complete:raise SystemExit(1)


if __name__=='__main__':main()

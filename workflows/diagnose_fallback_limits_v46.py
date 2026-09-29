"""Four source-only counterexamples distinguish inverse and command limits."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf8'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    source=root/'docs/evidence/phase9/fallback-v46-pilot-20260920/result.json';r=read(source)
    assert r['status']=='local_fallback_assay_complete' and r['local_gate']=='NO_GO'
    support_file=root/'docs/evidence/phase9/mpc-v44-pilot-20260920/fit-support.json';domains=read(support_file)
    handoff_path=root/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    handoff=read(handoff_path);frozen=Path(handoff['frozen_source_directory'])
    cases=[('base','hold-o64'),('heavy_moderate','hold-o64'),('uuv6','depth-minus-o128'),('uuv4','depth-minus-o128')]
    protocol=dict(schema='fallback-v46-limit-diagnosis-v1',cases=cases,maximum_seconds=60,output_limit_bytes=8*1024**2,
        input_sha256=sha(source),fit_support_sha256=sha(support_file),runner_sha256=sha(__file__),
        handoff_sha256=sha(handoff_path),original_source_commit=handoff['source_commit'],
        static_inverse_calls_per_case=1,slew=.01,processes=1,compute_threads=1,new_fits=0,new_server_runs=0,formal_test_access=False)
    if args.output.exists():raise FileExistsError('limit_diagnosis_exists')
    args.output.mkdir(parents=True)
    (args.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n',encoding='utf8')
    (args.output/'source.py').write_bytes(Path(__file__).read_bytes())
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):os.environ[key]='1'
    sys.path.insert(0,str(frozen));started=time.perf_counter();rows=[];error=None;status='failed'
    try:
        import numpy as np,torch
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        from workflows.projected_release_v38 import verify_bundle
        from workflows.feedback_inverse_v31 import solve_feasible_control
        from workflows.control_seam_v23 import ControlKernel
        from workflows.workpoint_v27 import _steady,ACCELERATION_TOLERANCE
        from workflows.feedback_inverse_v28 import deadzone_distance,MINIMUM_DEADZONE_DISTANCE
        verify_bundle(frozen,frozen.parent/'inputs',handoff['source_commit'])
        for name,label in cases:
            if time.perf_counter()-started>=60:raise TimeoutError('limit_diagnosis_budget')
            old=next(v for v in r['rows'] if v['configuration']==name and v['request']['label']==label)
            p=old['samples'][0]['packet'];target=np.asarray(p['demand']['target_wrench']);previous=np.asarray(old['previous'])
            domain=domains[name]
            assert tuple(domain['context_key'])==tuple(p['context_key']) and domain['model_id']==p['model_id']
            key=p['context_key'];scale=np.r_[[key[0]]*3,key[1:4]]
            t=time.perf_counter();inverse=solve_feasible_control(name,target);solve_ms=1000*(time.perf_counter()-t)
            command=np.asarray(inverse['command_4']);delta=command-previous;alpha=1.
            lower=np.asarray(domain['command_lower']);upper=np.asarray(domain['command_upper'])
            assert np.all(previous>=lower-1e-7) and np.all(previous<=upper+1e-7)
            for i,d in enumerate(delta):
                if d:
                    alpha=min(alpha,.01/abs(d),(upper[i]-previous[i])/d if d>0 else (lower[i]-previous[i])/d)
            alpha=max(0.,alpha);limited=(previous+alpha*delta).astype(np.float32)
            kernel=ControlKernel(name)
            def record(u):
                wrench,sent=_steady(kernel,u);error=(wrench-target)/scale
                return dict(command=np.asarray(u).tolist(),wrench=wrench.tolist(),pwm_raw=sent['pwm_raw'].tolist(),
                    error_against_original_target=error.tolist(),max_error_ratio=float(np.max(np.abs(error)/ACCELERATION_TOLERANCE)),
                    original_target_residual_passes=bool(np.all(np.abs(error)<=ACCELERATION_TOLERANCE)),
                    raw_pwm_and_deadzone_pass=bool(1-np.max(np.abs(sent['pwm_raw']))>=.05 and deadzone_distance(sent['pwm_raw'])>MINIMUM_DEADZONE_DISTANCE),
                    in_fit_box=bool(np.all(u>=lower-1e-7) and np.all(u<=upper+1e-7)),
                    slew_passes=bool(np.all(np.abs(u-previous)<=.01+1e-7)))
            row=dict(configuration=name,request=label,trace_sha256=old['trace_sha256'],original_target=target.tolist(),
                previous=record(previous),unlimited=record(command),limited=record(limited),alpha=alpha,
                source_inverse_ms=solve_ms,source_inverse_record=inverse)
            rows.append(row)
            print(json.dumps(dict(configuration=name,source_target_pass=row['unlimited']['original_target_residual_passes'],
                 source_max_step=float(np.max(np.abs(delta))),alpha=alpha,limited_target_pass=row['limited']['original_target_residual_passes'])),flush=True)
        verify_bundle(frozen,frozen.parent/'inputs',handoff['source_commit'])
        if time.perf_counter()-started>=60:raise TimeoutError('limit_diagnosis_budget')
        assert sha(__file__)==protocol['runner_sha256'] and sha(source)==protocol['input_sha256']
        status='local_limit_diagnosis_complete'
    except Exception as exc:error=f'{type(exc).__name__}:{exc}'
    result=dict(status=status,error=error,rows=rows,seconds=time.perf_counter()-started,
        protocol_sha256=sha(args.output/'protocol.json'),created_at=datetime.datetime.now().astimezone().isoformat(),
        controller_promoted=False,global_infeasibility_proven=False,
        limitations=['four_source_static_cases_only','no_issued_commands','limited_residual_not_relabelled_as_target_success'])
    (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    if sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())>protocol['output_limit_bytes']:
        raise RuntimeError('limit_diagnosis_output_budget')
    print(json.dumps(dict(status=status,seconds=result['seconds'],error=error)),flush=True)
    if status!='local_limit_diagnosis_complete':raise SystemExit(1)


if __name__=='__main__':main()

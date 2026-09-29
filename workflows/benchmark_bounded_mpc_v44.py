"""One fixed fit-only whole-solver/fallback diagnostic; no Isaac or promotion."""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fallback_child():
    import numpy as np
    import torch
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    from workflows.feedback_v31 import FeedbackPolicy, validate_decision
    request = json.loads(sys.stdin.read())
    x, zero = np.asarray(request['state'], dtype=float), np.zeros(4)
    policy = FeedbackPolicy(request['configuration'])
    started = time.perf_counter()
    decision = policy.decide(x, zero)
    accepted = validate_decision(decision, x, zero, request['configuration'])
    elapsed = 1000*(time.perf_counter()-started)
    print(json.dumps(dict(control_ms=elapsed, accepted=bool(accepted), command=decision['command_4'],
                         includes='decide_and_validate_decision', realtime_16_67ms_observed=bool(accepted and elapsed <= 1000/60))), flush=True)


def main():
    if '--fallback-child' in sys.argv:
        fallback_child(); return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--compiler-dir', required=True, type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    helper = load_file('mpc_assay_helper', project/'workflows/benchmark_command_state_v39.py')
    old = project/'docs/evidence/phase9/compiled-v43-pilot-20260920'
    prior, preceding = helper.read(old/'protocol.json'), helper.read(old/'result.json')
    assert preceding['status'] == 'local_compiled_predictor_go'
    assert preceding['protocol_sha256'] == helper.sha(old/'protocol.json')
    assert all(helper.sha(project/name) == digest for name,digest in prior['sources'].items())
    handoff_path = project/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    assert helper.sha(handoff_path) == prior['handoff_sha256']
    handoff = helper.read(handoff_path); frozen = Path(handoff['frozen_source_directory'])
    modules = ['koopman/command_state_v39.py', 'koopman/prepared_projected_v40.py',
        'koopman/prepared_allocation_v42.py', 'koopman/command_batch_v42.py', 'koopman/compiled_projected_v43.py',
        'koopman/control_objective_v44.py', 'koopman/bounded_mpc_v44.py']
    sources = modules+['workflows/benchmark_bounded_mpc_v44.py', 'workflows/benchmark_command_state_v39.py',
                      'tests/test_bounded_mpc_v44.py', 'tests/test_prepared_projected_v40.py', 'tests/test_command_batch_v41.py']
    bindings = {name: helper.sha(project/name) for name in sources}
    protocol = dict(schema='bounded-mpc-v44-local-diagnostic-v1', configurations=handoff['configurations'],
        origin_control=128, horizon=20, model='nonlinear__pooled', perturbation=[.002]*4, slew=[.01]*4,
        maximum_raw_pwm=.95, weights=dict(depth=1., attitude=1., vertical_speed=.1, angular_speed=.1,
                                         effort=.01, slew=.05, terminal=1.),
        reference=[5.5, 1., 0., 0., 0.], baseline='repeat_last_past_issued_command_no_future_truth',
        warmups=1, repetitions=3, solve_limit_ms=100., maximum_seconds=180, output_limit_bytes=32*1024**2,
        fallback_calls_per_configuration=1, fallback_child_limit_seconds=10, fallback_low_level_limit_ms=1000/60,
        sources=bindings, handoff_sha256=helper.sha(handoff_path), prior_result_sha256=helper.sha(old/'result.json'),
        compiler_directory=str(args.compiler_dir.resolve()), processes_concurrent=1, compute_threads=1,
        new_fits=0, formal_test_access=False, new_server_runs=0,
        gate='all_three_measured_solves_per_configuration_feasible_and_total_ms<=100_and_all_fallback_ms<=16.67; diagnose_fixed_cases_even_after_rejection')
    if args.output.exists(): raise FileExistsError('mpc_assay_output_exists')
    args.output.mkdir(parents=True); helper.dump(args.output/'protocol.json', protocol)
    for name in sources:
        target=args.output/'source'/name; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream: stream.write((project/name).read_bytes())
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS'): os.environ[key]='1'
    sys.path.insert(0, str(args.compiler_dir.resolve())); sys.path.insert(0, str(frozen))
    started=time.monotonic(); deadline=started+protocol['maximum_seconds']
    rows, status, error, runtime = [], 'failed', None, {}
    try:
        import numpy as np
        import numba, llvmlite, torch
        assert numba.__version__=='0.61.2' and llvmlite.__version__=='0.44.0'
        assert args.compiler_dir.resolve() in Path(numba.__file__).resolve().parents
        torch.set_num_threads(1); torch.set_num_interop_threads(1)
        runtime=dict(numpy=np.__version__, numba=numba.__version__, llvmlite=llvmlite.__version__)
        from workflows.projected_release_v38 import verify_bundle
        from workflows.identify_sparse_world_v30 import load_fit_cache, from_record
        verify_bundle(frozen, frozen.parent/'inputs', handoff['source_commit'])
        loaded={Path(name).stem:load_file(name[:-3].replace('/','.'),project/name) for name in modules}
        model_entry=handoff['eligible_models'][protocol['model']]; model_path=frozen/model_entry['path']
        assert helper.sha(model_path)==model_entry['sha256']
        model=from_record(helper.read(model_path)); core=loaded['bounded_mpc_v44']
        domains=core.load_fit_domains(project, model_path)
        helper.dump(args.output/'fit-support.json', {name:domain.record() for name,domain in domains.items()})
        episodes=[e for e in load_fit_cache(project) if e.case['excitation']=='prbs']
        assert len(episodes)==8 and all(e.case['role']=='fit' for e in episodes)
        for e in episodes:
            if time.monotonic()>=deadline: raise TimeoutError('mpc_assay_budget')
            name, episode_id=e.case['configuration'],e.case['run_id']; origin=protocol['origin_control']
            t=time.perf_counter(); predictor=loaded['compiled_projected_v43'].prepare_compiled(model,e.context)
            preparation_ms=1000*(time.perf_counter()-t)
            live=loaded['command_state_v39'].CausalCommandState(name,e.context,episode_id=episode_id,zero_rotor_reset_verified=True)
            for i in range(2*origin):
                live.record_issued(e.arrays['issued_control'][i],physics_index=i,episode_id=episode_id)
            snapshot=live.snapshot(configuration=name,context=e.context,origin_control=origin,episode_id=episode_id)
            solver=core.BoundedMPC(domains[name],predictor,model_id=model_entry['sha256'])
            samples=[]
            for repeat in range(protocol['repetitions']+1):
                if time.monotonic()>=deadline: raise TimeoutError('mpc_assay_budget')
                tick=time.perf_counter()
                previous=e.arrays['issued_control'][2*origin-1].copy()
                baseline=np.repeat(previous[None],protocol['horizon'],axis=0)
                result=solver.solve(snapshot,e.states[2*origin].copy(),baseline,previous,protocol['reference'],
                    episode_id=episode_id,reference_id='fixed-z5.5-upright',request_id=f'{episode_id}-{repeat}')
                # Include encoding the complete plan/predictions in measured cost.
                encoded=json.dumps(result,default=lambda a:a.tolist(),allow_nan=False)
                decoded=json.loads(encoded)
                total_ms=1000*(time.perf_counter()-tick)
                decoded.update(total_ms=total_ms, warmup=repeat==0, encoded_bytes=len(encoded.encode('utf8')),
                    passes_budget=bool(total_ms<=100 and result['status'] in ('selected','baseline')))
                samples.append(decoded)
            assert live.physics_index==2*origin
            env=dict(os.environ);env['PYTHONPATH']=str(frozen)
            fallback_started=time.perf_counter()
            try:
                child=subprocess.run([sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),'--fallback-child'],
                    input=json.dumps(dict(configuration=name,state=e.states[2*origin].tolist())),
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8',env=env,
                    timeout=min(10,max(.01,deadline-time.monotonic())),check=False)
                fallback=dict(native_exit=child.returncode,stdout=child.stdout,stderr=child.stderr,
                    process_ms=1000*(time.perf_counter()-fallback_started),timed_out=False)
                if child.returncode==0: fallback.update(json.loads(child.stdout.strip().splitlines()[-1]))
            except subprocess.TimeoutExpired as exc:
                fallback=dict(native_exit=None,timed_out=True,process_ms=1000*(time.perf_counter()-fallback_started),
                    stdout=(exc.stdout or b'').decode('utf8',errors='replace') if isinstance(exc.stdout,bytes) else exc.stdout,
                    stderr=(exc.stderr or b'').decode('utf8',errors='replace') if isinstance(exc.stderr,bytes) else exc.stderr)
            rows.append(dict(configuration=name,episode_id=episode_id,role='fit',trace_sha256=e.trace_sha256,
                model_sha256=model_entry['sha256'],support_id=domains[name].identity,
                prepare_before_control_ms=preparation_ms,samples=samples,fallback=fallback))
            helper.dump(args.output/f'{len(rows):02d}-{name}.json',rows[-1])
            print(json.dumps(dict(configuration=name,measured_solve_passes=sum(s['passes_budget'] for s in samples[1:]),
                                 fallback=fallback.get('control_ms','timeout_or_error'),seconds=time.monotonic()-started)),flush=True)
        verify_bundle(frozen,frozen.parent/'inputs',handoff['source_commit'])
        assert all(helper.sha(project/name)==digest for name,digest in bindings.items())
        if time.monotonic()>=deadline: raise TimeoutError('mpc_assay_budget')
        status='completed_local_controller_diagnostic'
    except Exception as exc: error=f'{type(exc).__name__}:{exc}'
    solve_go=len(rows)==8 and all(s['passes_budget'] for row in rows for s in row['samples'][1:])
    fallback_go=len(rows)==8 and all(row['fallback'].get('realtime_16_67ms_observed',False) for row in rows)
    result=dict(status=status,error=error,seconds=time.monotonic()-started,rows=rows,runtime=runtime,
        created_at=datetime.datetime.now().astimezone().isoformat(),protocol_sha256=helper.sha(args.output/'protocol.json'),
        cpu=helper.cpu_name(),solve_gate='GO' if solve_go else 'NO_GO',fallback_gate='GO' if fallback_go else 'NO_GO',
        overall_gate='GO' if status=='completed_local_controller_diagnostic' and solve_go and fallback_go else 'NO_GO',
        controller_promoted=False,evidence_level='local_fit_solver_and_fallback_diagnostic_only',
        limitations=['few_timing_samples_no_tail_guarantee','no_worker_arbitration','no_actual_command_issuance',
                     'fit_box_is_not_statistical_safety','solver_model_binding_verified_by_runner_not_live_adapter'])
    payload=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if len(payload.encode('utf8'))+sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())>protocol['output_limit_bytes']:
        raise RuntimeError('mpc_assay_output_budget')
    with (args.output/'result.json').open('x',encoding='utf8') as stream:stream.write(payload)
    print(json.dumps(dict(status=status,seconds=result['seconds'],solve_gate=result['solve_gate'],fallback_gate=result['fallback_gate'],error=error)),flush=True)
    if status!='completed_local_controller_diagnostic':raise SystemExit(1)


if __name__=='__main__':main()

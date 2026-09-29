"""Fixed fit-only complete-solver comparison and separate 100 ms admission."""
import argparse
from dataclasses import replace
import datetime
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


def load_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def compare_packets(actual,expected):
    import numpy as np
    maximum=0.
    for key in ('status','reason','candidate_count','selected_index','runtime_eligible','data_source_verified'):
        assert actual[key]==expected[key],key
    assert actual['status'] in ('selected','baseline')
    for key in ('commands','predictions','cost','baseline_cost'):
        np.testing.assert_allclose(actual[key],expected[key],rtol=1e-12,atol=1e-12,err_msg=key)
        maximum=max(maximum,float(np.max(np.abs(np.asarray(actual[key])-np.asarray(expected[key])))))
    for a,b in zip(actual['candidates'],expected['candidates']):
        for key in ('index','feasible','rejection'): assert a[key]==b[key],key
        if a['cost'] is None: assert b['cost'] is None
        else:
            np.testing.assert_allclose(a['cost'],b['cost'],rtol=1e-12,atol=1e-12)
            maximum=max(maximum,abs(a['cost']-b['cost']))
    ignore={'started_perf_counter_s','completed_perf_counter_s'}
    assert {k:v for k,v in actual['metadata'].items() if k not in ignore}=={k:v for k,v in expected['metadata'].items() if k not in ignore}
    return maximum


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--compiler-dir',required=True,type=Path)
    args=parser.parse_args(); root=Path(__file__).resolve().parents[1]
    helper=load_file('prepared_command_assay_helper',root/'workflows/benchmark_command_state_v39.py')
    prior_dir=root/'docs/evidence/phase9/mpc-v44-profile-20260920'
    prior=helper.read(prior_dir/'protocol.json'); prior_result=helper.read(prior_dir/'result.json')
    assert prior_result['status']=='local_complete_path_profile_complete'
    assert prior_result['protocol_sha256']==helper.sha(prior_dir/'protocol.json')
    assert all(helper.sha(root/name)==sha for name,sha in prior['sources'].items())
    handoff_path=root/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    assert helper.sha(handoff_path)==prior['handoff_sha256']
    handoff=helper.read(handoff_path); frozen=Path(handoff['frozen_source_directory'])
    modules=['koopman/command_state_v39.py','koopman/prepared_projected_v40.py',
        'koopman/prepared_allocation_v42.py','koopman/command_batch_v42.py','koopman/compiled_projected_v43.py',
        'koopman/control_objective_v44.py','koopman/bounded_mpc_v44.py','koopman/prepared_commands_v45.py',
        'koopman/command_batch_v45.py','koopman/bounded_mpc_v45.py']
    sources=modules+['tests/test_prepared_commands_v45.py','tests/test_bounded_mpc_v45.py',
        'workflows/benchmark_prepared_commands_v45.py','workflows/benchmark_command_state_v39.py']
    protocol=dict(schema='prepared-commands-v45-complete-solver-v1',configurations=handoff['configurations'],
        origin_control=128,horizon=20,model='nonlinear__pooled',reference=[5.5,1.,0.,0.,0.],
        baseline='repeat_last_past_issued_command_no_future_truth',warmups_per_path=1,
        interleaved_repetitions=3,comparison_diagnostic_limit_ms=1000.,strict_repetitions=3,strict_limit_ms=100.,
        perturbation=[.002]*4,slew=[.01]*4,maximum_raw_pwm=.95,weights='unchanged_v44_ObjectiveWeights',
        rtol=1e-12,atol=1e-12,speedup_median_minimum=1.5,per_configuration_speedup_minimum=1.,
        gate='all_equivalent_and_no_configuration_p50_regression_and_median_speedup>=1.5_and_all_24_strict_complete_ms<=100',
        maximum_seconds=180,output_limit_bytes=32*1024**2,processes=1,compute_threads=1,
        formal_test_access=False,new_fits=0,new_server_runs=0,
        initialization='geometry_and_compiler_prepared_before_worker_ready_measured_separately',
        sources={name:helper.sha(root/name) for name in sources},prior_result_sha256=helper.sha(prior_dir/'result.json'),
        handoff_sha256=helper.sha(handoff_path),compiler_directory=str(args.compiler_dir.resolve()))
    if args.output.exists():raise FileExistsError('prepared_command_output_exists')
    args.output.mkdir(parents=True);helper.dump(args.output/'protocol.json',protocol)
    for name in sources:
        target=args.output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write((root/name).read_bytes())
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[key]='1'
    sys.path.insert(0,str(args.compiler_dir.resolve()));sys.path.insert(0,str(frozen))
    started=time.perf_counter();rows=[];error=None;status='failed';runtime={}
    def budget():
        if time.perf_counter()-started>=protocol['maximum_seconds']:raise TimeoutError('prepared_command_assay_budget')
    try:
        import numpy as np
        import torch,numba,llvmlite
        assert numba.__version__=='0.61.2' and llvmlite.__version__=='0.44.0'
        assert args.compiler_dir.resolve() in Path(numba.__file__).resolve().parents
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        runtime=dict(numpy=np.__version__,numba=numba.__version__,llvmlite=llvmlite.__version__)
        from workflows.projected_release_v38 import verify_bundle
        from workflows.identify_sparse_world_v30 import load_fit_cache,from_record
        verify_bundle(frozen,frozen.parent/'inputs',handoff['source_commit'])
        loaded={Path(name).stem:load_file(name[:-3].replace('/','.'),root/name) for name in modules}
        entry=handoff['eligible_models'][protocol['model']];model_path=frozen/entry['path']
        assert helper.sha(model_path)==entry['sha256']
        model=from_record(helper.read(model_path));core=loaded['bounded_mpc_v44'];new=loaded['bounded_mpc_v45']
        domains=core.load_fit_domains(root,model_path)
        episodes=[e for e in load_fit_cache(root) if e.case['excitation']=='prbs']
        assert len(episodes)==8 and all(e.case['role']=='fit' for e in episodes)
        for e in episodes:
            budget(); name=e.case['configuration'];episode_id=e.case['run_id']
            tick=time.perf_counter();predictor=loaded['compiled_projected_v43'].prepare_compiled(model,e.context)
            compile_ms=1000*(time.perf_counter()-tick)
            live=loaded['command_state_v39'].CausalCommandState(name,e.context,episode_id=episode_id,zero_rotor_reset_verified=True)
            for i in range(256):live.record_issued(e.arrays['issued_control'][i],physics_index=i,episode_id=episode_id)
            snapshot=live.snapshot(configuration=name,context=e.context,origin_control=128,episode_id=episode_id)
            diagnostic=replace(core.SearchConfig(),timeout_ms=1000.)
            old=core.BoundedMPC(domains[name],predictor,model_id=entry['sha256'],config=diagnostic)
            tick=time.perf_counter()
            optimized=new.BoundedMPC(domains[name],predictor,model_id=entry['sha256'],config=diagnostic)
            allocation_prepare_ms=1000*(time.perf_counter()-tick)
            def call(solver):
                budget();t=time.perf_counter()
                previous=e.arrays['issued_control'][255].copy()
                baseline=np.repeat(previous[None],20,axis=0)
                result=solver.solve(snapshot,e.states[256].copy(),baseline,previous,protocol['reference'],
                    episode_id=episode_id,reference_id='fixed-z5.5-upright',request_id=episode_id+'-fixed-comparison')
                encoded=json.dumps(result,default=lambda a:a.tolist(),allow_nan=False)
                packet=json.loads(encoded);total_ms=1000*(time.perf_counter()-t)
                return dict(total_ms=total_ms,encoded_bytes=len(encoded.encode('utf8')),packet=packet)
            warm_old,warm_new=call(old),call(optimized)
            maximum=compare_packets(warm_new['packet'],warm_old['packet']);pairs=[]
            for i in range(3):
                if i%2: b,a=call(optimized),call(old)
                else:a,b=call(old),call(optimized)
                maximum=max(maximum,compare_packets(b['packet'],a['packet']))
                pairs.append(dict(reference=a,optimized=b))
            optimized.config=core.SearchConfig()
            strict=[]
            for i in range(3):
                sample=call(optimized)
                sample['passes_budget']=bool(sample['total_ms']<=100 and sample['packet']['status'] in ('selected','baseline'))
                strict.append(sample)
            assert live.physics_index==256
            old_ms=float(np.median([s['reference']['total_ms'] for s in pairs]))
            new_ms=float(np.median([s['optimized']['total_ms'] for s in pairs]))
            rows.append(dict(configuration=name,episode_id=episode_id,role='fit',trace_sha256=e.trace_sha256,
                model_sha256=entry['sha256'],support_id=domains[name].identity,
                prepare_compile_ms=compile_ms,prepare_allocation_ms=allocation_prepare_ms,
                warmups=dict(reference_ms=warm_old['total_ms'],optimized_ms=warm_new['total_ms']),
                paired_diagnostic=pairs,strict_samples=strict,reference_p50_ms=old_ms,optimized_p50_ms=new_ms,
                speedup=old_ms/new_ms,maximum_numeric_difference=maximum))
            helper.dump(args.output/f'{len(rows):02d}-{name}.json',rows[-1])
            print(json.dumps(dict(configuration=name,reference_p50_ms=old_ms,optimized_p50_ms=new_ms,
                speedup=old_ms/new_ms,strict_passes=sum(s['passes_budget'] for s in strict),maximum_difference=maximum)),flush=True)
        budget();verify_bundle(frozen,frozen.parent/'inputs',handoff['source_commit'])
        assert all(helper.sha(root/name)==sha for name,sha in protocol['sources'].items())
        status='local_prepared_command_assay_complete'
    except Exception as exc:error=f'{type(exc).__name__}:{exc}'
    complete=status=='local_prepared_command_assay_complete' and len(rows)==8
    speedup=float(np.median([row['speedup'] for row in rows])) if rows else None
    speed_go=complete and min(row['speedup'] for row in rows)>=1. and speedup>=1.5
    solve_go=complete and all(s['passes_budget'] for row in rows for s in row['strict_samples'])
    result=dict(status=status,error=error,seconds=time.perf_counter()-started,rows=rows,runtime=runtime,
        created_at=datetime.datetime.now().astimezone().isoformat(),protocol_sha256=helper.sha(args.output/'protocol.json'),
        median_speedup=speedup,speed_gate='GO' if speed_go else 'NO_GO',solve_gate='GO' if solve_go else 'NO_GO',
        local_gate='GO' if speed_go and solve_go else 'NO_GO',controller_promoted=False,live_system_gate='NOT_QUALIFIED',
        limitations=['few_timing_samples_no_tail_guarantee','fallback_unchanged_and_unqualified','worker_and_arbiter_missing',
                     'fit_starts_only_no_closed_loop','diagnostic_pairs_use_1000ms_not_admission'])
    helper.dump(args.output/'result.json',result)
    if sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())>protocol['output_limit_bytes']:
        raise RuntimeError('prepared_command_output_budget')
    print(json.dumps(dict(status=status,seconds=result['seconds'],local_gate=result['local_gate'],error=error)),flush=True)
    if not complete:raise SystemExit(1)


if __name__=='__main__':main()

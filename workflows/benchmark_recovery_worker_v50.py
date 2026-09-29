"""Eight fixed fit-only requests through the actual frozen-model worker.

This reconstructs old acknowledged origins, then predicts NEW proposed commands.
It does not issue those commands to a hull or certify a closed control loop.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,
        default=lambda x:x.tolist(),allow_nan=False)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--compiler-dir',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS'):
        os.environ[key]='1'
    handoff_path=root/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    handoff=json.loads(handoff_path.read_text(encoding='utf-8'))
    source_names=['koopman/'+name+'.py' for name in ('recovery_solver_v50','solver_worker_v49',
        'prepared_execution_v49','execution_ledger_v48','bounded_feedback_v47','bounded_feedback_v46',
        'bounded_mpc_v45','bounded_mpc_v44','control_objective_v44','compiled_projected_v43',
        'command_state_v39','prepared_projected_v40','prepared_commands_v45','command_batch_v45',
        'command_batch_v42','prepared_allocation_v42')]
    source_names+=['workflows/benchmark_recovery_worker_v50.py','tests/test_recovery_solver_v50.py']
    protocol=dict(schema='recovery-real-worker-v50-v1',configurations=handoff['configurations'],
        role='fit',excitation='prbs',origin_control=128,horizon=20,prefix_controls=8,
        prefix='repeat_current_v47_proposal_explicitly_not_future_feedback',
        baseline_tail='rate_limited_static_demand_from_current_observation',reference=[5.5,1.,0.,0.,0.],
        model_key='nonlinear__pooled',request_timeout_ms=100.,solver_whole_timeout_ms=100.,
        requests_per_configuration=1,ready_timeout_s=60.,maximum_seconds=240.,output_limit_bytes=32*1024**2,
        runtime='one_parent_one_worker_sequential_configurations_one_compute_thread',
        comparison_rtol=1e-12,comparison_atol=1e-12,
        gate='all_8_complete_feasible_bound_replies_received_and_decoded_within100ms',
        no_automatic_retries=True,new_fits=0,new_server_runs=0,formal_test_access=False,
        handoff_sha256=sha(handoff_path),sources={name:sha(root/name) for name in source_names})
    if args.output.exists():raise FileExistsError('recovery_output_exists')
    args.output.mkdir(parents=True);dump(args.output/'protocol.json',protocol)
    for name in source_names:
        p=args.output/'source'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((root/name).read_bytes())
    started=time.perf_counter();rows=[];error=None;active=None;complete=False
    def budget():
        if time.perf_counter()-started>=protocol['maximum_seconds']:raise TimeoutError('recovery_assay_budget')
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        from workflows.identify_sparse_world_v30 import load_fit_cache
        from koopman.bounded_mpc_v44 import load_fit_domains
        from koopman.bounded_feedback_v47 import TrackingFeedback
        from koopman.prepared_execution_v49 import PreparedCausalCommandState
        from koopman.execution_ledger_v48 import ExecutionCapture
        from koopman.recovery_solver_v50 import PlanningRequest,FrozenWorkerSpec,frozen_model_factory,request_binding
        from koopman.solver_worker_v49 import IsolatedSolverWorker,WorkerLimits
        frozen=Path(handoff['frozen_source_directory']);entry=handoff['eligible_models'][protocol['model_key']]
        domains=load_fit_domains(root,frozen/entry['path'])
        episodes=[e for e in load_fit_cache(root) if e.case['excitation']=='prbs']
        assert len(episodes)==8 and all(e.case['role']=='fit' for e in episodes)
        for e in episodes:
            budget();name=e.case['configuration'];domain=domains[name];episode=e.case['run_id']
            row=dict(configuration=name,episode_id=episode,trace_sha256=e.trace_sha256,
                     model_sha256=entry['sha256'],support_id=domain.identity,passes=False)
            live=PreparedCausalCommandState(name,e.context,episode_id=episode,zero_rotor_reset_verified=True)
            for i in range(256):live.record_issued(e.arrays['issued_control'][i],physics_index=i,episode_id=episode)
            origin=live.snapshot(configuration=name,context=e.context,origin_control=128,episode_id=episode)
            np.testing.assert_allclose(origin._actuator.current(),e.arrays['causal_rotor_speed'][256],rtol=1e-12,atol=1e-12)
            assert origin._actuator.elapsed_time==e.arrays['actuator_time_s'][256]
            x=e.states[256].copy();old=e.arrays['issued_control'][255].copy();ref=np.array(protocol['reference'])
            policy=TrackingFeedback(domain,e.context)
            fallback=policy.decide(x,ref,previous=old)
            row['fallback']=dict(status=fallback['status'],reason=fallback['reason'],elapsed_ms=fallback['elapsed_ms'])
            if fallback['status']=='ready':
                prefix=np.repeat(fallback['command'][None],8,axis=0)
                digest=hashlib.sha256(e.arrays['issued_control'][:256].astype(np.float32).tobytes()).hexdigest()
                # Labels deliberately identify an offline reconstructed capture.
                cap=ExecutionCapture('offline-fit-'+episode,episode,'verified-fit-zero-reset',256,digest,0,
                    'z5.5-upright',0,name,domain.context_key,entry['sha256'],domain.identity,time.perf_counter(),
                    x,ref,old,origin)
                request=PlanningRequest('fixed-v50-'+name,cap,prefix)
                spec=FrozenWorkerSpec(str(root),name,e.context,protocol['model_key'],entry['sha256'],
                    protocol['handoff_sha256'],domain.identity,str(args.compiler_dir.resolve()))
                active=IsolatedSolverWorker(frozen_model_factory,spec,limits=WorkerLimits())
                prepare=time.perf_counter();active.start();ready=None
                while ready is None:
                    budget();ready=active.poll()
                    if ready is None:time.sleep(.001)
                row['prepare_seconds']=time.perf_counter()-prepare;row['ready_event']=ready
                if ready['status']=='ready':
                    begin=time.perf_counter();submitted=active.submit(request.request_id,request)
                    row['submit']=submitted;reply=None;poll_ms=[]
                    if submitted['status']=='accepted':
                        while reply is None:
                            budget();tick=time.perf_counter();reply=active.poll();poll_ms.append(1000*(time.perf_counter()-tick))
                            if reply is None:time.sleep(.0005)
                        row.update(reply=reply,total_request_ms=1000*(time.perf_counter()-begin),
                                   maximum_parent_poll_ms=max(poll_ms))
                        if reply['status']=='result':
                            packet=reply['payload']
                            assert packet['binding']==request_binding(request)
                            assert packet['runtime_eligible'] is False and not packet['actual_history_advanced']
                            if packet['status'] in ('selected','baseline'):
                                np.testing.assert_array_equal(packet['commands'][:8],prefix)
                                assert packet['predictions'].shape==(40,11)
                                assert domain.check_states(packet['predictions']) is None
                                row['passes']=row['total_request_ms']<=100 and reply['elapsed_ms']<=100
                row['closed']=active.close();active=None
                assert row['closed']==dict(process_stopped=True,io_threads_stopped=True)
            assert live.physics_index==256
            rows.append(row);dump(args.output/f'{len(rows):02d}-{name}.json',row)
            print(json.dumps(dict(configuration=name,passes=row['passes'],prepare_s=row.get('prepare_seconds'),
                request_ms=row.get('total_request_ms'),reply_status=row.get('reply',{}).get('status'),
                reason=row.get('reply',{}).get('payload',{}).get('reason',row.get('reply',{}).get('reason')))),flush=True)
        budget();complete=len(rows)==8
        assert all(sha(root/name)==digest for name,digest in protocol['sources'].items())
        assert sha(handoff_path)==protocol['handoff_sha256']
    except Exception as exc:error=type(exc).__name__+':'+str(exc)
    finally:
        if active is not None:
            closed=active.close()
            if not all(closed.values()):error=str(error)+';worker_cleanup_incomplete'
    result=dict(status='complete' if complete and error is None else 'failed',error=error,
        seconds=time.perf_counter()-started,created_at=datetime.datetime.now().astimezone().isoformat(),
        protocol_sha256=sha(args.output/'protocol.json'),rows=rows,passed=sum(r['passes'] for r in rows),
        total=8,local_gate='GO' if complete and error is None and all(r['passes'] for r in rows) else 'NO_GO',
        live_system_gate='NOT_QUALIFIED',controller_promoted=False,
        limitations=['one_sample_each_no_tail_guarantee','historical_fit_origins_not_cold_start',
            'prefix_not_executed_on_hull','no_runtime_arbiter_or_actual_ack','new_baseline_not_v45_equivalence'])
    dump(args.output/'result.json',result)
    if sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())>protocol['output_limit_bytes']:
        raise RuntimeError('recovery_output_limit')
    print(json.dumps({k:result[k] for k in ('status','local_gate','passed','seconds','error')}),flush=True)
    if error is not None:raise SystemExit(1)


if __name__=='__main__':main()

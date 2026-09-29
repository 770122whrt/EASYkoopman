"""Bounded offline replay of acknowledged fit commands, not new execution."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
    return m


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    helper=load('ledger_assay_helper',root/'workflows/benchmark_command_state_v39.py')
    old=root/'docs/evidence/phase9/fallback-v47-pilot-20260920'
    prior=helper.read(old/'protocol.json');prior_result=helper.read(old/'result.json')
    assert prior_result['local_gate']=='GO' and prior_result['protocol_sha256']==helper.sha(old/'protocol.json')
    assert all(helper.sha(root/n)==h for n,h in prior['sources'].items())
    handoff_path=root/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    assert helper.sha(handoff_path)==prior['handoff_sha256']
    handoff=helper.read(handoff_path);frozen=Path(handoff['frozen_source_directory'])
    modules=[n for n in prior['sources'] if n.startswith('koopman/')]+['koopman/execution_ledger_v48.py']
    sources=modules+['tests/test_execution_ledger_v48.py','workflows/replay_execution_ledger_v48.py']
    protocol=dict(schema='execution-ledger-v48-existing-fit-replay-v1',configurations=handoff['configurations'],
        role='fit',excitation='prbs',start_control=0,control_intervals=32,repetitions=1,
        model_for_support='nonlinear__pooled',reference=[5.5,1.,0.,0.,0.],maximum_seconds=60,
        output_limit_bytes=16*1024**2,processes=1,compute_threads=1,rtol=1e-12,atol=1e-12,
        gate='all_8x32_historical_intervals_admitted_and_original_causal_speed_clock_equal',
        timing_scope='capture_reserve_dispatch_two_offline_acks_and_packet_encoding_no_feedback_no_IPC',
        reset_source='verified_fit_cache_zero_origin_previously_checked_against_original_reset_trace',
        input_source='recorded_actual_commands_not_new_v47_feedback_commands',
        new_simulation_intervals=0,new_model_fits=0,formal_test_access=False,controller_promoted=False,
        handoff_sha256=helper.sha(handoff_path),prior_result_sha256=helper.sha(old/'result.json'),
        sources={n:helper.sha(root/n) for n in sources})
    if args.output.exists():raise FileExistsError('replay_output_exists')
    args.output.mkdir(parents=True);helper.dump(args.output/'protocol.json',protocol)
    for n in sources:
        target=args.output/'source'/n;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write((root/n).read_bytes())
    for n in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):os.environ[n]='1'
    sys.path.insert(0,str(frozen));started=time.perf_counter();rows=[];error=None;status='failed'
    def budget():
        if time.perf_counter()-started>=protocol['maximum_seconds']:raise TimeoutError('ledger_replay_budget')
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        from workflows.projected_release_v38 import verify_bundle
        from workflows.identify_sparse_world_v30 import load_fit_cache
        verify_bundle(frozen,frozen.parent/'inputs',handoff['source_commit'])
        loaded={Path(n).stem:load(n[:-3].replace('/','.'),root/n) for n in modules}
        core=loaded['execution_ledger_v48'];feedback=loaded['bounded_feedback_v47']
        entry=handoff['eligible_models']['nonlinear__pooled']
        assert helper.sha(frozen/entry['path'])==entry['sha256']
        domains=loaded['bounded_mpc_v44'].load_fit_domains(root,frozen/entry['path'])
        episodes=[e for e in load_fit_cache(root) if e.case['excitation']=='prbs']
        assert len(episodes)==8 and all(e.case['role']=='fit' for e in episodes)
        for e in episodes:
            budget();name=e.case['configuration'];eid=e.case['run_id'];rid=e.trace_sha256
            ref=np.asarray(protocol['reference']);domain=domains[name];records=[];failure=None
            tick=time.perf_counter()
            policy=feedback.TrackingFeedback(domain,e.context)
            seed=policy.prepare_startup(e.states[0],ref)
            assert seed['status']=='prepared'
            reset=core.ResetObservation(eid,rid,0,e.states[0],e.arrays['causal_rotor_speed'][0])
            ledger=core.ExecutionLedger(domain,e.context,reset,reference=ref,reference_id='hold-5.5',startup_command=seed['command'])
            prepare_ms=1000*(time.perf_counter()-tick)
            for i in range(protocol['control_intervals']):
                budget()
                try:
                    tick=time.perf_counter()
                    capture=ledger.capture(core.BoundaryObservation(eid,rid,2*i,e.states[2*i]),ref,reference_id='hold-5.5')
                    token=ledger.reserve(capture,e.arrays['issued_control'][2*i],source='fallback',startup=i==0)
                    packet=ledger.dispatch(token)
                    acknowledgments=[ledger.acknowledge(token,e.arrays['issued_control'][2*i+j],
                        physics_index=2*i+j,episode_id=eid,reset_id=rid) for j in range(2)]
                    encoded=json.dumps(dict(packet=packet,acknowledgments=acknowledgments),default=lambda a:a.tolist(),allow_nan=False)
                    json.loads(encoded);total_ms=1000*(time.perf_counter()-tick)
                    following=ledger.capture(core.BoundaryObservation(eid,rid,2*i+2,e.states[2*i+2]),ref,reference_id='hold-5.5')
                    expected=e.arrays['causal_rotor_speed'][2*i+2];actual=following.origin._actuator.current()
                    np.testing.assert_allclose(actual,expected,rtol=1e-12,atol=1e-12)
                    np.testing.assert_allclose(following.origin._actuator.elapsed_time,e.arrays['actuator_time_s'][2*i+2],rtol=1e-12,atol=1e-12)
                    np.testing.assert_array_equal(following.previous,e.arrays['issued_control'][2*i+1])
                    assert ledger.physics_index==2*i+2 and ledger.startup_consumed and not ledger.pending
                    records.append(dict(control_index=i,total_ms=total_ms,startup_exception=packet['startup_exception'],
                        maximum_rotor_difference=float(np.max(np.abs(actual-expected))),history_digest=following.history_digest))
                except (ValueError,AssertionError) as exc:
                    failure=dict(control_index=i,error=f'{type(exc).__name__}:{exc}',confirmed_physics_index=ledger.physics_index)
                    break
            row=dict(configuration=name,episode_id=eid,role='fit',trace_sha256=e.trace_sha256,prepare_ms=prepare_ms,
                completed_intervals=len(records),failure=failure,intervals=records,actual_new_execution=False)
            rows.append(row);helper.dump(args.output/f'{name}.json',row)
            print(json.dumps({k:row[k] for k in ('configuration','completed_intervals','failure')}),flush=True)
        budget();verify_bundle(frozen,frozen.parent/'inputs',handoff['source_commit'])
        assert all(helper.sha(root/n)==h for n,h in protocol['sources'].items())
        status='offline_ledger_replay_complete'
    except Exception as exc:error=f'{type(exc).__name__}:{exc}'
    complete=status=='offline_ledger_replay_complete' and len(rows)==8
    go=complete and all(r['completed_intervals']==32 and r['failure'] is None for r in rows)
    result=dict(status=status,error=error,local_gate='GO' if go else 'NO_GO',seconds=time.perf_counter()-started,
        protocol_sha256=helper.sha(args.output/'protocol.json'),rows=rows,
        replayed_control_intervals=sum(r['completed_intervals'] for r in rows),
        actual_new_execution=False,new_model_fits=0,formal_test_access=False,controller_promoted=False,
        limitations=['historical_fit_commands_not_closed_loop','startup_prefix_only','offline_ack_not_adapter_proof',
                     'timing_excludes_feedback_and_IPC','no_tail_latency_or_realtime_certification'])
    helper.dump(args.output/'result.json',result)
    if sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())>protocol['output_limit_bytes']:
        raise RuntimeError('ledger_replay_output_limit')
    print(json.dumps(dict(status=status,local_gate=result['local_gate'],seconds=result['seconds'],error=error)),flush=True)
    if not complete:raise SystemExit(1)


if __name__=='__main__':main()

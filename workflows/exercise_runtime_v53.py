"""v53 exact-map cache pilot: real worker plus fixed states and SYNTHETIC receipts.

No plant is advanced. All safety/ack inputs are fixtures, and no observation is
taken from a forecast. This checks the integrated computation/history path, not
control performance, cold-start survival or end-to-end simulator real time.
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
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,
        default=lambda a:a.tolist(),allow_nan=False)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--compiler-dir',required=True,type=Path)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[key]='1'
    handoff_path=root/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    handoff=json.loads(handoff_path.read_text(encoding='utf-8'))
    previous_path=root/'docs/evidence/phase9/recovery-v51-worker-20260920/protocol.json'
    previous=json.loads(previous_path.read_text(encoding='utf-8'))
    assert all(sha(root/name)==digest for name,digest in previous['sources'].items())
    sources=list(previous['sources'])+['koopman/plan_arbiter_v52.py','koopman/runtime_coordinator_v52.py',
        'tests/test_plan_arbiter_v52.py','tests/test_runtime_coordinator_v52.py','workflows/exercise_runtime_v52.py',
        'koopman/cached_checks_v53.py','tests/test_cached_checks_v53.py','workflows/exercise_runtime_v53.py']
    protocol=dict(schema='runtime-coordinator-v53-two-config-pilot-v1',configurations=['base','uuv6_angled'],
        source_states='verified_fit_prbs_initial_state_held_constant',receipt_source='synthetic_fixture_not_physics',
        safety_source='synthetic_clearance4m_no_contact_xy0_not_sensor',controls_per_configuration=24,
        observation_feedback='fixed_state_never_forecast_output',model_key='nonlinear__pooled',horizon=20,
        prefix_controls=8,worker_timeout_ms=100.,wall_pacing_hz=60,control_compute_limit_ms=1000/60,
        timing='external_boundary_observation_step_two_synthetic_acks_excludes_plant_and_log_encoding',
        maximum_seconds=120.,output_limit_bytes=32*1024**2,processes='parent_plus_one_sequential_worker',
        new_fits=0,new_isaac_steps=0,formal_test_access=False,training_eligible=False,
        gate='all2_times24_completed_external_compute_within16.67ms_and_source_causal_history_equal',
        activation_count_separate_not_a_control_benefit_gate=True,no_retries=True,
        rtol=1e-12,atol=1e-12,handoff_sha256=sha(handoff_path),previous_protocol_sha256=sha(previous_path),
        sources={name:sha(root/name) for name in sources})
    if args.output.exists():raise FileExistsError('runtime_exercise_output_exists')
    args.output.mkdir(parents=True);dump(args.output/'protocol.json',protocol)
    for name in sources:
        p=args.output/'source'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((root/name).read_bytes())
    started=time.perf_counter();rows=[];error=None;worker=None
    def budget():
        if time.perf_counter()-started>=protocol['maximum_seconds']:raise TimeoutError('runtime_exercise_budget')
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        from workflows.identify_sparse_world_v30 import load_fit_cache
        from koopman.bounded_mpc_v44 import load_fit_domains
        from koopman.cached_checks_v53 import CachedTrackingFeedback as TrackingFeedback
        from koopman.execution_ledger_v48 import ResetObservation,BoundaryObservation
        from koopman.cached_checks_v53 import CachedExecutionLedger as PreparedExecutionLedger
        from koopman.command_state_v39 import CausalCommandState
        from koopman.solver_worker_v49 import IsolatedSolverWorker
        from koopman.recovery_solver_v50 import FrozenWorkerSpec
        from koopman.cached_checks_v53 import frozen_model_factory
        from koopman.runtime_coordinator_v52 import RuntimeCoordinator,SafetyObservation
        frozen=Path(handoff['frozen_source_directory']);entry=handoff['eligible_models'][protocol['model_key']]
        domains=load_fit_domains(root,frozen/entry['path'])
        episodes=[e for e in load_fit_cache(root) if e.case['excitation']=='prbs' and e.case['configuration'] in protocol['configurations']]
        assert len(episodes)==2 and all(e.case['role']=='fit' for e in episodes)
        for e in episodes:
            budget();name=e.case['configuration'];domain=domains[name];episode='synthetic-v53-'+name;reset='fixture-zero'
            x=e.states[0].copy();ref=np.array([5.5,1.,0,0,0]);n=len(e.arrays['causal_rotor_speed'][0])
            assert np.max(np.abs(e.arrays['causal_rotor_speed'][0]))==0
            policy=TrackingFeedback(domain,e.context);seed=policy.prepare_startup(x,ref)
            assert seed['status']=='prepared'
            ledger=PreparedExecutionLedger(domain,e.context,ResetObservation(episode,reset,0,x,np.zeros(n)),
                reference=ref,reference_id='z5.5-upright',startup_command=seed['command'],steady=policy.steady)
            spec=FrozenWorkerSpec(str(root),name,e.context,protocol['model_key'],entry['sha256'],
                protocol['handoff_sha256'],domain.identity,str(args.compiler_dir.resolve()))
            worker=IsolatedSolverWorker(frozen_model_factory,spec);t=time.perf_counter();worker.start();ready=None
            while ready is None:
                budget();ready=worker.poll()
                if ready is None:time.sleep(.001)
            prepare=time.perf_counter()-t
            row=dict(configuration=name,evidence_level='synthetic_execution_receipt_real_model_worker',
                fit_source_trace_sha256=e.trace_sha256,support_id=domain.identity,ready=ready,prepare_seconds=prepare,
                steps=[],passes=False,mpc_activations=0,stop_reason=None)
            if ready['status']=='ready':
                runtime=RuntimeCoordinator(ledger,policy,worker);epoch=time.perf_counter();commands=[]
                row['worker_events']=[];row['arbitration']=[]
                original_poll=worker.poll;original_choose=runtime.arbiter.choose
                def logged_poll():
                    event=original_poll()
                    if event is not None:
                        p=event.get('payload',{})
                        row['worker_events'].append(dict(control=ledger.physics_index//2,status=event['status'],
                            reason=event.get('reason'),elapsed_ms=event.get('elapsed_ms'),plan_status=p.get('status'),
                            plan_reason=p.get('reason'),solver_ms=p.get('elapsed_ms')))
                    return event
                def logged_choose(capture):
                    answer=original_choose(capture)
                    row['arbitration'].append(dict(control=ledger.physics_index//2,status=answer['status'],
                        source=answer.get('source'),reason=answer.get('reason')))
                    return answer
                worker.poll=logged_poll;runtime.arbiter.choose=logged_choose
                def safety(index):return SafetyObservation(episode,reset,index,np.zeros(2),4.,False)
                for control in range(24):
                    budget();wait=epoch+control/60-time.perf_counter()
                    if wait>0:time.sleep(wait)
                    tick=time.perf_counter();index=ledger.physics_index
                    decision=runtime.step(BoundaryObservation(episode,reset,index,x),ref,
                        reference_id='z5.5-upright',safety=safety(index))
                    acks=[]
                    if decision['status']=='dispatch':
                        packet=decision['packet']
                        for substep in range(2):
                            ack=runtime.acknowledge(packet['ticket'],packet['command'],physics_index=index+substep,
                                episode_id=episode,reset_id=reset,safety=safety(index+substep+1))
                            acks.append(ack)
                            if ack.get('actual_history_advanced'):commands.append(packet['command'].copy())
                            if ack['status']!='acknowledged':break
                    elapsed=1000*(time.perf_counter()-tick)
                    sample=dict(control=control,external_compute_ms=elapsed,start_lag_ms=1000*(tick-(epoch+control/60)),
                        decision=decision,acknowledgments=acks,confirmed_physics_index=ledger.physics_index)
                    row['steps'].append(sample)
                    if decision['status']!='dispatch':row['stop_reason']=decision['reason'];break
                    if len(acks)!=2 or acks[-1]['status']!='acknowledged':row['stop_reason']=acks[-1]['reason'];break
                    if elapsed>protocol['control_compute_limit_ms']:
                        row['stop_reason']='external_complete_compute_timeout';ledger.abort(row['stop_reason']);break
                row['stats']=runtime.stats.copy();row['mpc_activations']=runtime.stats['mpc_activations']
                # Independent original command allocator and actuator recurrence;
                # this replays fixture inputs only, not a boat trajectory.
                original=CausalCommandState(name,e.context,episode_id=episode,zero_rotor_reset_verified=True)
                for i,u in enumerate(commands):original.record_issued(u,physics_index=i,episode_id=episode)
                np.testing.assert_allclose(ledger._live._actuator.current(),original._actuator.current(),rtol=1e-12,atol=1e-12)
                assert ledger._live._actuator.elapsed_time==original._actuator.elapsed_time
                row['maximum_rotor_difference']=float(np.max(np.abs(ledger._live._actuator.current()-original._actuator.current())))
                row['maximum_compute_ms']=max(s['external_compute_ms'] for s in row['steps'])
                row['confirmed_physics_ticks']=len(commands)
                row['passes']=row['stop_reason'] is None and len(row['steps'])==24 and ledger.physics_index==48
            row['closed']=worker.close();worker=None
            assert row['closed']==dict(process_stopped=True,io_threads_stopped=True)
            rows.append(row);dump(args.output/f'{len(rows):02d}-{name}.json',row)
            print(json.dumps(dict(configuration=name,passes=row['passes'],controls=len(row['steps']),
                maximum_compute_ms=row.get('maximum_compute_ms'),activations=row['mpc_activations'],stop_reason=row['stop_reason'])),flush=True)
        budget();assert all(sha(root/name)==digest for name,digest in protocol['sources'].items())
        assert sha(handoff_path)==protocol['handoff_sha256']
    except Exception as exc:error=type(exc).__name__+':'+str(exc)
    finally:
        if worker is not None:
            closed=worker.close()
            if not all(closed.values()):error=str(error)+';worker_cleanup_incomplete'
    complete=error is None and len(rows)==2
    result=dict(status='complete' if complete else 'failed',error=error,seconds=time.perf_counter()-started,
        created_at=datetime.datetime.now().astimezone().isoformat(),protocol_sha256=sha(args.output/'protocol.json'),
        rows=rows,configurations_passed=sum(r['passes'] for r in rows),configurations_total=2,
        local_compute_gate='GO' if complete and all(r['passes'] for r in rows) else 'NO_GO',
        live_system_gate='NOT_QUALIFIED',controller_promoted=False,new_isaac_steps=0,
        limitations=['fixed_state_fixture_not_closed_loop','synthetic_safety_and_ack_not_real_adapter',
            'few_samples_no_latency_tail_guarantee','simulator_execution_time_excluded','activation_not_control_benefit'])
    dump(args.output/'result.json',result)
    if sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())>protocol['output_limit_bytes']:
        raise RuntimeError('runtime_exercise_output_budget')
    print(json.dumps({k:result[k] for k in ('status','local_compute_gate','configurations_passed','seconds','error')}),flush=True)
    if error is not None:raise SystemExit(1)


if __name__=='__main__':main()

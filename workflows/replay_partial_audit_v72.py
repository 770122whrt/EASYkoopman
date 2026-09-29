"""v67 30Hz explicit feedback-control arm can have zero MPC activations.

Record arbitration in memory, then replay it against acknowledged history.

Serialization is outside control cycles. The offline replay shares admission
mathematics, but reconstructs actuator history solely from actual commands.
It does not independently refit a model or rerun the optimizer.
"""
import hashlib
import json
import time
import numpy as np

from koopman.rate30_v67 import Rate30Arbiter as PlanArbiter, FEEDBACK_CONFIG
from koopman.recovery_solver_v50 import PlanningRequest, request_binding
from koopman.diagnostics_v23 import json_safe
from workflows.validate_control_trace_v23 import compare_values


def replay_partial_audit(report,reset,domain,context,*,reference,reference_id,physical_steps,allow_diagnostic=False, require_mpc=False):
    from koopman.rate30_v67 import ExecutionLedger as CachedExecutionLedger
    from koopman.execution_ledger_v48 import BoundaryObservation
    ledger=CachedExecutionLedger(domain,context,reset,reference=reference,reference_id=reference_id,
        startup_command=report['startup'],allow_diagnostic=allow_diagnostic, feedback_config=FEEDBACK_CONFIG)
    # Offline reconstruction only. Recompute the initial digest rather than
    # trusting any claimed actuator-history digest in the trace.
    ledger._execution_id=report['execution_id']
    ledger._digest=hashlib.sha256(json.dumps(dict(execution_id=ledger._execution_id,
        episode=reset.episode_id,reset=reset.reset_id,binding=ledger._binding),sort_keys=True).encode()).hexdigest()
    if not 0<physical_steps<=4*len(report['intervals']) or (physical_steps+3)//4!=len(report['intervals']):raise ValueError('partial_audit_count')
    times=[];position=0
    def clock():
        nonlocal position
        if position>=len(times):raise ValueError('audit_clock_exhausted')
        value=times[position];position+=1;return value
    arbiter=PlanArbiter(ledger,clock=clock)
    events=report['audit'];cursor=0;activations=0;digests=[];last_time=-float('inf')
    if not isinstance(events,list) or not 1<=len(events)<=512:raise ValueError('audit_events')
    for i,interval in enumerate(report['intervals']):
        if interval['physics_index']!=4*i:raise ValueError('audit_interval_sequence')
        cap=ledger.capture(BoundaryObservation(reset.episode_id,reset.reset_id,4*i,interval['state']),
                           reference,reference_id=reference_id)
        choice=None;registers=[]
        while cursor<len(events) and events[cursor]['physics_index']==4*i:
            e=events[cursor];cursor+=1
            sequence=[e['started'],*e['clock_reads'],e['finished']]
            if (e.get('exception') is not None or not np.isfinite(sequence).all()
                    or sequence[0]<last_time or np.any(np.diff(sequence)<0)):
                raise ValueError('audit_clock_or_exception')
            last_time=sequence[-1];times=e['clock_reads'];position=0
            method=e['method']
            if method=='register':
                r=e['request'];req=PlanningRequest(r['binding']['request_id'],cap,np.asarray(r['prefix'],dtype=np.float32))
                compare_values(json_safe(request_binding(req)),r['binding'],atol=0,path='audit_binding')
                for key,value in dict(state=cap.state,reference=cap.reference,previous=cap.previous,
                    rotor=cap.origin._actuator.current(),actuator_time=cap.origin._actuator.elapsed_time).items():
                    compare_values(json_safe(value),r[key],atol=1e-12,path='audit_'+key)
                result=arbiter.register(req,e['receipt'],prefix_source=e['prefix_source']);registers.append(req)
            elif method=='ingest':result=arbiter.ingest(e['event'])
            elif method=='invalidate':result=arbiter.invalidate(e['reason'])
            elif method in ('choose','following_prefix'):
                compare_values(dict(physics_index=cap.physics_index,state=json_safe(cap.state),
                    reference=json_safe(cap.reference),history_digest=cap.history_digest),e['capture'],atol=1e-12,path='audit_capture')
                result=getattr(arbiter,method)(cap)
                if method=='choose':
                    if choice is not None:raise ValueError('audit_duplicate_choice')
                    choice=result
                    activations+=int(bool(result.get('activated')))
            else:raise ValueError('audit_unknown_event')
            if position!=len(times):raise ValueError('audit_unused_clock')
            compare_values(json_safe(result),e.get('result'),atol=1e-7,path='audit_result')
        if choice is None:raise ValueError('audit_missing_choice')
        d=interval['decision'];p=d['packet'];command=np.asarray(p['command'],dtype=np.float32)
        if (d['status']!='dispatch' or p['physics_index']!=4*i
                or p['execution_id']!=ledger._execution_id or p['episode_id']!=reset.episode_id
                or p['reset_id']!=reset.reset_id or p['actual_execution_confirmed'] is not False
                or p['startup_exception'] is not (i==0)):
            raise ValueError('audit_packet_binding')
        if choice['status']=='proposal':
            compare_values(json_safe(command),json_safe(choice['command']),atol=1e-7,path='audit_dispatch_command')
            if p['source']!=choice['source']:raise ValueError('audit_dispatch_source')
        elif choice['status']=='fallback':
            if p['source']!=('committed_prefix' if registers else 'fallback'):raise ValueError('audit_fallback_source')
            if registers:
                compare_values(json_safe(command),json_safe(registers[-1].prefix[0]),atol=1e-7,path='audit_prefix_command')
        else:raise ValueError('audit_choice')
        token=ledger.reserve(cap,command,source=p['source'],startup=i==0);ledger.dispatch(token)
        for j in range(min(4,physical_steps-4*i)):
            receipt=ledger.acknowledge(token,command,physics_index=4*i+j,episode_id=reset.episode_id,reset_id=reset.reset_id)
            digests.append(receipt['history_digest'])
        if ledger._digest!=report['receipts'][i]:raise ValueError('audit_actual_receipt_digest')
    reasons=('runtime_ack_failed:runtime_safety_binding','execution_bridge:actual_state_outside_support',
        'execution_bridge_interval:execution_bridge:actual_state_outside_support',
        'episode:execution_bridge:actual_state_outside_support')
    terminal=events[cursor:]
    if len(terminal)!=len(reasons):raise ValueError('partial_stop_event_count')
    for e,reason in zip(terminal,reasons):
        if (e['method']!='invalidate' or e['physics_index']!=physical_steps or e.get('reason')!=reason
                or e.get('exception') is not None or e['clock_reads'] or e.get('result') is not None
                or e['started']!=physical_steps/120 or e['finished']!=physical_steps/120):
            raise ValueError('partial_stop_event_binding')
        arbiter.invalidate(reason)
        cursor+=1
    if cursor!=len(events) or activations!=report['activations'] or (require_mpc and activations<1):
        raise ValueError('audit_activation_or_unconsumed_events')
    return dict(activations=activations,confirmed_controls=(physical_steps-1)//4,actual_physics_steps=physical_steps,complete_episode=False,
        recomputed_final_digest=ledger._digest,physics_history_digests=digests,
        optimizer_recomputed=False,admission_math_reused=True)

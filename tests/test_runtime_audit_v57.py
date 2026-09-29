"""Synthetic scheduling replay; no simulator or real-time qualification."""
import copy
import pytest

from test_runtime_coordinator_v52 import setup, step, ack


def recorded_run():
    from workflows.runtime_audit_v57 import RecordingArbiter
    run,clock,worker=setup()
    run.arbiter=RecordingArbiter(run.ledger,clock=clock)
    intervals=[];receipts=[]
    reset=run.ledger._reset;domain=run.ledger._domain;context=run.ledger._context
    for i in range(10):
        clock.now=i/60
        d=step(run);assert d['status']=='dispatch',d
        intervals.append(dict(physics_index=2*i,decision=d,state=reset.state.copy()))
        ack(run,d)
        receipts.append(run.ledger._digest)
        if i==1:worker.complete()
    report=dict(audit=run.arbiter.export(),intervals=intervals,receipts=receipts,
        execution_id=run.ledger._execution_id,startup=run.ledger._startup,
        activations=run.stats['mpc_activations'])
    return report,reset,domain,context


def test_replay_recovers_real_receipts_and_one_activation_without_running_solver():
    from workflows.runtime_audit_v57 import replay_audit
    report,reset,domain,context=recorded_run()
    result=replay_audit(report,reset,domain,context,reference=reset.state[:5],reference_id='ref',allow_diagnostic=True)
    assert result['activations']==1 and result['confirmed_controls']==10
    assert result['recomputed_final_digest']==report['receipts'][-1]


@pytest.mark.parametrize('bad',['history','state','prefix','worker_binding','late_reply','command','receipt','activation','missing_event'])
def test_replay_rejects_forged_or_inconsistent_activation_evidence(bad):
    from workflows.runtime_audit_v57 import replay_audit
    report,reset,domain,context=recorded_run();r=copy.deepcopy(report)
    register=next(e for e in r['audit'] if e['method']=='register')
    ingest=next(e for e in r['audit'] if e['method']=='ingest')
    if bad=='history':register['request']['binding']['history_digest']='f'*64
    if bad=='state':register['request']['state'][0]+=.1
    if bad=='prefix':register['request']['prefix'][0][0]+=.001
    if bad=='worker_binding':ingest['event']['generation']='other'
    if bad=='late_reply':ingest['event']['elapsed_ms']=101.
    if bad=='command':r['intervals'][9]['decision']['packet']['command'][0]+=.001
    if bad=='receipt':r['receipts'][-1]='e'*64
    if bad=='activation':r['activations']=2
    if bad=='missing_event':r['audit'].remove(ingest)
    with pytest.raises((ValueError,AssertionError),match='audit|trace_pair'):
        replay_audit(r,reset,domain,context,reference=reset.state[:5],reference_id='ref',allow_diagnostic=True)


def test_diagnostic_domain_cannot_enter_production_replay():
    from workflows.runtime_audit_v57 import replay_audit
    report,reset,domain,context=recorded_run()
    with pytest.raises(ValueError):
        replay_audit(report,reset,domain,context,reference=reset.state[:5],reference_id='ref')

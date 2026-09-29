"""A rejected replacement cannot erase a still independently valid active plan."""
from copy import deepcopy
import numpy as np
import pytest

import test_plan_arbiter_v52 as original_tests
from test_plan_arbiter_v52 import *
from koopman.recovery_solver_v50 import PlanningRequest


@pytest.fixture(autouse=True)
def use_continuous_arbiter(monkeypatch):
    from koopman.plan_continuity_v54 import PlanArbiter,RuntimeCoordinator
    import koopman.plan_arbiter_v52 as old
    import koopman.runtime_coordinator_v52 as old_runtime
    monkeypatch.setattr(old,'PlanArbiter',PlanArbiter)
    monkeypatch.setattr(old_runtime,'RuntimeCoordinator',RuntimeCoordinator)


def replacement():
    ledger,u,ref,clock,arb,_,event=original_tests.fixture()
    arb.ingest(event);advance(ledger,u);clock.now=.133
    chosen=arb.choose(capture(ledger));execute(ledger,chosen['command']);clock.now=.15
    cap=capture(ledger);prefix=arb.following_prefix(cap)
    req=PlanningRequest('replacement',cap,prefix)
    receipt=dict(status='accepted',generation='transport-A',key='key-B',request_id='replacement')
    arb.register(req,receipt,prefix_source='mpc')
    late=dict(status='result',generation='transport-A',key='key-B',request_id='replacement',elapsed_ms=99.,payload={})
    clock.now=.251
    assert arb.ingest(late)['status']=='rejected'
    return ledger,ref,clock,arb,chosen['command']


def test_rejected_replacement_keeps_active_plan_after_full_history_state_validation():
    ledger,_,_,arb,_=replacement()
    assert not arb.pending and arb.active
    got=arb.choose(capture(ledger))
    assert got['source']=='mpc' and got['plan_index']==9
    assert ledger.physics_index==20 and got['actual_history_advanced'] is False


@pytest.mark.parametrize('changed',['history','reference','worker','age','state'])
def test_retained_plan_is_never_exempt_from_current_admission(changed):
    ledger,ref,clock,arb,u=replacement();x=initial()
    if changed=='history':
        altered=u.copy();altered[0]+=.001;execute(ledger,altered)
    if changed=='reference':ref[0]+=.01
    if changed=='worker':ledger.restart_worker_generation()
    if changed=='age':clock.now=.5
    if changed=='state':x[5]=.03
    cap=observed(ledger,x,ref,'different' if changed=='reference' else 'reference-1')
    assert arb.choose(cap)['status']=='fallback'

"""30Hz four-receipt evidence replay; synthetic execution, not Isaac physics."""
from copy import deepcopy
import numpy as np
import pytest
from test_rate30_v67 import setup, capture, ack
from test_plan_arbiter_v52 import Clock


def recorded_run():
    from workflows.runtime_audit_v67 import RecordingArbiter
    ledger, command, ref = setup()
    clock = Clock()
    arbiter = RecordingArbiter(ledger, clock=clock)
    intervals, receipts = [], []
    for i in range(3):
        clock.now = i/30
        cap = capture(ledger, ref)
        assert arbiter.choose(cap)['status'] == 'fallback'
        ticket = ledger.reserve(cap, command, source='fallback', startup=i == 0)
        packet = ledger.dispatch(ticket)
        intervals.append(dict(physics_index=4*i, state=cap.state,
            decision=dict(status='dispatch', packet=packet)))
        for j in range(4):
            ack(ledger, ticket, command, 4*i+j)
        receipts.append(ledger._digest)
    report = dict(audit=arbiter.export(), intervals=intervals, receipts=receipts,
        execution_id=ledger._execution_id, startup=ledger._startup, activations=0)
    return report, ledger, ref


def replay(report, ledger, ref, **kwargs):
    from workflows.runtime_audit_v67 import replay_audit
    return replay_audit(report, ledger._reset, ledger._domain, ledger._context,
        reference=ref, reference_id='ref', allow_diagnostic=True, require_mpc=False, **kwargs)


def test_replay_reconstructs_all_twelve_actual_receipts():
    report, ledger, ref = recorded_run()
    result = replay(report, ledger, ref)
    assert len(result['physics_history_digests']) == 12
    assert result['recomputed_final_digest'] == ledger._digest
    assert result['confirmed_controls'] == 3


@pytest.mark.parametrize('bad', ['half_boundary', 'receipt', 'command', 'missing_event'])
def test_replay_rejects_wrong_rate_and_forged_history(bad):
    report, ledger, ref = recorded_run()
    report = deepcopy(report)
    if bad == 'half_boundary': report['intervals'][1]['physics_index'] = 2
    if bad == 'receipt': report['receipts'][1] = '0'*64
    if bad == 'command': report['intervals'][1]['decision']['packet']['command'][0] += .01
    if bad == 'missing_event': report['audit'].pop()
    with pytest.raises((ValueError, AssertionError)):
        replay(report, ledger, ref)


@pytest.mark.parametrize('ms,passed', [(32., True), (34., False)])
def test_validator_applies_thirty_hz_deadline(ms, passed):
    from workflows.validate_effects_v67 import validate_timing
    row = dict(external_cycle_wall_ms=ms, whole_cycle_wall_ms=ms-.1,
        scheduled_start_lateness_ms=0, timing_mode='startup_then_realtime',
        timing_phase='steady', wall_deadline_missed=ms > 1000/30)
    if passed: validate_timing(row, 1, 'startup_then_realtime')
    else:
        with pytest.raises(ValueError, match='steady_deadline'):
            validate_timing(row, 1, 'startup_then_realtime')

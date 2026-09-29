import copy

import pytest

from workflows.projected_protocol_v38 import cases


def test_reservations_inherit_prior_attempts_and_cannot_repeat_case():
    from workflows.projected_budget_v38 import initial_budget, reserve, settle, validate_budget
    b = initial_budget('a'*64)
    q = cases()[0]
    b = reserve(b, 'collector', q['run_id'], 300.)
    assert b['charged_seconds']['collector'] == 300.
    with pytest.raises(ValueError):
        reserve(b, 'collector', cases()[1]['run_id'], 300.)
    b = settle(b, 'collector', q['run_id'], 17., 0)
    validate_budget(b, 'a'*64)
    assert b['charged_seconds']['collector'] == 17.
    with pytest.raises(ValueError):
        reserve(b, 'collector', q['run_id'], 300.)
    bad = copy.deepcopy(b)
    bad['charged_seconds']['collector'] = 0.
    with pytest.raises(ValueError):
        validate_budget(bad, 'a'*64)


def test_no_skipping_case_failed_attempt_or_resource_cap():
    from workflows.projected_budget_v38 import initial_budget, reserve, settle
    b = initial_budget('a'*64)
    with pytest.raises(ValueError):
        reserve(b, 'collector', cases('test')[0]['run_id'], 300.)
    b = reserve(b, 'collector', cases()[0]['run_id'], 300.)
    b = settle(b, 'collector', cases()[0]['run_id'], 17., 1)
    with pytest.raises(ValueError):
        reserve(b, 'collector', cases()[1]['run_id'], 300.)
    b = initial_budget('a'*64)
    b = reserve(b, 'analysis', 'first', 3600.)
    with pytest.raises(ValueError):
        reserve(b, 'analysis', 'second', 1.)
    b = settle(b, 'analysis', 'first', 3599., 0)
    with pytest.raises(ValueError):
        reserve(b, 'analysis', 'second', 2.)


def test_actual_overrun_is_preserved_and_blocks_later_work():
    from workflows.projected_budget_v38 import initial_budget, reserve, settle, validate_budget
    b = reserve(initial_budget('a'*64), 'analysis', 'slow', 3600.)
    b = settle(b, 'analysis', 'slow', 3602., 0)
    assert b['charged_seconds']['analysis'] == 3602.
    with pytest.raises(ValueError):
        validate_budget(b, 'a'*64)


def test_no_live_case_without_its_exact_reservation_and_output(tmp_path):
    from workflows.projected_budget_v38 import initial_budget, reserve, verify_case_reservation, write_budget
    q = cases()[0]
    write_budget(tmp_path/'budget.json', initial_budget('a'*64))
    with pytest.raises(ValueError):
        verify_case_reservation(tmp_path, q, tmp_path/q['role']/q['run_id'], 'a'*64)
    write_budget(tmp_path/'budget.json', reserve(initial_budget('a'*64), 'collector', q['run_id'], 300.))
    verify_case_reservation(tmp_path, q, tmp_path/q['role']/q['run_id'], 'a'*64)
    for other, output in [(cases()[1], tmp_path/'preflight'/cases()[1]['run_id']), (q, tmp_path/'elsewhere')]:
        with pytest.raises(ValueError):
            verify_case_reservation(tmp_path, other, output, 'a'*64)


def test_failed_native_can_be_archived_and_audited_without_reopening_experiments():
    from workflows.projected_budget_v38 import initial_budget, reserve, settle
    b = reserve(initial_budget('a'*64), 'collector', cases()[0]['run_id'], 300.)
    b = settle(b, 'collector', cases()[0]['run_id'], 17., 1)
    b = reserve(b, 'analysis', 'archive:preflight', 30.)
    b = settle(b, 'analysis', 'archive:preflight', 1., 0)
    b = reserve(b, 'analysis', 'pullback:preflight', 30.)
    b = settle(b, 'analysis', 'pullback:preflight', 1., 0)
    assert b['attempts'][0]['native_exit'] == 1
    for bucket, name in [('collector', cases()[1]['run_id']), ('analysis', 'formal_analysis:validation')]:
        with pytest.raises(ValueError):
            reserve(b, bucket, name, 30.)


def preflight_pullback_failure():
    """Synthetic complete-preflight ledger; no real experiment authorization."""
    from workflows.projected_budget_v38 import initial_budget, reserve, settle
    b = initial_budget('a'*64)
    for q in cases('preflight'):
        b = settle(reserve(b, 'collector', q['run_id'], 30.), 'collector', q['run_id'], 1., 0)
        name = 'online_semantics:'+q['run_id']
        b = settle(reserve(b, 'analysis', name, 30.), 'analysis', name, 1., 0)
    b = settle(reserve(b, 'analysis', 'archive:preflight', 30.), 'analysis', 'archive:preflight', 1., 0)
    return settle(reserve(b, 'analysis', 'pullback:preflight', 30.), 'analysis', 'pullback:preflight', 1., 1)


def test_numeric_recovery_retains_failed_prefix_and_charges_all_recheck_work():
    from workflows.projected_budget_v38 import recover_numeric_pullback, reserve, validate_budget
    parent = preflight_pullback_failure()
    recovered = recover_numeric_pullback(parent, 'b'*64, preflight_audit_sha256='c'*64, diagnostic_seconds=3.)
    assert recovered['attempts'][:18] == parent['attempts']
    assert recovered['attempts'][17]['native_exit'] == 1
    assert recovered['charged_seconds']['analysis'] == parent['charged_seconds']['analysis']+3.
    validate_budget(recovered, 'b'*64)
    reserve(recovered, 'collector', cases('validation')[0]['run_id'], 30.)
    for bad in (dict(recovered, numeric_recovery=None), dict(recovered, charged_seconds=parent['charged_seconds'])):
        with pytest.raises(ValueError): validate_budget(bad, 'b'*64)
    changed = copy.deepcopy(recovered); changed['attempts'][0]['charged_seconds'] += .1
    changed['charged_seconds']['collector'] += .1
    with pytest.raises(ValueError): validate_budget(changed, 'b'*64)


def test_recovery_cannot_clear_collector_or_later_failures():
    from workflows.projected_budget_v38 import recover_numeric_pullback, reserve, settle, validate_budget
    parent = preflight_pullback_failure()
    native_failure = copy.deepcopy(parent); native_failure['attempts'][0]['native_exit'] = 1
    with pytest.raises(ValueError): recover_numeric_pullback(native_failure, 'b'*64, preflight_audit_sha256='c'*64, diagnostic_seconds=3.)
    unknown_failure = copy.deepcopy(parent); unknown_failure['attempts'][-1]['name'] = 'score:validation'
    with pytest.raises(ValueError): recover_numeric_pullback(unknown_failure, 'b'*64, preflight_audit_sha256='c'*64, diagnostic_seconds=3.)
    recovered = recover_numeric_pullback(parent, 'b'*64, preflight_audit_sha256='c'*64, diagnostic_seconds=3.)
    name = cases('validation')[0]['run_id']
    failed = settle(reserve(recovered, 'collector', name, 30.), 'collector', name, 2., 1)
    with pytest.raises(ValueError): validate_budget(failed, 'b'*64)
    assert failed['attempts'][-1]['native_exit'] == 1


def test_recovery_never_resets_the_original_cap():
    from workflows.projected_budget_v38 import recover_numeric_pullback
    with pytest.raises(ValueError):
        recover_numeric_pullback(preflight_pullback_failure(), 'b'*64,
                                 preflight_audit_sha256='c'*64, diagnostic_seconds=3600.)


def validation_pullback_failure():
    from workflows.projected_budget_v38 import recover_numeric_pullback, reserve, settle
    b = recover_numeric_pullback(preflight_pullback_failure(), 'b'*64,
                                preflight_audit_sha256='c'*64, diagnostic_seconds=3.)
    for q in cases('validation'):
        b = settle(reserve(b, 'collector', q['run_id'], 30.), 'collector', q['run_id'], 1., 0)
        name = 'online_semantics:'+q['run_id']
        b = settle(reserve(b, 'analysis', name, 30.), 'analysis', name, 1., 0)
    b = settle(reserve(b, 'analysis', 'archive:validation', 30.), 'analysis', 'archive:validation', 1., 0)
    return settle(reserve(b, 'analysis', 'pullback:validation', 30.), 'analysis', 'pullback:validation', 1., 1)


def test_validation_recovery_retains_both_failures_and_cannot_clear_any_other_failure():
    from workflows.projected_budget_v38 import recover_validation_pullback, reserve, settle, validate_budget
    before = validation_pullback_failure()
    with pytest.raises(ValueError): validate_budget(before, 'b'*64)
    fixed = recover_validation_pullback(before, 'd'*64, validation_audit_sha256='e'*64, diagnostic_seconds=4.)
    assert fixed['attempts'][:69] == before['attempts']
    assert [r['native_exit'] for r in fixed['attempts'] if r['native_exit']] == [1, 1]
    assert fixed['charged_seconds']['analysis'] == before['charged_seconds']['analysis']+4.
    validate_budget(fixed, 'd'*64)
    reserve(fixed, 'analysis', 'formal_analysis:validation', 30.)
    for index in (0, 19, 67):
        changed=copy.deepcopy(before); changed['attempts'][index]['native_exit']=1
        with pytest.raises(ValueError):
            recover_validation_pullback(changed, 'd'*64, validation_audit_sha256='e'*64, diagnostic_seconds=4.)
    changed=copy.deepcopy(fixed);changed['validation_numeric_recovery']['parent_attempts_digest']='f'*64
    with pytest.raises(ValueError):validate_budget(changed, 'd'*64)
    name='formal_analysis:validation'
    failed=settle(reserve(fixed,'analysis',name,30.),'analysis',name,1.,1)
    with pytest.raises(ValueError):validate_budget(failed,'d'*64)


def test_validation_recovery_does_not_accept_repeated_resolution_or_reset_cap():
    from workflows.projected_budget_v38 import recover_validation_pullback
    before=validation_pullback_failure()
    fixed=recover_validation_pullback(before,'d'*64,validation_audit_sha256='e'*64,diagnostic_seconds=4.)
    for parent, seconds in ((before,3600.),(fixed,4.)):
        with pytest.raises(ValueError):
            recover_validation_pullback(parent,'f'*64,validation_audit_sha256='e'*64,diagnostic_seconds=seconds)

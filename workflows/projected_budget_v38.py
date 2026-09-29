"""Single-supervisor reservations; failures and overruns remain charged."""
import copy
import json
import math
from pathlib import Path
import re

from workflows.projected_protocol_v38 import cases, digest, protocol, validate_case
from workflows.projected_resource_v38 import resource_limits


def initial_budget(freeze_sha256):
    result = dict(schema='projected-formal-budget-v38', freeze_sha256=freeze_sha256,
                  attempts=[], charged_seconds=dict(collector=0., analysis=0.))
    validate_budget(result, freeze_sha256)
    return result


def _seconds(value, *, zero=False):
    return type(value) in (int, float) and math.isfinite(value) and (value >= 0 if zero else value > 0)


def _recovered_failure_index(budget):
    """Only a frozen, explicitly resolved preflight pullback may be inherited.

    This validates ledger consistency, not permission. verify_snapshot separately
    binds this record to the repaired freeze and the independent audit receipt.
    """
    if 'numeric_recovery' not in budget:
        return None
    r = budget['numeric_recovery']
    if (not isinstance(r, dict) or r.get('schema') != 'projected-v38-numeric-recovery'
            or r.get('parent_attempt_count') != 18 or type(r.get('parent_attempt_count')) is not int
            or any(not isinstance(r.get(k), str) or re.fullmatch('[a-f0-9]{64}', r[k]) is None
                   for k in ('parent_freeze_sha256', 'parent_attempts_digest', 'preflight_audit_sha256'))
            or r.get('parent_freeze_sha256') == budget['freeze_sha256']
            or not _seconds(r.get('diagnostic_seconds')) or len(budget['attempts']) < 19):
        raise ValueError('formal_numeric_recovery_identity')
    prefix = budget['attempts'][:18]
    expected = []
    for q in cases('preflight'):
        expected.extend([('collector', q['run_id']), ('analysis', 'online_semantics:'+q['run_id'])])
    expected += [('analysis', 'archive:preflight'), ('analysis', 'pullback:preflight')]
    if (digest(prefix) != r['parent_attempts_digest']
            or [(q.get('bucket'), q.get('name')) for q in prefix] != expected
            or any(q.get('status') != 'exited' or type(q.get('native_exit')) is not int
                   or q['native_exit'] != (1 if i == 17 else 0) for i, q in enumerate(prefix))):
        raise ValueError('formal_numeric_recovery_prefix')
    charged = budget['attempts'][18]
    if charged != dict(bucket='analysis', name='numeric_repair_reaudit', status='exited',
                       charged_seconds=r['diagnostic_seconds'], native_exit=0):
        raise ValueError('formal_numeric_recovery_charges')
    return 17


def recover_numeric_pullback(parent, freeze_sha256, *, preflight_audit_sha256, diagnostic_seconds):
    """Construct a successor ledger without editing, dropping or clearing failure.

    The caller must freeze the recovery metadata and all audit evidence before
    any live release. This helper alone cannot authorize collection.
    """
    validate_budget(parent, parent['freeze_sha256'], allow_failed_evidence=True)
    if 'numeric_recovery' in parent or len(parent['attempts']) != 18:
        raise ValueError('formal_numeric_recovery_parent')
    result = copy.deepcopy(parent)
    result['freeze_sha256'] = freeze_sha256
    result['numeric_recovery'] = dict(schema='projected-v38-numeric-recovery',
        parent_freeze_sha256=parent['freeze_sha256'], parent_attempt_count=18,
        parent_attempts_digest=digest(parent['attempts']), preflight_audit_sha256=preflight_audit_sha256,
        diagnostic_seconds=diagnostic_seconds)
    result['attempts'].append(dict(bucket='analysis', name='numeric_repair_reaudit', status='exited',
                                   charged_seconds=diagnostic_seconds, native_exit=0))
    result['charged_seconds']['analysis'] += diagnostic_seconds
    validate_budget(result, freeze_sha256)
    return result


def validate_budget(budget, freeze_sha256, *, allow_failed_evidence=False):
    if (budget.get('schema') != 'projected-formal-budget-v38' or budget.get('freeze_sha256') != freeze_sha256
            or not isinstance(freeze_sha256, str) or re.fullmatch('[a-f0-9]{64}', freeze_sha256) is None
            or not isinstance(budget.get('attempts'), list)
            or set(budget.get('charged_seconds', {})) != {'collector', 'analysis'}):
        raise ValueError('formal_budget_identity')
    recovered_index = _recovered_failure_index(budget)
    validation_index = _recovered_validation_index(budget)
    totals = dict(collector=0., analysis=0.)
    ids, native, reserved = set(), [], 0
    for i, row in enumerate(budget['attempts']):
        bucket, name = row.get('bucket'), row.get('name')
        if (bucket not in totals or not isinstance(name, str) or not name
                or (bucket, name) in ids or not _seconds(row.get('charged_seconds'))
                or row.get('status') not in ('reserved', 'exited')):
            raise ValueError('formal_budget_attempt')
        ids.add((bucket, name))
        totals[bucket] += row['charged_seconds']
        if bucket == 'collector':
            native.append(name)
        if row['status'] == 'reserved':
            reserved += 1
            if i != len(budget['attempts'])-1:
                raise ValueError('formal_budget_unsettled_attempt')
        elif type(row.get('native_exit')) is not int or (row['native_exit'] != 0
                and i not in (recovered_index, validation_index) and not allow_failed_evidence):
            raise ValueError('formal_budget_previous_failure')
    if reserved > 1 or native != [q['run_id'] for q in cases()][:len(native)] or len(native) > 56:
        raise ValueError('formal_budget_case_order')
    for bucket, total in totals.items():
        given = budget['charged_seconds'][bucket]
        if (not _seconds(given, zero=True) or not math.isclose(total, given, abs_tol=1e-8, rel_tol=0)
                or total > resource_limits(budget)[bucket+'_seconds']):
            raise ValueError('formal_budget_accounting_or_cap')
    return budget


def _recovered_validation_index(budget):
    """One explicit resolution of the preserved r21 validation pullback only.

    Release also checks the frozen audit and original failed ledger; this is
    accounting validation, never sufficient release authority by itself.
    """
    r=budget.get('validation_numeric_recovery')
    if r is None:
        return None
    if (not isinstance(r,dict) or r.get('schema')!='projected-v38-validation-numeric-recovery'
            or type(r.get('parent_attempt_count')) is not int or r['parent_attempt_count']!=69
            or len(budget['attempts'])<70 or 'numeric_recovery' not in budget
            or any(not isinstance(r.get(k),str) or re.fullmatch('[a-f0-9]{64}',r[k]) is None
                   for k in ('parent_freeze_sha256','parent_attempts_digest','validation_audit_sha256'))
            or r['parent_freeze_sha256']==budget['freeze_sha256']
            or not _seconds(r.get('diagnostic_seconds'))):
        raise ValueError('formal_validation_recovery_identity')
    prefix=budget['attempts'][:69]
    expected=[]
    for q in cases('validation'):
        expected.extend([('collector',q['run_id']),('analysis','online_semantics:'+q['run_id'])])
    expected += [('analysis','archive:validation'),('analysis','pullback:validation')]
    if (digest(prefix)!=r['parent_attempts_digest']
            or [(q.get('bucket'),q.get('name')) for q in prefix[19:]]!=expected
            or any(q.get('status')!='exited' or type(q.get('native_exit')) is not int
                   or q['native_exit']!=(1 if i in (17,68) else 0) for i,q in enumerate(prefix))
            or budget['attempts'][69]!=dict(bucket='analysis',name='validation_numeric_repair_reaudit',
                status='exited',charged_seconds=r['diagnostic_seconds'],native_exit=0)):
        raise ValueError('formal_validation_recovery_prefix_or_charges')
    return 68


def recover_validation_pullback(parent, freeze_sha256, *, validation_audit_sha256, diagnostic_seconds):
    validate_budget(parent,parent['freeze_sha256'],allow_failed_evidence=True)
    if ('validation_numeric_recovery' in parent or 'numeric_recovery' not in parent
            or len(parent['attempts'])!=69):
        raise ValueError('formal_validation_recovery_parent')
    result=copy.deepcopy(parent);result['freeze_sha256']=freeze_sha256
    result['validation_numeric_recovery']=dict(schema='projected-v38-validation-numeric-recovery',
        parent_freeze_sha256=parent['freeze_sha256'],parent_attempt_count=69,
        parent_attempts_digest=digest(parent['attempts']),validation_audit_sha256=validation_audit_sha256,
        diagnostic_seconds=diagnostic_seconds)
    result['attempts'].append(dict(bucket='analysis',name='validation_numeric_repair_reaudit',status='exited',
                                  charged_seconds=diagnostic_seconds,native_exit=0))
    result['charged_seconds']['analysis']+=diagnostic_seconds
    validate_budget(result,freeze_sha256)
    return result


def _evidence_operation(bucket, name):
    return bucket == 'analysis' and name in {op+':'+role for op in ('archive', 'pullback')
                                            for role in ('preflight', 'validation', 'test')}


def reserve(budget, bucket, name, seconds):
    evidence = _evidence_operation(bucket, name)
    validate_budget(budget, budget['freeze_sha256'], allow_failed_evidence=evidence)
    if (bucket not in ('collector', 'analysis') or not _seconds(seconds)
            or any(row['status'] == 'reserved' or (row['bucket'], row['name']) == (bucket, name)
                   for row in budget['attempts'])
            or bucket == 'collector' and seconds > 300):
        raise ValueError('formal_budget_reservation')
    result = copy.deepcopy(budget)
    result['attempts'].append(dict(bucket=bucket, name=name, status='reserved', charged_seconds=seconds))
    result['charged_seconds'][bucket] += seconds
    validate_budget(result, result['freeze_sha256'], allow_failed_evidence=evidence)
    return result


def settle(budget, bucket, name, seconds, native_exit):
    validate_budget(budget, budget['freeze_sha256'], allow_failed_evidence=_evidence_operation(bucket, name))
    if not _seconds(seconds) or type(native_exit) is not int or not budget['attempts']:
        raise ValueError('formal_budget_settlement')
    result = copy.deepcopy(budget)
    attempt = result['attempts'][-1]
    if (attempt['bucket'], attempt['name'], attempt['status']) != (bucket, name, 'reserved'):
        raise ValueError('formal_budget_settlement')
    result['charged_seconds'][bucket] += seconds-attempt['charged_seconds']
    attempt.update(status='exited', native_exit=native_exit, charged_seconds=seconds)
    # Return even an overrun/failed ledger, so the caller can durably record it.
    # Any subsequent reservation or admission will then fail closed.
    return result


def write_budget(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+'.pending')
    with temporary.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
    temporary.replace(path)


def verify_case_reservation(transfer, case, output, freeze_sha256):
    transfer = Path(transfer)
    validate_case(case)
    budget = json.loads((transfer/'budget.json').read_text(encoding='utf8'))
    validate_budget(budget, freeze_sha256)
    if (not budget['attempts'] or Path(output).resolve() != (transfer/case['role']/case['run_id']).resolve()
            or (budget['attempts'][-1]['bucket'], budget['attempts'][-1]['name'], budget['attempts'][-1]['status'])
                != ('collector', case['run_id'], 'reserved')):
        raise ValueError('formal_case_not_reserved')
    return budget['attempts'][-1]

"""Resource-only amendment fixtures are never experimental authority."""
import copy
import os

import pytest

from tests.test_projected_budget_v38 import validation_pullback_failure
from workflows.projected_budget_v38 import recover_validation_pullback, reserve, settle, validate_budget


def parent_budget():
    b = recover_validation_pullback(validation_pullback_failure(), 'd'*64,
        validation_audit_sha256='e'*64, diagnostic_seconds=4.)
    for name in ('formal_analysis:validation', 'independent_analysis:validation'):
        b = settle(reserve(b, 'analysis', name, 30.), 'analysis', name, 1., 0)
    return b


def amended():
    from workflows.projected_resource_v38 import amend_budget
    return amend_budget(parent_budget(), 'f'*64, approval_sha256='a'*64,
                        parent_budget_sha256='b'*64, validation_audit_sha256='c'*64)


def test_only_explicit_amendment_adds_900_seconds_without_resetting_any_attempt():
    from workflows.projected_resource_v38 import resource_limits
    parent = parent_budget(); b = amended()
    assert b['attempts'] == parent['attempts'] and b['charged_seconds'] == parent['charged_seconds']
    assert [x['native_exit'] for x in b['attempts'] if x['native_exit']] == [1, 1]
    assert resource_limits(parent)['analysis_seconds'] == 3600
    assert resource_limits(b)['analysis_seconds'] == 4500
    for key in ('collector_seconds', 'analysis_processes', 'disk_bytes'):
        assert resource_limits(parent)[key] == resource_limits(b)[key]
    used = b['charged_seconds']['analysis']
    reserve(b, 'analysis', 'formal_analysis:test', 4500-used)
    for budget, amount in ((b, 4500-used+.01), (parent, 3600-used+.01)):
        with pytest.raises(ValueError): reserve(budget, 'analysis', 'formal_analysis:test', amount)


@pytest.mark.parametrize('mutation', ['cost', 'failure', 'cap', 'count', 'approval', 'reset'])
def test_amendment_rejects_tampered_history_or_scope(mutation):
    b = amended(); r = b['resource_amendment']
    if mutation == 'cost':
        b['attempts'][70]['charged_seconds'] += 1
        b['charged_seconds']['analysis'] += 1
    elif mutation == 'failure': b['attempts'][71]['native_exit'] = 1
    elif mutation == 'cap': r['resource_cap']['collector_seconds'] += 900
    elif mutation == 'count': r['parent_attempt_count'] = True
    elif mutation == 'approval': r['approval_sha256'] = 'unknown'
    elif mutation == 'reset': b['charged_seconds']['analysis'] = 0
    with pytest.raises(ValueError): validate_budget(b, 'f'*64)


def test_amendment_cannot_repeat_or_erase_new_failure():
    from workflows.projected_resource_v38 import amend_budget
    b = amended()
    with pytest.raises(ValueError):
        amend_budget(b, '9'*64, approval_sha256='a'*64, parent_budget_sha256='b'*64,
                     validation_audit_sha256='c'*64)
    failed = settle(reserve(b, 'analysis', 'formal_analysis:test', 30.),
                    'analysis', 'formal_analysis:test', 2., 1)
    with pytest.raises(ValueError): validate_budget(failed, 'f'*64)


def test_original_data_analysis_and_new_test_keep_distinct_identities():
    from workflows.projected_release_v38 import stage_identity, analysis_identity
    f = dict(schema='projected-formal-v38-resource-amendment-before-test', source_commit='a'*40,
        resource_parent_source_commit='b'*40, resource_parent_freeze_sha256='c'*64,
        validation_numeric_recovery_sha256='d'*64, validation_source_commit='e'*40,
        parent_freeze_sha256='f'*64)
    assert stage_identity(f, 'validation', '9'*64) == ('e'*40, 'f'*64)
    assert analysis_identity(f, 'validation', '9'*64) == ('b'*40, 'c'*64)
    assert analysis_identity(f, 'test', '9'*64) == ('a'*40, '9'*64)
    assert stage_identity(f, 'test', '9'*64) == ('a'*40, '9'*64)
    with pytest.raises(ValueError): analysis_identity(dict(f, resource_parent_source_commit=''), 'validation', '9'*64)


def test_hardlinks_count_once_but_equal_independent_copies_still_count_twice(tmp_path):
    from workflows.projected_resource_v38 import storage_usage
    (tmp_path/'a').mkdir(); (tmp_path/'b').mkdir()
    p = tmp_path/'a/asset'; p.write_bytes(b'physics asset')
    os.link(p, tmp_path/'b/asset')
    (tmp_path/'b/copy').write_bytes(p.read_bytes())
    report = storage_usage([tmp_path/'a', tmp_path/'b'])
    assert report['logical_bytes'] == 3*p.stat().st_size
    assert report['unique_file_bytes'] == 2*p.stat().st_size
    assert len(report['hardlink_groups']) == 1


def test_resource_authorization_is_bound_and_cannot_expand_any_other_cap():
    from workflows.projected_release_v38 import validate_authorization
    from workflows.projected_resource_v38 import amended_limits
    r = dict(schema='projected-formal-v38-resource-amendment', decision='approved', authorized_by='user',
        freeze_sha256='a'*64, resource_cap=amended_limits(), parent_freeze_sha256='b'*64,
        parent_authorization_sha256='c'*64, approval_sha256='d'*64,
        approval_reference='SYNTHETIC TEST ONLY')
    validate_authorization(r, 'a'*64)
    for key in ('analysis_seconds', 'collector_seconds', 'analysis_processes', 'disk_bytes'):
        bad = copy.deepcopy(r); bad['resource_cap'][key] += 1
        with pytest.raises(ValueError): validate_authorization(bad, 'a'*64)
    for key in ('parent_freeze_sha256', 'parent_authorization_sha256', 'approval_sha256'):
        with pytest.raises(ValueError): validate_authorization(dict(r, **{key: None}), 'a'*64)


def test_resource_approval_receipt_rejects_changed_scope():
    from workflows.projected_resource_v38 import validate_approval
    r = dict(schema='projected-v38-resource-amendment-user-approval', decision='approved', authorized_by='user',
        approval_reference='SYNTHETIC ONLY', user_reply='SYNTHETIC ONLY', original_analysis_cap_seconds=3600,
        analysis_cap_seconds=4500, additional_seconds=900, collector_cap_seconds=5400, analysis_processes=4,
        disk_bytes=4*1024**3, remaining_test_cases=24, model_count=18, new_model_fits=0,
        scientific_thresholds_unchanged=True, parent_freeze_sha256='a'*64,
        parent_settled_budget_sha256='b'*64, independent_validation_audit_sha256='c'*64)
    validate_approval(r)
    for key, value in [('remaining_test_cases', 25), ('new_model_fits', True), ('analysis_cap_seconds', 4501),
                       ('decision', 'pending'), ('approval_reference', ''), ('parent_freeze_sha256', '')]:
        with pytest.raises(ValueError): validate_approval(dict(r, **{key: value}))


def test_resource_package_cannot_change_prediction_math_or_original_protocol():
    from workflows.package_projected_resource_v38 import validate_resource_change
    old = b'from workflows.projected_budget_v38 import reserve\ndef run():\n    remaining = 3600-budget["charged_seconds"]["analysis"]\ndef score_episode():\n    return 7\n'
    new = b'from workflows.projected_resource_v38 import resource_limits\n' + old.replace(
        b'3600-budget', b'resource_limits(budget)["analysis_seconds"]-budget')
    validate_resource_change('workflows/evaluate_projected_formal_v38.py', old, new)
    with pytest.raises(ValueError):
        validate_resource_change('workflows/evaluate_projected_formal_v38.py', old, new.replace(b'return 7', b'return 8'))
    with pytest.raises(ValueError):
        validate_resource_change('workflows/projected_protocol_v38.py', old, new)

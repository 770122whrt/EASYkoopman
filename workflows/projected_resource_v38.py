"""One approved +900 s analysis amendment, with the entire original ledger intact.

Ledger consistency is not authorization: release verifies the actual approval,
parent freeze, parent authorization, and independent validation certificate.
"""
import copy
from pathlib import Path
import re

from workflows.projected_protocol_v38 import digest, protocol

SCHEMA = 'projected-formal-v38-resource-amendment-before-test'
INPUT_FILES = ('resource-amendment.json', 'resource-approval.json', 'resource-parent-budget.json',
               'resource-parent-freeze.json', 'resource-parent-authorization.json',
               'validation-analysis-audit.json', 'validation-pullback.json')


def amended_limits():
    return dict(protocol()['resource_cap'], analysis_seconds=4500)


def validate_approval(record):
    expected = dict(schema='projected-v38-resource-amendment-user-approval', decision='approved', authorized_by='user',
        original_analysis_cap_seconds=3600, analysis_cap_seconds=4500, additional_seconds=900,
        collector_cap_seconds=5400, analysis_processes=4, disk_bytes=4*1024**3,
        remaining_test_cases=24, model_count=18, new_model_fits=0, scientific_thresholds_unchanged=True)
    if (not isinstance(record, dict)
            or any(record.get(k) != v or type(record.get(k)) is not type(v) for k, v in expected.items())
            or any(not isinstance(record.get(k), str) or not record[k].strip()
                   for k in ('approval_reference', 'user_reply'))
            or any(not isinstance(record.get(k), str) or re.fullmatch('[a-f0-9]{64}', record[k]) is None
                   for k in ('parent_freeze_sha256', 'parent_settled_budget_sha256',
                             'independent_validation_audit_sha256'))):
        raise ValueError('formal_resource_approval_scope')


def resource_limits(budget):
    if 'resource_amendment' not in budget:
        return protocol()['resource_cap']
    r = budget['resource_amendment']
    if (not isinstance(r, dict) or r.get('schema') != 'projected-v38-analysis-budget-amendment'
            or type(r.get('parent_attempt_count')) is not int or r['parent_attempt_count'] != 72
            or len(budget.get('attempts', [])) < 72
            or any(not isinstance(r.get(k), str) or re.fullmatch('[a-f0-9]{64}', r[k]) is None
                for k in ('parent_freeze_sha256', 'parent_attempts_digest', 'parent_budget_sha256',
                          'approval_sha256', 'validation_audit_sha256'))
            or r['parent_freeze_sha256'] == budget.get('freeze_sha256')
            or r.get('resource_cap') != amended_limits()
            or any(type(r['resource_cap'][k]) is not type(v) for k, v in amended_limits().items())
            or digest(budget['attempts'][:72]) != r['parent_attempts_digest']):
        raise ValueError('formal_resource_amendment_identity_or_prefix')
    last = budget['attempts'][70:72]
    if [(q.get('bucket'), q.get('name'), q.get('status'), q.get('native_exit')) for q in last] != [
            ('analysis', 'formal_analysis:validation', 'exited', 0),
            ('analysis', 'independent_analysis:validation', 'exited', 0)]:
        raise ValueError('formal_resource_amendment_validation_incomplete')
    return amended_limits()


def amend_budget(parent, freeze_sha256, *, approval_sha256, parent_budget_sha256, validation_audit_sha256):
    from workflows.projected_budget_v38 import validate_budget
    validate_budget(parent, parent['freeze_sha256'])
    if 'resource_amendment' in parent or len(parent['attempts']) != 72:
        raise ValueError('formal_resource_amendment_parent')
    result = copy.deepcopy(parent)
    result['freeze_sha256'] = freeze_sha256
    result['resource_amendment'] = dict(schema='projected-v38-analysis-budget-amendment',
        parent_attempt_count=72, parent_freeze_sha256=parent['freeze_sha256'],
        parent_attempts_digest=digest(parent['attempts']), parent_budget_sha256=parent_budget_sha256,
        approval_sha256=approval_sha256, validation_audit_sha256=validation_audit_sha256,
        resource_cap=amended_limits())
    validate_budget(result, freeze_sha256)
    return result


def storage_usage(roots):
    """Physical file contents per host; report path sum too, never dedup by hash.

Only true hardlinks share allocation. Equal independent files still count twice.
Directory/FS metadata is covered by the separately reserved safety margin.
"""
    files, logical, seen_paths = {}, 0, set()
    for root in roots:
        root = Path(root)
        if root.is_symlink():
            raise ValueError('formal_disk_symlink')
        for path in root.rglob('*'):
            if path.is_symlink():
                raise ValueError('formal_disk_symlink')
            if not path.is_file() or str(path.resolve()) in seen_paths:
                continue
            seen_paths.add(str(path.resolve()))
            stat = path.stat(); logical += stat.st_size
            key = (stat.st_dev, stat.st_ino) if stat.st_ino else str(path.resolve())
            entry = files.setdefault(key, dict(bytes=stat.st_size, paths=[]))
            if entry['bytes'] != stat.st_size:
                raise ValueError('formal_disk_changed_during_measurement')
            entry['paths'].append(str(path))
    return dict(logical_bytes=logical, unique_file_bytes=sum(q['bytes'] for q in files.values()),
                hardlink_groups=[q for q in files.values() if len(q['paths']) > 1])

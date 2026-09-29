"""Small r21 audit-repair delta over preserved r20; no new scientific protocol."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from workflows.package_projected_v38 import dump, git, preflight
from workflows.projected_archive_v38 import AUDIT_REPAIR_FILES, audit_raw, validate_audit_only_change
from workflows.projected_budget_v38 import recover_numeric_pullback
from workflows.projected_release_v38 import read, sha, verify_snapshot
from workflows.projected_protocol_v38 import protocol


def build(root, parent, directory, *, revision_name='r21'):
    root, parent, directory = Path(root).resolve(), Path(parent).resolve(), Path(directory).resolve()
    if directory.exists() or not directory.is_relative_to(root/'.pytest-tmp'):
        raise ValueError('repair_package_destination')
    if revision_name not in ('r21','r22'):
        raise ValueError('repair_revision_name')
    old = read(parent/'package.json'); base = Path(old['clone_root'])
    old_manifest = read(base/'SOURCE_MANIFEST.json')
    if (git(base, 'rev-parse', 'HEAD') != old['source_commit']
            or git(base, 'status', '--porcelain=v1', '--untracked-files=all')
            or any(sha(base/n) != h for n, h in old_manifest['files_sha256'].items())):
        raise ValueError('repair_parent_changed')
    names = set(old_manifest['files_sha256']) | {n for n in AUDIT_REPAIR_FILES if (root/n).is_file()}
    payloads, hashes, original = {}, {}, {}
    for name in sorted(names):
        path = root/name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('repair_source_path')
        data = path.read_bytes(); original[name] = sha(path)
        if name.endswith('.sh'):
            data = data.replace(b'\r\n', b'\n')
        import hashlib
        h = hashlib.sha256(data).hexdigest()
        if h != old_manifest['files_sha256'].get(name) and name not in AUDIT_REPAIR_FILES:
            raise ValueError('repair_changes_scientific_source:'+name)
        if h != old_manifest['files_sha256'].get(name) and name=='workflows/evaluate_projected_formal_v38.py':
            validate_audit_only_change(name,(base/name).read_bytes(),data)
        payloads[name], hashes[name] = data, h
    directory.mkdir()
    source = directory/'source'
    # One checkout and a delta bundle; the parent remains required and preserved.
    git(directory, 'clone', '--shared', str(base), str(source))
    git(source, 'checkout', '-b', 'phase84-projected-v38-'+revision_name)
    for name, data in payloads.items():
        path = source/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    snapshot = dict(schema='phase8.4-isolated-source-snapshot-v1', origin_head=git(root, 'rev-parse', 'HEAD'),
        origin_branch=git(root, 'branch', '--show-current'), purpose=revision_name+' numerical audit repair; scientific scoring frozen',
        files_sha256=hashes, origin_files_sha256=original,
        parent_source_commit=old['source_commit'], parent_source_manifest_sha256=sha(base/'SOURCE_MANIFEST.json'))
    dump(source/'SOURCE_MANIFEST.json', snapshot)
    changed = sorted({n for n in names if hashes[n] != old_manifest['files_sha256'].get(n)} | {'SOURCE_MANIFEST.json'})
    for start in range(0, len(changed), 25):
        git(source, 'add', '-f', '--', *changed[start:start+25])
    git(source, '-c', 'user.name=EasyUUV source packaging', '-c', 'user.email=source-package@localhost',
        'commit', '-m', revision_name+' explicit numerical audit repair over preserved experiment')
    commit = git(source, 'rev-parse', 'HEAD')
    bundle = directory/('EasyUUV-projected-v38-'+revision_name+'-delta.bundle')
    git(source, 'bundle', 'create', str(bundle), 'HEAD', '^'+old['source_commit'])
    git(source, 'bundle', 'verify', str(bundle))
    if git(source, 'status', '--porcelain=v1', '--untracked-files=all'):
        raise ValueError('repair_source_not_clean')
    record = dict(status='repair_source_ready_tests_pending', origin_root=str(root), source_root=str(source),
        clone_root=str(source), parent_package=str(parent), parent_source_commit=old['source_commit'],
        parent_freeze_sha256=sha(parent/'inputs/freeze.json'), source_commit=commit,
        source_manifest_sha256=sha(source/'SOURCE_MANIFEST.json'), source_files=len(hashes),
        changed_files=changed, bundle_path=str(bundle), bundle_sha256=sha(bundle), bundle_bytes=bundle.stat().st_size,
        bundle_requires_parent=True, model_fits=0, formal_release=False)
    dump(directory/'package.json', record)
    dump(directory/'auditor-revision.json', dict(schema='projected-v38-auditor-revision',
        parent_source_commit=old['source_commit'], parent_freeze_sha256=record['parent_freeze_sha256'],
        auditor_source_commit=commit, parent_source_manifest_sha256=sha(base/'SOURCE_MANIFEST.json'),
        auditor_source_manifest_sha256=record['source_manifest_sha256']))
    return record


def audit_child(directory, raw, archive_sha):
    result = audit_raw(Path(raw), 'preflight', archive_sha,
                       auditor_revision=read(Path(directory)/'auditor-revision.json'))
    with (Path(directory)/'reaudit/parent-preflight-audit.json').open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


def reaudit(directory, raw, parent_budget, diagnostics, cache_probe):
    directory, raw = Path(directory).resolve(), Path(raw).resolve()
    package = read(directory/'package.json'); out = directory/'reaudit'
    if out.exists():
        raise ValueError('repair_reaudit_already_attempted')
    if Path(__file__).resolve().parents[1] != Path(package['source_root']):
        raise ValueError('repair_reaudit_requires_tested_snapshot')
    before = read(parent_budget); diag = read(diagnostics); cache = read(cache_probe)
    if (sha(parent_budget) != diag['prior_budget_sha256'] or diag['native_exit'] != 0
            or cache['native_exit'] != 0 or len(cache['records']) != 8):
        raise ValueError('repair_diagnostic_lineage')
    prior_seconds = diag['diagnostic_charged_seconds']+cache['combined_probe_seconds']
    cap = min(120., 3600.-before['charged_seconds']['analysis']-prior_seconds)
    if cap < 30:
        raise ValueError('repair_reaudit_budget')
    out.mkdir(); started = time.monotonic(); code = 1
    report = dict(status='running', parent_budget_sha256=sha(parent_budget), prior_diagnostic_seconds=prior_seconds,
        cap_seconds=cap, diagnostic_reports={str(diagnostics):sha(diagnostics), str(cache_probe):sha(cache_probe)},
        new_simulation_intervals=0, model_fits=0)
    dump(out/'operation.json', report)
    try:
        with (out/'reaudit.log').open('xb') as log:
            command = [sys.executable, '-X', 'utf8', '-B', '-m', 'workflows.package_projected_repair_v38',
                'audit-child', '--directory', str(directory), '--raw', str(raw),
                '--archive-sha', sha(raw.parent/'preflight-evidence.tar.gz')]
            code = subprocess.run(command, cwd=package['source_root'], stdout=log, stderr=subprocess.STDOUT,
                timeout=cap-5, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1')).returncode
        if code:
            raise ValueError('repair_reaudit_failed')
        report.update(status='repair_reaudit_passed', audit_sha256=sha(out/'parent-preflight-audit.json'))
    finally:
        seconds = time.monotonic()-started
        report.update(native_exit=code, seconds=seconds, charged_seconds=prior_seconds+seconds)
        dump(out/'operation.json', report)
    shutil.copyfile(parent_budget, out/'parent-budget.json')
    return report


def freeze(directory):
    directory = Path(directory).resolve(); package = read(directory/'package.json')
    root, source = Path(package['origin_root']), Path(package['source_root'])
    operation = read(directory/'reaudit/operation.json')
    if operation.get('status') != 'repair_reaudit_passed' or operation.get('native_exit') != 0:
        raise ValueError('repair_reaudit_not_passed')
    tests = {}
    for role, expected in (('root', root), ('clone', source)):
        p = directory/('preflight-'+role); record = read(p/'tests.json')
        if (record.get('status') != 'source_tests_passed' or record.get('native_exit') != 0
                or record['root'] != str(expected) or record['log_sha256'] != sha(p/'tests.log')
                or record['tests'] != read(source/'scripts/phase8_4_projected_v38_tests.json')['tests']):
            raise ValueError('repair_tests_not_passed')
        tests[role] = record
    manifest = read(source/'SOURCE_MANIFEST.json')
    if (git(source, 'rev-parse', 'HEAD') != package['source_commit']
            or git(source, 'status', '--porcelain=v1', '--untracked-files=all')
            or sha(package['bundle_path']) != package['bundle_sha256']
            or any(sha(source/n) != h or sha(root/n) != manifest['origin_files_sha256'][n]
                   for n, h in manifest['files_sha256'].items())):
        raise ValueError('repair_tested_source_changed')
    old_inputs = Path(package['parent_package'])/'inputs'
    parent_budget = read(directory/'reaudit/parent-budget.json')
    audit = directory/'reaudit/parent-preflight-audit.json'
    if sha(audit) != operation['audit_sha256'] or sha(directory/'reaudit/parent-budget.json') != operation['parent_budget_sha256']:
        raise ValueError('repair_reaudit_changed')
    # Metadata does not depend on the successor freeze: avoid a circular hash.
    preview = recover_numeric_pullback(parent_budget, '0'*64, preflight_audit_sha256=sha(audit),
                                      diagnostic_seconds=operation['charged_seconds'])
    inputs = directory/'inputs'; inputs.mkdir(exist_ok=False)
    for name in ('protocol.json', 'evaluation-policy.json', 'policy.json', 'model-manifest.json', 'historical-budget.json'):
        shutil.copyfile(old_inputs/name, inputs/name)
    shutil.copyfile(old_inputs/'authorization.json', inputs/'authorization-parent.json')
    shutil.copyfile(directory/'reaudit/parent-budget.json', inputs/'parent-budget.json')
    shutil.copyfile(audit, inputs/'parent-preflight-audit.json')
    dump(inputs/'numeric-recovery.json', preview['numeric_recovery'])
    dump(inputs/'numeric-diagnostics.json', operation)
    dump(inputs/'local-readiness.json', dict(status='local_source_package_checks_passed',
        source_commit=package['source_commit'], bundle_sha256=package['bundle_sha256'], tests=tests, simulation_evidence=False))
    frozen = dict(read(old_inputs/'freeze.json'), schema='projected-formal-v38-numeric-repair-before-validation',
        source_commit=package['source_commit'], source_manifest_sha256=sha(source/'SOURCE_MANIFEST.json'),
        local_readiness_sha256=sha(inputs/'local-readiness.json'), numeric_recovery_sha256=sha(inputs/'numeric-recovery.json'),
        numeric_diagnostics_sha256=sha(inputs/'numeric-diagnostics.json'), parent_freeze_sha256=package['parent_freeze_sha256'])
    dump(inputs/'freeze.json', frozen)
    budget = recover_numeric_pullback(parent_budget, sha(inputs/'freeze.json'), preflight_audit_sha256=sha(audit),
                                     diagnostic_seconds=operation['charged_seconds'])
    dump(inputs/'budget.json', budget)
    dump(inputs/'authorization-pending.json', dict(schema='projected-formal-v38-numeric-amendment', decision='pending',
        authorized_by=None, approval_reference=None, freeze_sha256=sha(inputs/'freeze.json'),
        parent_freeze_sha256=package['parent_freeze_sha256'], parent_authorization_sha256=sha(inputs/'authorization-parent.json'),
        resource_cap=protocol()['resource_cap']))
    verify_snapshot(source, inputs, package['source_commit'])
    package.update(status='tested_numeric_repair_frozen', freeze_sha256=sha(inputs/'freeze.json'),
        root_tests=tests['root']['summary'], clone_tests=tests['clone']['summary'], reuses_original_preflight=True)
    dump(directory/'package.json', package)
    return package


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=('build', 'reaudit', 'audit-child', 'freeze'))
    p.add_argument('--directory', required=True); p.add_argument('--root'); p.add_argument('--parent')
    p.add_argument('--raw'); p.add_argument('--archive-sha'); p.add_argument('--parent-budget')
    p.add_argument('--diagnostics'); p.add_argument('--cache-probe')
    args = p.parse_args()
    if args.action == 'build': result = build(args.root, args.parent, args.directory)
    elif args.action == 'freeze': result = freeze(args.directory)
    elif args.action == 'audit-child': result = audit_child(args.directory, args.raw, args.archive_sha)
    else: result = reaudit(args.directory, args.raw, args.parent_budget, args.diagnostics, args.cache_probe)
    print(json.dumps(result, indent=2))

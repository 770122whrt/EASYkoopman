"""Freeze a resource-only successor without copying immutable USD asset contents."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil

from workflows.package_projected_v38 import dump, git
from workflows.package_projected_validation_repair_v38 import tested_package
from workflows.projected_resource_v38 import SCHEMA, amend_budget, amended_limits, validate_approval, storage_usage
from workflows.projected_release_v38 import read, sha, verify_bundle

ASSETS = ('easyuuv_nc/data/embodiment/embodiment.usd',
          'easyuuv_nc/data/embodiment/Props/instanceable_meshes.usd')
CHANGES = frozenset({
    'workflows/projected_resource_v38.py', 'workflows/package_projected_resource_v38.py',
    'workflows/projected_budget_v38.py', 'workflows/projected_release_v38.py',
    'workflows/projected_archive_v38.py', 'workflows/run_projected_formal_v38.py',
    'workflows/evaluate_projected_formal_v38.py', 'tests/test_projected_resource_v38.py',
    'scripts/phase8_4_projected_v38_tests.json', 'scripts/phase8_4_projected_v38_server.sh',
    'docs/phase8_4_projected_formal_v38_runbook.md'})


def validate_resource_change(name, before, after):
    if before == after:
        return
    if name not in CHANGES:
        raise ValueError('resource_changes_scientific_source:'+name)
    if name in ('workflows/evaluate_projected_formal_v38.py', 'workflows/run_projected_formal_v38.py'):
        class UndoCap(ast.NodeTransformer):
            def visit_Subscript(self, node):
                if ast.dump(node, include_attributes=False) == ast.dump(ast.parse(
                        "resource_limits(budget)['analysis_seconds']", mode='eval').body, include_attributes=False):
                    return ast.Constant(value=3600)
                return self.generic_visit(node)
        tree = ast.parse(after)
        tree.body = [n for n in tree.body if not (isinstance(n, ast.ImportFrom)
                     and n.module == 'workflows.projected_resource_v38')]
        tree = UndoCap().visit(tree)
        if ast.dump(ast.parse(before), include_attributes=False) != ast.dump(tree, include_attributes=False):
            raise ValueError('resource_changes_scientific_source:'+name)


def build(root, parent, directory):
    root, parent, directory = (Path(p).resolve() for p in (root, parent, directory))
    if directory.exists() or not directory.is_relative_to(root/'.pytest-tmp'):
        raise ValueError('resource_package_destination')
    old = read(parent/'package.json'); base = Path(old['source_root'])
    before = read(base/'SOURCE_MANIFEST.json')['files_sha256']
    if (git(base, 'rev-parse', 'HEAD') != old['source_commit']
            or git(base, 'status', '--porcelain=v1', '--untracked-files=all')
            or any(sha(base/n) != h for n, h in before.items())):
        raise ValueError('resource_parent_source_changed')
    names = sorted(set(before) | CHANGES)
    payloads, hashes, origin = {}, {}, {}
    for name in names:
        p = root/name
        if p.is_symlink() or not p.resolve().is_relative_to(root):
            raise ValueError('resource_source_path')
        data = p.read_bytes(); origin[name] = sha(p)
        if name.endswith('.sh'): data = data.replace(b'\r\n', b'\n')
        validate_resource_change(name, (base/name).read_bytes() if name in before else b'', data)
        payloads[name] = data; hashes[name] = hashlib.sha256(data).hexdigest()
    directory.mkdir(); source = directory/'source'
    # No old file is unlinked or rewritten. New hardlinks are created only at
    # previously absent destinations and only for hash-identical frozen assets.
    git(directory, 'clone', '--shared', '--no-checkout', str(base), str(source))
    git(source, 'symbolic-ref', 'HEAD', 'refs/heads/phase84-projected-v38-r23')
    git(source, 'update-ref', 'HEAD', old['source_commit'])
    git(source, 'read-tree', old['source_commit'])
    for name, data in payloads.items():
        p = source/name; p.parent.mkdir(parents=True, exist_ok=True)
        if name in ASSETS:
            if hashes[name] != before[name]: raise ValueError('resource_shared_asset_changed')
            os.link(base/name, p)
        else:
            p.write_bytes(data)
    dump(source/'SOURCE_MANIFEST.json', dict(schema='phase8.4-isolated-source-snapshot-v1',
        origin_head=git(root, 'rev-parse', 'HEAD'), origin_branch=git(root, 'branch', '--show-current'),
        purpose='Approved +900s analysis resource amendment; physics/models/scoring unchanged',
        files_sha256=hashes, origin_files_sha256=origin, parent_source_commit=old['source_commit'],
        parent_source_manifest_sha256=sha(base/'SOURCE_MANIFEST.json'), immutable_shared_assets=list(ASSETS)))
    changed = sorted({n for n in names if hashes[n] != before.get(n)} | {'SOURCE_MANIFEST.json'})
    for start in range(0, len(changed), 25): git(source, 'add', '-f', '--', *changed[start:start+25])
    git(source, '-c', 'user.name=EasyUUV source packaging', '-c', 'user.email=source-package@localhost',
        'commit', '-m', 'r23 approved analysis budget amendment; preserve frozen validation evidence')
    commit = git(source, 'rev-parse', 'HEAD')
    bundle = directory/'EasyUUV-projected-v38-r23-delta.bundle'
    git(source, 'bundle', 'create', str(bundle), 'HEAD', '^'+old['source_commit'])
    git(source, 'bundle', 'verify', str(bundle))
    if git(source, 'status', '--porcelain=v1', '--untracked-files=all'):
        raise ValueError('resource_source_not_clean')
    if any(sha(base/n) != h for n, h in before.items()):
        raise ValueError('resource_parent_source_changed')
    record = dict(status='resource_source_ready_tests_pending', origin_root=str(root), source_root=str(source),
        clone_root=str(source), parent_package=str(parent), parent_source_commit=old['source_commit'],
        source_commit=commit, source_manifest_sha256=sha(source/'SOURCE_MANIFEST.json'),
        source_files=len(hashes), changed_files=changed, bundle_path=str(bundle), bundle_sha256=sha(bundle),
        bundle_bytes=bundle.stat().st_size, bundle_requires_parent=True, model_fits=0, formal_release=False,
        storage=storage_usage([base, source]))
    dump(directory/'package.json', record)
    return record


def freeze(directory, evidence):
    directory, evidence = Path(directory).resolve(), Path(evidence).resolve()
    package, tests = tested_package(directory)
    source = Path(package['source_root']); old = Path(package['parent_package'])/'inputs'
    approval_path = evidence/'analysis-budget-amendment-approval.json'
    prior_path = evidence/'live-budget.json'; audit_path = evidence/'validation-analysis-audit.json'
    approval = read(approval_path); validate_approval(approval)
    prior = read(prior_path); parent = read(old/'freeze.json')
    if (approval['parent_freeze_sha256'] != sha(old/'freeze.json')
            or approval['parent_settled_budget_sha256'] != sha(prior_path)
            or approval['independent_validation_audit_sha256'] != sha(audit_path)):
        raise ValueError('resource_approval_evidence_changed')
    preview = amend_budget(prior, '0'*64, approval_sha256=sha(approval_path),
        parent_budget_sha256=sha(prior_path), validation_audit_sha256=sha(audit_path))
    inputs = directory/'inputs'; inputs.mkdir(exist_ok=False)
    from workflows.projected_archive_v38 import RECOVERY_INPUT_FILES, VALIDATION_RECOVERY_INPUT_FILES
    for name in ('protocol.json', 'evaluation-policy.json', 'policy.json', 'model-manifest.json',
                 'historical-budget.json', *RECOVERY_INPUT_FILES, *VALIDATION_RECOVERY_INPUT_FILES):
        shutil.copyfile(old/name, inputs/name)
    for original, name in ((old/'freeze.json', 'resource-parent-freeze.json'),
            (old/'authorization.json', 'resource-parent-authorization.json'), (prior_path, 'resource-parent-budget.json'),
            (approval_path, 'resource-approval.json'), (audit_path, 'validation-analysis-audit.json')):
        shutil.copyfile(original, inputs/name)
    shutil.copyfile(inputs/'parent-validation-audit.json', inputs/'validation-pullback.json')
    dump(inputs/'resource-amendment.json', preview['resource_amendment'])
    dump(inputs/'local-readiness.json', dict(status='local_source_package_checks_passed',
        source_commit=package['source_commit'], bundle_sha256=package['bundle_sha256'], tests=tests, simulation_evidence=False))
    frozen = dict(parent, schema=SCHEMA, source_commit=package['source_commit'],
        source_manifest_sha256=sha(source/'SOURCE_MANIFEST.json'), local_readiness_sha256=sha(inputs/'local-readiness.json'),
        resource_parent_source_commit=parent['source_commit'], resource_parent_freeze_sha256=sha(old/'freeze.json'),
        resource_amendment_sha256=sha(inputs/'resource-amendment.json'))
    dump(inputs/'freeze.json', frozen)
    budget = amend_budget(prior, sha(inputs/'freeze.json'), approval_sha256=sha(approval_path),
        parent_budget_sha256=sha(prior_path), validation_audit_sha256=sha(audit_path))
    dump(inputs/'budget.json', budget)
    dump(inputs/'authorization.json', dict(schema='projected-formal-v38-resource-amendment', decision='approved',
        authorized_by='user', approval_reference=approval['approval_reference']+': '+approval['user_reply'],
        freeze_sha256=sha(inputs/'freeze.json'), resource_cap=amended_limits(),
        parent_freeze_sha256=sha(old/'freeze.json'), parent_authorization_sha256=sha(inputs/'resource-parent-authorization.json'),
        approval_sha256=sha(approval_path)))
    verify_bundle(source, inputs, package['source_commit'])
    package.update(status='tested_resource_amendment_frozen', freeze_sha256=sha(inputs/'freeze.json'),
        root_tests=tests['root']['summary'], clone_tests=tests['clone']['summary'],
        preserved_attempts=len(prior['attempts']), charged_seconds=budget['charged_seconds'], analysis_cap_seconds=4500)
    dump(directory/'package.json', package)
    return package


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('action', choices=('build', 'freeze'))
    p.add_argument('--root'); p.add_argument('--parent'); p.add_argument('--directory', required=True); p.add_argument('--evidence')
    a = p.parse_args()
    result = build(a.root, a.parent, a.directory) if a.action == 'build' else freeze(a.directory, a.evidence)
    print(json.dumps(result, indent=2))

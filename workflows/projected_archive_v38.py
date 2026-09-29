"""Archive and independently recheck real formal traces. Never synthesize success."""
import argparse
import ast
from contextlib import contextmanager
import hashlib
import io
import json
import math
from pathlib import Path
import re
import tarfile
import time

from workflows.formal_evidence_v25 import unpack_verified, verify_raw
from workflows.projected_adapter_v38 import load_episode
from workflows.projected_budget_v38 import reserve, settle, validate_budget, write_budget
from workflows.projected_protocol_v38 import cases, digest, guarded_exit_code, protocol
from workflows.projected_release_v38 import read, sha, verify_bundle, validate_validation_result
from workflows.projected_resource_v38 import resource_limits
from workflows.run_projected_formal_v38 import check_disk, disk_bytes

INPUT_FILES = ('freeze.json', 'authorization.json', 'protocol.json', 'evaluation-policy.json',
               'policy.json', 'historical-budget.json', 'local-readiness.json', 'model-manifest.json', 'budget.json')

# A numerical audit repair may advance operation/test files, never the plant,
# controller, adapter, predictor, model bytes, protocol or scientific gates.
AUDIT_REPAIR_FILES = frozenset({
    'workflows/projected_archive_v38.py', 'workflows/audit_projected_v38.py',
    'workflows/projected_budget_v38.py', 'workflows/projected_release_v38.py',
    'workflows/package_projected_repair_v38.py',
    'workflows/evaluate_projected_formal_v38.py',
    'workflows/package_projected_validation_repair_v38.py',
    'tests/test_projected_archive_v38.py', 'tests/test_projected_audit_v38.py',
    'tests/test_projected_budget_v38.py', 'tests/test_projected_release_v38.py',
    'tests/test_projected_repair_v38.py',
    'scripts/phase8_4_projected_v38_server.sh', 'scripts/phase8_4_projected_v38_tests.json',
    'docs/phase8_4_projected_formal_v38_runbook.md',
    'docs/phase8_4_projected_formal_v38_proposal.md',
})
RECOVERY_INPUT_FILES = ('numeric-recovery.json', 'parent-budget.json',
                        'parent-preflight-audit.json', 'numeric-diagnostics.json', 'authorization-parent.json')
VALIDATION_RECOVERY_INPUT_FILES = ('validation-numeric-recovery.json', 'validation-parent-budget.json',
    'parent-validation-audit.json', 'validation-numeric-diagnostics.json', 'parent-freeze.json')

# A maximum residual can change by at most the pointwise reconstruction change.
# Keep these shared with cache verification instead of imposing a tighter,
# unrelated residual-summary allowance on the same command reconstruction.
ROTOR_RECOMPUTATION_ATOL = 1e-4
WRENCH_RECOMPUTATION_ATOL = 1e-5


def validate_audit_only_change(name, before, after):
    if before==after:
        return
    if name not in AUDIT_REPAIR_FILES:
        raise ValueError('repair_changes_scientific_source:'+name)
    if name=='workflows/evaluate_projected_formal_v38.py':
        # Only worker identity wiring may advance; scoring and scheduling stay.
        def scientific_tree(payload):
            tree=ast.parse(payload)
            tree.body=[n for n in tree.body if not isinstance(n,ast.FunctionDef) or n.name!='work']
            return ast.dump(tree,include_attributes=False)
        if scientific_tree(before)!=scientific_tree(after):
            raise ValueError('repair_changes_scientific_source:'+name)


def compare_semantic_summaries(server, local):
    """Compare derived measurements after both original physics checks pass.

    Counts, identities, limits and decisions stay exact. Reconstructed causal
    residuals involve float32 allocation and rotor history; their agreement
    allowance is 10% (control/PWM/rotor) or 1% (wrench) of the UNCHANGED physical
    rejection bounds. Other listed reductions allow only float64 roundoff.
    This comparison does not replace load_episode or qualify a failed trace.
    """
    reductions = {('/'+name): (1e-12, 1e-9) for name in (
        'minimum_hull_clearance_m', 'maximum_velocity_balance_residual_m_s',
        'minimum_pwm_headroom', 'minimum_deadzone_distance_pwm')}
    for name in ('linear_speed_m_s', 'angular_speed_rad_s', 'tilt_rad',
                 'horizontal_displacement_m', 'vertical_displacement_m'):
        reductions['/maximum_motion/'+name] = (1e-12, 1e-9)
    for name in ('linear_speed_m_s', 'angular_speed_rad_s', 'tilt_rad'):
        reductions['/tail/maximum/'+name] = (1e-12, 1e-9)
    for i in range(6):
        reductions['/maximum_allocation_acceleration_error_6/'+str(i)] = (1e-12, 1e-9)
    causal_limits = {}
    for i, (atol, limit) in enumerate(zip((1e-7, 1e-7, ROTOR_RECOMPUTATION_ATOL,
                                          WRENCH_RECOMPUTATION_ATOL), (1e-6, 1e-6, 1e-3, 1e-3))):
        path = '/maximum_control_pwm_speed_wrench_errors/'+str(i)
        reductions[path] = (atol, 0.)
        causal_limits[path] = limit
    differences = []

    def fail(path):
        raise ValueError('formal_pullback_semantic_recomputation:'+path)

    def compare(left, right, path=''):
        if type(left) is not type(right):
            fail(path)
        if isinstance(left, dict):
            if left.keys() != right.keys():
                fail(path)
            for key in sorted(left):
                compare(left[key], right[key], path+'/'+key)
        elif isinstance(left, list):
            if len(left) != len(right):
                fail(path)
            for i, (a, b) in enumerate(zip(left, right)):
                compare(a, b, path+'/'+str(i))
        elif type(left) is float:
            if not math.isfinite(left) or not math.isfinite(right):
                fail(path)
            if path in causal_limits and not (0 <= left <= causal_limits[path] and 0 <= right <= causal_limits[path]):
                fail(path)
            atol, rtol = reductions.get(path, (0., 0.))
            allowed = atol+rtol*max(abs(left), abs(right))
            difference = abs(left-right)
            if difference > allowed:
                fail(path)
            if difference:
                differences.append(dict(path=path, server=left, local=right,
                    absolute_difference=difference, allowed_difference=allowed))
        elif left != right:
            fail(path)

    compare(server, local)
    return dict(policy='semantic-numeric-agreement-v1', differences=differences)


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False,
        default=lambda a: a.tolist())+'\n', encoding='utf8')


@contextmanager
def accounted_analysis(budget_path, name):
    budget_path = Path(budget_path)
    before = read(budget_path)
    remaining = resource_limits(before)['analysis_seconds']-before['charged_seconds']['analysis']
    if remaining < 30:
        raise ValueError('formal_evidence_analysis_budget')
    budget = reserve(before, 'analysis', name, remaining)
    write_budget(budget_path, budget)
    started, code = time.monotonic(), 1
    try:
        yield started+remaining-5
        if time.monotonic()-started >= remaining:
            raise TimeoutError('formal_evidence_analysis_budget')
        code = 0
    finally:
        budget = settle(budget, 'analysis', name, time.monotonic()-started, code)
        write_budget(budget_path, budget)


def validate_inventory_identity(inventory, role, source, freeze_sha):
    expected = dict(schema='projected-formal-v38-archive', role=role, source_commit=source,
                    freeze_sha256=freeze_sha, protocol_digest=digest(protocol()), cases=cases(role))
    if any(inventory.get(k) != v for k, v in expected.items()):
        raise ValueError('formal_archive_identity')


def verify_runtime(directory):
    directory = Path(directory)
    patch = 'd056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079'
    release = '0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20'
    expected = {'conda_environment.txt': 'isaaclab',
        'python_executable.txt': '/opt/conda/envs/isaaclab/bin/python3.11',
        'isaaclab_release_tag.txt': 'v2.2.1', 'isaaclab_release_commit.txt': release,
        'isaaclab_repo_parent_commit.txt': release,
        'isaaclab_repo_commit.txt': 'c91a125c73c8b574878419a9583afc0b63b99f0a',
        'isaaclab_repo_patch.sha256': patch, 'isaaclab_version_file.txt': '2.2.1',
        'isaaclab_repo_dirty_files.txt': 'source/isaaclab_mimic/setup.py\nsource/isaaclab_rl/setup.py'}
    # The activated Python is recorded after realpath by the server preflight.
    for name, value in expected.items():
        if (directory/name).read_text(encoding='utf8').strip() != value:
            raise ValueError('formal_runtime_capture:'+name)
    if (directory/'preflight_failure.txt').exists() or sha(directory/'logs/isaaclab_repo_diff.patch') != patch:
        raise ValueError('formal_runtime_preflight_failed')
    for name in ('setuptools_version.txt', 'logs/python_version.log',
                 'logs/setuptools_version.log', 'logs/editable_install.log'):
        if not (directory/name).is_file() or not (directory/name).stat().st_size:
            raise ValueError('formal_runtime_capture:'+name)
    return {p.relative_to(directory).as_posix(): sha(p) for p in directory.rglob('*') if p.is_file()}


def archive_stage(root, transfer, role):
    root, transfer = Path(root), Path(transfer)
    selected = cases(role)
    source = read(transfer/'freeze.json')['source_commit']
    verify_bundle(root, transfer, source)
    freeze_sha = sha(transfer/'freeze.json')
    status = read(transfer/role/'stage-status.json')
    if (status.get('role') != role or status.get('source_commit') != source
            or status.get('freeze_sha256') != freeze_sha or status.get('status') not in
                ('projected_formal_stage_completed_pending_pullback', 'failed')):
        raise ValueError('formal_archive_stage_pending_or_foreign')
    destination = transfer/(role+'-evidence.tar.gz')
    if destination.exists():
        raise ValueError('formal_archive_already_exists')
    inventory = dict(schema='projected-formal-v38-archive', role=role, source_commit=source,
        freeze_sha256=freeze_sha, protocol_digest=digest(protocol()), cases=selected, files={})
    with accounted_analysis(transfer/'budget.json', 'archive:'+role) as deadline:
        paths = {'source/'+name: root/name for name in read(root/'SOURCE_MANIFEST.json')['files_sha256']}
        paths['source/SOURCE_MANIFEST.json'] = root/'SOURCE_MANIFEST.json'
        paths.update({'inputs/'+name: transfer/name for name in INPUT_FILES})
        if read(transfer/'freeze.json').get('numeric_recovery_sha256'):
            paths.update({'inputs/'+name: transfer/name for name in RECOVERY_INPUT_FILES})
        if read(transfer/'freeze.json').get('validation_numeric_recovery_sha256'):
            paths.update({'inputs/'+name: transfer/name for name in VALIDATION_RECOVERY_INPUT_FILES})
        if read(transfer/'freeze.json').get('resource_amendment_sha256'):
            from workflows.projected_resource_v38 import INPUT_FILES as RESOURCE_INPUT_FILES
            paths.update({'inputs/'+name: transfer/name for name in RESOURCE_INPUT_FILES})
        paths.update({role+'/'+p.relative_to(transfer/role).as_posix(): p
                      for p in (transfer/role).rglob('*') if p.is_file()})
        runtime_dir = transfer/('runtime-'+role)
        if not runtime_dir.is_dir():
            raise ValueError('formal_runtime_preflight_evidence_missing')
        verify_runtime(runtime_dir)
        paths.update({'runtime/'+p.relative_to(runtime_dir).as_posix(): p
                      for p in runtime_dir.rglob('*') if p.is_file()})
        for name, path in paths.items():
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) and not path.resolve().is_relative_to(transfer.resolve()):
                raise ValueError('formal_archive_path')
            inventory['files'][name] = dict(bytes=path.stat().st_size, sha256=sha(path))
        total = sum(v['bytes'] for v in inventory['files'].values())
        # Conservative admission allows room for a worst-case uncompressed archive.
        if disk_bytes(root, transfer)+total >= 4*1024**3:
            raise ValueError('formal_archive_disk_budget')
        with tarfile.open(destination, 'x:gz') as tar:
            for name, path in sorted(paths.items()):
                if time.monotonic() >= deadline:
                    raise TimeoutError('formal_archive_deadline')
                if sha(path) != inventory['files'][name]['sha256']:
                    raise ValueError('formal_archive_source_changed')
                tar.add(path, arcname=name, recursive=False)
            data = (json.dumps(inventory, indent=2)+'\n').encode()
            item = tarfile.TarInfo('inventory.json');item.size = len(data)
            tar.addfile(item, io.BytesIO(data))
        check_disk(root, transfer)
    result = dict(status='archived_pending_independent_pullback', role=role, source_commit=source,
        archive_sha256=sha(destination), archive_bytes=destination.stat().st_size,
        unpacked_bytes=total, remote_new_work_bytes=disk_bytes(root, transfer),
        budget_sha256=sha(transfer/'budget.json'), model_handoff=False)
    dump(transfer/(role+'-archive.json'), result)
    return result


def _running_code_matches(source, auditor_revision=None):
    running_root = Path(__file__).resolve().parents[1]
    if auditor_revision is not None:
        r = auditor_revision
        if (not isinstance(r, dict) or r.get('schema') != 'projected-v38-auditor-revision'
                or any(not isinstance(r.get(k), str) or re.fullmatch('[a-f0-9]{40}', r[k]) is None
                       for k in ('parent_source_commit', 'auditor_source_commit'))
                or not isinstance(r.get('parent_freeze_sha256'), str)
                or re.fullmatch('[a-f0-9]{64}', r['parent_freeze_sha256']) is None
                or sha(source/'SOURCE_MANIFEST.json') != r.get('parent_source_manifest_sha256')
                or sha(running_root/'SOURCE_MANIFEST.json') != r.get('auditor_source_manifest_sha256')):
            raise ValueError('formal_auditor_revision_identity')
        before = read(source/'SOURCE_MANIFEST.json')['files_sha256']
        after = read(running_root/'SOURCE_MANIFEST.json')['files_sha256']
        if not set(before) <= set(after):
            raise ValueError('formal_auditor_revision_missing_source')
        for name, h in after.items():
            path = (running_root/name).resolve()
            if (not path.is_relative_to(running_root) or '..' in Path(name).parts or ':' in name
                    or sha(path) != h or (before.get(name) != h and name not in AUDIT_REPAIR_FILES)):
                raise ValueError('formal_auditor_revision_source:'+name)
            if before.get(name)!=h and name=='workflows/evaluate_projected_formal_v38.py':
                validate_audit_only_change(name,(source/name).read_bytes(),path.read_bytes())
        return
    for name, h in read(source/'SOURCE_MANIFEST.json')['files_sha256'].items():
        if name.endswith('.py') and sha(running_root/name) != h:
            raise ValueError('formal_pullback_running_code_changed:'+name)


def audit_raw(raw, role, expected_archive_sha, *, auditor_revision=None):
    raw = Path(raw)
    inventory = read(raw/'inventory.json')
    verify_raw(raw, inventory)
    source = inventory['source_commit']
    freeze_sha = sha(raw/'inputs/freeze.json')
    validate_inventory_identity(inventory, role, source, freeze_sha)
    verify_bundle(raw/'source', raw/'inputs', source)
    _running_code_matches(raw/'source', auditor_revision) if auditor_revision is not None else _running_code_matches(raw/'source')
    if auditor_revision is not None and (role not in ('preflight', 'validation')
            or auditor_revision['parent_source_commit'] != source
            or auditor_revision['parent_freeze_sha256'] != freeze_sha):
        raise ValueError('formal_auditor_revision_parent')
    runtime_hashes = verify_runtime(raw/'runtime')
    status = read(raw/role/'stage-status.json')
    if (status.get('role') != role or status.get('source_commit') != source
            or status.get('freeze_sha256') != freeze_sha):
        raise ValueError('formal_pullback_stage_identity')
    if status.get('status') == 'failed':
        # Preserve the complete failed archive; do not promote a usable prefix.
        return dict(status='rejected_formal_stage_archive_preserved', role=role, source_commit=source,
            freeze_sha256=freeze_sha, archive_sha256=expected_archive_sha, exception=status.get('exception'),
            accepted_data=False, model_handoff=False)
    selected = cases(role)
    ids = {q['run_id'] for q in selected}
    if (status.get('status') != 'projected_formal_stage_completed_pending_pullback'
            or len(status.get('accepted', [])) != len(ids) or set(status['accepted']) != ids
            or status.get('rejected') != [] or set(status.get('trace_sha256', {})) != ids):
        raise ValueError('formal_pullback_stage_inventory')
    semantic_sha, recomputation = {}, {}
    for q in selected:
        name = q['run_id'];directory = raw/role/name
        trace_path = directory/'trace.json';trace_hash = sha(trace_path)
        if trace_hash != status['trace_sha256'][name]:
            raise ValueError('formal_pullback_trace_binding')
        trace = read(trace_path);exits = read(directory/'collector-exit.json')
        if ((raw/role/(name+'.exit_status')).read_text().strip() != '0'
                or guarded_exit_code(exits.get('child_native_exit'), trace, q, source) != 0
                or type(exits.get('guarded_collector_exit')) is not int or exits['guarded_collector_exit'] != 0
                or exits.get('trace_sha256') != trace_hash):
            raise ValueError('formal_pullback_native_exit')
        # Recompute physics, role, backend and ordered command-memory acceptance.
        episode = load_episode(trace_path, q, source, trace_hash, raw/'source')
        check = json.loads(json.dumps(episode.acceptance, default=lambda a: a.tolist()))
        if role == 'preflight' and not check['tail']['eligible_for_excitation']:
            raise ValueError('formal_pullback_preflight_tail')
        semantic_path = raw/role/(name+'.validation.json')
        recomputation[name] = compare_semantic_summaries(read(semantic_path), check)
        semantic_sha[name] = sha(semantic_path)
    return dict(status='projected_formal_source_runtime_inventory_pullback_accepted', role=role,
        source_commit=source, freeze_sha256=freeze_sha, trace_sha256=status['trace_sha256'],
        semantic_sha256=semantic_sha, archive_sha256=expected_archive_sha,
        semantic_recomputation=recomputation,
        **({'auditor_revision': auditor_revision} if auditor_revision is not None else {}),
        validator_sha256=sha(raw/'source/workflows/validate_projected_formal_v38.py'),
        stage_status_sha256=sha(raw/role/'stage-status.json'), training_eligible=False, model_handoff=False,
        runtime_sha256=runtime_hashes,
        physics_ticks=sum(2*q['intervals'] for q in selected))


def accept_archive(directory, role, expected_archive_sha, budget_path, *, remote_bytes):
    """Local pullback: caller must supply freshly measured remote new-work bytes.

    directory is one role under a dedicated new experiment pullback root. The
    separate copied live budget is settled here, then synchronized back by hash.
    """
    directory, budget_path = Path(directory), Path(budget_path)
    cases(role)
    archive = directory/(role+'-evidence.tar.gz')
    if any((directory/name).exists() for name in ('raw', 'acceptance.json', 'rejection.json')):
        raise ValueError('formal_pullback_already_attempted')
    if type(remote_bytes) is not int or remote_bytes < 0 or sha(archive) != expected_archive_sha:
        raise ValueError('formal_pullback_archive_or_disk_receipt')
    with tarfile.open(archive, 'r:gz') as tar:
        expanded = sum(m.size for m in tar.getmembers())
    local_bytes = sum(p.stat().st_size for p in directory.parent.rglob('*') if p.is_file())
    if remote_bytes+local_bytes+expanded >= 4*1024**3:
        raise ValueError('formal_combined_disk_budget')
    with accounted_analysis(budget_path, 'pullback:'+role):
        unpack_verified(archive, directory/'raw', expected_archive_sha)
        result = audit_raw(directory/'raw', role, expected_archive_sha)
        if read(budget_path)['freeze_sha256'] != result['freeze_sha256']:
            raise ValueError('formal_pullback_budget_identity')
    # Success/rejection is published only after accounting completes successfully.
    filename = 'acceptance.json' if result['status'].endswith('pullback_accepted') else 'rejection.json'
    with (directory/filename).open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


def release_test(root, transfer):
    root, transfer = Path(root), Path(transfer)
    source = read(transfer/'freeze.json')['source_commit']
    frozen, manifest = verify_bundle(root, transfer, source)
    from workflows.projected_release_v38 import verify_accepted_stage
    freeze_sha = sha(transfer/'freeze.json')
    acceptance = verify_accepted_stage(root, transfer, 'validation', source, freeze_sha)
    from workflows.projected_release_v38 import stage_identity, analysis_identity, analysis_directory
    directory = analysis_directory(transfer, 'validation')
    result_path, scores_path = directory/'result.json', directory/'scores.json'
    validate_validation_result(read(result_path), read(scores_path), manifest, acceptance,
        *analysis_identity(frozen, 'validation', freeze_sha),
        data_identity=stage_identity(read(transfer/'freeze.json'),'validation',freeze_sha))
    from workflows.projected_release_v38 import verify_analysis_audit
    verify_analysis_audit(transfer, 'validation', source, freeze_sha)
    validate_budget(read(transfer/'budget.json'), freeze_sha)
    record = dict(status='released_prespecified_test_after_validation_GO', source_commit=source,
        freeze_sha256=freeze_sha, validation_result_sha256=sha(result_path), validation_scores_sha256=sha(scores_path),
        validation_acceptance_sha256=sha(transfer/'validation-pullback.json'),
        model_manifest_sha256=sha(transfer/'model-manifest.json'), test_cases=[q['run_id'] for q in cases('test')])
    record['validation_audit_sha256'] = sha(transfer/'validation-analysis-audit.json')
    with (transfer/'test-release.json').open('x', encoding='utf8') as stream:
        json.dump(record, stream, indent=2)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('archive', 'accept', 'release-test'))
    parser.add_argument('--stage', choices=('preflight', 'validation', 'test'))
    parser.add_argument('--transfer')
    parser.add_argument('--directory')
    parser.add_argument('--sha256')
    parser.add_argument('--budget')
    parser.add_argument('--remote-bytes', type=int)
    args = parser.parse_args();root = Path(__file__).resolve().parents[1]
    if args.action == 'archive':
        result = archive_stage(root, args.transfer, args.stage)
    elif args.action == 'accept':
        result = accept_archive(args.directory, args.stage, args.sha256, args.budget, remote_bytes=args.remote_bytes)
    else:
        result = release_test(root, args.transfer)
    print(json.dumps(result, indent=2))

"""Build/test a clean isolated source bundle; never commit the working repository."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from workflows.projected_models_v38 import ANCHOR, build_manifest
from workflows.projected_protocol_v38 import protocol
from workflows.projected_evaluation_v38 import policy
from workflows.feedback_v31 import parameters
from workflows.projected_release_v38 import read, sha, verify_snapshot
from workflows.projected_budget_v38 import initial_budget

HISTORY = (
    'docs/evidence/phase8_4/identification-fit-20260913-r17/analysis-budget.json',
    'docs/evidence/phase8_4/server-validation-20260913-r19/validation/raw/budget.json',
    'source/results/phase8.4-controlled-lift-v33-20260913/budget.json',
    'source/results/phase8.4-state-projection-v34-20260913/budget.json',
    'source/results/phase8.4-kinematic-dictionary-v35-20260913/budget.json',
    'docs/evidence/phase8_4/command-prediction-v37-20260913/budget.json',
)


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf8')


def git(directory, *args):
    return subprocess.run(['git', '-c', 'core.excludesFile=', '-c', 'core.autocrlf=false',
        '-c', 'core.longpaths=true', '-c', 'commit.gpgsign=false',
        '-c', 'core.hooksPath='+str(Path(directory).resolve()/'.disabled-package-hooks'), *args],
        cwd=directory, check=True, capture_output=True).stdout.decode('utf8').strip()


def build(root, directory):
    root, directory = Path(root).resolve(), Path(directory).resolve()
    if not directory.is_relative_to((root/'.pytest-tmp').resolve()) or directory.exists():
        raise ValueError('formal_package_requires_new_owned_directory')
    manifest = build_manifest(root)
    tracked = git(root, 'ls-files', '-z').split('\0')
    folders = ('easyuuv_nc/', 'koopman/', 'workflows/', 'tests/', 'scripts/')
    names = {p for p in tracked if p.startswith(folders) or '/' not in p and p.endswith('.py')}
    names.update({'.gitignore', '.gitattributes', 'pyproject.toml'})
    for folder in folders:
        names.update(p.relative_to(root).as_posix() for p in (root/folder).rglob('*.py') if '__pycache__' not in p.parts)
    names.update(p.relative_to(root).as_posix() for p in (root/'scripts').glob('*.sh'))
    names = {p for p in names if not p.endswith('.md') and not p.startswith(
        ('easyuuv_nc/docs/', 'easyuuv_nc/artifacts/', 'easyuuv_nc/checkpoints/'))}
    names.update(entry['path'] for entry in manifest['models'].values())
    names.update({ANCHOR,
        'docs/evidence/phase8_4/identification-fit-20260913-r17/cache-inventory.json',
        'docs/evidence/phase8_4/server-identification-20260913-r17/fit/acceptance.json',
        'scripts/phase8_4_projected_v38_server.sh', 'scripts/phase8_4_projected_v38_local_preflight.ps1',
        'scripts/phase8_4_projected_v38_tests.json', 'docs/phase8_4_projected_formal_v38_runbook.md',
        'docs/phase8_4_projected_formal_v38_proposal.md'})
    directory.mkdir()
    source = directory/'source';source.mkdir()
    hashes, original, normalized = {}, {}, []
    for name in sorted(names):
        path = root/name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('formal_package_unsafe_source:'+name)
        data = path.read_bytes();original[name] = hashlib.sha256(data).hexdigest()
        if name.endswith('.sh'):
            changed = data.replace(b'\r\n', b'\n')
            if changed != data:
                normalized.append(name)
            data = changed
        target = source/name;target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes(data)
        hashes[name] = sha(target)
    source_manifest = dict(schema='phase8.4-isolated-source-snapshot-v1',
        origin_head=git(root, 'rev-parse', 'HEAD'), origin_branch=git(root, 'branch', '--show-current'),
        purpose='Frozen projected-v38 formal validation; no refitting; no authorization implied',
        files_sha256=hashes, origin_files_sha256=original, shell_files_normalized_to_lf=normalized)
    dump(source/'SOURCE_MANIFEST.json', source_manifest)
    git(source, 'init', '-b', 'phase84-projected-v38-snapshot')
    paths = sorted(names | {'SOURCE_MANIFEST.json'})
    for start in range(0, len(paths), 30):
        git(source, 'add', '-f', '--', *paths[start:start+30])
    git(source, '-c', 'user.name=EasyUUV source packaging', '-c', 'user.email=source-package@localhost',
        'commit', '-m', 'Isolated v38 formal source snapshot; original checkout untouched')
    source_commit = git(source, 'rev-parse', 'HEAD')
    if git(source, 'status', '--porcelain=v1', '--untracked-files=all'):
        raise ValueError('formal_package_source_not_clean')
    bundle = directory/'EasyUUV-projected-v38.bundle'
    git(source, 'bundle', 'create', str(bundle), 'HEAD', 'refs/heads/phase84-projected-v38-snapshot')
    git(source, 'bundle', 'verify', str(bundle))
    clone = directory/'verified-clone';git(directory, 'clone', str(bundle), str(clone))
    for name, h in hashes.items():
        if sha(clone/name) != h:
            raise ValueError('formal_package_clone_hash:'+name)
    if git(clone, 'rev-parse', 'HEAD') != source_commit or git(clone, 'status', '--porcelain=v1', '--untracked-files=all'):
        raise ValueError('formal_package_clone_not_clean')
    record = dict(status='source_bundle_verified_tests_pending', source_commit=source_commit,
        origin_root=str(root), source_root=str(source), clone_root=str(clone), bundle_path=str(bundle),
        bundle_sha256=sha(bundle), bundle_bytes=bundle.stat().st_size, source_files=len(hashes),
        source_manifest_sha256=sha(clone/'SOURCE_MANIFEST.json'), authorization=False, simulation_evidence=False)
    dump(directory/'package.json', record)
    return record


def preflight(root, python, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('formal_preflight_output_exists')
    tests = read(root/'scripts/phase8_4_projected_v38_tests.json')['tests']
    if any(not (root/name).is_file() for name in tests):
        raise ValueError('formal_preflight_test_missing')
    output.mkdir(parents=True)
    command = [str(Path(python).resolve()), '-X', 'utf8', '-B', '-m', 'pytest', '-q', *tests,
               '-p', 'no:cacheprovider', '--basetemp', str(output/'pytest-temp')]
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1',
                       OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    started = time.monotonic()
    result = subprocess.run(command, cwd=root, env=environment, capture_output=True)
    log = (result.stdout+result.stderr).decode('utf8', errors='replace')
    (output/'tests.log').write_text(log, encoding='utf8')
    record = dict(status='source_tests_passed' if result.returncode == 0 else 'source_tests_failed',
        root=str(root), native_exit=result.returncode, seconds=time.monotonic()-started, tests=tests,
        summary=log.strip().splitlines()[-1] if log.strip() else 'no output', log_sha256=sha(output/'tests.log'),
        simulation_evidence=False)
    dump(output/'tests.json', record)
    if result.returncode:
        raise RuntimeError('formal_preflight_tests_failed; see '+str(output/'tests.log'))
    return record


def freeze(directory):
    directory = Path(directory).resolve();package = read(directory/'package.json')
    root, clone = Path(package['origin_root']), Path(package['clone_root'])
    if (directory/'inputs').exists():
        raise ValueError('formal_freeze_already_exists')
    reports = {}
    for role, expected_root in (('root', root), ('clone', clone)):
        location = directory/('preflight-'+role)
        record = read(location/'tests.json')
        if (record.get('native_exit') != 0 or record.get('status') != 'source_tests_passed'
                or record.get('root') != str(expected_root) or record.get('simulation_evidence') is not False
                or record.get('log_sha256') != sha(location/'tests.log')
                or record.get('tests') != read(clone/'scripts/phase8_4_projected_v38_tests.json')['tests']):
            raise ValueError('formal_freeze_tests_not_complete')
        reports[role] = dict(report_sha256=sha(location/'tests.json'), **record)
    if sha(package['bundle_path']) != package['bundle_sha256']:
        raise ValueError('formal_bundle_changed')
    source_manifest = read(clone/'SOURCE_MANIFEST.json')
    for name, h in source_manifest['files_sha256'].items():
        if sha(clone/name) != h or sha(root/name) != source_manifest['origin_files_sha256'][name]:
            raise ValueError('formal_preflight_source_changed:'+name)
    if git(clone, 'rev-parse', 'HEAD') != package['source_commit'] or git(clone, 'status', '--porcelain=v1', '--untracked-files=all'):
        raise ValueError('formal_freeze_clone_not_clean')
    inputs = directory/'inputs';inputs.mkdir()
    objects = {
        'protocol.json': protocol(), 'evaluation-policy.json': policy(), 'policy.json': parameters(),
        'model-manifest.json': build_manifest(clone),
        'historical-budget.json': dict(note='Separate historical ledgers; v37 includes v36, do not sum overlapping ledgers',
            ledgers={name: dict(sha256=sha(root/name), ledger=read(root/name)) for name in HISTORY}),
        'local-readiness.json': dict(status='local_source_package_checks_passed', source_commit=package['source_commit'],
            bundle_sha256=package['bundle_sha256'], tests=reports, simulation_evidence=False),
    }
    for name, value in objects.items():
        dump(inputs/name, value)
    frozen = dict(schema='projected-formal-v38-before-any-new-data', source_commit=package['source_commit'],
        source_manifest_sha256=sha(clone/'SOURCE_MANIFEST.json'), model_fits=0, model_handoff=False)
    bindings = {'protocol_sha256':'protocol.json', 'evaluation_policy_sha256':'evaluation-policy.json',
        'feedback_policy_sha256':'policy.json', 'model_manifest_sha256':'model-manifest.json',
        'historical_budget_sha256':'historical-budget.json', 'local_readiness_sha256':'local-readiness.json'}
    frozen.update({key:sha(inputs/name) for key,name in bindings.items()})
    dump(inputs/'freeze.json', frozen)
    dump(inputs/'budget.json', initial_budget(sha(inputs/'freeze.json')))
    dump(inputs/'authorization-pending.json', dict(schema='projected-formal-v38-new-D23', decision='pending',
        authorized_by=None, approval_reference=None, freeze_sha256=sha(inputs/'freeze.json'), resource_cap=protocol()['resource_cap']))
    verify_snapshot(clone, inputs, package['source_commit'])
    package.update(status='local_package_ready_pending_new_D23', freeze_sha256=sha(inputs/'freeze.json'),
        root_tests=reports['root']['summary'], clone_tests=reports['clone']['summary'], model_manifest_sha256=sha(inputs/'model-manifest.json'))
    dump(directory/'package.json', package)
    return package


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('build', 'preflight', 'freeze'))
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--directory', required=True)
    parser.add_argument('--python')
    args = parser.parse_args()
    if args.action == 'build':
        value = build(args.root, args.directory)
    elif args.action == 'preflight':
        value = preflight(args.root, args.python, args.directory)
    else:
        value = freeze(args.directory)
    print(json.dumps(value, indent=2, ensure_ascii=False))

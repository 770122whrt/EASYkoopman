"""Independent pullback checks for actual v25 stage archives."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import tarfile
from workflows.formal_contract_v25 import proposal,analysis_policy,authorize,digest
from workflows.validate_formal_trace_v25 import validate_trace,DIRECT_RL_SHA


def sha_file(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_name(name):
    path=PurePosixPath(name)
    return bool(name and not path.is_absolute() and '\\' not in name and ':' not in name
                and '..' not in path.parts and path.as_posix()==name)


def verify_raw(raw,inventory):
    expected=inventory['files']
    if any(not _safe_name(name) for name in expected):raise ValueError('formal_raw_path')
    actual={p.relative_to(raw).as_posix() for p in raw.rglob('*') if p.is_file()}
    if actual!=set(expected)|{'inventory.json'}:raise ValueError('formal_raw_inventory')
    for name,item in expected.items():
        path=raw/name
        if path.is_symlink() or not path.resolve().is_relative_to(raw.resolve()):raise ValueError('formal_raw_path')
        if path.stat().st_size!=item['bytes'] or sha_file(path)!=item['sha256']:raise ValueError('formal_raw_hash')


def unpack_verified(archive,raw,expected_sha):
    if sha_file(archive)!=expected_sha:raise ValueError('formal_archive_hash')
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers();names=[m.name for m in members]
        if (len(names)!=len(set(names)) or any(not _safe_name(m.name) or not m.isfile() for m in members)
                or 'inventory.json' not in names):raise ValueError('formal_archive_paths_or_inventory')
        inventory=json.load(tar.extractfile('inventory.json'))
        if set(names)!=set(inventory['files'])|{'inventory.json'}:raise ValueError('formal_archive_inventory')
        if sum(m.size for m in members)>4*1024**3:raise ValueError('formal_archive_size')
        # Verify every byte before reserving the extraction output.
        for name,item in inventory['files'].items():
            value=tar.extractfile(name).read()
            if len(value)!=item['bytes'] or hashlib.sha256(value).hexdigest()!=item['sha256']:
                raise ValueError('formal_archive_member_hash')
        raw.mkdir(exist_ok=False)
        for member in members:
            target=raw/member.name;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as output:output.write(tar.extractfile(member).read())
    verify_raw(raw,inventory)
    return inventory


def cases_for_stage(stage):
    roles={'preflight':['preflight'],'fit-validation':['fit','validation'],'test':['test']}[stage]
    return [case for case in proposal()['entries'] if case['role'] in roles]


def check_stage_raw(raw,stage,approval):
    inventory=json.loads((raw/'inventory.json').read_text());verify_raw(raw,inventory)
    source=approval['source_commit'];cases=cases_for_stage(stage)
    if (inventory['stage']!=stage or inventory['source_commit']!=source or inventory['cases']!=cases
            or inventory['role_protocol_sha256']!=digest(proposal())
            or inventory['analysis_policy_sha256']!=digest(analysis_policy())):raise ValueError('formal_stage_inventory_binding')
    local_approval=json.loads((raw/'inputs/d23_approval.json').read_text())
    if local_approval!=approval:raise ValueError('formal_stage_approval_binding')
    roles=json.loads((raw/'inputs/role_protocol.json').read_text());policy=json.loads((raw/'inputs/analysis_policy.json').read_text())
    status=json.loads((raw/'transfer'/stage/'stage-status.json').read_text())
    if (status['status']!='stage_collection_semantics_passed_pending_inventory_pullback'
            or status['accepted']!=[c['run_id'] for c in cases] or status['source_commit']!=source):raise ValueError('formal_stage_status')
    manifest=json.loads((raw/'source/SOURCE_MANIFEST.json').read_text())
    for name,item in inventory['files'].items():
        if name.startswith('source/') and name not in ('source/SOURCE_MANIFEST.json','source/DirectRLEnv.py'):
            if manifest['files_sha256'][name[len('source/'):]]!=item['sha256']:raise ValueError('formal_stage_source_file')
    if sha_file(raw/'source/DirectRLEnv.py')!=DIRECT_RL_SHA:raise ValueError('formal_stage_runtime_file')
    checks=[]
    for case in cases:
        authorize(roles,policy,approval,source,case['run_id'])
        if (raw/'transfer'/stage/(case['run_id']+'.exit_status')).read_text().strip()!='0':raise ValueError('formal_stage_native_exit')
        path=raw/'results/collection'/case['run_id']/'trace.json';data=json.loads(path.read_text())
        check=validate_trace(data,case,source)
        check.update(trace_sha256=sha_file(path),role=case['role'],configuration=case['configuration'])
        checks.append(check)
    return {'status':'source_runtime_continuity_pullback_accepted','stage':stage,'source_commit':source,
            'approval_sha256':digest(approval),'cases':checks,'files':len(inventory['files']),
            'intervals':sum(c['intervals'] for c in cases),'model_handoff':False}


def accept_stage(directory,stage,expected_archive_sha,approval):
    if (directory/'acceptance.json').exists():raise ValueError('formal_stage_already_accepted')
    archive=directory/(stage+'-evidence.tar.gz')
    unpack_verified(archive,directory/'raw',expected_archive_sha)
    accepted=check_stage_raw(directory/'raw',stage,approval)
    accepted['archive_sha256']=expected_archive_sha
    with (directory/'acceptance.json').open('x',encoding='utf8') as output:json.dump(accepted,output,indent=2)
    return accepted


def recheck_stage(directory,stage,approval):
    prior=json.loads((directory/'acceptance.json').read_text())
    if sha_file(directory/(stage+'-evidence.tar.gz'))!=prior['archive_sha256']:raise ValueError('formal_stage_archive_changed')
    actual=check_stage_raw(directory/'raw',stage,approval)
    if dict(actual,archive_sha256=prior['archive_sha256'])!=prior:raise ValueError('formal_stage_acceptance_changed')
    return actual

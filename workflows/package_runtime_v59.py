"""Add only Phase9 modules to the verified v56 asset directory; no recopy of USD.

Old source/model manifests retain their bytes and meaning. The executable
release is a separate manifest and confers no permission to run an experiment.
"""
import argparse
import ast
import json
from pathlib import Path

from workflows.phase9_preflight_v59 import REQUIRED_RUNTIME_FILES, digest, proposal, verify_release
from workflows.runtime_assets_v56 import AssetLocation, confined, load_assets, read, sha
from workflows.collect_runtime_v59 import HANDOFF_SHA


LOCAL_TESTS=('tests/test_runtime_repair_v59.py', 'tests/test_runtime_episode_v57.py', 'tests/test_phase9_preflight_v57.py', 'tests/test_runtime_collector_v57.py', 'tests/test_runtime_audit_v57.py', 'tests/test_validate_runtime_v57.py', 'tests/test_isaac_execution_v55.py', 'tests/test_plan_continuity_v54.py', 'tests/test_runtime_coordinator_v52.py', 'tests/test_plan_arbiter_v52.py', 'tests/test_execution_ledger_v48.py', 'tests/test_prepared_execution_v49.py', 'tests/test_cached_checks_v53.py', 'tests/test_collector_supervisor_v28.py', 'tests/test_runtime_stage_v58.py', 'tests/test_runtime_release_v58.py')
ADDITIONAL_FILES=('workflows/run_runtime_v59.py','workflows/package_runtime_v59.py',
    'scripts/phase9_runtime_preflight_v59.sh','scripts/requirements_phase9_compile_v43.txt',
    'docs/phase9_runtime_preflight_v59_runbook.md',
    'docs/evidence/phase8_3/server-initialization-repair-20260912/raw/installed/direct_rl_env.py',
    'docs/evidence/phase9/server-preflight-v58-20260920/remote/results/p9-v57-base/trace-before-cleanup.json')


def supervision_contract():
    return dict(schema='phase9-runtime-supervision-v59',
        entrypoint='workflows.run_runtime_v59',case_entrypoint='workflows.collect_runtime_v59',
        validator_entrypoint='workflows.validate_runtime_v59',
        source_protocol_sha256=digest(proposal()),maximum_wall_seconds=1800,maximum_case_seconds=180,
        total_research_package_bytes_both_hosts=512*1024**2,per_host_bytes=256*1024**2,
        stop_per_host_bytes=192*1024**2,disk_poll_seconds=.05,
        disk_scope='release_source_models_fit_assets_and_generated_research_logs_results; existing_shared_runtime_excluded',
        active_application_processes=3,python_resource_tracker_helpers_at_most=1,
        compute_threads_per_process=1,cleanup_probes=['timeout_descendants','native_zero_orphan_descendants'],
        no_install_or_environment_upgrade=True,no_retries=True,requires_explicit_new_approval=True,
        simulator_environment_gate='Isaac5.0_Lab2.2.1_frozen_patch_before_environment_creation',
        compiler_gate=dict(numba='0.61.2',llvmlite='0.44.0',numpy='1.26.4'),
        no_control_benefit_claim=True)


def dependency_closure(root,entrypoints):
    root=Path(root).resolve();found=set();pending=list(entrypoints)
    def resolve(module):
        base=module.replace('.','/')
        for rel in (base+'.py',base+'/__init__.py','tests/'+base+'.py'):
            if (root/rel).is_file():return rel
        return None
    def enqueue(module):
        rel=resolve(module)
        if rel is not None and rel not in found:pending.append(rel)
    while pending:
        rel=pending.pop()
        if rel in found:continue
        path=confined(root,rel)
        if not path.is_file():raise FileNotFoundError(rel)
        found.add(rel)
        if path.suffix!='.py':continue
        parts=Path(rel).parts[:-1]
        for count in range(1,len(parts)+1):
            parent='/'.join(parts[:count])+'/__init__.py'
            if (root/parent).is_file() and parent not in found:pending.append(parent)
        tree=ast.parse(path.read_bytes())
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for name in node.names:enqueue(name.name)
            elif isinstance(node,ast.ImportFrom):
                module=node.module or ''
                if node.level:
                    prefix='.'.join(parts[:len(parts)-node.level+1]);module='.'.join(x for x in (prefix,module) if x)
                if module:enqueue(module)
                for name in node.names:
                    if name.name!='*':enqueue('.'.join(x for x in (module,name.name) if x))
            elif (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                    and node.func.attr=='import_module' and node.args
                    and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str)
                    and not node.args[0].value.startswith('.')):enqueue(node.args[0].value)
    return sorted(found)


def plan_overlay(origin,destination,relative_files,*,maximum_new_bytes):
    origin=Path(origin).resolve();destination=Path(destination).resolve()
    if not destination.is_dir():raise ValueError('release_existing_asset_directory_required')
    records=[];new_bytes=0
    for rel in sorted(set(relative_files)):
        src=confined(origin,rel);dst=confined(destination,rel)
        if not src.is_file() or src.is_symlink():raise FileNotFoundError('release_source_missing:'+rel)
        h=sha(src);exists=dst.exists()
        if exists and (not dst.is_file() or dst.is_symlink() or sha(dst)!=h):
            raise ValueError('release_immutable_destination_conflict:'+rel)
        if not exists:new_bytes+=src.stat().st_size
        records.append(dict(relative_path=rel,sha256=h,source=str(src),destination=str(dst),exists=exists))
    if new_bytes>maximum_new_bytes:raise ValueError('release_new_bytes')
    return dict(new_bytes=new_bytes,records=records)


def apply_overlay(plan):
    # Revalidate every planned source/destination before the first write.
    for r in plan['records']:
        if sha(Path(r['source']))!=r['sha256']:raise ValueError('release_source_changed')
        dst=Path(r['destination'])
        if dst.exists() and (not dst.is_file() or sha(dst)!=r['sha256']):raise ValueError('release_destination_changed')
    for r in plan['records']:
        dst=Path(r['destination'])
        if dst.exists():continue
        payload=Path(r['source']).read_bytes()
        import hashlib
        if hashlib.sha256(payload).hexdigest()!=r['sha256']:raise ValueError('release_source_changed')
        dst.parent.mkdir(parents=True,exist_ok=True)
        with dst.open('xb') as f:f.write(payload)
        if sha(dst)!=r['sha256']:raise ValueError('release_copy_mismatch')


def verify_executable_release(root):
    result=verify_release(root);r=result['manifest']
    required=set(REQUIRED_RUNTIME_FILES)|set(ADDITIONAL_FILES)|set(LOCAL_TESTS)
    if (r.get('supervision_contract')!=supervision_contract() or r.get('local_tests')!=list(LOCAL_TESTS)
            or not required<=r['files_sha256'].keys()):raise ValueError('runtime_supervision_contract')
    root=Path(root).resolve()
    for parent in ('workflows','koopman','easyuuv_nc','tests'):
        for path in (root/parent).rglob('*.py'):
            if path.relative_to(root).as_posix() not in r['files_sha256']:
                raise ValueError('runtime_unfrozen_source:'+path.name)
    return result


def prepare_release(origin,asset_root):
    origin=Path(origin).resolve();asset_root=Path(asset_root).resolve()
    if (asset_root/'PHASE9_RELEASE.json').exists():raise FileExistsError('runtime_release_already_frozen')
    location=AssetLocation(str(asset_root),'.','assets/v38/inputs',HANDOFF_SHA)
    assets=load_assets(location,model_key='nonlinear__pooled')
    relocated=read(asset_root/'ASSET_RELOCATION.json')
    for rel,h in relocated['files_sha256'].items():
        if sha(confined(asset_root,rel))!=h:raise ValueError('runtime_original_asset_changed')
    entries=[rel for rel in REQUIRED_RUNTIME_FILES if rel.endswith('.py')]
    entries+=list(LOCAL_TESTS)+[ADDITIONAL_FILES[0],ADDITIONAL_FILES[1]]
    closure=dependency_closure(origin,entries)
    overlay=plan_overlay(origin,asset_root,closure+list(ADDITIONAL_FILES),maximum_new_bytes=8*1024**2)
    # One fixed assets-only directory, no changes to old source or USD bytes.
    apply_overlay(overlay)
    files=dict(relocated['files_sha256']);files['ASSET_RELOCATION.json']=sha(asset_root/'ASSET_RELOCATION.json')
    files.update({r['relative_path']:r['sha256'] for r in overlay['records']})
    manifest=dict(schema='phase9-executable-release-v59',protocol_sha256=digest(proposal()),
        supervision_contract=supervision_contract(),local_tests=list(LOCAL_TESTS),files_sha256=files,
        asset_relocation_sha256=files['ASSET_RELOCATION.json'],handoff_sha256=HANDOFF_SHA,
        model_sha256=assets.model_sha256,new_overlay_bytes=overlay['new_bytes'],model_fits=0,
        new_server_approval=False,source_dependency_closure=closure)
    with (asset_root/'PHASE9_RELEASE.json').open('x',encoding='utf8') as f:json.dump(manifest,f,indent=2,allow_nan=False)
    result=verify_executable_release(asset_root)
    return dict(release_sha256=result['release_sha256'],protocol_sha256=result['protocol_sha256'],
        files=len(files),new_overlay_bytes=overlay['new_bytes'],model_sha256=assets.model_sha256)


def main():
    p=argparse.ArgumentParser();p.add_argument('--origin',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--assets',type=Path,required=True);p.add_argument('--verify-only',action='store_true');args=p.parse_args()
    result=verify_executable_release(args.assets) if args.verify_only else prepare_release(args.origin,args.assets)
    print(json.dumps({k:v for k,v in result.items() if k!='manifest'},indent=2));return 0


if __name__=='__main__':raise SystemExit(main())

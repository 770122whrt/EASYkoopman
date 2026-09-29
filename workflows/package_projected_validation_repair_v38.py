"""One r22 numerical amendment; reuse r21 validation, never recollect or refit."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from workflows.package_projected_v38 import dump, git
from workflows.package_projected_repair_v38 import build
from workflows.projected_archive_v38 import audit_raw, RECOVERY_INPUT_FILES
from workflows.projected_budget_v38 import recover_validation_pullback
from workflows.projected_release_v38 import read, sha, verify_bundle
from workflows.projected_protocol_v38 import protocol


def tested_package(directory):
    directory=Path(directory); package=read(directory/'package.json')
    root,source=Path(package['origin_root']),Path(package['source_root'])
    tests={}
    suffix=package.get('test_suffix','')
    if suffix not in ('','-storage'):
        raise ValueError('validation_repair_test_suffix')
    for role,expected in (('root',root),('clone',source)):
        p=directory/('preflight-'+role+suffix);record=read(p/'tests.json')
        if (record.get('status')!='source_tests_passed' or record.get('native_exit')!=0
                or record['root']!=str(expected) or record['log_sha256']!=sha(p/'tests.log')
                or record['tests']!=read(source/'scripts/phase8_4_projected_v38_tests.json')['tests']):
            raise ValueError('validation_repair_tests_not_passed')
        tests[role]=record
    manifest=read(source/'SOURCE_MANIFEST.json')
    if (git(source,'rev-parse','HEAD')!=package['source_commit']
            or git(source,'status','--porcelain=v1','--untracked-files=all')
            or sha(package['bundle_path'])!=package['bundle_sha256']
            or any(sha(source/n)!=h or sha(root/n)!=manifest['origin_files_sha256'][n]
                   for n,h in manifest['files_sha256'].items())):
        raise ValueError('validation_repair_tested_source_changed')
    return package,tests


def audit_child(directory,raw,archive_sha):
    directory,raw=Path(directory),Path(raw)
    result=audit_raw(raw,'validation',archive_sha,auditor_revision=read(directory/'auditor-revision.json'))
    with (directory/'reaudit/parent-validation-audit.json').open('x',encoding='utf8') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    return result


def reaudit(directory,raw,diagnosis):
    directory,raw,diagnosis=Path(directory).resolve(),Path(raw).resolve(),Path(diagnosis).resolve()
    package,_=tested_package(directory)
    if Path(__file__).resolve().parents[1]!=Path(package['source_root']):
        raise ValueError('validation_repair_requires_tested_snapshot')
    operation=read(diagnosis/'operation.json');result=read(diagnosis/'result.json')
    parent_path=diagnosis/'failed-budget.json';before=read(parent_path)
    if (operation.get('native_exit')!=0 or operation.get('prior_budget_sha256')!=sha(parent_path)
            or result.get('status')!='diagnostic_only_no_admission' or result.get('physics_pass_count')!=24
            or result.get('model_fits')!=0 or result.get('new_simulation_intervals')!=0):
        raise ValueError('validation_repair_diagnostic_lineage')
    prior=float(operation['charged_seconds'])
    cap=min(600.,3600.-before['charged_seconds']['analysis']-prior)
    if cap<30:
        raise ValueError('validation_repair_analysis_budget')
    out=directory/'reaudit';out.mkdir(exist_ok=False)
    report=dict(status='running',parent_budget_sha256=sha(parent_path),prior_diagnostic_seconds=prior,
        diagnostic_operation_sha256=sha(diagnosis/'operation.json'),diagnostic_result_sha256=sha(diagnosis/'result.json'),
        cap_seconds=cap,new_simulation_intervals=0,model_fits=0)
    dump(out/'operation.json',report);started=time.monotonic();code=1
    try:
        command=[sys.executable,'-X','utf8','-B','-m','workflows.package_projected_validation_repair_v38',
            'audit-child','--directory',str(directory),'--raw',str(raw),
            '--archive-sha',sha(raw.parent/'validation-evidence.tar.gz')]
        with (out/'reaudit.log').open('xb') as log:
            try:
                code=subprocess.run(command,cwd=package['source_root'],stdout=log,stderr=subprocess.STDOUT,
                    timeout=cap-5,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',
                    OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')).returncode
            except subprocess.TimeoutExpired:
                code=124
        if code:
            raise ValueError('validation_repair_reaudit_failed')
        report.update(status='validation_repair_reaudit_passed',audit_sha256=sha(out/'parent-validation-audit.json'))
    finally:
        elapsed=time.monotonic()-started
        report.update(native_exit=code,seconds=elapsed,charged_seconds=prior+elapsed)
        dump(out/'operation.json',report)
    shutil.copyfile(parent_path,out/'parent-budget.json')
    return report


def freeze(directory):
    directory=Path(directory).resolve();package,tests=tested_package(directory)
    old=Path(package['parent_package'])/'inputs';source=Path(package['source_root'])
    operation=read(directory/'reaudit/operation.json')
    if operation.get('status')!='validation_repair_reaudit_passed' or operation.get('native_exit')!=0:
        raise ValueError('validation_repair_reaudit_not_passed')
    parent_path=directory/'reaudit/parent-budget.json';audit=directory/'reaudit/parent-validation-audit.json'
    if sha(parent_path)!=operation['parent_budget_sha256'] or sha(audit)!=operation['audit_sha256']:
        raise ValueError('validation_repair_reaudit_changed')
    parent=read(parent_path)
    if parent['freeze_sha256']!=sha(old/'freeze.json'):
        raise ValueError('validation_repair_parent_freeze')
    preview=recover_validation_pullback(parent,'0'*64,validation_audit_sha256=sha(audit),
                                       diagnostic_seconds=operation['charged_seconds'])
    inputs=directory/'inputs';inputs.mkdir(exist_ok=False)
    for name in ('protocol.json','evaluation-policy.json','policy.json','model-manifest.json','historical-budget.json',
                 *RECOVERY_INPUT_FILES):
        shutil.copyfile(old/name,inputs/name)
    shutil.copyfile(old/'freeze.json',inputs/'parent-freeze.json')
    shutil.copyfile(parent_path,inputs/'validation-parent-budget.json')
    shutil.copyfile(audit,inputs/'parent-validation-audit.json')
    dump(inputs/'validation-numeric-recovery.json',preview['validation_numeric_recovery'])
    dump(inputs/'validation-numeric-diagnostics.json',operation)
    dump(inputs/'local-readiness.json',dict(status='local_source_package_checks_passed',source_commit=package['source_commit'],
        bundle_sha256=package['bundle_sha256'],tests=tests,simulation_evidence=False))
    old_freeze=read(old/'freeze.json')
    frozen=dict(old_freeze,schema='projected-formal-v38-numeric-repair-before-scoring',source_commit=package['source_commit'],
        source_manifest_sha256=sha(source/'SOURCE_MANIFEST.json'),local_readiness_sha256=sha(inputs/'local-readiness.json'),
        parent_freeze_sha256=sha(old/'freeze.json'),validation_source_commit=old_freeze['source_commit'],
        authorization_parent_freeze_sha256=old_freeze['parent_freeze_sha256'],
        validation_numeric_recovery_sha256=sha(inputs/'validation-numeric-recovery.json'),
        validation_numeric_diagnostics_sha256=sha(inputs/'validation-numeric-diagnostics.json'))
    dump(inputs/'freeze.json',frozen)
    budget=recover_validation_pullback(parent,sha(inputs/'freeze.json'),validation_audit_sha256=sha(audit),
                                      diagnostic_seconds=operation['charged_seconds'])
    dump(inputs/'budget.json',budget)
    # User already approved original D-23, continuation and small numerical tolerance.
    dump(inputs/'authorization.json',dict(schema='projected-formal-v38-numeric-amendment',decision='approved',
        authorized_by='user',approval_reference='Original call_yAGHkuXnJZ6cnVnQHmLigQ4J question0: 批准，按此范围继续; '
        'user continuation: 我已经开启服务器了 继续完成; numeric instruction: 完全相等可以换成一个小的容差即可 没有必要完全相同',
        freeze_sha256=sha(inputs/'freeze.json'),parent_freeze_sha256=frozen['authorization_parent_freeze_sha256'],
        parent_authorization_sha256=sha(inputs/'authorization-parent.json'),resource_cap=protocol()['resource_cap']))
    verify_bundle(source,inputs,package['source_commit'])
    package.update(status='tested_validation_numeric_repair_frozen',freeze_sha256=sha(inputs/'freeze.json'),
        root_tests=tests['root']['summary'],clone_tests=tests['clone']['summary'],
        reuses_original_preflight=True,reuses_original_validation=True,new_fits=0,
        analysis_seconds_including_repair=budget['charged_seconds']['analysis'])
    dump(directory/'package.json',package)
    return package


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('build','reaudit','audit-child','freeze'))
    p.add_argument('--directory',required=True);p.add_argument('--root');p.add_argument('--parent')
    p.add_argument('--raw');p.add_argument('--diagnosis');p.add_argument('--archive-sha')
    a=p.parse_args()
    if a.action=='build': r=build(a.root,a.parent,a.directory,revision_name='r22')
    elif a.action=='reaudit':r=reaudit(a.directory,a.raw,a.diagnosis)
    elif a.action=='audit-child':r=audit_child(a.directory,a.raw,a.archive_sha)
    else:r=freeze(a.directory)
    print(json.dumps(r,indent=2))

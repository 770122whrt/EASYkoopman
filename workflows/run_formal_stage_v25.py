"""Bounded server stages; dry checks never start Isaac or mint an approval."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from workflows.formal_contract_v25 import (proposal, analysis_policy, authorize, digest,
    validate_stage, verify_gate_artifacts, source_identity, accept_preflights, RESULT_RELATIVE)
from workflows.validate_formal_trace_v25 import validate_trace


def prepare(root, transfer, stage):
    roles=json.loads((transfer/'role_protocol.json').read_text())
    policy=json.loads((transfer/'analysis_policy.json').read_text())
    approval=json.loads((transfer/'d23_approval.json').read_text())
    source=source_identity()
    selected={'preflight':('preflight',),'fit-validation':('fit','validation'),'test':('test',)}[stage]
    cases=[e for e in proposal()['entries'] if e['role'] in selected]
    # Approval precedes source/runtime/output operations, including the shell setup.
    for case in cases:authorize(roles,policy,approval,source,case['run_id'])
    if str(root)!=roles['remote_project_root']:raise ValueError('formal_server_root')
    manifest=json.loads((root/'SOURCE_MANIFEST.json').read_text())
    for name,sha in manifest['files_sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise ValueError('formal_source_hash')
    gate_path=None
    if stage!='preflight':
        gate_path=root/RESULT_RELATIVE/('pre-test-freeze.json' if stage=='test' else 'preflight-gate.json')
    gate=json.loads(gate_path.read_text()) if gate_path else None
    for case in cases:validate_stage(case,gate,source,digest(roles))
    verify_gate_artifacts(gate,root)
    if (transfer/stage).exists():raise ValueError('formal_stage_already_attempted')
    return cases,source,gate_path


def run(root,transfer,stage):
    cases,source,gate_path=prepare(root,transfer,stage)
    directory=transfer/stage;directory.mkdir()
    budget_path=transfer/'collection-budget.json'
    budget=json.loads(budget_path.read_text()) if budget_path.exists() else {'charged_seconds':0.,'attempts':[]}
    status={'status':'running','stage':stage,'source_commit':source,'accepted':[]}
    try:
        for case in cases:
            used=sum(p.stat().st_size for base in (transfer,root/RESULT_RELATIVE) if base.exists()
                     for p in base.rglob('*') if p.is_file())
            if used>=4*1024**3:raise ValueError('formal_disk_budget')
            remaining=180*60-budget['charged_seconds']
            if remaining<30:raise ValueError('formal_collection_time_budget')
            reservation=min(600.,remaining)
            attempt={'case':case['run_id'],'charged_seconds':reservation,'status':'reserved'}
            budget['charged_seconds']+=reservation;budget['attempts'].append(attempt)
            # A crash retains the conservative full reservation, never resets the budget.
            budget_path.write_text(json.dumps(budget,indent=2))
            command=['timeout','--signal=TERM','--kill-after=15s',f'{reservation-15}s',
                     '/root/IsaacLab/isaaclab.sh','-p','-B','-m','workflows.formal_contract_v25',
                     '--roles',str(transfer/'role_protocol.json'),'--policy',str(transfer/'analysis_policy.json'),
                     '--approval',str(transfer/'d23_approval.json'),'--case',case['run_id'],'--execute']
            if gate_path:command+=['--stage-gate',str(gate_path)]
            started=time.monotonic()
            with (directory/(case['run_id']+'.log')).open('x') as log:
                result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,check=False)
            elapsed=time.monotonic()-started
            budget['charged_seconds']+=elapsed-reservation
            attempt.update(charged_seconds=elapsed,status='exited',native_exit=result.returncode)
            budget_path.write_text(json.dumps(budget,indent=2))
            (directory/(case['run_id']+'.exit_status')).write_text(str(result.returncode)+'\n')
            if result.returncode:raise ValueError('formal_native_exit:'+case['run_id'])
            trace=root/RESULT_RELATIVE/'collection'/case['run_id']/'trace.json'
            accepted=validate_trace(json.loads(trace.read_text()),case,source)
            (directory/(case['run_id']+'.validation.json')).write_text(json.dumps(accepted,indent=2))
            status['accepted'].append(case['run_id'])
        if stage=='preflight':status['gate']=str(accept_preflights(root,transfer))
        status['status']='stage_collection_semantics_passed_pending_inventory_pullback'
    except BaseException as exc:
        status.update(status='failed',exception=f'{type(exc).__name__}:{exc}')
        raise
    finally:
        (directory/'stage-status.json').write_text(json.dumps(status,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transfer',type=Path,required=True)
    parser.add_argument('--stage',choices=['preflight','fit-validation','test'],required=True)
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    if args.check_only:
        cases,source,_=prepare(root,args.transfer,args.stage)
        print(json.dumps({'status':'authorized_stage_preparation_only','cases':len(cases),'source_commit':source,'simulation_started':False}))
    else:run(root,args.transfer,args.stage)


if __name__=='__main__':main()

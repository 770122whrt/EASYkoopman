"""New fixed validation cohort after v31 repair; cumulative budgets inherited."""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from workflows.identification_protocol_v32 import cases,protocol,digest,pulse,EXPERIMENT
from workflows.feedback_v31 import parameters
from workflows.validate_identification_v32 import validate_trace,rejected_trace
from workflows.calibration_trace_v27 import LIMITS,TAIL_LIMITS

from workflows.validation_release_v32 import REMOTE_ROOT,TRANSFER_ROOT,verify_release

ROOT=Path(__file__).resolve().parents[1]
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def reservation_seconds(budget):
    if len(budget['attempts'])>=54:raise ValueError('identification_process_budget')
    remaining=protocol()['resource_cap']['collector_seconds']-budget['charged_seconds']
    if remaining<30:raise ValueError('identification_time_budget')
    return min(300,remaining)


def verify_preflight(directory,source,root):
    directory=Path(directory);status=read(directory/'stage-status.json')
    qs=[q for q in cases() if q['role']=='preflight'];ids={q['run_id'] for q in qs}
    if (status['status']!='identification_stage_completed_pending_pullback' or status['source_commit']!=source
            or set(status['accepted'])!=ids or len(status['accepted'])!=8 or status['rejected']
            or set(status['trace_sha256'])!=ids):raise ValueError('identification_prior_inventory')
    for q in qs:
        p=directory/q['run_id']/'trace.json';ex=directory/q['run_id']/'collector-exit.json'
        code=directory/(q['run_id']+'.exit_status')
        if not all(x.is_file() for x in (p,ex,code)):raise ValueError('identification_prior_missing')
        if sha(p)!=status['trace_sha256'][q['run_id']]:raise ValueError('identification_prior_hash')
        exit_record=read(ex)
        if (code.read_text().strip()!='0' or exit_record['child_native_exit']!=0
                or exit_record['guarded_collector_exit']!=0 or exit_record['trace_sha256']!=sha(p)):
            raise ValueError('identification_prior_native')
        check=validate_trace(read(p),q,source,root)
        if not check['tail']['eligible_for_excitation']:raise ValueError('identification_preflight_tail')
    return status


def prepare(root,transfer,stage):
    if stage!='validation':raise ValueError('validation_role_required')
    from workflows.collect_koopman_v21_identification import _repository_commit
    source=_repository_commit();verify_release(root,transfer,source)
    if (transfer/stage).exists():raise ValueError('validation_stage_already_attempted')
    if sha(transfer/'budget.json')!=sha(transfer/'prior-budget.json'):
        raise ValueError('validation_budget_not_inherited')
    selected=[q for q in cases() if q['role']=='validation']
    selected.sort(key=lambda q:({'long_body':0,'asymmetric':1}.get(q['configuration'],2)))
    for q in selected:pulse(q)
    return selected,source


def run(root,transfer,stage):
    selected,source=prepare(root,transfer,stage)
    directory=transfer/stage;directory.mkdir()
    budgetpath=transfer/'budget.json'
    budget=read(budgetpath) if budgetpath.exists() else None
    status={'status':'running','source_commit':source,'trace_sha256':{},'accepted':[],'rejected':[]}
    try:
        for q in selected:
            if sum(p.stat().st_size for p in transfer.parent.rglob('*') if p.is_file())>=protocol()['resource_cap']['disk_bytes']:
                raise ValueError('identification_disk_budget')
            reservation=reservation_seconds(budget)
            attempt={'case':q['run_id'],'status':'reserved','charged_seconds':reservation}
            budget['charged_seconds']+=reservation;budget['attempts'].append(attempt)
            budgetpath.write_text(json.dumps(budget,indent=2))
            command=['timeout','--signal=TERM','--kill-after=15s',f'{reservation-15}s',
                     '/root/IsaacLab/isaaclab.sh','-p','-B','-m','workflows.collect_validation_v32',
                     '--case',q['run_id'],'--output',str(directory/q['run_id']),
                     '--source-commit',source,'--policy',str(transfer/'policy.json')]
            started=time.monotonic()
            with (directory/(q['run_id']+'.log')).open('x') as log:
                result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
            elapsed=time.monotonic()-started;budget['charged_seconds']+=elapsed-reservation
            attempt.update(status='exited',native_exit=result.returncode,charged_seconds=elapsed)
            budgetpath.write_text(json.dumps(budget,indent=2))
            (directory/(q['run_id']+'.exit_status')).write_text(str(result.returncode)+'\n')
            path=directory/q['run_id']/'trace.json';data=read(path)
            status['trace_sha256'][q['run_id']]=sha(path)
            if data['status']=='failed_identification':
                if result.returncode==0:raise ValueError('identification_failure_exit_lost')
                check=rejected_trace(data,q,source);status['rejected'].append(q['run_id'])
            else:
                if result.returncode:raise ValueError('identification_native_exit')
                check=validate_trace(data,q,source,root);status['accepted'].append(q['run_id'])
            (directory/(q['run_id']+'.validation.json')).write_text(json.dumps(check,indent=2))
            print(json.dumps({'case':q['run_id'],'status':check['status']}),flush=True)
            if status['rejected']:raise ValueError('identification_case_rejected')
        status['status']='identification_stage_completed_pending_pullback'
    except BaseException as exc:
        status.update(status='failed',exception=f'{type(exc).__name__}:{exc}');raise
    finally:(directory/'stage-status.json').write_text(json.dumps(status,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=('validation',),required=True)
    p.add_argument('--check-only',action='store_true');args=p.parse_args();transfer=Path(TRANSFER_ROOT)
    if args.check_only:
        qs,source=prepare(ROOT,transfer,args.stage)
        print(json.dumps({'status':'prepared_only','source_commit':source,'cases':len(qs)}))
    else:run(ROOT,transfer,args.stage)

"""Serial bounded diagnostic stages, conservative budget and immutable attempts."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
from workflows.free_water_microtrace_v26 import cases,EXPERIMENT
from workflows.validate_free_water_v26 import validate_trace,compare_pair

STAGES=('on-off','heavy','asymmetric')
ROOT=Path(__file__).resolve().parents[1]
REMOTE_ROOT='/root/EASYkoopman-phase8-4-free-water-20260913-r9'
TRANSFER_ROOT='/root/phase84-transfer-20260913/free-water-r9'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def stage_cases(stage):
    if stage not in STAGES:raise ValueError('free_water_stage')
    i=STAGES.index(stage)*2
    return cases()[i:i+2]


def prepare(root,transfer,stage):
    from workflows.collect_koopman_v21_identification import _repository_commit
    source=_repository_commit()
    if str(root)!=REMOTE_ROOT or str(transfer)!=TRANSFER_ROOT:raise ValueError('free_water_runtime_root')
    request=read(transfer/'request.json')
    if (request!={'experiment':EXPERIMENT,'source_commit':source,'cases':cases(),
                 'authorization':'user_server_powered_continue_data_adaptation_20260913'}):
        raise ValueError('free_water_run_binding')
    manifest=read(root/'SOURCE_MANIFEST.json')
    for name,h in manifest['files_sha256'].items():
        if sha(root/name)!=h:raise ValueError('free_water_source_hash:'+name)
    if (transfer/stage).exists():raise ValueError('free_water_stage_already_attempted')
    # Recompute prerequisite traces and pairs, not just a hand-written GO file.
    for previous in STAGES[:STAGES.index(stage)]:
        directory=transfer/previous;status=read(directory/'stage-status.json')
        if status['status']!='diagnostic_stage_passed_pending_pullback' or status['source_commit']!=source:
            raise ValueError('free_water_previous_stage')
        traces=[]
        for q in stage_cases(previous):
            path=directory/q['run_id']/'trace.json'
            if sha(path)!=status['trace_sha256'][q['run_id']]:raise ValueError('free_water_gate_hash')
            if (directory/(q['run_id']+'.exit_status')).read_text().strip()!='0':raise ValueError('free_water_previous_exit')
            d=read(path);validate_trace(d,q,source,root);traces.append(d)
        pair=compare_pair(*traces)
        if not pair['precontact_equivalent_within_fixed_tolerances']:raise ValueError('free_water_previous_pair')
    return stage_cases(stage),source


def run(root,transfer,stage):
    selected,source=prepare(root,transfer,stage);directory=transfer/stage;directory.mkdir()
    budgetpath=transfer/'budget.json';budget=read(budgetpath) if budgetpath.exists() else {'charged_seconds':0.,'attempts':[]}
    status={'status':'running','source_commit':source,'trace_sha256':{},'accepted':[]};traces=[]
    try:
        for q in selected:
            if len(budget['attempts'])>=6:raise ValueError('free_water_process_count_budget')
            if sum(p.stat().st_size for p in transfer.rglob('*') if p.is_file())>=512*1024**2:raise ValueError('free_water_disk_budget')
            remaining=1800-budget['charged_seconds']
            if remaining<30:raise ValueError('free_water_time_budget')
            reservation=min(300,remaining);attempt={'case':q['run_id'],'status':'reserved','charged_seconds':reservation}
            budget['charged_seconds']+=reservation;budget['attempts'].append(attempt);budgetpath.write_text(json.dumps(budget,indent=2))
            command=['timeout','--signal=TERM','--kill-after=15s',f'{reservation-15}s','/root/IsaacLab/isaaclab.sh','-p','-B','-m',
                     'workflows.free_water_microtrace_v26','--case',q['run_id'],'--output',str(directory/q['run_id']),'--source-commit',source]
            started=time.monotonic()
            with (directory/(q['run_id']+'.log')).open('x') as log:
                result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
            elapsed=time.monotonic()-started;budget['charged_seconds']+=elapsed-reservation
            attempt.update(status='exited',native_exit=result.returncode,charged_seconds=elapsed)
            budgetpath.write_text(json.dumps(budget,indent=2));(directory/(q['run_id']+'.exit_status')).write_text(str(result.returncode)+'\n')
            if result.returncode:raise ValueError('free_water_native_exit')
            path=directory/q['run_id']/'trace.json';data=read(path)
            check=validate_trace(data,q,source,root)
            (directory/(q['run_id']+'.validation.json')).write_text(json.dumps(check,indent=2))
            status['trace_sha256'][q['run_id']]=sha(path);status['accepted'].append(q['run_id']);traces.append(data)
        pair=compare_pair(*traces);(directory/'pair.json').write_text(json.dumps(pair,indent=2))
        if not pair['precontact_equivalent_within_fixed_tolerances']:raise ValueError('free_water_pair_mismatch')
        status['status']='diagnostic_stage_passed_pending_pullback'
    except BaseException as exc:
        status.update(status='failed',exception=f'{type(exc).__name__}:{exc}');raise
    finally:(directory/'stage-status.json').write_text(json.dumps(status,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=STAGES,required=True);p.add_argument('--check-only',action='store_true')
    args=p.parse_args();transfer=Path(TRANSFER_ROOT)
    if args.check_only:print(json.dumps({'status':'prepared_only','source_commit':prepare(ROOT,transfer,args.stage)[1]}))
    else:run(ROOT,transfer,args.stage)

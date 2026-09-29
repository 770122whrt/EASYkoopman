"""Two fixed calibration stages; independent per-configuration admission."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
from workflows.workpoint_v27 import cases,EXPERIMENT,validate_calibration,commands
from workflows.validate_calibration_v27 import validate_trace,rejected_trace
from workflows.calibration_trace_v27 import LIMITS,TAIL_LIMITS

ROOT=Path(__file__).resolve().parents[1]
REMOTE_ROOT='/root/EASYkoopman-phase8-4-calibration-20260913-r11'
TRANSFER_ROOT='/root/phase84-transfer-20260913/calibration-r11'
STAGES=('trim','excitation')
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def reservation_seconds(budget):
    if len(budget['attempts'])>=16:raise ValueError('calibration_process_budget')
    remaining=2400-budget['charged_seconds']
    if remaining<30:raise ValueError('calibration_time_budget')
    return min(300,remaining)


def excitation_eligible(data,source,root):
    if data.get('status')!='completed_calibration_pending_acceptance':
        raise ValueError('calibration_trace_status')
    return validate_trace(data,data['request'],source,root)['tail']['eligible_for_excitation']


def prepare(root,transfer,stage):
    from workflows.collect_koopman_v21_identification import _repository_commit
    source=_repository_commit()
    if str(root)!=REMOTE_ROOT or str(transfer)!=TRANSFER_ROOT or stage not in STAGES:
        raise ValueError('calibration_runtime_root')
    expected={'experiment':EXPERIMENT,'source_commit':source,'cases':cases(),
              'calibration_sha256':sha(transfer/'calibration.json'),
              'motion_limits':LIMITS,'tail_limits':TAIL_LIMITS,
              'authorization':'user_continue_adaptation_calibration_tests_20260913'}
    if read(transfer/'request.json')!=expected:raise ValueError('calibration_run_binding')
    for name,h in read(root/'SOURCE_MANIFEST.json')['files_sha256'].items():
        if sha(root/name)!=h:raise ValueError('calibration_source_hash:'+name)
    table=read(transfer/'calibration.json')
    for c in table.values():validate_calibration(c)
    if (transfer/stage).exists():raise ValueError('calibration_stage_already_attempted')
    selected=[q for q in cases() if q['stage']==stage];skipped=[]
    for q in selected:commands(q,table[q['configuration']])
    if stage=='excitation':
        status=read(transfer/'trim/stage-status.json')
        if status['status']!='calibration_stage_completed_pending_pullback' or status['source_commit']!=source:
            raise ValueError('calibration_previous_stage')
        admitted=[]
        for q in selected:
            prior=next(c for c in cases() if c['stage']=='trim' and c['configuration']==q['configuration'])
            path=transfer/'trim'/prior['run_id']/'trace.json'
            if sha(path)!=status['trace_sha256'][prior['run_id']]:raise ValueError('calibration_prior_hash')
            d=read(path)
            if d['status']=='failed_calibration':
                reason=rejected_trace(d,prior,source)
                eligible=False
            else:
                if (transfer/'trim'/(prior['run_id']+'.exit_status')).read_text().strip()!='0':
                    raise ValueError('calibration_prior_native_exit')
                reason=validate_trace(d,prior,source,root);eligible=reason['tail']['eligible_for_excitation']
            if eligible:admitted.append(q)
            else:skipped.append({'run_id':q['run_id'],'reason':'trim_not_admitted','trim_result':reason})
        selected=admitted
    return selected,skipped,source


def run(root,transfer,stage):
    selected,skipped,source=prepare(root,transfer,stage)
    directory=transfer/stage;directory.mkdir()
    budgetpath=transfer/'budget.json'
    budget=read(budgetpath) if budgetpath.exists() else {'charged_seconds':0.,'attempts':[]}
    status={'status':'running','source_commit':source,'trace_sha256':{},'accepted':[],
            'rejected':[],'skipped':skipped}
    try:
        for q in selected:
            if sum(p.stat().st_size for p in transfer.rglob('*') if p.is_file())>=1024**3:
                raise ValueError('calibration_disk_budget')
            reservation=reservation_seconds(budget)
            attempt={'case':q['run_id'],'status':'reserved','charged_seconds':reservation}
            budget['charged_seconds']+=reservation;budget['attempts'].append(attempt)
            budgetpath.write_text(json.dumps(budget,indent=2))
            command=['timeout','--signal=TERM','--kill-after=15s',f'{reservation-15}s',
                     '/root/IsaacLab/isaaclab.sh','-p','-B','-m','workflows.collect_calibration_v27',
                     '--case',q['run_id'],'--output',str(directory/q['run_id']),
                     '--source-commit',source,'--calibration',str(transfer/'calibration.json')]
            started=time.monotonic()
            with (directory/(q['run_id']+'.log')).open('x') as log:
                result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
            elapsed=time.monotonic()-started;budget['charged_seconds']+=elapsed-reservation
            attempt.update(status='exited',native_exit=result.returncode,charged_seconds=elapsed)
            budgetpath.write_text(json.dumps(budget,indent=2))
            (directory/(q['run_id']+'.exit_status')).write_text(str(result.returncode)+'\n')
            path=directory/q['run_id']/'trace.json';data=read(path)
            status['trace_sha256'][q['run_id']]=sha(path)
            if data['status']=='failed_calibration':
                check=rejected_trace(data,q,source);status['rejected'].append(q['run_id'])
            else:
                if result.returncode:raise ValueError('calibration_native_exit')
                check=validate_trace(data,q,source,root);status['accepted'].append(q['run_id'])
            (directory/(q['run_id']+'.validation.json')).write_text(json.dumps(check,indent=2))
            print(json.dumps({'case':q['run_id'],'result':check}),flush=True)
        status['status']='calibration_stage_completed_pending_pullback'
    except BaseException as exc:
        status.update(status='failed',exception=f'{type(exc).__name__}:{exc}');raise
    finally:(directory/'stage-status.json').write_text(json.dumps(status,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=STAGES,required=True)
    p.add_argument('--check-only',action='store_true');args=p.parse_args();transfer=Path(TRANSFER_ROOT)
    if args.check_only:
        q,skipped,source=prepare(ROOT,transfer,args.stage)
        print(json.dumps({'status':'prepared_only','source_commit':source,'cases':len(q),'skipped':skipped}))
    else:run(ROOT,transfer,args.stage)

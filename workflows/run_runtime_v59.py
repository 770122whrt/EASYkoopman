"""Sequential Linux supervisor for the fixed v57 interface preflight.

Every collector/validator has its own process group. Native success, semantic
acceptance, output hashes, group cleanup and resource checks are separate gates.
One attempted stage is terminal; no automatic retries or budget from v38.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from workflows.phase9_preflight_v59 import authorize_case, cases, proposal
from workflows.runtime_assets_v56 import sha


PER_HOST_BYTES=256*1024**2
DISK_STOP_BYTES=192*1024**2  # Leave room for shutdown records; check every 50ms.


def dump(path,value):
    with Path(path).open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def disk_bytes(root):
    total=0
    for p in Path(root).rglob('*'):
        if p.is_symlink():raise ValueError('runtime_disk_symlink')
        if p.is_file():total+=p.stat().st_size
    return total


def live_group_members(pgid):
    """Linux /proc proof excludes dead zombies, not merely killpg(0) success."""
    members=[]
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():continue
        try:
            fields=(directory/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2])==pgid and fields[0] not in ('Z','X'):members.append(int(directory.name))
        except (FileNotFoundError,ProcessLookupError):pass  # Process exited during read.
    return members


def bounded_process(command,root,log,*,timeout_seconds,clock=time.monotonic):
    if sys.platform!='linux':raise ValueError('runtime_supervisor_requires_linux')
    if not 0<timeout_seconds<=180:raise ValueError('runtime_process_time_budget')
    started=clock();deadline=started+timeout_seconds
    cleanup_reserve=min(3.,timeout_seconds/4);stop_at=deadline-cleanup_reserve
    process=None;reason='completed';native=None;members=[]
    try:
        if disk_bytes(root)>=DISK_STOP_BYTES:raise ValueError('runtime_disk_guard')
        environment=os.environ.copy()
        environment.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(Path(root).resolve()),
            OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',NUMBA_NUM_THREADS='1')
        with Path(log).open('xb') as stream:
            process=subprocess.Popen(command,cwd=root,stdout=stream,stderr=subprocess.STDOUT,
                                     env=environment,start_new_session=True)
            while process.poll() is None:
                if clock()>=stop_at:reason='timeout';break
                if disk_bytes(root)>=DISK_STOP_BYTES:reason='disk_guard';break
                time.sleep(min(.05,max(0.,stop_at-clock())))
            native=process.poll()
    finally:
        if process is not None:
            pgid=process.pid
            # Cleanup is required even when the group leader exited zero.
            members=live_group_members(pgid)
            if members:
                try:os.killpg(pgid,signal.SIGTERM)
                except ProcessLookupError:pass
                grace=min(clock()+.25,deadline)
                while clock()<grace and live_group_members(pgid):time.sleep(.01)
                if live_group_members(pgid):
                    try:os.killpg(pgid,signal.SIGKILL)
                    except ProcessLookupError:pass
            try:process.wait(timeout=max(.001,deadline-clock()))
            except subprocess.TimeoutExpired:reason='cleanup_timeout'
            while clock()<deadline and live_group_members(pgid):time.sleep(.01)
            members=live_group_members(pgid);native=process.poll()
    elapsed=clock()-started
    if reason!='completed' or elapsed>timeout_seconds or disk_bytes(root)>PER_HOST_BYTES:
        native=native if type(native) is int and native!=0 else 1
    return dict(native_exit=native,reason=reason,seconds=elapsed,group_stopped=not members,
                remaining_group_pids=members,bytes_after=disk_bytes(root))


def run_sequence(launch,readback,*,clock=time.monotonic,started=None):
    started=clock() if started is None else started;limit=proposal()['maximum_wall_seconds']
    report=dict(status='running',attempts=[],accepted=[],model_fits=0,control_benefit_claim=False)
    try:
        for q in cases():
            case_started=clock()
            for kind in ('collector','validator'):
                stage_remaining=limit-(clock()-started)
                case_remaining=proposal()['maximum_case_seconds']-(clock()-case_started)
                if stage_remaining<=3:raise ValueError('runtime_stage_wall_budget')
                if case_remaining<=3:raise ValueError('runtime_case_wall_budget')
                remaining=min(stage_remaining,case_remaining)
                result=launch(q,kind,remaining)
                report['attempts'].append(dict(case_id=q['case_id'],kind=kind,allocated_wall_seconds=remaining,**result))
                if type(result.get('native_exit')) is not int or result['native_exit']!=0:
                    raise ValueError('runtime_'+kind+'_native_failed')
                if result.get('group_stopped') is not True:raise ValueError('runtime_group_cleanup_unconfirmed')
            accepted=readback(q)
            if clock()-started>limit:raise ValueError('runtime_stage_wall_budget')
            if clock()-case_started>proposal()['maximum_case_seconds']:raise ValueError('runtime_case_wall_budget')
            report['accepted'].append(accepted)
        report['status']='completed_runtime_interface_preflight'
    except BaseException as exc:
        report.update(status='stopped_runtime_no_go',exception=type(exc).__name__+':'+str(exc))
    report['seconds']=clock()-started
    return report


def check_environment(root):
    if sys.platform!='linux' or Path(__file__).resolve().parents[1]!=Path(root).resolve():
        raise ValueError('runtime_linux_release_checkout_required')
    versions={k:importlib.metadata.version(k) for k in ('numba','llvmlite','numpy','torch')}
    if versions['numba']!='0.61.2' or versions['llvmlite']!='0.44.0':raise ValueError('runtime_compiler_version')
    if versions['numpy']!='1.26.4':raise ValueError('runtime_numpy_version')
    return dict(python=sys.version,executable=sys.executable,versions=versions,
                platform=sys.platform,isaac_source_check='performed_by_collector_before_environment_creation')


def probe_process_cleanup(root,folder):
    """Real Linux subprocesses only; no simulator, fitting or benchmark claim."""
    child='import time;time.sleep(60)'
    prefix='import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",'+repr(child)+']);'
    commands=[('timeout',prefix+'time.sleep(60)'),('orphan',prefix)]
    results=[]
    for name,code in commands:
        r=bounded_process([sys.executable,'-B','-c',code],root,folder/('probe-'+name+'.log'),timeout_seconds=1.5)
        results.append(dict(probe=name,**r));dump(folder/('probe-'+name+'.json'),results[-1])
        expected=(r['reason']=='timeout' and r['native_exit']!=0) if name=='timeout' else (r['reason']=='completed' and r['native_exit']==0)
        if not expected or r['group_stopped'] is not True:raise ValueError('runtime_cleanup_probe_failed:'+name)
    return results


def run_stage(root,approval):
    started=time.monotonic();root=Path(root).resolve()
    binding=authorize_case(root,cases()[0],approval)
    from workflows.package_runtime_v59 import verify_executable_release
    verify_executable_release(root)
    folder=root/'runtime-stage-v59';folder.mkdir(exist_ok=False)
    approval_path=folder/'approval-bound.json';dump(approval_path,approval)
    result=dict(status='stopped_runtime_no_go',**binding,attempts=[],accepted=[],model_fits=0,control_benefit_claim=False)
    try:
        dump(folder/'environment.json',check_environment(root))
        result['cleanup_probes']=probe_process_cleanup(root,folder)
        def launch(q,kind,remaining):
            module='workflows.collect_runtime_v59' if kind=='collector' else 'workflows.validate_runtime_v59'
            command=[sys.executable,'-B','-m',module,'--release-root',str(root),
                     '--approval',str(approval_path),'--case',q['case_id']]
            command+=['--native-child'] if kind=='collector' else ['--native-exit','0']
            outcome=bounded_process(command,root,folder/(q['case_id']+'-'+kind+'.log'),timeout_seconds=remaining)
            dump(folder/(q['case_id']+'-'+kind+'-exit.json'),outcome)
            return outcome
        def readback(q):
            trace=root/'results'/q['case_id']/'trace.json';path=trace.with_name('acceptance.json')
            a=json.loads(path.read_text(encoding='utf8'))
            if (a['status']!='runtime_interface_preflight_passed' or a['request']!=q
                    or a['release_sha256']!=binding['release_sha256'] or a['protocol_sha256']!=binding['protocol_sha256']
                    or a['trace_sha256']!=sha(trace) or a['physics_steps']!=2*q['controls']
                    or a['arbitration']['activations']<1 or a['control_benefit_claim'] is not False):
                raise ValueError('runtime_acceptance_readback')
            if disk_bytes(root)>PER_HOST_BYTES:raise ValueError('runtime_stage_bytes')
            return dict(case_id=q['case_id'],acceptance_sha256=sha(path),trace_sha256=sha(trace))
        result.update(run_sequence(launch,readback,started=started))
    except BaseException as exc:
        result.update(status='stopped_runtime_no_go',exception=type(exc).__name__+':'+str(exc))
    finally:
        result.update(seconds=time.monotonic()-started,bytes_after=disk_bytes(root))
        if result['seconds']>1800 or result['bytes_after']>PER_HOST_BYTES:result['status']='stopped_runtime_no_go'
        dump(folder/'stage-result.json',result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--release-root',type=Path,required=True)
    parser.add_argument('--approval',type=Path);parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    if args.check_only:
        from workflows.package_runtime_v59 import verify_executable_release
        release=verify_executable_release(args.release_root)
        print(json.dumps(dict(release_sha256=release['release_sha256'],environment=check_environment(args.release_root)),indent=2))
        return 0
    if args.approval is None:raise ValueError('runtime_new_explicit_approval_required')
    def stop(signum,frame):raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,stop)
    result=run_stage(args.release_root,json.loads(args.approval.read_text(encoding='utf8')))
    print(json.dumps(result,indent=2));return 0 if result['status']=='completed_runtime_interface_preflight' else 1


if __name__=='__main__':raise SystemExit(main())

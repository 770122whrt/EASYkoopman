"""Approved isolated configuration failures, unchanged per-case physical gates."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False)

def completed(native):
    return native.get('reason')=='completed' and native.get('group_stopped') is True and not native.get('remaining_group_pids')

def classify(native, analysis=None, failure=None):
    if not completed(native):return 'global_stop'
    audit=native.get('analysis',{})
    if native.get('native_exit')==0:
        if completed(audit) and audit.get('native_exit')==0 and analysis and analysis.get('status')=='physical_and_causal_replay_passed':return 'accepted'
        return 'global_stop'
    if (native.get('native_exit')==1 and completed(audit) and audit.get('native_exit')==0
            and failure and failure.get('status')=='configuration_support_no_go'):
        return 'configuration_no_go'
    return 'global_stop'


def accepted_prior_case(folder,case):
    folder=Path(folder)
    native=read(folder/'native.json');analysis=read(folder/'analysis.json')
    with gzip.open(folder/'output/diagnostic.json.gz','rt') as f:data=json.load(f)
    if (classify(native,analysis)!='accepted' or analysis['case']!=case or data['case']!=case
            or data.get('exception') or data['cleanup_errors']
            or data['status']!='diagnostic_returned' or len(data['substeps'])!=4*case['controls']):
        raise ValueError('inherited_case_not_accepted')
    return 'accepted'


def retained_research_bytes(entries,disk_bytes,*,debugger_root=None):
    total=0
    for entry in entries:
        if entry.name=='EASYkoopman-phase9-runtime-env-v58':continue
        if debugger_root is not None and entry==Path(debugger_root):
            # Approved extracted packages contain ordinary library symlinks.
            # Their distinct tool allowance is not the research evidence tree.
            size=sum(p.lstat().st_size for p in entry.rglob('*') if p.is_file() or p.is_symlink())
            if size>64*1024**2:raise ValueError('debugger_tool_disk_budget')
            continue
        total+=disk_bytes(entry) if entry.is_dir() else entry.stat().st_size
    return total


def check_resource_approval(protocol,manifest_sha256,arguments):
    if protocol.get('requires_resource_amendment_approval'):
        if arguments!=['--resource-approval',manifest_sha256]:
            raise ValueError('explicit_resource_amendment_approval_required')

def main():
    started=time.monotonic()
    root=Path('/root/EASYkoopman-phase9-runtime-v59-20260920');addon=Path(__file__).resolve().parent
    sys.path.insert(0,str(root))
    from workflows.phase9_preflight_v59 import verify_release
    from workflows import run_runtime_v59 as runner
    protocol=read(addon/'protocol.json');manifest=read(addon/'MANIFEST.json')
    check_resource_approval(protocol,sha(addon/'MANIFEST.json'),sys.argv[1:])
    def verify():
        for name,digest in manifest['files_sha256'].items():
            path=(addon/name).resolve()
            if not path.is_relative_to(addon) or sha(path)!=digest:raise ValueError('addon_integrity:'+name)
        if verify_release(root)['release_sha256']!=protocol['release_sha256']:raise ValueError('frozen_release')
        for path,digest in protocol['historical_files_sha256'].items():
            if sha(path)!=digest:raise ValueError('historical_evidence_changed')
    def retained():
        debugger=protocol.get('debugger_tool_root')
        if debugger not in (None,'/root/EASYkoopman-phase9-debugger-v70-20260921'):raise ValueError('debugger_directory_binding')
        return retained_research_bytes(Path('/root').glob('EASYkoopman-phase9-*'),runner.disk_bytes,debugger_root=debugger)
    limit=protocol['limits'];charged=0.;attempts=0
    report=dict(status='running',configurations={},new_fits=0,charged_seconds=0.,physical_starts=0,
        manifest_sha256=sha(addon/'MANIFEST.json'),inherited=protocol['inherited_status'])
    (addon/'results').mkdir(exist_ok=False)
    runner.PER_HOST_BYTES=limit['new_bytes_per_host'];runner.DISK_STOP_BYTES=limit['new_bytes_per_host']-1024**2
    def run_case(case):
        nonlocal charged,attempts
        verify()
        if retained()>limit['retained_research_bytes_per_host']:raise ValueError('retained_disk_budget')
        remaining=min(limit['total_seconds']-charged,limit['total_seconds']-(time.monotonic()-started)-15.)
        if remaining<=6 or attempts>=limit['attempts']:raise ValueError('total_budget')
        cpu=case is None;case_id='cpu-check' if cpu else case['case_id']
        folder=addon/'results'/case_id;folder.mkdir(exist_ok=False)
        entry='check_multiconfig_worker_v68.py' if cpu else 'collect_effects_v67.py'
        command=[sys.executable,'-B','-u',str(addon/'bin'/entry),'--release-root',str(root),'--output',str(folder/('readiness.json' if cpu else 'output'))]
        if not cpu:command+=['--case',case_id]
        allocated=min(limit['case_seconds'],remaining);attempts+=1
        if not cpu:report['physical_starts']+=1
        native=runner.bounded_process(command,addon,folder/'collector.log',timeout_seconds=allocated)
        charged+=native['seconds'];native.update(case_id=case_id,manifest_sha256=report['manifest_sha256'])
        analysis=failure=None
        if not cpu and completed(native):
            analyzer='analyze_effects_v67.py' if native['native_exit']==0 else 'analyze_failure_v68.py'
            time_left=min(60.,allocated-native['seconds'],limit['total_seconds']-charged,
                limit['total_seconds']-(time.monotonic()-started)-15.)
            if time_left>3:
                command=[sys.executable,'-B',str(addon/'bin'/analyzer),'--release-root',str(root),'--case',case_id]
                native['analysis']=runner.bounded_process(command,addon,folder/'analysis.log',timeout_seconds=time_left)
                charged+=native['analysis']['seconds']
            if (folder/'analysis.json').exists():analysis=read(folder/'analysis.json')
            if (folder/'failure-analysis.json').exists():failure=read(folder/'failure-analysis.json')
        dump(folder/'native.json',native);verify()
        report['charged_seconds']=charged
        if cpu:
            readiness=read(folder/'readiness.json')
            status='accepted' if completed(native) and native['native_exit']==0 and readiness.get('passed') is True and readiness['model_sha256']==protocol['model_sha256'] else 'global_stop'
        else:status=classify(native,analysis,failure)
        print(json.dumps(dict(case=case_id,status=status,seconds=native['seconds'],charged_seconds=charged)),flush=True)
        return status
    try:
        verify()
        inherited_cpu=protocol.get('inherited_cpu_readiness_path')
        if inherited_cpu:
            ready=read(inherited_cpu);native=read(Path(inherited_cpu).parent/'native.json')
            if (not completed(native) or native['native_exit']!=0 or ready.get('passed') is not True
                    or ready['model_sha256']!=protocol['model_sha256']
                    or [r['configuration'] for r in ready['workers']]!=protocol['configuration_order']):
                raise ValueError('inherited_cpu_readiness_failed')
            print(json.dumps(dict(cpu_readiness='reused_verified_unchanged_workers',path=inherited_cpu)),flush=True)
        elif run_case(None)!='accepted':raise ValueError('cpu_readiness_failed')
        order=protocol.get('execution_configuration_order',protocol['configuration_order'])
        if not order or any(name not in protocol['configuration_order'] for name in order):raise ValueError('execution_order')
        for name in order:
            config=report['configurations'][name]=dict(status='running',cases={},not_run=[])
            selected=[q for q in protocol['cases'] if q['configuration']==name]
            for index,case in enumerate(selected):
                inherited_case=protocol.get('inherited_case_paths',{}).get(case['case_id'])
                if inherited_case:
                    verify();status=accepted_prior_case(inherited_case,case)
                    config.setdefault('inherited_cases',[]).append(case['case_id'])
                else:status=run_case(case)
                config['cases'][case['case_id']]=status
                if status=='global_stop':raise ValueError('unclassified_or_integrity_failure:'+case['case_id'])
                if status=='configuration_no_go':
                    config.update(status='configuration_support_no_go',not_run=[q['case_id'] for q in selected[index+1:]])
                    break
            else:config['status']='four_arms_accepted'
        report['status']='bounded_coverage_finished' if order==protocol['configuration_order'] else 'bounded_subset_finished'
    except BaseException as exc:
        report.update(status='global_stop',exception=type(exc).__name__+':'+str(exc))
    finally:
        report.update(charged_seconds=charged,retained_bytes=retained(),addon_bytes=runner.disk_bytes(addon),wall_seconds=time.monotonic()-started)
        if report['wall_seconds']>limit['total_seconds']:report['status']='global_stop'
        if report['retained_bytes']>limit['retained_research_bytes_per_host'] or report['addon_bytes']>limit['new_bytes_per_host']:report['status']='global_stop'
        dump(addon/'results/stage-result.json',report)
        print(json.dumps(report),flush=True)
    return 0 if report['status'] in ('bounded_coverage_finished','bounded_subset_finished') else 1

if __name__=='__main__':raise SystemExit(main())

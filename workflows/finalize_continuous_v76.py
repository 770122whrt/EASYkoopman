"""Inventory a finished bounded experiment, preserving failures and all files."""
import argparse,hashlib,json,subprocess,tarfile
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True);a=p.parse_args()
    processes=subprocess.check_output(['ps','-eo','pid,args'],text=True)
    active=[x for x in processes.splitlines() if any('-m workflows.'+name in x for name in
        ('collect_continuous_v76','run_continuous_v76','validate_continuous_v76'))]
    if active:raise RuntimeError('active_experiment_processes:'+str(active))
    cases=[]
    for cfg in ('base','uuv4','long_body','uuv6'):
        for kind in ('feedback','projected_koopman','nominal_physics'):
            suffix='r1' if cfg=='base' and kind=='feedback' else 'r3'
            name=f'{cfg}-pitch-{kind}-{suffix}';directory=a.root/name
            summary=json.loads((directory/'summary.json').read_text())
            accepted=(directory/'acceptance.json').exists()
            digest=hashlib.sha256((directory/'trace.json.gz').read_bytes()).hexdigest()
            if accepted:
                check=json.loads((directory/'acceptance.json').read_text())
                assert check['status']=='accepted_bounded_simulation_time_closed_loop'
                assert digest==check['trace_sha256']
            else:assert summary['status']=='failed'
            assert summary['model_fits']==0 and not summary['cleanup_errors']
            assert summary['cleanup_completed']['environment'] and summary['cleanup_completed']['simulation_app']
            cases.append(dict(name=name,accepted=accepted,physical_steps=summary['physical_steps'],
                exception=summary.get('exception'),trace_sha256=digest))
    exits=[dict(file=p.name,**json.loads(p.read_text())) for p in a.root.glob('*.exit.json')]
    assert all(x['group_stopped'] for x in exits)
    files={p.relative_to(a.root).as_posix():dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
           for p in sorted(a.root.rglob('*')) if p.is_file()}
    size=sum(x['bytes'] for x in files.values());assert size<128*1024**2
    result=dict(scope='v76_first_group_development',cases=cases,main_cases=len(cases),
        accepted_main_cases=sum(x['accepted'] for x in cases),
        main_physics_steps=sum(x['physical_steps'] for x in cases),native_runs=exits,
        recorded_collector_validator_wall_seconds=sum(x['seconds'] for x in exits),
        active_experiment_processes=active,files=files,bytes_before_inventory=size,
        budget_note='Native run wall time includes main and development failures; offline CPU analysis is separately recorded',
        model_fits=0,phase9_complete=False,representation_gain_proven=False)
    with (a.root/'post-audit.json').open('x') as f:json.dump(result,f,indent=2)
    with tarfile.open(a.archive,'x:gz') as archive:
        for p in sorted(a.root.rglob('*')):
            if p.is_file():archive.add(p,arcname=p.relative_to(a.root).as_posix(),recursive=False)
    print(json.dumps(dict(main_cases=12,accepted_main_cases=result['accepted_main_cases'],
        bytes=size,native_wall_seconds=result['recorded_collector_validator_wall_seconds'],
        archive=str(a.archive),archive_sha256=hashlib.sha256(a.archive.read_bytes()).hexdigest())))


if __name__=='__main__':main()

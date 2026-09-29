"""Explicit-case bounded runner; diagnostic summaries cannot affect accounting."""
import argparse,json,sys,time
from pathlib import Path
from workflows.run_continuous_v76 import run
from workflows.protocol_v77 import settings


def charges(root):
    records=[json.loads(p.read_text()) for p in root.glob('*.exit.json')]
    return sum(r['seconds'] for r in records),sum('workflows.collect_reliable_v77' in r['command'] for r in records)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--assets',required=True);p.add_argument('--manifest',required=True)
    p.add_argument('--queue',type=Path,required=True);a=p.parse_args();a.root.mkdir(exist_ok=True)
    for case in json.loads(a.queue.read_text()):
        cfg,kind,profile,suffix=case;settings(profile)
        spent,starts=charges(a.root)
        if spent+1100>7200 or starts>=22:raise RuntimeError('v77_total_budget_guard')
        if sum(p.stat().st_size for p in a.root.rglob('*') if p.is_file())>256*1024**2:raise RuntimeError('v77_disk_guard')
        name=f'{cfg}-pitch-{kind}-{profile}-{suffix}';out=a.root/name
        command=[sys.executable,'-B','-m','workflows.collect_reliable_v77','--configuration',cfg,'--controller',kind,
            '--profile',profile,'--assets',a.assets,'--manifest',a.manifest,'--output',str(out)]
        r=run(command,a.root/(name+'.log'),1000);print(json.dumps(dict(case=name,stage='collector',**r)),flush=True)
        if r['native_exit']!=0 or not r['group_stopped']:return 1
        r=run([sys.executable,'-B','-m','workflows.validate_reliable_v77','--trace',str(out/'trace.json.gz'),
               '--assets',a.assets,'--native-exit','0'],a.root/(name+'-validation.log'),90)
        print(json.dumps(dict(case=name,stage='validator',**r)),flush=True)
        if r['native_exit']!=0 or not r['group_stopped']:return 1
        d=json.loads((out/'summary.json').read_text())
        print(json.dumps(dict(case=name,status='accepted',metrics=d['metrics'])),flush=True)
    return 0


if __name__=='__main__':sys.exit(main())

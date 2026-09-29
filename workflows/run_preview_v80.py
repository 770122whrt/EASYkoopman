"""Bounded serial v80 queue. Every failed collection/validation remains charged."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from workflows.run_continuous_v76 import run


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--assets',required=True);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--queue',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]
    def verify():
        for rel,digest in json.loads(a.manifest.read_text())['files'].items():
            if hashlib.sha256((root/rel).read_bytes()).hexdigest()!=digest:raise ValueError('source_changed:'+rel)
    verify()
    for case in json.loads(a.queue.read_text()):
        prior=[json.loads(f.read_text()) for f in a.output.glob('*.exit.json')]
        spent=sum(r['seconds'] for r in prior)
        starts=sum('workflows.collect_preview_v80' in r['command'] for r in prior)
        if starts>=8 or spent+2380>10800:raise ValueError('stage_resource_budget')
        if sum(f.stat().st_size for f in a.output.rglob('*') if f.is_file())>400*1024**2:
            raise ValueError('output_reserve_budget')
        name=case['name'];target=a.output/name
        cmd=[sys.executable,'-B','-m','workflows.collect_preview_v80','--configuration',case['configuration'],
             '--controller',case['controller'],'--preview',case['preview'],'--task',case.get('task','pitch_pos'),
             '--assets',a.assets,'--manifest',str(a.manifest),'--output',str(target)]
        result=run(cmd,a.output/(name+'.log'),2200)
        print(json.dumps(dict(case=name,stage='collector',**result)),flush=True)
        verify()
        if result['native_exit']!=0 or not result['group_stopped']:return 1
        cmd=[sys.executable,'-B','-m','workflows.validate_preview_v80','--trace',str(target/'trace.json.gz'),
             '--assets',a.assets,'--native-exit','0']
        result=run(cmd,a.output/(name+'-validation.log'),180)
        print(json.dumps(dict(case=name,stage='validator',**result)),flush=True)
        verify()
        if result['native_exit']!=0 or not result['group_stopped']:return 1
        print(json.dumps(dict(case=name,status='accepted',metrics=json.loads((target/'summary.json').read_text())['metrics'])),flush=True)
    return 0


if __name__=='__main__':sys.exit(main())

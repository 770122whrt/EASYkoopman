"""Serial bounded collector/validator runs; stop at first failure for inspection."""
import argparse,json,os,signal,subprocess,sys,time
from pathlib import Path
from workflows.run_runtime_v58 import live_group_members


def run(command,log,timeout):
    started=time.monotonic()
    with log.open('xb') as stream:
        process=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:code=process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);code=process.wait(timeout=5)
        remaining=live_group_members(process.pid)
        if remaining:
            os.killpg(process.pid,signal.SIGTERM);time.sleep(.5)
            if live_group_members(process.pid):os.killpg(process.pid,signal.SIGKILL)
            time.sleep(.1)
        stopped=not live_group_members(process.pid)
    result=dict(native_exit=code,group_stopped=stopped,seconds=time.monotonic()-started,command=command)
    with log.with_suffix('.exit.json').open('x') as f:json.dump(result,f,indent=2)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--assets',required=True);p.add_argument('--manifest',required=True)
    p.add_argument('--queue',type=Path,required=True);a=p.parse_args()
    cases=json.loads(a.queue.read_text());start=time.monotonic()
    prior=sum(json.loads(p.read_text()).get('wall_seconds',0) for p in a.root.glob('*/summary.json'))
    for cfg,controller,suffix in cases:
        if prior+time.monotonic()-start>5400-600:raise TimeoutError('stage_budget_reserve')
        if sum(p.stat().st_size for p in a.root.rglob('*') if p.is_file())>128*1024**2:raise ValueError('stage_disk_guard')
        name=cfg+'-pitch-'+controller+'-'+suffix;output=a.root/name
        cmd=[sys.executable,'-B','-m','workflows.collect_continuous_v76','--configuration',cfg,
             '--controller',controller,'--assets',a.assets,'--manifest',a.manifest,'--output',str(output)]
        result=run(cmd,a.root/(name+'.log'),600)
        print(json.dumps(dict(case=name,stage='collector',**result)),flush=True)
        if result['native_exit']!=0 or not result['group_stopped']:return 1
        result=run([sys.executable,'-B','-m','workflows.validate_continuous_v76','--trace',str(output/'trace.json.gz'),
                    '--assets',a.assets,'--native-exit','0'],a.root/(name+'-validation.log'),90)
        print(json.dumps(dict(case=name,stage='validator',**result)),flush=True)
        if result['native_exit']!=0 or not result['group_stopped']:return 1
        summary=json.loads((output/'summary.json').read_text())
        print(json.dumps(dict(case=name,status='accepted',metrics=summary['metrics'])),flush=True)
    return 0


if __name__=='__main__':sys.exit(main())

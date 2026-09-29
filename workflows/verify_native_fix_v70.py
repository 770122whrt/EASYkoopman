"""One actual native-exit regression case; stop before any further physical run."""
import hashlib,json,sys,time
from pathlib import Path
ROOT=Path('/root/EASYkoopman-phase9-runtime-v59-20260920')
sys.path.insert(0,str(ROOT))
from workflows.run_runtime_v59 import bounded_process
from workflows.phase9_preflight_v59 import verify_release

def main():
    start=time.monotonic();addon=Path(__file__).resolve().parent
    manifest=json.loads((addon/'MANIFEST.json').read_text())
    def verify():
        verify_release(ROOT)
        for name,expected in manifest['files_sha256'].items():
            if hashlib.sha256((addon/name).read_bytes()).hexdigest()!=expected:raise ValueError('addon_changed:'+name)
    verify()
    case='uuv4-pitch-feedback';folder=addon/'results'/case;folder.mkdir(parents=True,exist_ok=False)
    n=bounded_process([sys.executable,'-B','-u',str(addon/'bin/collect_effects_v67.py'),
        '--release-root',str(ROOT),'--case',case,'--output',str(folder/'output')],addon,folder/'collector.log',timeout_seconds=120)
    if n['native_exit']==0 and n['reason']=='completed' and n['group_stopped']:
        n['analysis']=bounded_process([sys.executable,'-B',str(addon/'bin/analyze_effects_v67.py'),
            '--release-root',str(ROOT),'--case',case],addon,folder/'analysis.log',timeout_seconds=min(50,175-(time.monotonic()-start)))
    verify()
    with (folder/'native.json').open('x') as f:json.dump(n,f,indent=2)
    result=dict(status='native_fix_validation_finished',physical_starts=1,wall_seconds=time.monotonic()-start,native=n,
        accepted=bool(n['native_exit']==0 and n.get('analysis',{}).get('native_exit')==0 and (folder/'analysis.json').exists()))
    with (addon/'results/stage-result.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result))
    return 0 if result['accepted'] else 1

if __name__=='__main__':raise SystemExit(main())

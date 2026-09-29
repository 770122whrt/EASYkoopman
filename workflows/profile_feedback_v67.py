"""Bounded same-input replay of actual failed decisions; no simulation or fitting."""
import argparse,json,gzip,time,sys,os,cProfile,pstats,gc
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--addon',required=True);p.add_argument('--output',required=True);args=p.parse_args()
sys.path.insert(0,args.root)
import koopman
koopman.__path__.insert(0,str(Path(args.addon)/'koopman'))
import numpy as np,torch
torch.set_num_threads(1)
from koopman.inexact_tracking_v66 import InexactTrackingFeedback
from koopman.bounded_feedback_v46 import FeedbackConfig
from workflows.runtime_assets_v56 import AssetLocation,load_assets
from workflows.collect_runtime_v59 import HANDOFF_SHA
from koopman.diagnostics_v23 import json_safe
assets=load_assets(AssetLocation(args.root,'.','assets/v38/inputs',HANDOFF_SHA),model_key='nonlinear__pooled')
started=time.perf_counter();out=dict(schema='feedback-tail-replay-v67',diagnostic_only=True,fit_or_simulation=False,
 thread_limits={k:os.environ.get(k) for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS')},cases=[])
for name in ['base-depth-feedback-v66-retry','base-pitch-feedback-v66']:
 data=json.load(gzip.open(Path(args.addon)/'results'/name/'output/diagnostic.json.gz','rt'))
 item=data['inexact_feedback_audit'][-1];case=dict(name=name,original_elapsed_ms=item['result']['elapsed_ms'],runs=[])
 fb=InexactTrackingFeedback(assets.domains['base'],assets.context('base'),config=FeedbackConfig(timeout_ms=10))
 for i in range(100):
  if time.perf_counter()-started>60:raise TimeoutError('replay_budget')
  t=time.perf_counter();cpu=time.process_time();thread=time.thread_time()
  answer=fb.decide(item['state'],item['reference'],previous=item['previous'])
  case['runs'].append(dict(wall_ms=1000*(time.perf_counter()-t),cpu_ms=1000*(time.process_time()-cpu),
   thread_ms=1000*(time.thread_time()-thread),status=answer['status'],reason=answer['reason'],
   command=answer['command'],evaluations=answer['evaluations'],iterations=answer['iterations']))
 fb=InexactTrackingFeedback(assets.domains['base'],assets.context('base'),config=FeedbackConfig(timeout_ms=1000))
 profiler=cProfile.Profile();answer=profiler.runcall(fb.decide,item['state'],item['reference'],previous=item['previous'])
 stats=pstats.Stats(profiler);case['profile_top']=sorted([dict(file=k[0],line=k[1],function=k[2],calls=v[1],self_s=v[2],cumulative_s=v[3]) for k,v in stats.stats.items()],key=lambda x:x['cumulative_s'],reverse=True)[:20]
 times=[r['wall_ms'] for r in case['runs']];case['summary']=dict(p50_ms=float(np.median(times)),p95_ms=float(np.percentile(times,95)),maximum_ms=max(times),timeout_count=sum(r['reason']=='timeout' for r in case['runs']))
 out['cases'].append(case)
out['seconds']=time.perf_counter()-started
Path(args.output).write_text(json.dumps(json_safe(out),indent=2,allow_nan=False))
print(json.dumps(dict(seconds=out['seconds'],cases=[dict(name=c['name'],**c['summary']) for c in out['cases']])))

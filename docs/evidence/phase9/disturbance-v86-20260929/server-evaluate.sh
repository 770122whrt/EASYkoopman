#!/bin/bash
set -euo pipefail
source /root/shared-nvme/agentic-auv/activate.sh
cd /root/shared-nvme/agentic-auv/workspaces/disturbance-v86-20260929
export PYTHONPATH=/root/shared-nvme/agentic-auv/solverdeps/casadi-3.7.2-v76:$PWD
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
unset DISPLAY
/root/shared-nvme/agentic-auv/runtime/bin/python -B - <<'PY'
from pathlib import Path
import hashlib,json,sys
from workflows.protocol_v86 import cases
from workflows.run_continuous_v76 import run
for q in cases():
    assert json.loads((Path('data')/q['run_id']/'acceptance.json').read_text())['status']=='accepted_data_only'
for action in ('train','validation','test'):
    output='model.json' if action=='train' else action+'.json'
    command=[sys.executable,'-B','-m','workflows.fit_disturbance_v86',action,
        '--data','data','--manifest','v86-manifest.json','--output',output]
    if action!='train':command+=['--model','model.json']
    r=run(command,Path(action+'.log'),180)
    print(json.dumps(dict(stage=action,**r)),flush=True)
    if r['native_exit'] or not r['group_stopped']:
        print(Path(action+'.log').read_text()[-12000:],flush=True);raise SystemExit(1)
    if action!='train':print(json.dumps(json.loads(Path(output).read_text())['gates']),flush=True)
sha=hashlib.sha256(Path('model.json').read_bytes()).hexdigest()
print('FROZEN_MODEL_SHA256='+sha,flush=True)
r=run([sys.executable,'-B','-m','workflows.solve_disturbance_v86',
    '--data','data','--manifest','v86-manifest.json','--model','model.json','--model-sha',sha,
    '--assets','/root/shared-nvme/agentic-auv/assets/frozen-v38-v76-20260924',
    '--output','solver.json'],Path('solver.log'),600)
print(json.dumps(dict(stage='offline_solver',**r)),flush=True)
if r['native_exit'] or not r['group_stopped']:
    print(Path('solver.log').read_text()[-12000:],flush=True);raise SystemExit(1)
print(json.dumps({k:dict(passed=v['passed'],rows=[dict(episode=q['episode'],passed=q['passed'],failure=q.get('failure')) for q in v['rows']])
    for k,v in json.loads(Path('solver.json').read_text())['arms'].items()}),flush=True)
PY

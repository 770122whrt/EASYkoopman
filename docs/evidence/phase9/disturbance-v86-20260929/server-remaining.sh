#!/bin/bash
set -euo pipefail
source /root/shared-nvme/agentic-auv/activate.sh
cd /root/shared-nvme/agentic-auv/workspaces/disturbance-v86-20260929
export PYTHONPATH=/root/shared-nvme/agentic-auv/solverdeps/casadi-3.7.2-v76:$PWD
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
unset DISPLAY
/root/shared-nvme/agentic-auv/runtime/bin/python -B - <<'PY'
from pathlib import Path
import json,sys
from workflows.disturbance_data_v86 import verify_manifest,load_episode
from workflows.protocol_v86 import cases
from workflows.run_continuous_v76 import run
sha=verify_manifest('v86-manifest.json')
root=Path('data')
assert json.loads((root/cases()[0]['run_id']/'acceptance.json').read_text())['status']=='accepted_data_only'
for q in cases()[1:]:
    print('START '+q['run_id'],flush=True)
    if (root/q['run_id']).exists():raise FileExistsError(q['run_id'])
    r=run([sys.executable,'-B','-m','workflows.collect_disturbance_data_v86','--case',q['run_id'],
        '--manifest','v86-manifest.json','--output',str(root/q['run_id'])],root/(q['run_id']+'.log'),600)
    print(json.dumps(r),flush=True)
    if r['native_exit'] or not r['group_stopped']:
        print((root/(q['run_id']+'.log')).read_text()[-12000:],flush=True);raise SystemExit(1)
    try:
        e=load_episode(root/q['run_id'],sha)
        result=dict(status='accepted_data_only',case=e['case'],trace_sha256=e['trace_sha256'],
            states_shape=list(e['states'].shape),inputs_shape=list(e['inputs'].shape),
            prediction_benefit_established=False,closed_loop_benefit_established=False)
    except Exception as exc:
        result=dict(status='failed_data_acceptance',error=type(exc).__name__+':'+str(exc))
    with (root/q['run_id']/'acceptance.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result),flush=True)
    if result['status']!='accepted_data_only':raise SystemExit(1)
PY

#!/bin/bash
set -euo pipefail
source /root/shared-nvme/agentic-auv/activate.sh
cd /root/shared-nvme/agentic-auv/workspaces/matrix-v88-20260929
export PYTHONPATH=/root/shared-nvme/agentic-auv/solverdeps/casadi-3.7.2-v76:$PWD
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
unset DISPLAY
/root/shared-nvme/agentic-auv/runtime/bin/python -B - "$@" <<'PY'
from pathlib import Path
import hashlib,json,sys
from concurrent.futures import ThreadPoolExecutor
from workflows.disturbance_data_v88 import verify_manifest,load_episode
from workflows.protocol_v88 import cases
from workflows.run_continuous_v76 import run
sha=verify_manifest('v88-manifest.json')
root=Path('data');root.mkdir(exist_ok=True)
model='docs/evidence/phase9/diverse-v87-20260929/server/model.json'
support='docs/evidence/phase9/matrix-v88-20260929/support.json'

def checked(command,log,timeout):
    r=run(command,Path(log),timeout);print(json.dumps(r),flush=True)
    if r['native_exit'] or not r['group_stopped']:
        print(Path(log).read_text()[-6000:],flush=True);raise RuntimeError('native_failed:'+log)
    return r

def collect(q):
    import numpy as np
    print('START '+q['run_id'],flush=True)
    if (root/q['run_id']).exists():raise FileExistsError(q['run_id'])
    checked([sys.executable,'-B','-m','workflows.collect_disturbance_data_v88','--case',q['run_id'],
        '--manifest','v88-manifest.json','--output',str(root/q['run_id'])],str(root/(q['run_id']+'.log')),600)
    try:
        e=load_episode(root/q['run_id'],sha);x=e['states']
        result=dict(status='accepted_data_only',case=e['case'],trace_sha256=e['trace_sha256'],
            states_shape=list(x.shape),inputs_shape=list(e['inputs'].shape),
            max_linear_speed=float(np.max(np.linalg.norm(x[:,5:8],axis=1))),
            max_angular_speed=float(np.max(np.linalg.norm(x[:,8:],axis=1))),
            max_attitude_rad=float(np.max(2*np.arccos(np.clip(abs(x[:,1]),0,1)))))
    except Exception as exc:result=dict(status='failed_data_acceptance',error=type(exc).__name__+':'+str(exc))
    with (root/q['run_id']/'acceptance.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result),flush=True)
    if result['status']!='accepted_data_only':raise RuntimeError('acceptance_failed:'+q['run_id'])

mode=sys.argv[1]
if mode=='preflight':
    tests=['test_support_v88','test_solver_v88','test_matrix_data_v88','test_timeout_candidate_v86',
        'test_disturbance_lifted_v86','test_data_v86','test_command_state_v39','test_continuous_prediction_v76',
        'test_continuous_mpc_v76','test_continuous_mpc_v80','test_preview_solver_v80']
    checked([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',
        *['tests/'+t+'.py' for t in tests],'-k','not release and not package','--junitxml=server-tests.xml'],
        'server-tests.log',300)
    print(Path('server-tests.log').read_text()[-4000:],flush=True)
elif mode=='data':
    with ThreadPoolExecutor(max_workers=2) as pool:
        q=cases()
        for i in range(0,len(q),2):
            pending=[pool.submit(collect,c) for c in q[i:i+2]]
            for p in pending:p.result()
elif mode=='evaluate':
    for q in cases():assert json.loads((root/q['run_id']/'acceptance.json').read_text())['status']=='accepted_data_only'
    for role in ('validation','test'):
        checked([sys.executable,'-B','-m','workflows.evaluate_disturbance_v88','--role',role,
            '--data','data','--manifest','v88-manifest.json','--model',model,'--output',role+'.json'],role+'.log',600)
        print(role+' complete',flush=True)
elif mode=='solve':
    support_sha=hashlib.sha256(Path(support).read_bytes()).hexdigest()
    checked([sys.executable,'-B','-m','workflows.solve_disturbance_v88','--data','data','--manifest','v88-manifest.json',
        '--model',model,'--support',support,'--support-sha',support_sha,
        '--assets','/root/shared-nvme/agentic-auv/assets/frozen-v38-v76-20260924','--output','solver.json'],
        'solver.log',2400)
else:raise ValueError(mode)
PY

#!/bin/bash
set -euo pipefail
source /root/shared-nvme/agentic-auv/activate.sh
cd /root/shared-nvme/agentic-auv/workspaces/diverse-v87-20260929
export PYTHONPATH=/root/shared-nvme/agentic-auv/solverdeps/casadi-3.7.2-v76:$PWD
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
unset DISPLAY
/root/shared-nvme/agentic-auv/runtime/bin/python -B - "$@" <<'PY'
from pathlib import Path
import hashlib,json,sys
from concurrent.futures import ThreadPoolExecutor
from workflows.disturbance_data_v87 import verify_manifest,load_episode
from workflows.protocol_v87 import cases
from workflows.run_continuous_v76 import run
sha=verify_manifest('v87-manifest.json')
root=Path('data');root.mkdir(exist_ok=True)
pilot=next(q for q in cases() if q['role']=='train' and q['amplitude_scale']==2 and q['excitation']=='chirp')

def collect(q):
    print('START '+q['run_id'],flush=True)
    if (root/q['run_id']).exists():raise FileExistsError(q['run_id'])
    r=run([sys.executable,'-B','-m','workflows.collect_disturbance_data_v87','--case',q['run_id'],
        '--manifest','v87-manifest.json','--output',str(root/q['run_id'])],root/(q['run_id']+'.log'),600)
    print(json.dumps(r),flush=True)
    if r['native_exit'] or not r['group_stopped']:
        print((root/(q['run_id']+'.log')).read_text()[-8000:],flush=True);raise RuntimeError('collector_failed:'+q['run_id'])
    try:
        import numpy as np
        e=load_episode(root/q['run_id'],sha);x=e['states']
        result=dict(status='accepted_data_only',case=e['case'],trace_sha256=e['trace_sha256'],
            states_shape=list(x.shape),inputs_shape=list(e['inputs'].shape),
            max_linear_speed=float(np.max(np.linalg.norm(x[:,5:8],axis=1))),
            max_angular_speed=float(np.max(np.linalg.norm(x[:,8:],axis=1))),
            max_attitude_rad=float(np.max(2*np.arccos(np.clip(abs(x[:,1]),0,1)))),
            prediction_benefit_established=False,closed_loop_benefit_established=False)
    except Exception as exc:
        result=dict(status='failed_data_acceptance',error=type(exc).__name__+':'+str(exc))
    with (root/q['run_id']/'acceptance.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result),flush=True)
    if result['status']!='accepted_data_only':raise RuntimeError('data_acceptance_failed:'+q['run_id'])
    return result

mode=sys.argv[1]
if mode=='preflight':
    tests=['test_diverse_v87','test_timeout_candidate_v86','test_disturbance_lifted_v86','test_protocol_v86',
        'test_data_v86','test_fit_disturbance_v86','test_control_v86','test_command_state_v39',
        'test_continuous_prediction_v76','test_continuous_mpc_v76','test_continuous_mpc_v80',
        'test_preview_solver_v80','test_preview_decision_v79','test_causal_inputs_v84',
        'test_lifted_propagation_v84','test_physical_control_v76','test_geometry_v76']
    # Package creation test requires a Git checkout, absent from this source snapshot.
    r=run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',
        *['tests/'+t+'.py' for t in tests],'-k','not v87_release_includes',
        '--junitxml=server-tests.xml'],Path('server-tests.log'),240)
    print(json.dumps(r),flush=True);print(Path('server-tests.log').read_text()[-6000:],flush=True)
    if r['native_exit'] or not r['group_stopped']:raise SystemExit(1)
    collect(pilot)
elif mode=='data':
    assert json.loads((root/pilot['run_id']/'acceptance.json').read_text())['status']=='accepted_data_only'
    remaining=[q for q in cases() if q!=pilot]
    # Submit pairs only; stop before the next pair on any failure.
    with ThreadPoolExecutor(max_workers=2) as pool:
        for i in range(0,len(remaining),2):
            futures=[pool.submit(collect,q) for q in remaining[i:i+2]]
            for future in futures:future.result()
elif mode=='evaluate':
    for q in cases():
        assert json.loads((root/q['run_id']/'acceptance.json').read_text())['status']=='accepted_data_only'
    assert json.loads(Path('train.exit.json').read_text())['native_exit']==0
    assert Path('model.json').is_file()
    for action in ('validation','test'):
        output='model.json' if action=='train' else action+'.json'
        command=[sys.executable,'-B','-m','workflows.fit_disturbance_v87',action,
            '--data','data','--manifest','v87-manifest.json','--output',output]
        if action!='train':command+=['--model','model.json']
        r=run(command,Path(action+'.log'),300)
        print(json.dumps(dict(stage=action,**r)),flush=True)
        if r['native_exit'] or not r['group_stopped']:
            print(Path(action+'.log').read_text()[-8000:],flush=True);raise SystemExit(1)
        if action!='train':print(json.dumps(json.loads(Path(output).read_text())['gates']),flush=True)
    model_sha=hashlib.sha256(Path('model.json').read_bytes()).hexdigest()
    print('MODEL_SHA256='+model_sha,flush=True)
    r=run([sys.executable,'-B','-m','workflows.solve_disturbance_v87','--data','data',
        '--manifest','v87-manifest.json','--model','model.json','--model-sha',model_sha,
        '--assets','/root/shared-nvme/agentic-auv/assets/frozen-v38-v76-20260924',
        '--output','solver.json'],Path('solver.log'),900)
    print(json.dumps(dict(stage='solver',**r)),flush=True)
    if r['native_exit'] or not r['group_stopped']:
        print(Path('solver.log').read_text()[-8000:],flush=True);raise SystemExit(1)
    print(json.dumps({k:v['passed'] for k,v in json.loads(Path('solver.json').read_text())['arms'].items()}),flush=True)
else:raise ValueError(mode)
PY

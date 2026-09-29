#!/bin/bash
set -euo pipefail
source /root/shared-nvme/agentic-auv/activate.sh
cd /root/shared-nvme/agentic-auv/workspaces/diverse-v87-20260929
export PYTHONPATH=/root/shared-nvme/agentic-auv/solverdeps/casadi-3.7.2-v76:$PWD
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
/root/shared-nvme/agentic-auv/runtime/bin/python -B - <<'PY'
from pathlib import Path
import json,sys,hashlib
from workflows.protocol_v87 import cases
from workflows.run_continuous_v76 import run
for q in cases():
    if q['role']=='train':assert json.loads((Path('data')/q['run_id']/'acceptance.json').read_text())['status']=='accepted_data_only'
r=run([sys.executable,'-B','-m','workflows.fit_disturbance_v87','train','--data','data',
    '--manifest','v87-manifest.json','--output','model.json'],Path('train.log'),300)
print(json.dumps(r),flush=True)
if r['native_exit'] or not r['group_stopped']:
    print(Path('train.log').read_text()[-8000:]);raise SystemExit(1)
print('MODEL_SHA256='+hashlib.sha256(Path('model.json').read_bytes()).hexdigest(),flush=True)
PY

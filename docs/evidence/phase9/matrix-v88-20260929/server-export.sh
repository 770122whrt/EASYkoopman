#!/bin/bash
set -euo pipefail
source /root/shared-nvme/agentic-auv/activate.sh
cd /root/shared-nvme/agentic-auv/workspaces/matrix-v88-20260929
export PYTHONPATH=/root/shared-nvme/agentic-auv/solverdeps/casadi-3.7.2-v76:$PWD
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
/root/shared-nvme/agentic-auv/runtime/bin/python -B - <<'PY'
from pathlib import Path
import hashlib,json,tarfile
from workflows.disturbance_data_v88 import verify_manifest
sha=verify_manifest('v88-manifest.json')
files=sorted(p for p in Path('data').rglob('*') if p.is_file())
files += [Path(n) for n in ['v88-manifest.json','support-load-check.json','validation.json','test.json','solver.json',
    'server-tests.log','server-tests.xml','server-tests.exit.json','validation.log','validation.exit.json',
    'test.log','test.exit.json','solver.log','solver.exit.json','preflight.log','collection.log','evaluation.log','solve-run.log']]
files += [Path('docs/evidence/phase9/diverse-v87-20260929/server/model.json'),Path('docs/evidence/phase9/matrix-v88-20260929/support.json')]
inventory=dict(source_manifest_sha256=sha,files={str(p):dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in files})
with Path('evidence-inventory.json').open('x') as f:json.dump(inventory,f,indent=2)
with Path('evidence.tar.gz').open('xb') as f:
    with tarfile.open(fileobj=f,mode='w:gz') as tar:
        for p in files+[Path('evidence-inventory.json')]:tar.add(p,arcname=str(p),recursive=False)
print(json.dumps(dict(files=len(files),archive_sha256=hashlib.sha256(Path('evidence.tar.gz').read_bytes()).hexdigest(),archive_bytes=Path('evidence.tar.gz').stat().st_size)))
PY
ps -eo pid,etime,args | grep -E 'workflows.(collect_disturbance|solve_disturbance|evaluate_disturbance)|multiprocessing.spawn' | grep -v grep || true
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader

#!/bin/bash
set -euo pipefail
source /root/shared-nvme/agentic-auv/activate.sh
cd /root/shared-nvme/agentic-auv/workspaces/matrix-v88-20260929
export PYTHONPATH=/root/shared-nvme/agentic-auv/solverdeps/casadi-3.7.2-v76:$PWD
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
/root/shared-nvme/agentic-auv/runtime/bin/python -B - <<'PY'
import hashlib,json
from pathlib import Path
from workflows.runtime_assets_v56 import load_assets,AssetLocation
from koopman.control_support_v88 import load_domain
from workflows.disturbance_data_v88 import verify_manifest,MODEL_PATH,SUPPORT_PATH
sha=verify_manifest('v88-manifest.json')
a=load_assets(AssetLocation('/root/shared-nvme/agentic-auv/assets/frozen-v38-v76-20260924','.','assets/v38/inputs','5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
d=load_domain(SUPPORT_PATH,hashlib.sha256(Path(SUPPORT_PATH).read_bytes()).hexdigest(),a.domains['base'],MODEL_PATH)
r=dict(accepted=True,source_manifest_sha256=sha,domain=d.record(),identity=d.identity)
with Path('support-load-check.json').open('x') as f:json.dump(r,f,indent=2)
print(json.dumps(dict(accepted=True,identity=d.identity)))
PY

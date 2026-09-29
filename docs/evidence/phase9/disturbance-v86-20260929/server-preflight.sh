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
from workflows.disturbance_data_v86 import verify_manifest
from workflows.run_continuous_v76 import run
print('manifest',verify_manifest('v86-manifest.json'),flush=True)
names=['timeout_candidate_v86','disturbance_lifted_v86','protocol_v86','data_v86',
       'fit_disturbance_v86','control_v86','command_state_v39','continuous_prediction_v76',
       'continuous_mpc_v76','continuous_mpc_v80','preview_solver_v80','preview_decision_v79',
       'causal_inputs_v84','lifted_propagation_v84','physical_control_v76','geometry_v76']
r=run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',
    *['tests/test_'+n+'.py' for n in names],'--junitxml=server-tests.xml'],Path('server-tests.log'),180)
print(Path('server-tests.log').read_text(),flush=True)
print(json.dumps(r),flush=True)
raise SystemExit(0 if r['native_exit']==0 and r['group_stopped'] else 1)
PY

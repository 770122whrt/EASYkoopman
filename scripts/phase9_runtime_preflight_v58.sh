#!/usr/bin/env bash
set -Eeuo pipefail
readonly PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly PYTHON_BIN="${1:?explicit existing Isaac Python executable required}"
readonly APPROVAL="${2:?new Phase9 approval JSON required}"
[[ -x "$PYTHON_BIN" && -f "$APPROVAL" && -f "$PROJECT_ROOT/PHASE9_RELEASE.json" ]]
cd -- "$PROJECT_ROOT"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PROJECT_ROOT"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMBA_NUM_THREADS=1
# Supervisor SIGTERM closes the active isolated child process group. Five
# seconds remain for cleanup; timeout/native failure never grants acceptance.
exec timeout --signal=TERM --kill-after=5s 1795s "$PYTHON_BIN" -B -m workflows.run_runtime_v58 \
  --release-root "$PROJECT_ROOT" --approval "$APPROVAL"

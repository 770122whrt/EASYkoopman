#!/usr/bin/env bash
set -Eeuo pipefail
readonly PROJECT_ROOT=/root/EASYkoopman-phase8-4-projected-formal-v38-r23
readonly TRANSFER_ROOT=/root/phase84-projected-formal-v38-r23
readonly ISAACLAB_PY=/root/IsaacLab/isaaclab.sh
readonly STAGE="${1:?preflight, validation or test required}"
case "$STAGE" in preflight|validation|test) ;; *) exit 2 ;; esac
cd "$PROJECT_ROOT"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PROJECT_ROOT"
/opt/conda/envs/isaaclab/bin/python -B -m workflows.run_projected_formal_v38 --stage "$STAGE" --check-only
readonly PREFLIGHT_ROOT="$TRANSFER_ROOT/runtime-$STAGE"
[[ ! -e "$PREFLIGHT_ROOT" ]] || exit 1
mkdir "$PREFLIGHT_ROOT"
source scripts/phase6_server_preflight.sh
source scripts/phase6_offline_install.sh
phase6_activate_conda_env "$PREFLIGHT_ROOT" /opt/conda/etc/profile.d/conda.sh isaaclab /opt/conda/envs/isaaclab/bin/python
phase6_capture_locked_isaaclab_state "$PREFLIGHT_ROOT" /root/IsaacLab 2.2.1 v2.2.1 \
  0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20 c91a125c73c8b574878419a9583afc0b63b99f0a \
  d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079 \
  source/isaaclab_mimic/setup.py source/isaaclab_rl/setup.py
phase6_prepare_offline_python_env "$PREFLIGHT_ROOT" "$ISAACLAB_PY" "$PROJECT_ROOT"
python -B -m workflows.run_projected_formal_v38 --stage "$STAGE"

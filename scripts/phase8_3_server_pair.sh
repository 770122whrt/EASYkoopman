#!/usr/bin/env bash
# First gate only: two 32-interval runs. Invoke under the runbook's 30m timeout.
set -Eeuo pipefail
readonly PROJECT_ROOT="/root/EASYkoopman-phase8-3-trace-20260912"
readonly RESULT_ROOT="$PROJECT_ROOT/tmp/phase8_3/first-pair-status"
readonly ISAACLAB_ROOT="/root/IsaacLab"
readonly ISAACLAB_PY="$ISAACLAB_ROOT/isaaclab.sh"
readonly CONDA_PYTHON="/opt/conda/envs/isaaclab/bin/python"
[[ "$(pwd -P)" == "$PROJECT_ROOT" ]] || { echo wrong_project_root >&2; exit 1; }
[[ ! -e "$RESULT_ROOT" ]] || { echo preserve_existing_attempt >&2; exit 1; }
for mode in on off; do
    [[ ! -e "$PROJECT_ROOT/tmp/phase8_3/trace-base-8201-$mode" ]] || exit 1
done
mkdir -p "$RESULT_ROOT/logs"
trap 'rc=$?; printf "%s\n" "$rc" > "$RESULT_ROOT/runner.exit_status"' EXIT
source "$PROJECT_ROOT/scripts/phase6_server_preflight.sh"
source "$PROJECT_ROOT/scripts/phase6_offline_install.sh"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PROJECT_ROOT"
phase6_activate_conda_env "$RESULT_ROOT" /opt/conda/etc/profile.d/conda.sh isaaclab "$CONDA_PYTHON"
phase6_capture_locked_isaaclab_state "$RESULT_ROOT" "$ISAACLAB_ROOT" 2.2.1 v2.2.1 \
    0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20 c91a125c73c8b574878419a9583afc0b63b99f0a \
    d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079 \
    source/isaaclab_mimic/setup.py source/isaaclab_rl/setup.py
phase6_prepare_offline_python_env "$RESULT_ROOT" "$ISAACLAB_PY" "$PROJECT_ROOT"
# These checks do not import Isaac; actual runtime versions are also checked in the driver.
"$CONDA_PYTHON" -B - <<'PY' > "$RESULT_ROOT/source_preflight.json"
import hashlib, json
from pathlib import Path
from importlib.metadata import version
from workflows.collect_koopman_v21_identification import _repository_commit
root = Path.cwd()
manifest = json.loads((root / 'SOURCE_MANIFEST.json').read_text())
for name, expected in manifest['files_sha256'].items():
    if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
        raise RuntimeError('source_manifest_mismatch:' + name)
if '.'.join(version('isaacsim').split('.')[:2]) != '5.0':
    raise RuntimeError('isaacsim_version_mismatch')
print(json.dumps({'source_commit': _repository_commit(), 'manifest_files': len(manifest['files_sha256'])}))
PY
for mode in on off; do
    set +e
    timeout --signal=TERM --kill-after=30s 10m "$ISAACLAB_PY" -p -B -m workflows.trace_control_v23 \
        --run-id "trace-base-8201-$mode" --trace "$mode" --execute \
        > "$RESULT_ROOT/logs/$mode.log" 2>&1
    native_status=$?
    set -e
    printf '%s\n' "$native_status" > "$RESULT_ROOT/$mode.exit_status"
    [[ "$native_status" -eq 0 ]] || exit "$native_status"
done
"$CONDA_PYTHON" -B -m workflows.validate_control_trace_v23 \
    --trace-on tmp/phase8_3/trace-base-8201-on/trace.json \
    --trace-off tmp/phase8_3/trace-base-8201-off/trace.json \
    > "$RESULT_ROOT/pair-validation.json"
# Bind the actually loaded env, not only the current working directory.
"$CONDA_PYTHON" -B - <<'PY' > "$RESULT_ROOT/loaded-binding.json"
import hashlib, json
from pathlib import Path
from workflows.collect_koopman_v21_identification import _repository_commit
root = Path.cwd()
expected = {'EasyUUVEnv': root / 'easyuuv_nc/env/easyuuv_env.py',
            'DirectRLEnv': Path('/root/IsaacLab/source/isaaclab/isaaclab/envs/direct_rl_env.py')}
commit = _repository_commit()
for mode in ('on', 'off'):
    report = json.loads((root / f'tmp/phase8_3/trace-base-8201-{mode}/trace.json').read_text())
    if report['source_commit'] != commit:
        raise RuntimeError('loaded_source_commit_mismatch')
    for name, path in expected.items():
        recorded = report['loaded_sources'][name]
        if (Path(recorded['path']).resolve() != path.resolve()
                or recorded['sha256'] != hashlib.sha256(path.read_bytes()).hexdigest()):
            raise RuntimeError('loaded_source_binding_mismatch:' + name)
print(json.dumps({'status': 'loaded_binding_pass', 'source_commit': commit}))
PY
printf 'pair_gate_pass_pending_pullback\n' > "$RESULT_ROOT/status.txt"
# Stop here. Inventory and byte-for-byte pullback follow after this script exits.

#!/usr/bin/env bash
set -Eeuo pipefail

readonly EXPECTED_COMMIT_FILE="${1:?expected source commit sidecar required}"
readonly PROJECT_ROOT="/root/EASYkoopman-phase8-pilot-v2"
readonly RESULT_ROOT="$PROJECT_ROOT/source/results/koopman_phase8_pilot"
readonly STATUS_ROOT="$PROJECT_ROOT/source/results/koopman_phase8_pilot_status"
readonly ISAACLAB_ROOT="/root/IsaacLab"
readonly ISAACLAB_PY="/root/IsaacLab/isaaclab.sh"
readonly OFFLINE_INSTALL_HELPER="$PROJECT_ROOT/scripts/phase6_offline_install.sh"
readonly CONDA_SH="/opt/conda/etc/profile.d/conda.sh"
readonly CONDA_ENVIRONMENT="isaaclab"
readonly CONDA_PYTHON="/opt/conda/envs/isaaclab/bin/python"
readonly RUNNER="$PROJECT_ROOT/workflows/collect_koopman_v2_identification.py"
readonly AUDITOR="$PROJECT_ROOT/workflows/audit_koopman_v2_pilot.py"
readonly VALIDATOR="$PROJECT_ROOT/workflows/validate_phase8_evidence.py"
readonly POLICY_VALIDATOR="$PROJECT_ROOT/workflows/validate_phase8_pilot_policy.py"
readonly POLICY="$PROJECT_ROOT/protocols/phase8/pilot_collection_policy.json"
readonly EXPECTED_ISAAC_SIM="5.0"
readonly EXPECTED_ISAAC_LAB="2.2.1"
readonly EXPECTED_ISAAC_LAB_RELEASE_TAG="v2.2.1"
readonly EXPECTED_ISAAC_LAB_RELEASE_COMMIT="0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20"
readonly EXPECTED_ISAAC_LAB_REPO_COMMIT="c91a125c73c8b574878419a9583afc0b63b99f0a"
readonly EXPECTED_ISAAC_LAB_PATCH_SHA256="d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079"
readonly -a EXPECTED_ISAAC_LAB_DIRTY_FILES=(
    "source/isaaclab_mimic/setup.py"
    "source/isaaclab_rl/setup.py"
)

# shellcheck disable=SC1091
source "$PROJECT_ROOT/scripts/phase6_server_preflight.sh"
# shellcheck disable=SC1091
source "$OFFLINE_INSTALL_HELPER"
# The shared helper enforces a known setuptools version and installs with
# --no-deps --no-build-isolation --no-index; these Phase 8 markers are kept
# explicit so the offline dependency contract remains directly auditable.
export PYTHONDONTWRITEBYTECODE=1

die() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

expected_commit="$(tr -d '\r\n' < "$EXPECTED_COMMIT_FILE")"
[[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]] || die "expected_commit_invalid"
server_head="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
[[ "$server_head" == "$expected_commit" ]] || die "server_head_mismatch"
status="$(git -C "$PROJECT_ROOT" -c core.excludesFile= status --porcelain=v1 --untracked-files=all)"
[[ -z "$status" ]] || die "server_checkout_not_clean"
[[ ! -e "$RESULT_ROOT" ]] || die "stale_result_reuse"
[[ ! -e "$STATUS_ROOT" ]] || die "stale_status_reuse"
[[ -x "$ISAACLAB_PY" ]] || die "isaaclab_launcher_missing"
[[ -f "$CONDA_SH" ]] || die "conda_activation_script_missing"
mkdir -p "$RESULT_ROOT"/{episodes,manifests,logs} "$STATUS_ROOT"
phase6_activate_conda_env "$STATUS_ROOT" "$CONDA_SH" "$CONDA_ENVIRONMENT" "$CONDA_PYTHON"
if ! "$CONDA_PYTHON" "$POLICY_VALIDATOR" --policy "$POLICY" --json \
    > "$STATUS_ROOT/pilot_policy_validator.json"; then
    die "pilot_policy_validator_failed"
fi
policy_sha256="$(sha256sum "$POLICY" | awk '{print $1}')"
validated_policy_sha256="$(
    "$CONDA_PYTHON" -c \
        'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["policy_sha256"])' \
        "$STATUS_ROOT/pilot_policy_validator.json"
)"
[[ "$policy_sha256" == "$validated_policy_sha256" ]] || die "pilot_policy_hash_mismatch"
printf '%s\n' "$policy_sha256" > "$STATUS_ROOT/pilot_policy.sha256"
cp "$POLICY" "$RESULT_ROOT/pilot_collection_policy.json"

set +e
"$ISAACLAB_PY" -p -c \
    'from importlib.metadata import version; print("PHASE6_ACTUAL_ISAAC_SIM=" + ".".join(version("isaacsim").split(".")[:2]))' \
    > "$STATUS_ROOT/isaac_sim_version.log" 2>&1
sim_status=$?
set -e
actual_sim="$(sed -n 's/^PHASE6_ACTUAL_ISAAC_SIM=//p' "$STATUS_ROOT/isaac_sim_version.log" | tail -n 1 | tr -d '\r')"
phase6_require_preflight_value "$STATUS_ROOT" "isaac_sim_version" "$EXPECTED_ISAAC_SIM" "$actual_sim" "$sim_status"
phase6_capture_locked_isaaclab_state \
    "$STATUS_ROOT" "$ISAACLAB_ROOT" "$EXPECTED_ISAAC_LAB" \
    "$EXPECTED_ISAAC_LAB_RELEASE_TAG" "$EXPECTED_ISAAC_LAB_RELEASE_COMMIT" \
    "$EXPECTED_ISAAC_LAB_REPO_COMMIT" "$EXPECTED_ISAAC_LAB_PATCH_SHA256" \
    "${EXPECTED_ISAAC_LAB_DIRTY_FILES[@]}" || die "isaaclab_locked_state_mismatch"
actual_lab="$(tr -d '\r\n' < "$STATUS_ROOT/isaaclab_version_file.txt")"
phase6_prepare_offline_python_env "$STATUS_ROOT" "$ISAACLAB_PY" "$PROJECT_ROOT"
printf '%s\n' "$expected_commit" > "$STATUS_ROOT/source_commit.txt"
printf '%s\n' "$actual_sim" > "$STATUS_ROOT/isaac_sim_version.txt"
printf '%s\n' "$actual_lab" > "$STATUS_ROOT/isaaclab_version.txt"

any_failed=0
run_one() {
    local configuration="$1"
    local native_status tee_status semantic_status validator_status
    local -a pipeline_status
    set +e
    # One configuration process collects its two policy episodes sequentially.
    "$ISAACLAB_PY" -p -u "$RUNNER" \
        --policy "$POLICY" --configuration "$configuration" --headless \
        --result-root "$RESULT_ROOT" \
        2>&1 | tee "$STATUS_ROOT/$configuration.process.log"
    pipeline_status=("${PIPESTATUS[@]}")
    set -e
    native_status="${pipeline_status[0]:-125}"
    tee_status="${pipeline_status[1]:-125}"
    semantic_status="fail"
    if [[ "$native_status" -eq 0 && "$tee_status" -eq 0 ]]; then
        set +e
        "$ISAACLAB_PY" -p -c \
            "import json,pathlib; p=json.loads(pathlib.Path('$POLICY').read_text()); c='$configuration'; e=[x for x in p['entries'] if x['configuration']==c]; r=pathlib.Path('$RESULT_ROOT'); assert len(e)==2; assert all((r/'episodes'/(x['episode_id']+'.jsonl')).is_file() and (r/'manifests'/(x['episode_id']+'.manifest.json')).is_file() for x in e)" \
            > "$STATUS_ROOT/$configuration.validator.log" 2>&1
        validator_status=$?
        set -e
        [[ "$validator_status" -eq 0 ]] && semantic_status="pass"
    fi
    printf '%s\n' "$native_status" > "$STATUS_ROOT/$configuration.native_status"
    printf '%s\n' "$tee_status" > "$STATUS_ROOT/$configuration.tee_status"
    printf '%s\n' "$semantic_status" > "$STATUS_ROOT/$configuration.semantic_status"
    if [[ "$native_status" -ne 0 || "$tee_status" -ne 0 || "$semantic_status" != "pass" ]]; then
        any_failed=1
    fi
}

run_one base
run_one long_body
run_one heavy_moderate
run_one asymmetric
run_one uuv6
run_one uuv6_angled
run_one uuv4
run_one uuv4_angled

if [[ "$any_failed" -ne 0 ]]; then
    printf '%s\n' "runner_failure_blocks_audit" | tee "$STATUS_ROOT/qualification_failure.txt" >&2
    exit 1
fi

# Manifests share locked runtime facts; process/tee/semantic status is additionally
# preserved per configuration in STATUS_ROOT and checked before audit/pullback.
"$ISAACLAB_PY" -p "$AUDITOR" --root "$RESULT_ROOT" --require-server --json \
    2>&1 | tee "$STATUS_ROOT/auditor.json"
"$ISAACLAB_PY" -p "$VALIDATOR" \
    --envelope "$RESULT_ROOT/pilot_envelope.json" \
    --qualification server_isaac_identification_pilot --json \
    2>&1 | tee "$STATUS_ROOT/validator.json"
if find "$PROJECT_ROOT" -type d -name __pycache__ -print -quit | grep -q .; then
    die "bytecode_pollution"
fi
(
    cd "$RESULT_ROOT"
    find . -type f -print0 | sort -z | xargs -0 sha256sum > "$STATUS_ROOT/all_files.sha256"
    sha256sum -c "$STATUS_ROOT/all_files.sha256"
) > "$STATUS_ROOT/inventory_validator.json"
sha256sum "$RESULT_ROOT/pilot_envelope.json" | tee "$STATUS_ROOT/pilot_envelope.sha256"

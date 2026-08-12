#!/usr/bin/env bash
set -Eeuo pipefail

readonly EXPECTED_COMMIT_FILE="${1:?expected source commit sidecar required}"
readonly PROJECT_ROOT="/root/EASYkoopman-phase7-v2"
readonly RESULT_ROOT="$PROJECT_ROOT/source/results/koopman_phase7"
readonly ISAACLAB_ROOT="/root/IsaacLab"
readonly ISAACLAB_PY="/root/IsaacLab/isaaclab.sh"
readonly RUNNER="$PROJECT_ROOT/workflows/collect_koopman_v2_smoke.py"
readonly VALIDATOR="$PROJECT_ROOT/workflows/validate_koopman_v2.py"
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

# Reuse the Phase 6 unchanged-server validator.  The locked server checkout has
# no Git tag object; release identity is VERSION + parent + exact patch state.
# shellcheck disable=SC1091
source "$PROJECT_ROOT/scripts/phase6_server_preflight.sh"

export PYTHONDONTWRITEBYTECODE=1

die() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

record_preflight_failure() {
    local check_name="$1"
    local expected="$2"
    local actual="$3"
    local status="$4"
    mkdir -p "$RESULT_ROOT/logs"
    printf 'check=%s\nexpected=%s\nactual=%s\ncommand_status=%s\n' \
        "$check_name" "$expected" "$actual" "$status" \
        > "$RESULT_ROOT/preflight_failure.txt"
    die "runtime_version_mismatch:$check_name"
}

expected_commit="$(tr -d '\r\n' < "$EXPECTED_COMMIT_FILE")"
[[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]] || die "expected_commit_invalid"
server_head="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
[[ "$server_head" == "$expected_commit" ]] || die "server_head_mismatch"
status="$(git -C "$PROJECT_ROOT" -c core.excludesFile= status --porcelain=v1 --untracked-files=all)"
[[ -z "$status" ]] || die "server_checkout_not_clean"
[[ ! -e "$RESULT_ROOT" ]] || die "stale_result_reuse"
[[ -x "$ISAACLAB_PY" ]] || die "isaaclab_launcher_missing"
mkdir -p "$RESULT_ROOT"/{episodes,manifests,logs,failures,status}

set +e
actual_sim="$($ISAACLAB_PY -p -c \
    'from importlib.metadata import version; print(".".join(version("isaacsim").split(".")[:2]))' \
    2>"$RESULT_ROOT/logs/isaac_sim_version.log")"
sim_status=$?
set -e
[[ "$sim_status" -eq 0 && "$actual_sim" == "$EXPECTED_ISAAC_SIM" ]] \
    || record_preflight_failure "isaac_sim" "$EXPECTED_ISAAC_SIM" "$actual_sim" "$sim_status"

phase6_capture_locked_isaaclab_state \
    "$RESULT_ROOT" \
    "$ISAACLAB_ROOT" \
    "$EXPECTED_ISAAC_LAB" \
    "$EXPECTED_ISAAC_LAB_RELEASE_TAG" \
    "$EXPECTED_ISAAC_LAB_RELEASE_COMMIT" \
    "$EXPECTED_ISAAC_LAB_REPO_COMMIT" \
    "$EXPECTED_ISAAC_LAB_PATCH_SHA256" \
    "${EXPECTED_ISAAC_LAB_DIRTY_FILES[@]}" \
    || die "isaaclab_locked_state_mismatch"
actual_lab="$(tr -d '\r\n' < "$RESULT_ROOT/isaaclab_version_file.txt")"

set +e
setuptools_version="$($ISAACLAB_PY -p -c \
    'from importlib.metadata import version; print(version("setuptools"))' \
    2>"$RESULT_ROOT/logs/setuptools_version.log")"
setuptools_status=$?
set -e
[[ "$setuptools_status" -eq 0 && -n "$setuptools_version" ]] \
    || record_preflight_failure "setuptools" "installed" "$setuptools_version" "$setuptools_status"

set +e
$ISAACLAB_PY -p -m pip install -e "$PROJECT_ROOT" \
    --no-deps --no-build-isolation --no-index \
    > "$RESULT_ROOT/logs/editable_install.log" 2>&1
install_status=$?
set -e
[[ "$install_status" -eq 0 ]] \
    || record_preflight_failure "offline_editable_install" 0 "$install_status" "$install_status"

printf '%s\n' "$expected_commit" > "$RESULT_ROOT/source_commit.txt"
printf '%s\n' "$actual_sim" > "$RESULT_ROOT/isaac_sim_version.txt"
printf '%s\n' "$actual_lab" > "$RESULT_ROOT/isaaclab_version.txt"

any_failed=0
run_one() {
    local configuration="$1"
    local episode_id="phase7-${configuration}-$(date -u +%Y%m%dT%H%M%SZ)"
    local native_status tee_status semantic_status
    local -a pipeline_status
    set +e
    "$ISAACLAB_PY" -p -u "$RUNNER" \
        --task EasyUUV-Direct-v1 \
        --configuration "$configuration" \
        --steps 8 --seed 0 --scenario phase7-server-smoke \
        --episode-id "$episode_id" --headless \
        --result-root "$RESULT_ROOT" \
        --output-jsonl "$RESULT_ROOT/episodes/$configuration.jsonl" \
        --output-manifest "$RESULT_ROOT/manifests/$configuration.manifest.json" \
        --failure-json "$RESULT_ROOT/failures/$configuration.failure.json" \
        2>&1 | tee "$RESULT_ROOT/logs/$configuration.log"
    pipeline_status=("${PIPESTATUS[@]}")
    set -e
    native_status="${pipeline_status[0]:-125}"
    tee_status="${pipeline_status[1]:-125}"
    semantic_status="fail"
    if [[ "$native_status" -eq 0 && "$tee_status" -eq 0 ]]; then
        set +e
        "$ISAACLAB_PY" -p "$VALIDATOR" \
            --jsonl "$RESULT_ROOT/episodes/$configuration.jsonl" \
            --manifest "$RESULT_ROOT/manifests/$configuration.manifest.json" \
            --json > "$RESULT_ROOT/status/$configuration.validator.json" 2>&1
        validator_status=$?
        set -e
        [[ "$validator_status" -eq 0 ]] && semantic_status="pass"
    fi
    printf '%s\n' "$native_status" > "$RESULT_ROOT/status/$configuration.native_status"
    printf '%s\n' "$tee_status" > "$RESULT_ROOT/status/$configuration.tee_status"
    printf '%s\n' "$semantic_status" > "$RESULT_ROOT/status/$configuration.semantic_status"
    if [[ "$native_status" -ne 0 || "$tee_status" -ne 0 || "$semantic_status" != "pass" ]]; then
        any_failed=1
    fi
}

run_one base
run_one uuv6
run_one uuv4

if [[ "$any_failed" -ne 0 ]]; then
    printf '%s\n' "runner_failure_blocks_merge" | tee "$RESULT_ROOT/qualification_failure.txt" >&2
    exit 1
fi

readonly MERGER="$PROJECT_ROOT/workflows/merge_koopman_v2_evidence.py"

if find "$PROJECT_ROOT" -type d -name __pycache__ -print -quit | grep -q .; then
    die "bytecode_pollution"
fi

"$ISAACLAB_PY" -p "$MERGER" \
    --manifest "$RESULT_ROOT/manifests/base.manifest.json" \
    --manifest "$RESULT_ROOT/manifests/uuv6.manifest.json" \
    --manifest "$RESULT_ROOT/manifests/uuv4.manifest.json" \
    --log "base=$RESULT_ROOT/logs/base.log" \
    --log "uuv6=$RESULT_ROOT/logs/uuv6.log" \
    --log "uuv4=$RESULT_ROOT/logs/uuv4.log" \
    --output "$RESULT_ROOT/evidence.json" --require-server \
    2>&1 | tee "$RESULT_ROOT/merge.log"

"$ISAACLAB_PY" -p "$VALIDATOR" --aggregate "$RESULT_ROOT/evidence.json" --json \
    2>&1 | tee "$RESULT_ROOT/validator.json"
sha256sum "$RESULT_ROOT/evidence.json" | tee "$RESULT_ROOT/evidence.sha256"
find "$RESULT_ROOT" -type f -print0 | sort -z | xargs -0 sha256sum \
    > "$RESULT_ROOT/all_files.sha256"

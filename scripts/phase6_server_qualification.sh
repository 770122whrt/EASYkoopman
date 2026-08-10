#!/usr/bin/env bash
set -Eeuo pipefail

readonly EXPECTED_COMMIT_FILE="${1:?expected source commit sidecar required}"
readonly PROJECT_ROOT="/root/EASYkoopman-phase6-v2"
readonly RESULT_ROOT="$PROJECT_ROOT/source/results/koopman_phase6"
readonly PREFLIGHT_ROOT="$RESULT_ROOT"
readonly ISAACLAB_ROOT="/root/IsaacLab"
readonly ISAACLAB_PY="/root/IsaacLab/isaaclab.sh"
readonly RUNNER="$PROJECT_ROOT/workflows/qualify_easyuuv_v2.py"
readonly MERGER="$PROJECT_ROOT/workflows/merge_easyuuv_v2_qualification.py"
readonly VALIDATOR="$PROJECT_ROOT/workflows/validate_easyuuv_v2_qualification.py"
readonly TASK_PROBE="$PROJECT_ROOT/scripts/phase6_probe_gym_tasks.py"
readonly PIPELINE_GATE="$PROJECT_ROOT/scripts/phase6_pipeline_gate.sh"
readonly PREFLIGHT_HELPER="$PROJECT_ROOT/scripts/phase6_server_preflight.sh"

# The repository intentionally contains source, not platform-specific generated
# bytecode.  Keep the server checkout stable across the probe and eight separate
# Python processes so the tracked-source provenance gate remains meaningful.
export PYTHONDONTWRITEBYTECODE=1

# shellcheck source=scripts/phase6_pipeline_gate.sh
source "$PIPELINE_GATE"
# shellcheck source=scripts/phase6_server_preflight.sh
source "$PREFLIGHT_HELPER"

die() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

expected_commit="$(tr -d '\r\n' < "$EXPECTED_COMMIT_FILE")"
[[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]] || die "expected_commit_invalid"
server_head="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
[[ "$server_head" == "$expected_commit" ]] || die "server_head_mismatch"
tracked_status="$(git -C "$PROJECT_ROOT" status --porcelain=v1 --untracked-files=no)"
[[ -z "$tracked_status" ]] || die "tracked_source_drift"

[[ -x "$ISAACLAB_PY" ]] || die "isaaclab_launcher_missing"
mkdir -p "$PREFLIGHT_ROOT" "$RESULT_ROOT/logs"
set +e
isaaclab_tag="$(git -C "$ISAACLAB_ROOT" describe --tags --exact-match HEAD \
    2> "$RESULT_ROOT/logs/isaaclab_repo_tag.log")"
isaaclab_tag_status=$?
set -e
phase6_require_preflight_value \
    "$PREFLIGHT_ROOT" "isaaclab_repo_tag" "v2.2.1" \
    "$isaaclab_tag" "$isaaclab_tag_status"
isaaclab_commit="$(git -C "$ISAACLAB_ROOT" rev-parse HEAD)"
[[ "$isaaclab_commit" =~ ^[0-9a-f]{40}$ ]] || die "isaaclab_commit_invalid"
isaaclab_tracked_status="$(git -C "$ISAACLAB_ROOT" status --porcelain=v1 --untracked-files=no)"
[[ -z "$isaaclab_tracked_status" ]] || die "isaaclab_tracked_source_drift"

set +e
"$ISAACLAB_PY" -p -c \
    'from importlib.metadata import version; print("PHASE6_ACTUAL_ISAAC_SIM=" + ".".join(version("isaacsim").split(".")[:2]))' \
    > "$RESULT_ROOT/logs/isaac_sim_version.log" 2>&1
isaac_sim_status=$?
set -e
actual_isaac_sim="$(sed -n 's/^PHASE6_ACTUAL_ISAAC_SIM=//p' \
    "$RESULT_ROOT/logs/isaac_sim_version.log" | tail -n 1 | tr -d '\r')"
phase6_require_preflight_value \
    "$PREFLIGHT_ROOT" "isaac_sim_version" "5.0" \
    "$actual_isaac_sim" "$isaac_sim_status"
"$ISAACLAB_PY" -p -m pip install -e "$PROJECT_ROOT" --no-deps

mkdir -p \
    "$RESULT_ROOT/rows" \
    "$RESULT_ROOT/logs" \
    "$RESULT_ROOT/exit_codes" \
    "$RESULT_ROOT/log_exit_codes"
printf '%s\n' "$expected_commit" > "$RESULT_ROOT/source_commit.txt"
printf '%s\n' "$isaaclab_tag" > "$RESULT_ROOT/isaaclab_repo_tag.txt"
printf '%s\n' "$isaaclab_commit" > "$RESULT_ROOT/isaaclab_repo_commit.txt"
"$ISAACLAB_PY" -p -c \
    'from importlib.metadata import version; print("isaacsim_distribution=" + version("isaacsim")); print("isaaclab_distribution=" + version("isaaclab"))' \
    | tee "$RESULT_ROOT/runtime_distributions.txt"
"$ISAACLAB_PY" -p "$TASK_PROBE" 2>&1 | tee "$RESULT_ROOT/gym_tasks.log"

any_failed=0
run_one() {
    local configuration="$1"
    local steps="$2"
    local runner_status
    local log_status
    local -a pipeline_status
    set +e
    "$ISAACLAB_PY" -p -u "$RUNNER" \
        --task EasyUUV-Direct-v1 \
        --configuration "$configuration" \
        --steps "$steps" \
        --seed 0 \
        --num-envs 1 \
        --headless \
        --result-root "$RESULT_ROOT" \
        --output-json "$RESULT_ROOT/rows/$configuration.json" \
        2>&1 | tee "$RESULT_ROOT/logs/$configuration.log"
    pipeline_status=("${PIPESTATUS[@]}")
    set -e
    runner_status="${pipeline_status[0]:-125}"
    log_status="${pipeline_status[1]:-125}"
    if ! phase6_record_pipeline_status \
        "$RESULT_ROOT" "$configuration" "$runner_status" "$log_status"; then
        any_failed=1
    fi
    return 0
}

run_one base 64
run_one long_body 8
run_one heavy_moderate 8
run_one asymmetric 8
run_one uuv6 8
run_one uuv6_angled 8
run_one uuv4 8
run_one uuv4_angled 8

if [[ "$any_failed" -ne 0 ]]; then
    printf '%s\n' "runner_failure_blocks_merge" \
        | tee "$RESULT_ROOT/qualification_failure.txt" >&2
    exit 1
fi

"$ISAACLAB_PY" -p "$MERGER" \
    --input "$RESULT_ROOT/rows/base.json" \
    --input "$RESULT_ROOT/rows/long_body.json" \
    --input "$RESULT_ROOT/rows/heavy_moderate.json" \
    --input "$RESULT_ROOT/rows/asymmetric.json" \
    --input "$RESULT_ROOT/rows/uuv6.json" \
    --input "$RESULT_ROOT/rows/uuv6_angled.json" \
    --input "$RESULT_ROOT/rows/uuv4.json" \
    --input "$RESULT_ROOT/rows/uuv4_angled.json" \
    --result-root "$RESULT_ROOT" \
    --output "$RESULT_ROOT/qualification.json" \
    2>&1 | tee "$RESULT_ROOT/merge.log"

"$ISAACLAB_PY" -p "$VALIDATOR" "$RESULT_ROOT/qualification.json" --json \
    --expected-source-commit-file "$EXPECTED_COMMIT_FILE" \
    --expected-isaaclab-commit-file "$RESULT_ROOT/isaaclab_repo_commit.txt" \
    --expected-isaaclab-tag-file "$RESULT_ROOT/isaaclab_repo_tag.txt" \
    2>&1 | tee "$RESULT_ROOT/validator.json"
sha256sum "$RESULT_ROOT/qualification.json" \
    | tee "$RESULT_ROOT/qualification.sha256"

#!/usr/bin/env bash
set -Eeuo pipefail

readonly PROJECT_ROOT="${PROJECT_ROOT:-/root/EASYkoopman-phase8-2-v1}"
readonly RESULT_ROOT="${RESULT_ROOT:-/root/EASYkoopman-phase8-2-results-v1}"
readonly DATASET_ROOT="$RESULT_ROOT/dataset"
readonly STATUS_ROOT="$RESULT_ROOT/status"
readonly CONFIGURATION_ROOT="$RESULT_ROOT/configurations"
readonly ISAACLAB_ROOT="/root/IsaacLab"
readonly ISAACLAB_PY="${ISAACLAB_PY:-$ISAACLAB_ROOT/isaaclab.sh}"
readonly CONDA_SH="/opt/conda/etc/profile.d/conda.sh"
readonly CONDA_ENVIRONMENT="isaaclab"
readonly CONDA_PYTHON="/opt/conda/envs/isaaclab/bin/python"
readonly ROLE_PROTOCOL="$PROJECT_ROOT/protocols/phase8_1/main_role_assignment_protocol.json"
readonly ANALYSIS_POLICY="$PROJECT_ROOT/protocols/phase8_1/analysis_policy.json"
readonly APPROVAL_RECORD="$PROJECT_ROOT/protocols/phase8_1/d23_approval.json"
readonly COLLECTOR="$PROJECT_ROOT/workflows/collect_koopman_v21_identification.py"
readonly OFFLINE_INSTALL_HELPER="$PROJECT_ROOT/scripts/phase6_offline_install.sh"
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
readonly -a CONFIGURATIONS=(
    base long_body heavy_moderate asymmetric uuv6 uuv6_angled uuv4 uuv4_angled
)

# shellcheck disable=SC1091
source "$PROJECT_ROOT/scripts/phase6_server_preflight.sh"
# shellcheck disable=SC1091
source "$OFFLINE_INSTALL_HELPER"
export PYTHONDONTWRITEBYTECODE=1

[[ ! -e "$RESULT_ROOT" ]] || { echo stale_or_partial_phase8_2_result_root >&2; exit 1; }
[[ -x "$ISAACLAB_PY" ]] || { echo isaaclab_launcher_missing >&2; exit 1; }
[[ -f "$CONDA_SH" ]] || { echo conda_activation_script_missing >&2; exit 1; }
mkdir -p "$DATASET_ROOT"/{episodes,manifests,logs} "$STATUS_ROOT" "$CONFIGURATION_ROOT"

phase6_activate_conda_env \
    "$STATUS_ROOT" "$CONDA_SH" "$CONDA_ENVIRONMENT" "$CONDA_PYTHON"
set +e
"$ISAACLAB_PY" -p -c \
    'from importlib.metadata import version; print("PHASE8_2_ACTUAL_ISAAC_SIM=" + ".".join(version("isaacsim").split(".")[:2]))' \
    > "$STATUS_ROOT/isaac_sim_version.log" 2>&1
sim_status=$?
set -e
actual_sim="$(sed -n 's/^PHASE8_2_ACTUAL_ISAAC_SIM=//p' "$STATUS_ROOT/isaac_sim_version.log" | tail -n 1 | tr -d '\r')"
phase6_require_preflight_value "$STATUS_ROOT" "isaac_sim_version" "$EXPECTED_ISAAC_SIM" "$actual_sim" "$sim_status"
phase6_capture_locked_isaaclab_state \
    "$STATUS_ROOT" "$ISAACLAB_ROOT" "$EXPECTED_ISAAC_LAB" \
    "$EXPECTED_ISAAC_LAB_RELEASE_TAG" "$EXPECTED_ISAAC_LAB_RELEASE_COMMIT" \
    "$EXPECTED_ISAAC_LAB_REPO_COMMIT" "$EXPECTED_ISAAC_LAB_PATCH_SHA256" \
    "${EXPECTED_ISAAC_LAB_DIRTY_FILES[@]}"
phase6_prepare_offline_python_env "$STATUS_ROOT" "$ISAACLAB_PY" "$PROJECT_ROOT"

source_commit="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
printf '%s\n' "$source_commit" > "$STATUS_ROOT/source_commit.txt"
sha256sum "$ROLE_PROTOCOL" | awk '{print $1}' > "$STATUS_ROOT/role_protocol.sha256"
sha256sum "$ANALYSIS_POLICY" | awk '{print $1}' > "$STATUS_ROOT/analysis_policy.sha256"
sha256sum "$APPROVAL_RECORD" | awk '{print $1}' > "$STATUS_ROOT/d23_approval.sha256"
"$CONDA_PYTHON" "$PROJECT_ROOT/workflows/validate_phase81_d23_approval.py" \
    --approval-record "$APPROVAL_RECORD" --role-protocol "$ROLE_PROTOCOL" \
    --analysis-policy "$ANALYSIS_POLICY" > "$STATUS_ROOT/d23_validator.log"

any_failed=0
for configuration in "${CONFIGURATIONS[@]}"; do
    config_root="$CONFIGURATION_ROOT/$configuration"
    declare -a pipeline_status=()
    set +e
    "$ISAACLAB_PY" -p "$COLLECTOR" \
        --approval-record "$APPROVAL_RECORD" \
        --role-protocol "$ROLE_PROTOCOL" \
        --analysis-policy "$ANALYSIS_POLICY" \
        --output-root "$config_root" \
        --configuration "$configuration" \
        --source-commit "$source_commit" --headless \
        2>&1 | tee "$STATUS_ROOT/$configuration.collector.log"
    pipeline_status=("${PIPESTATUS[@]}")
    set -e
    native_status="${pipeline_status[0]:-125}"
    tee_status="${pipeline_status[1]:-125}"
    printf '%s\n' "$native_status" > "$STATUS_ROOT/$configuration.native_status"
    printf '%s\n' "$tee_status" > "$STATUS_ROOT/$configuration.tee_status"
    semantic_status="fail"
    if [[ "$native_status" -eq 0 && "$tee_status" -eq 0 ]]; then
        episode_count="$(find "$config_root/episodes" -maxdepth 1 -type f -name '*.jsonl' | wc -l)"
        manifest_count="$(find "$config_root/manifests" -maxdepth 1 -type f -name '*.manifest.json' | wc -l)"
        log_count="$(find "$config_root/logs" -maxdepth 1 -type f -name '*.log' | wc -l)"
        part_count="$(find "$config_root" -type f -name '*.part' | wc -l)"
        if [[ "$episode_count" -eq 12 && "$manifest_count" -eq 12 && "$log_count" -eq 12 && "$part_count" -eq 0 ]]; then
            cp -a "$config_root/episodes/." "$DATASET_ROOT/episodes/"
            cp -a "$config_root/manifests/." "$DATASET_ROOT/manifests/"
            cp -a "$config_root/logs/." "$DATASET_ROOT/logs/"
            semantic_status="pass"
        fi
    fi
    printf '%s\n' "$semantic_status" > "$STATUS_ROOT/$configuration.semantic_status"
    [[ "$semantic_status" == "pass" ]] || any_failed=1
done
[[ "$any_failed" -eq 0 ]] || { echo runner_failure_blocks_inventory >&2; exit 1; }

episode_count="$(find "$DATASET_ROOT/episodes" -type f -name '*.jsonl' | wc -l)"
manifest_count="$(find "$DATASET_ROOT/manifests" -type f -name '*.manifest.json' | wc -l)"
log_count="$(find "$DATASET_ROOT/logs" -type f -name '*.log' | wc -l)"
part_count="$(find "$DATASET_ROOT" -type f -name '*.part' | wc -l)"
[[ "$episode_count" -eq 96 && "$manifest_count" -eq 96 && "$log_count" -eq 96 && "$part_count" -eq 0 ]] \
    || { echo exact_96_set_failed >&2; exit 1; }

"$CONDA_PYTHON" "$PROJECT_ROOT/workflows/build_phase82_dataset_index.py" build \
    --dataset-root "$DATASET_ROOT" --role-protocol "$ROLE_PROTOCOL" \
    --inventory "$DATASET_ROOT/dataset_inventory.json" \
    --split "$DATASET_ROOT/loco_split_manifest.json" \
    --source-commit "$source_commit" | tee "$STATUS_ROOT/dataset_index_builder.json"
"$CONDA_PYTHON" "$PROJECT_ROOT/workflows/validate_phase82_dataset_index.py" \
    --dataset-root "$DATASET_ROOT" --role-protocol "$ROLE_PROTOCOL" \
    --inventory "$DATASET_ROOT/dataset_inventory.json" \
    --split "$DATASET_ROOT/loco_split_manifest.json" \
    --source-commit "$source_commit" | tee "$STATUS_ROOT/dataset_index_validator.json"
(cd "$DATASET_ROOT"; find . -type f -print0 | sort -z | xargs -0 sha256sum > "$STATUS_ROOT/all_files.sha256"; sha256sum -c "$STATUS_ROOT/all_files.sha256") \
    > "$STATUS_ROOT/file_inventory_validator.log"
printf 'pass\n' > "$STATUS_ROOT/collection_complete.status"
printf 'phase8_2_server_collection=pass\n'

#!/usr/bin/env bash
set -Eeuo pipefail
readonly PROJECT_ROOT="${PROJECT_ROOT:-/root/EASYkoopman-phase8-main-v2}"
readonly ISAACLAB_ROOT="/root/IsaacLab"
readonly ISAACLAB_PY="${ISAACLAB_PY:-$ISAACLAB_ROOT/isaaclab.sh}"
readonly RESULT_ROOT="$PROJECT_ROOT/source/results/koopman_phase8_dataset"
readonly STATUS_ROOT="$PROJECT_ROOT/source/results/koopman_phase8_main_status"
readonly ROLE_PROTOCOL="$PROJECT_ROOT/protocols/phase8/main_role_assignment_protocol.json"
readonly ANALYSIS_POLICY="$PROJECT_ROOT/protocols/phase8/analysis_policy.json"
readonly COLLECTOR="$PROJECT_ROOT/workflows/collect_koopman_v2_identification.py"
readonly OFFLINE_INSTALL_HELPER="$PROJECT_ROOT/scripts/phase6_offline_install.sh"
readonly CONDA_SH="/opt/conda/etc/profile.d/conda.sh"
readonly CONDA_ENVIRONMENT="isaaclab"
readonly CONDA_PYTHON="/opt/conda/envs/isaaclab/bin/python"
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

# Reuse the server/runtime contract already exercised by Phases 6, 7 and the
# Phase 8 pilot.  Main collection must not depend on an interactive SSH shell
# having activated Conda before the runner starts.
# shellcheck disable=SC1091
source "$PROJECT_ROOT/scripts/phase6_server_preflight.sh"
# shellcheck disable=SC1091
source "$OFFLINE_INSTALL_HELPER"
export PYTHONDONTWRITEBYTECODE=1

[[ ! -e "$RESULT_ROOT" && ! -e "$STATUS_ROOT" ]] || { echo stale_or_partial_main_root >&2; exit 1; }
[[ -x "$ISAACLAB_PY" ]] || { echo isaaclab_launcher_missing >&2; exit 1; }
[[ -f "$CONDA_SH" ]] || { echo conda_activation_script_missing >&2; exit 1; }
mkdir -p "$RESULT_ROOT"/{episodes,manifests,logs} "$STATUS_ROOT"

phase6_activate_conda_env \
    "$STATUS_ROOT" "$CONDA_SH" "$CONDA_ENVIRONMENT" "$CONDA_PYTHON"
set +e
"$ISAACLAB_PY" -p -c \
    'from importlib.metadata import version; print("PHASE6_ACTUAL_ISAAC_SIM=" + ".".join(version("isaacsim").split(".")[:2]))' \
    > "$STATUS_ROOT/isaac_sim_version.log" 2>&1
sim_status=$?
set -e
actual_sim="$(sed -n 's/^PHASE6_ACTUAL_ISAAC_SIM=//p' \
    "$STATUS_ROOT/isaac_sim_version.log" | tail -n 1 | tr -d '\r')"
phase6_require_preflight_value \
    "$STATUS_ROOT" "isaac_sim_version" "$EXPECTED_ISAAC_SIM" \
    "$actual_sim" "$sim_status"
phase6_capture_locked_isaaclab_state \
    "$STATUS_ROOT" "$ISAACLAB_ROOT" "$EXPECTED_ISAAC_LAB" \
    "$EXPECTED_ISAAC_LAB_RELEASE_TAG" "$EXPECTED_ISAAC_LAB_RELEASE_COMMIT" \
    "$EXPECTED_ISAAC_LAB_REPO_COMMIT" "$EXPECTED_ISAAC_LAB_PATCH_SHA256" \
    "${EXPECTED_ISAAC_LAB_DIRTY_FILES[@]}"
phase6_prepare_offline_python_env "$STATUS_ROOT" "$ISAACLAB_PY" "$PROJECT_ROOT"

cp "$ROLE_PROTOCOL" "$RESULT_ROOT/main_role_assignment_protocol.json"
cp "$ANALYSIS_POLICY" "$RESULT_ROOT/analysis_policy.json"
source_commit="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
printf '%s\n' "$source_commit" > "$STATUS_ROOT/source_commit.txt"
sha256sum "$ROLE_PROTOCOL" | awk '{print $1}' > "$STATUS_ROOT/role_protocol.sha256"
sha256sum "$ANALYSIS_POLICY" | awk '{print $1}' > "$STATUS_ROOT/analysis_policy.sha256"

any_failed=0
for configuration in base long_body heavy_moderate asymmetric uuv6 uuv6_angled uuv4 uuv4_angled; do
    declare -a pipeline_status=()
    set +e
    "$ISAACLAB_PY" -p "$COLLECTOR" --policy "$ROLE_PROTOCOL" --configuration "$configuration" --result-root "$RESULT_ROOT" --headless 2>&1 | tee "$STATUS_ROOT/$configuration.log"
    pipeline_status=("${PIPESTATUS[@]}")
    set -e
    native_status="${pipeline_status[0]:-125}"
    tee_status="${pipeline_status[1]:-125}"
    printf '%s\n' "$native_status" > "$STATUS_ROOT/$configuration.native_status"
    printf '%s\n' "$tee_status" > "$STATUS_ROOT/$configuration.tee_status"
    semantic_status="fail"
    if [[ "$native_status" -eq 0 && "$tee_status" -eq 0 ]]; then
        episode_count="$(find "$RESULT_ROOT/episodes" -maxdepth 1 -type f -name "phase8-main-${configuration}-*.jsonl" | wc -l)"
        manifest_count="$(find "$RESULT_ROOT/manifests" -maxdepth 1 -type f -name "phase8-main-${configuration}-*.manifest.json" | wc -l)"
        log_count="$(find "$RESULT_ROOT/logs" -maxdepth 1 -type f -name "phase8-main-${configuration}-*.log" | wc -l)"
        part_count="$(find "$RESULT_ROOT/episodes" -maxdepth 1 -type f -name "phase8-main-${configuration}-*.part" | wc -l)"
        if [[ "$episode_count" -eq 12 && "$manifest_count" -eq 12 && "$log_count" -eq 12 && "$part_count" -eq 0 ]]; then
            semantic_status="pass"
        else
            printf 'configuration_exact_12_failed configuration=%s episodes=%s manifests=%s logs=%s parts=%s\n' \
                "$configuration" "$episode_count" "$manifest_count" "$log_count" "$part_count" >&2
        fi
    fi
    printf '%s\n' "$semantic_status" > "$STATUS_ROOT/$configuration.semantic_status"
    [[ "$semantic_status" == pass ]] || any_failed=1
done
[[ "$any_failed" -eq 0 ]] || { echo runner_failure_blocks_inventory >&2; exit 1; }

episode_count="$(find "$RESULT_ROOT/episodes" -type f -name '*.jsonl' | wc -l)"
manifest_count="$(find "$RESULT_ROOT/manifests" -type f -name '*.manifest.json' | wc -l)"
log_count="$(find "$RESULT_ROOT/logs" -type f -name '*.log' | wc -l)"
[[ "$episode_count" -eq 96 && "$manifest_count" -eq 96 && "$log_count" -eq 96 ]] || { echo exact_96_set_failed >&2; exit 1; }

runtime_json="$RESULT_ROOT/runtime_provenance.json"
# Evidence packaging does not require SimulationApp.  Use the locked Conda
# interpreter directly so launcher banners cannot contaminate captured values
# and Python failures retain their real nonzero exit status.
"$CONDA_PYTHON" -c 'import json; from pathlib import Path; from workflows.qualify_easyuuv_v2 import detect_runtime_provenance; import isaaclab; p=detect_runtime_provenance(isaaclab.__file__); Path("source/results/koopman_phase8_dataset/runtime_provenance.json").write_text(json.dumps(p["runtime_provenance"],sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")'
runtime_sha="$("$CONDA_PYTHON" -c 'from koopman.evidence_v2 import canonical_sha256,load_bounded_json; print(canonical_sha256(load_bounded_json("source/results/koopman_phase8_dataset/runtime_provenance.json")))')"
created_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
"$CONDA_PYTHON" workflows/build_koopman_v2_inventory.py --root "$RESULT_ROOT" --intent "$ROLE_PROTOCOL" --runtime-sha256 "$runtime_sha" --qualification server_isaac_identification_dataset --output "$RESULT_ROOT/dataset_inventory.json"
"$CONDA_PYTHON" workflows/build_koopman_v2_splits.py --root "$RESULT_ROOT" --protocol "$ROLE_PROTOCOL" --inventory "$RESULT_ROOT/dataset_inventory.json" --created-at "$created_at" --output "$RESULT_ROOT/loco_split_manifest.json"
"$CONDA_PYTHON" workflows/build_phase8_main_envelope.py --root "$RESULT_ROOT" --source-commit "$source_commit" --experiment-id phase8-main-identification-v2-proposal --role-protocol "$RESULT_ROOT/main_role_assignment_protocol.json" --analysis-policy "$RESULT_ROOT/analysis_policy.json" --runtime "$runtime_json" --inventory "$RESULT_ROOT/dataset_inventory.json" --split "$RESULT_ROOT/loco_split_manifest.json" --output "$RESULT_ROOT/dataset_envelope.json"
"$CONDA_PYTHON" workflows/validate_phase8_evidence.py --envelope "$RESULT_ROOT/dataset_envelope.json" --qualification server_isaac_identification_dataset --json | tee "$STATUS_ROOT/validator.json"
(cd "$RESULT_ROOT"; find . -type f ! -name all_files.sha256 -print0 | sort -z | xargs -0 sha256sum > "$STATUS_ROOT/all_files.sha256"; sha256sum -c "$STATUS_ROOT/all_files.sha256") > "$STATUS_ROOT/inventory_validator.json"
sha256sum "$RESULT_ROOT/dataset_envelope.json" > "$STATUS_ROOT/dataset_envelope.sha256"

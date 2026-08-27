#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="${PROJECT_ROOT:-/root/EASYkoopman-phase8-main-v2}"
ISAACLAB_PY="${ISAACLAB_PY:-/root/IsaacLab/isaaclab.sh}"
RESULT_ROOT="$PROJECT_ROOT/source/results/koopman_phase8_dataset"
STATUS_ROOT="$PROJECT_ROOT/source/results/koopman_phase8_main_status"
ROLE_PROTOCOL="$PROJECT_ROOT/protocols/phase8/main_role_assignment_protocol.json"
ANALYSIS_POLICY="$PROJECT_ROOT/protocols/phase8/analysis_policy.json"
COLLECTOR="$PROJECT_ROOT/workflows/collect_koopman_v2_identification.py"
[[ ! -e "$RESULT_ROOT" && ! -e "$STATUS_ROOT" ]] || { echo stale_or_partial_main_root >&2; exit 1; }
mkdir -p "$RESULT_ROOT" "$STATUS_ROOT"
cp "$ROLE_PROTOCOL" "$RESULT_ROOT/main_role_assignment_protocol.json"
cp "$ANALYSIS_POLICY" "$RESULT_ROOT/analysis_policy.json"
source_commit="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
printf '%s\n' "$source_commit" > "$STATUS_ROOT/source_commit.txt"
sha256sum "$ROLE_PROTOCOL" | awk '{print $1}' > "$STATUS_ROOT/role_protocol.sha256"
sha256sum "$ANALYSIS_POLICY" | awk '{print $1}' > "$STATUS_ROOT/analysis_policy.sha256"

any_failed=0
for configuration in base long_body heavy_moderate asymmetric uuv6 uuv6_angled uuv4 uuv4_angled; do
    set +e
    "$ISAACLAB_PY" -p "$COLLECTOR" --policy "$ROLE_PROTOCOL" --configuration "$configuration" --result-root "$RESULT_ROOT" --headless 2>&1 | tee "$STATUS_ROOT/$configuration.log"
    native_status=${PIPESTATUS[0]}; tee_status=${PIPESTATUS[1]}
    set -e
    printf '%s\n' "$native_status" > "$STATUS_ROOT/$configuration.native_status"
    printf '%s\n' "$tee_status" > "$STATUS_ROOT/$configuration.tee_status"
    semantic_status=pass; [[ "$native_status" -eq 0 && "$tee_status" -eq 0 ]] || semantic_status=fail
    printf '%s\n' "$semantic_status" > "$STATUS_ROOT/$configuration.semantic_status"
    [[ "$semantic_status" == pass ]] || any_failed=1
done
[[ "$any_failed" -eq 0 ]] || { echo runner_failure_blocks_inventory >&2; exit 1; }

episode_count="$(find "$RESULT_ROOT/episodes" -type f -name '*.jsonl' | wc -l)"
manifest_count="$(find "$RESULT_ROOT/manifests" -type f -name '*.manifest.json' | wc -l)"
log_count="$(find "$RESULT_ROOT/logs" -type f -name '*.log' | wc -l)"
[[ "$episode_count" -eq 96 && "$manifest_count" -eq 96 && "$log_count" -eq 96 ]] || { echo exact_96_set_failed >&2; exit 1; }

runtime_json="$RESULT_ROOT/runtime_provenance.json"
"$ISAACLAB_PY" -p -c 'import json; from pathlib import Path; from workflows.qualify_easyuuv_v2 import detect_runtime_provenance; import isaaclab; p=detect_runtime_provenance(isaaclab.__file__); Path("source/results/koopman_phase8_dataset/runtime_provenance.json").write_text(json.dumps(p["runtime_provenance"],sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")'
runtime_sha="$("$ISAACLAB_PY" -p -c 'from koopman.evidence_v2 import canonical_sha256,load_bounded_json; print(canonical_sha256(load_bounded_json("source/results/koopman_phase8_dataset/runtime_provenance.json")))')"
created_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
"$ISAACLAB_PY" -p workflows/build_koopman_v2_inventory.py --root "$RESULT_ROOT" --intent "$ROLE_PROTOCOL" --runtime-sha256 "$runtime_sha" --qualification server_isaac_identification_dataset --output "$RESULT_ROOT/dataset_inventory.json"
"$ISAACLAB_PY" -p workflows/build_koopman_v2_splits.py --root "$RESULT_ROOT" --protocol "$ROLE_PROTOCOL" --inventory "$RESULT_ROOT/dataset_inventory.json" --created-at "$created_at" --output "$RESULT_ROOT/loco_split_manifest.json"
"$ISAACLAB_PY" -p workflows/build_phase8_main_envelope.py --root "$RESULT_ROOT" --source-commit "$source_commit" --experiment-id phase8-main-identification-v2-proposal --role-protocol "$RESULT_ROOT/main_role_assignment_protocol.json" --analysis-policy "$RESULT_ROOT/analysis_policy.json" --runtime "$runtime_json" --inventory "$RESULT_ROOT/dataset_inventory.json" --split "$RESULT_ROOT/loco_split_manifest.json" --output "$RESULT_ROOT/dataset_envelope.json"
"$ISAACLAB_PY" -p workflows/validate_phase8_evidence.py --envelope "$RESULT_ROOT/dataset_envelope.json" --qualification server_isaac_identification_dataset --json | tee "$STATUS_ROOT/validator.json"
(cd "$RESULT_ROOT"; find . -type f ! -name all_files.sha256 -print0 | sort -z | xargs -0 sha256sum > "$STATUS_ROOT/all_files.sha256"; sha256sum -c "$STATUS_ROOT/all_files.sha256") > "$STATUS_ROOT/inventory_validator.json"
sha256sum "$RESULT_ROOT/dataset_envelope.json" > "$STATUS_ROOT/dataset_envelope.sha256"

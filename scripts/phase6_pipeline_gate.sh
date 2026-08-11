#!/usr/bin/env bash

# Record both sides of one runner | tee pipeline.  A successful physics runner
# is not acceptable evidence when its mandatory log could not be persisted.
phase6_record_pipeline_status() {
    local result_root="${1:?result root required}"
    local configuration="${2:?configuration required}"
    local runner_status="${3:?runner status required}"
    local log_status="${4:?log status required}"

    if [[ ! "$runner_status" =~ ^[0-9]+$ || ! "$log_status" =~ ^[0-9]+$ ]]; then
        printf 'invalid_pipeline_status:%s:runner=%s:log=%s\n' \
            "$configuration" "$runner_status" "$log_status" >&2
        return 1
    fi
    if ! printf '%s\n' "$runner_status" \
        > "$result_root/exit_codes/$configuration.txt"; then
        printf 'runner_status_write_failed:%s\n' "$configuration" >&2
        return 1
    fi
    if ! printf '%s\n' "$log_status" \
        > "$result_root/log_exit_codes/$configuration.txt"; then
        printf 'log_status_write_failed:%s\n' "$configuration" >&2
        return 1
    fi
    if [[ "$log_status" -ne 0 ]]; then
        printf 'log_capture_failed:%s:%s\n' "$configuration" "$log_status" >&2
        return 1
    fi
    [[ "$runner_status" -eq 0 ]]
}

phase6_require_runner_artifact() {
    local result_root="${1:?result root required}"
    local configuration="${2:?configuration required}"
    local python_executable="${3:?python executable required}"
    local artifact="$result_root/rows/$configuration.json"
    local gate_file="$result_root/artifact_gate_codes/$configuration.txt"

    if [[ ! -s "$artifact" ]]; then
        printf '%s\n' 1 > "$gate_file"
        printf 'runner_artifact_missing:%s\n' "$configuration" >&2
        return 1
    fi
    if "$python_executable" -c '
import json
import sys

path, expected_configuration = sys.argv[1:]
with open(path, encoding="utf-8") as stream:
    payload = json.load(stream)
results = payload.get("results")
valid = (
    payload.get("evidence_level") == "server_isaac_smoke"
    and isinstance(results, list)
    and len(results) == 1
    and isinstance(results[0], dict)
    and results[0].get("configuration") == expected_configuration
    and results[0].get("status") == "pass"
)
raise SystemExit(0 if valid else 1)
' "$artifact" "$configuration"; then
        printf '%s\n' 0 > "$gate_file"
        return 0
    fi
    printf '%s\n' 1 > "$gate_file"
    printf 'runner_artifact_invalid:%s\n' "$configuration" >&2
    return 1
}

phase6_require_gym_probe_log() {
    local log_path="${1:?Gym probe log required}"
    local count
    local task_id
    local -a task_ids=(
        "EasyUUV-Direct-v1"
        "EasyUUV-Direct-Parametric-v1"
        "EasyUUV-Direct-Parametric-SatObs-v1"
        "EasyUUV-Direct-Parametric-Wide256-v1"
    )

    if [[ ! -s "$log_path" ]]; then
        printf 'gym_probe_log_missing:%s\n' "$log_path" >&2
        return 1
    fi
    count="$(grep -F -c 'embodiment_usd=' "$log_path" || true)"
    if [[ "$count" -ne 1 ]]; then
        printf 'gym_probe_asset_record_invalid:%s\n' "$count" >&2
        return 1
    fi
    for task_id in "${task_ids[@]}"; do
        count="$(grep -F -c "gym_task_id=$task_id;entry_point=" "$log_path" || true)"
        if [[ "$count" -ne 1 ]]; then
            printf 'gym_probe_record_invalid:%s:count=%s\n' \
                "$task_id" "$count" >&2
            return 1
        fi
    done
}

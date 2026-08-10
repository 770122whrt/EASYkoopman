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

#!/usr/bin/env bash

phase6_record_preflight_failure() {
    local result_root="$1"
    local check_name="$2"
    local expected="$3"
    local actual="$4"
    local command_status="$5"
    local failure_path="$result_root/preflight_failure.txt"

    mkdir -p "$result_root" "$result_root/logs"
    actual="${actual//$'\r'/}"
    actual="${actual//$'\n'/\\n}"
    printf 'check=%s\nexpected=%s\nactual=%s\ncommand_status=%s\n' \
        "$check_name" "$expected" "$actual" "$command_status" \
        > "$failure_path"
    printf 'ERROR: preflight_failed:%s:expected=%s;actual=%s;command_status=%s\n' \
        "$check_name" "$expected" "$actual" "$command_status" >&2
    return 1
}

phase6_require_preflight_value() {
    local result_root="$1"
    local check_name="$2"
    local expected="$3"
    local actual="$4"
    local command_status="$5"

    if [[ "$command_status" -ne 0 || "$actual" != "$expected" ]]; then
        phase6_record_preflight_failure \
            "$result_root" "$check_name" "$expected" "$actual" "$command_status"
        return 1
    fi
}

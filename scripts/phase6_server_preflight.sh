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

phase6_require_preflight_observation() {
    local result_root="$1"
    local check_name="$2"
    local expected_description="$3"
    local actual="$4"
    local command_status="$5"

    if [[ "$command_status" -ne 0 || -z "$actual" ]]; then
        phase6_record_preflight_failure \
            "$result_root" "$check_name" "$expected_description" \
            "$actual" "$command_status"
        return 1
    fi
}

phase6_activate_conda_env() {
    local result_root="$1"
    local conda_sh="$2"
    local environment_name="$3"
    local expected_python="$4"
    local source_status
    local activation_status=125
    local actual_python=""
    local expected_python_resolved

    mkdir -p "$result_root" "$result_root/logs"
    set +e
    # shellcheck disable=SC1090
    source "$conda_sh" > "$result_root/logs/conda_activation.log" 2>&1
    source_status=$?
    if [[ "$source_status" -eq 0 ]]; then
        conda activate "$environment_name" \
            >> "$result_root/logs/conda_activation.log" 2>&1
        activation_status=$?
    fi
    set -e
    phase6_require_preflight_value \
        "$result_root" "conda_source" "0" "$source_status" "$source_status" \
        || return 1
    phase6_require_preflight_value \
        "$result_root" "conda_activate" "0" \
        "$activation_status" "$activation_status" || return 1

    actual_python="$(command -v python || true)"
    expected_python_resolved="$(realpath "$expected_python")"
    if [[ -n "$actual_python" ]]; then
        actual_python="$(realpath "$actual_python")"
    fi
    phase6_require_preflight_value \
        "$result_root" "conda_python" "$expected_python_resolved" \
        "$actual_python" "0" || return 1
    printf '%s\n' "$environment_name" > "$result_root/conda_environment.txt"
    printf '%s\n' "$actual_python" > "$result_root/python_executable.txt"
    "$actual_python" --version > "$result_root/logs/python_version.log" 2>&1
}

phase6_capture_locked_isaaclab_state() {
    local result_root="$1"
    local repository="$2"
    local expected_version="$3"
    local release_tag="$4"
    local expected_release_commit="$5"
    local expected_head="$6"
    local expected_patch_sha256="$7"
    shift 7
    local -a expected_dirty_files=("$@")
    local actual_version
    local actual_head
    local actual_parent
    local actual_staged
    local actual_untracked
    local actual_dirty
    local expected_dirty
    local patch_path="$result_root/logs/isaaclab_repo_diff.patch"
    local actual_patch_sha256

    mkdir -p "$result_root" "$result_root/logs"
    actual_version="$(tr -d '\r\n' < "$repository/VERSION")"
    phase6_require_preflight_value \
        "$result_root" "isaaclab_version_file" "$expected_version" \
        "$actual_version" "0" || return 1

    actual_head="$(git -C "$repository" rev-parse HEAD)"
    phase6_require_preflight_value \
        "$result_root" "isaaclab_repo_commit" "$expected_head" \
        "$actual_head" "0" || return 1
    actual_parent="$(git -C "$repository" cat-file -p "$actual_head" \
        | sed -n 's/^parent //p' | head -n 1)"
    phase6_require_preflight_value \
        "$result_root" "isaaclab_release_parent" "$expected_release_commit" \
        "$actual_parent" "0" || return 1

    actual_staged="$(git -C "$repository" diff --cached --name-only)"
    phase6_require_preflight_value \
        "$result_root" "isaaclab_staged_files" "" "$actual_staged" "0" \
        || return 1
    actual_untracked="$(git -C "$repository" status --porcelain=v1 \
        --untracked-files=all | sed -n 's/^?? //p')"
    phase6_require_preflight_value \
        "$result_root" "isaaclab_untracked_files" "" "$actual_untracked" "0" \
        || return 1

    actual_dirty="$(git -C "$repository" diff --name-only)"
    expected_dirty="$(printf '%s\n' "${expected_dirty_files[@]}")"
    phase6_require_preflight_value \
        "$result_root" "isaaclab_dirty_files" "$expected_dirty" \
        "$actual_dirty" "0" || return 1
    git -C "$repository" diff --binary > "$patch_path"
    actual_patch_sha256="$(sha256sum "$patch_path" | awk '{print $1}')"
    phase6_require_preflight_value \
        "$result_root" "isaaclab_patch_sha256" "$expected_patch_sha256" \
        "$actual_patch_sha256" "0" || return 1

    printf '%s\n' "$release_tag" > "$result_root/isaaclab_release_tag.txt"
    printf '%s\n' "$expected_release_commit" \
        > "$result_root/isaaclab_release_commit.txt"
    printf '%s\n' "$actual_head" > "$result_root/isaaclab_repo_commit.txt"
    printf '%s\n' "$actual_parent" \
        > "$result_root/isaaclab_repo_parent_commit.txt"
    printf '%s\n' "$actual_patch_sha256" \
        > "$result_root/isaaclab_repo_patch.sha256"
    printf '%s\n' "${expected_dirty_files[@]}" \
        > "$result_root/isaaclab_repo_dirty_files.txt"
    printf '%s\n' "$actual_version" > "$result_root/isaaclab_version_file.txt"
}

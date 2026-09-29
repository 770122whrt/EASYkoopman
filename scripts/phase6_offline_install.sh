#!/usr/bin/env bash

phase6_prepare_offline_python_env() {
    local result_root="$1"
    local isaaclab_python="$2"
    local project_root="$3"
    local setuptools_status
    local setuptools_version
    local install_status

    mkdir -p "$result_root" "$result_root/logs"
    set +e
    "$isaaclab_python" -p -c \
        'from importlib.metadata import version; print("PHASE6_ACTUAL_SETUPTOOLS=" + version("setuptools"))' \
        > "$result_root/logs/setuptools_version.log" 2>&1
    setuptools_status=$?
    set -e
    setuptools_version="$(sed -n 's/^PHASE6_ACTUAL_SETUPTOOLS=//p' \
        "$result_root/logs/setuptools_version.log" | tail -n 1 | tr -d '\r')"
    phase6_require_preflight_observation \
        "$result_root" "setuptools_version" "installed_setuptools_distribution" \
        "$setuptools_version" "$setuptools_status"
    printf '%s\n' "$setuptools_version" > "$result_root/setuptools_version.txt"

    set +e
    "$isaaclab_python" -p -m pip install -e "$project_root" \
        --no-deps --no-build-isolation --no-index \
        > "$result_root/logs/editable_install.log" 2>&1
    install_status=$?
    set -e
    phase6_require_preflight_value \
        "$result_root" "editable_install" "0" "$install_status" "$install_status"
}

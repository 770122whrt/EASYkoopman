#!/usr/bin/env bash

PROJECT_ROOT="/root/EASYkoopman-phase6-v2"
RESULT_ROOT="$PROJECT_ROOT/source/results/koopman_phase6"
ISAACLAB_PY="/root/IsaacLab/isaaclab.sh"
RUNNER="$PROJECT_ROOT/workflows/qualify_easyuuv_v2.py"

mkdir -p "$RESULT_ROOT/rows" "$RESULT_ROOT/logs" "$RESULT_ROOT/exit_codes"

run_one() {
    local configuration="$1"
    local steps="$2"
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
    printf '%s\n' "${PIPESTATUS[0]}" > "$RESULT_ROOT/exit_codes/$configuration.txt"
}

run_one base 64
run_one long_body 8
run_one heavy_moderate 8
run_one asymmetric 8
run_one uuv6 8
run_one uuv6_angled 8
run_one uuv4 8
run_one uuv4_angled 8

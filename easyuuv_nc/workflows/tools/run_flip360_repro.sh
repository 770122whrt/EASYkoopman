#!/bin/bash
# ---------------------------------------------------------------------------
# easyuuv_nc — flip360 免训练 checkpoint 复现 (验收 ②)
#
# 复用 legacy run_milestone_tests.sh 的 Task B (flip360) Phase-8 契约，但全部
# 路径切到干净子仓库 easyuuv_nc/，通过 `conda run -n isaaclab python -u` 调用
# adapt.py（-u 无缓冲，实时捕获 print 标记）。
#
# 用法：
#   bash easyuuv_nc/workflows/tools/run_flip360_repro.sh [TOTAL_STEPS]
# 默认 TOTAL_STEPS=6000（与 legacy milestone Task B 一致）。传入较小值可做冒烟。
# ---------------------------------------------------------------------------
set -euo pipefail

TOTAL_STEPS="${1:-6000}"

# easyuuv_nc 包根（本脚本位于 easyuuv_nc/workflows/tools/）。
NC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PARENT_OF_NC="$(cd "${NC_DIR}/.." && pwd)"

CHECKPOINT="${NC_DIR}/checkpoints/wide256/model_249.pt"
INV_PROXY="${NC_DIR}/artifacts/dynamics_proxy/inv_proxy_12_v1_large.pt"
FM_BUNDLE="${NC_DIR}/artifacts/fm_bundle"
TASK_B_CFG="${NC_DIR}/workflows/configs/tasks/v1_task_b_flip360_barrier.yaml"
LOG="${NC_DIR}/flip360_repro.log"

echo "========================================================="
echo "  easyuuv_nc flip360 repro (Task B, ${TOTAL_STEPS} steps)"
echo "  NC_DIR      = ${NC_DIR}"
echo "  CHECKPOINT  = ${CHECKPOINT}"
echo "  INV_PROXY   = ${INV_PROXY}"
echo "  FM_BUNDLE   = ${FM_BUNDLE}"
echo "========================================================="

# ``import easyuuv_nc`` 需要 PARENT_OF_NC 在 PYTHONPATH（adapt.py 也会自举，
# 但显式设置可覆盖任意工作目录调用）。
export PYTHONPATH="${PARENT_OF_NC}:${PYTHONPATH:-}"

conda run -n isaaclab python -u "${NC_DIR}/workflows/adapt.py" \
    --task EasyUUV-Direct-Parametric-Wide256-v1 \
    --experiment_name easyuuv_parametric \
    --num_envs 1 \
    --workflow_config "${TASK_B_CFG}" \
    --total_steps "${TOTAL_STEPS}" \
    --headless \
    --stdw_update_target zeta4 \
    --l_tgt_space action_bridge \
    --state_match_z_source fm_midpoint \
    --phase56_runtime_bundle_dir "${FM_BUNDLE}" \
    --stdw_inv_proxy "${INV_PROXY}" \
    --domain_adapt_backend esuot_light \
    --stdw_target_domain_mode mixed_all \
    --stdw_update_acceptance batch_trust \
    --stdw_direction_gate True \
    --stdw_direction_gate_source target_anchor \
    --stdw_depth_guard True \
    --stdw_zeta_depth_min_multiplier 0.9 \
    --checkpoint "${CHECKPOINT}" \
    --lyapunov_dv_criterion practical_band \
    --lyapunov_depth_barrier_mode delete \
    --stdw_dir_guard both \
    --stdw_dir_guard_min_pass_rate 0.5 \
    2>&1 | tee "${LOG}"

echo "========================================================="
echo "  flip360 repro finished. Log: ${LOG}"
echo "========================================================="

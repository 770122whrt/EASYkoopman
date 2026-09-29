#!/usr/bin/env bash
set -euo pipefail

source /opt/conda/etc/profile.d/conda.sh
conda activate isaaclab

cd /root/IsaacLab

KOOPMAN_MANIFEST=/root/EASYkoopman/source/results/koopman_phase2_5/selected_model_manifest.json
BASE=/root/EASYkoopman/source/results/koopman_phase5_2

run_eval() {
  local profile_name="$1"
  local checkpoint_path="$2"
  local summary_path="$3"
  local out_dir="$BASE/$profile_name/eval"
  mkdir -p "$out_dir"

  for traj in step sine irregular; do
    echo "[PHASE52-EVAL] profile=$profile_name traj=$traj"
    WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_ppo_koopman.py \
      --task EasyUUV-Direct-v1 \
      --num_envs 1 \
      --headless \
      --policy_mode checkpoint \
      --play_checkpoint "$checkpoint_path" \
      --source_training_summary_path "$summary_path" \
      --result_bucket retrained_ppo_koopman_mpc \
      --ppo_evidence_level phase5_2_matched_eval \
      --koopman_manifest_path "$KOOPMAN_MANIFEST" \
      --trajectory_type "$traj" \
      --trajectory_cycles 1 \
      --steps_per_action 50 \
      --eval_name "phase52_${profile_name}_${traj}" \
      --ppo_koopman_log_path "$out_dir/ppo_${traj}.jsonl"
  done
}

run_eval baseline_rerun \
  /root/IsaacLab/logs/rsl_rl/phase52_baseline_rerun/2026-07-05_10-20-59_baseline_rerun_200/model_199.pt \
  "$BASE/baseline_rerun/training_summary.json"

run_eval reward_v1_only \
  /root/IsaacLab/logs/rsl_rl/phase52_reward_v1_only/2026-07-05_10-24-46_reward_v1_only_200/model_199.pt \
  "$BASE/reward_v1_only/training_summary.json"

run_eval adapter_soft_v1_only \
  /root/IsaacLab/logs/rsl_rl/phase52_adapter_soft_v1_only/2026-07-05_10-28-20_adapter_soft_v1_only_200/model_199.pt \
  "$BASE/adapter_soft_v1_only/training_summary.json"

run_eval mpc_health_v1_only \
  /root/IsaacLab/logs/rsl_rl/phase52_mpc_health_v1_only/2026-07-05_10-31-49_mpc_health_v1_only_200/model_199.pt \
  "$BASE/mpc_health_v1_only/training_summary.json"

#!/usr/bin/env bash
set -u -o pipefail

source /opt/conda/etc/profile.d/conda.sh
conda activate isaaclab

REPO=/root/EASYkoopman
ISAAC=/root/IsaacLab
BASE=${PHASE54_BASE:-$REPO/source/results/koopman_phase5_4}
KOOPMAN_MANIFEST=${PHASE54_KOOPMAN_MANIFEST:-$REPO/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json}
if [[ ! -f "$KOOPMAN_MANIFEST" ]]; then
  KOOPMAN_MANIFEST=$REPO/source/results/koopman_phase2_5/selected_model_manifest.json
fi
PHASE52_SUMMARY=${PHASE54_PHASE52_SUMMARY:-$REPO/source/results/koopman_phase5_2/phase5_2_experiment_summary.json}
PHASE53_SELECTION=${PHASE54_PHASE53_SELECTION:-$REPO/source/results/koopman_phase5_3/phase5_3_cross_selection.json}
PHASE53_CROSS_METRICS=${PHASE54_PHASE53_CROSS_METRICS:-$REPO/source/results/koopman_phase5_3/cross_reward_v1_mpc_health_matched_metrics.json}

SENTINEL_ITER=${PHASE54_SENTINEL_ITER:-50}
CANDIDATE_ITER=${PHASE54_CANDIDATE_ITER:-200}
REFINEMENT_ITER=${PHASE54_REFINEMENT_ITER:-200}
SENTINEL_SAVE_INTERVAL=${PHASE54_SENTINEL_SAVE_INTERVAL:-10}
CANDIDATE_SAVE_INTERVAL=${PHASE54_CANDIDATE_SAVE_INTERVAL:-50}
REFINEMENT_SAVE_INTERVAL=${PHASE54_REFINEMENT_SAVE_INTERVAL:-50}
EVAL_CYCLES=${PHASE54_EVAL_CYCLES:-1}
STEPS_PER_ACTION=${PHASE54_STEPS_PER_ACTION:-50}
FORCE=${PHASE54_FORCE:-0}

ROUND1_PROFILES=(
  r_pwm025
  r_pwm030
  r_pwm035
  r_pwm030_action_smooth
  r_pwm030_fallback025
  rm_timeout14
  rm_timeout16
  rm_midweights
  rm_midweights_timeout14
  rm_lightweights_timeout14
  rm_horizon4_timeout14
)

if [[ -n "${PHASE54_ROUND1_PROFILES:-}" ]]; then
  read -r -a ROUND1_PROFILES <<< "$PHASE54_ROUND1_PROFILES"
fi

mkdir -p "$BASE"

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "[PHASE54][ERROR] Missing required file: $path" >&2
    exit 2
  fi
}

require_file "$KOOPMAN_MANIFEST"
require_file "$PHASE52_SUMMARY"
require_file "$PHASE53_SELECTION"
require_file "$PHASE53_CROSS_METRICS"

summary_path() {
  local profile="$1"
  local stage="$2"
  echo "$BASE/$profile/${stage}_summary.json"
}

metrics_path() {
  local profile="$1"
  local stage="$2"
  echo "$BASE/$profile/${stage}_matched_metrics.json"
}

checkpoint_from_summary() {
  /opt/conda/envs/isaaclab/bin/python -c 'import json, sys; data=json.load(open(sys.argv[1])); print(data.get("selected_checkpoint") or data.get("checkpoint_path") or "")' "$1"
}

run_train() {
  local profile="$1"
  local stage="$2"
  local iterations="$3"
  local save_interval="$4"
  local evidence="phase5_4_pareto_candidate"
  if [[ "$stage" == "sentinel" ]]; then
    evidence="phase5_4_pareto_sentinel"
  elif [[ "$stage" == "refinement" ]]; then
    evidence="phase5_4_pareto_refinement"
  fi

  local out_dir="$BASE/$profile"
  local summary="$out_dir/${stage}_summary.json"
  mkdir -p "$out_dir"
  if [[ "$FORCE" != "1" && -s "$summary" ]]; then
    echo "[PHASE54][TRAIN][SKIP] profile=$profile stage=$stage summary=$summary"
    return 0
  fi

  echo "[PHASE54][TRAIN] profile=$profile stage=$stage iterations=$iterations evidence=$evidence"
  cd "$ISAAC" || return 1
  if ! WANDB_MODE=disabled ./isaaclab.sh -p "$REPO/workflows/train_ppo_koopman.py" \
    --task EasyUUV-Direct-v1 \
    --num_envs 1 \
    --headless \
    --max_iterations "$iterations" \
    --save_interval "$save_interval" \
    --controller_mode koopman_mpc \
    --adapter_mode heuristic_reference_delta_v0 \
    --koopman_backend direct_state \
    --koopman_manifest_path "$KOOPMAN_MANIFEST" \
    --result_bucket retrained_ppo_koopman_mpc \
    --ppo_evidence_level "$evidence" \
    --profile_id "$profile" \
    --training_ladder_stage "$stage" \
    --source_phase5_2_summary_path "$PHASE52_SUMMARY" \
    --source_phase5_3_summary_path "$PHASE53_SELECTION" \
    --phase5_summary_path "$summary" \
    --experiment_name "phase54_${profile}" \
    --run_name "${profile}_${stage}_${iterations}"; then
    echo "{\"profile_id\":\"$profile\",\"stage\":\"$stage\",\"status\":\"failed\"}" > "$out_dir/${stage}_failed.json"
    return 1
  fi

  local checkpoint
  checkpoint="$(checkpoint_from_summary "$summary")"
  if [[ -z "$checkpoint" || ! -f "$checkpoint" ]]; then
    echo "[PHASE54][ERROR] No checkpoint discovered for profile=$profile stage=$stage summary=$summary" >&2
    echo "{\"profile_id\":\"$profile\",\"stage\":\"$stage\",\"status\":\"missing_checkpoint\"}" > "$out_dir/${stage}_failed.json"
    return 1
  fi

  /opt/conda/envs/isaaclab/bin/python "$REPO/workflows/validate_phase5_4_checkpoint_provenance.py" \
    --checkpoint "$checkpoint" \
    --source_training_summary_path "$summary" \
    --expected_evidence_level "$evidence" \
    --json > "$out_dir/${stage}_provenance.json"
}

run_matched_eval() {
  local profile="$1"
  local stage="$2"
  local summary
  summary="$(summary_path "$profile" "$stage")"
  if [[ ! -s "$summary" ]]; then
    echo "[PHASE54][EVAL][SKIP] profile=$profile stage=$stage missing summary"
    return 1
  fi
  local checkpoint
  checkpoint="$(checkpoint_from_summary "$summary")"
  if [[ -z "$checkpoint" || ! -f "$checkpoint" ]]; then
    echo "[PHASE54][EVAL][SKIP] profile=$profile stage=$stage missing checkpoint"
    return 1
  fi

  local out_dir="$BASE/$profile/eval_${stage}"
  mkdir -p "$out_dir"
  for traj in step sine irregular; do
    local log="$out_dir/${traj}.jsonl"
    if [[ "$FORCE" != "1" && -s "$log" ]]; then
      echo "[PHASE54][EVAL][SKIP] profile=$profile stage=$stage traj=$traj log=$log"
    else
      echo "[PHASE54][EVAL] profile=$profile stage=$stage traj=$traj"
      cd "$ISAAC" || return 1
      if ! WANDB_MODE=disabled ./isaaclab.sh -p "$REPO/workflows/play_ppo_koopman.py" \
        --task EasyUUV-Direct-v1 \
        --num_envs 1 \
        --headless \
        --policy_mode checkpoint \
        --play_checkpoint "$checkpoint" \
        --source_training_summary_path "$summary" \
        --controller_mode koopman_mpc \
        --koopman_manifest_path "$KOOPMAN_MANIFEST" \
        --trajectory_type "$traj" \
        --trajectory_cycles "$EVAL_CYCLES" \
        --steps_per_action "$STEPS_PER_ACTION" \
        --result_bucket retrained_ppo_koopman_mpc \
        --profile_id "$profile" \
        --ppo_evidence_level phase5_4_pareto_matched_eval \
        --eval_name "phase54_${profile}_${stage}_${traj}" \
        --ppo_koopman_log_path "$log"; then
        echo "{\"profile_id\":\"$profile\",\"stage\":\"$stage\",\"trajectory\":\"$traj\",\"status\":\"failed\"}" > "$out_dir/${traj}_failed.json"
        return 1
      fi
    fi
    /opt/conda/envs/isaaclab/bin/python "$REPO/workflows/validate_ppo_koopman_log.py" "$log" > "$out_dir/${traj}_validation.txt"
  done

  /opt/conda/envs/isaaclab/bin/python "$REPO/workflows/analyze_phase5_2_health.py" \
    "$out_dir/step.jsonl" \
    "$out_dir/sine.jsonl" \
    "$out_dir/irregular.jsonl" \
    --latency_budget_ms 20.0 \
    --summary_path "$(metrics_path "$profile" "$stage")" > "$out_dir/analysis.txt"
}

selection_args_for_metrics() {
  local stage_filter="$1"
  for profile in "${ROUND1_PROFILES[@]}"; do
    local metrics
    metrics="$(metrics_path "$profile" candidate)"
    if [[ -s "$metrics" ]]; then
      printf ' --candidate %s=%q' "$profile" "$metrics"
    fi
  done
  if [[ "$stage_filter" == "with_round2" ]]; then
    for metrics in "$BASE"/*/refinement_matched_metrics.json; do
      [[ -e "$metrics" ]] || continue
      local profile
      profile="$(basename "$(dirname "$metrics")")"
      printf ' --candidate %s=%q' "$profile" "$metrics"
    done
  fi
}

run_selector() {
  local output="$1"
  local mode="$2"
  local extra_flag=()
  if [[ "$mode" == "round2_complete" ]]; then
    extra_flag=(--round2_complete)
  elif [[ "$mode" == "diagnostic_stop" ]]; then
    extra_flag=(--diagnostic_stop_accepted)
  fi

  local candidate_args
  candidate_args="$(selection_args_for_metrics "$([[ "$mode" == "round2_complete" ]] && echo with_round2 || echo round1)")"
  if [[ -z "$candidate_args" ]]; then
    echo "[PHASE54][SELECT][SKIP] no candidate metrics available"
    return 1
  fi

  # shellcheck disable=SC2086
  /opt/conda/envs/isaaclab/bin/python "$REPO/workflows/select_phase5_4_candidate.py" \
    --baseline_rerun_path "$PHASE52_SUMMARY" \
    --reward_v1_path "$PHASE52_SUMMARY" \
    --cross_reward_mpc_path "$PHASE53_CROSS_METRICS" \
    ${extra_flag[@]+"${extra_flag[@]}"} \
    $candidate_args \
    --output_path "$output" > "${output%.json}.txt"
}

write_selected_manifest() {
  local selection="$1"
  local output="$BASE/selected_phase5_4_profile_manifest.json"
  /opt/conda/envs/isaaclab/bin/python -c '
import json, pathlib, sys
selection_path = pathlib.Path(sys.argv[1])
base = pathlib.Path(sys.argv[2])
output = pathlib.Path(sys.argv[3])
selection = json.loads(selection_path.read_text())
profile = selection.get("selected_profile_id")
payload = {"selection_path": str(selection_path), "selection_status": selection.get("selection_status"), "selected_profile_id": profile}
if profile:
    score = selection.get("selected_score") or {}
    summary_path = base / profile / ("refinement_summary.json" if score.get("sweep_round") == "round2" else "candidate_summary.json")
    payload["selected_summary_path"] = str(summary_path)
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        payload["selected_checkpoint"] = summary.get("selected_checkpoint") or summary.get("checkpoint_path")
        payload["checkpoint_provenance"] = summary.get("checkpoint_provenance")
        payload["phase5_4_track"] = summary.get("phase5_4_track")
        payload["parameter_distance_from_parent"] = summary.get("parameter_distance_from_parent")
payload["allowed_claims"] = selection.get("allowed_claims", [])
payload["disallowed_claims"] = selection.get("disallowed_claims", [])
output.write_text(json.dumps(payload, indent=2) + "\n")
' "$selection" "$BASE" "$output"
  echo "[PHASE54][MANIFEST] $output"
}

echo "[PHASE54] base=$BASE"
echo "[PHASE54] manifest=$KOOPMAN_MANIFEST"
echo "[PHASE54] phase52_summary=$PHASE52_SUMMARY"
echo "[PHASE54] phase53_selection=$PHASE53_SELECTION"
echo "[PHASE54] phase53_cross_metrics=$PHASE53_CROSS_METRICS"

completed_candidates=()
for profile in "${ROUND1_PROFILES[@]}"; do
  run_train "$profile" sentinel "$SENTINEL_ITER" "$SENTINEL_SAVE_INTERVAL" || continue
done

for profile in "${ROUND1_PROFILES[@]}"; do
  if run_train "$profile" candidate "$CANDIDATE_ITER" "$CANDIDATE_SAVE_INTERVAL"; then
    if run_matched_eval "$profile" candidate; then
      completed_candidates+=("$profile")
    fi
  fi
done

ROUND1_SELECTION="$BASE/phase5_4_round1_selection.json"
if run_selector "$ROUND1_SELECTION" round1; then
  /opt/conda/envs/isaaclab/bin/python "$REPO/workflows/plan_phase5_4_refinement.py" \
    --selection_path "$ROUND1_SELECTION" \
    --output_path "$BASE/phase5_4_round2_plan.json" > "$BASE/phase5_4_round2_plan.txt"
fi

mapfile -t ROUND2_PROFILES < <(/opt/conda/envs/isaaclab/bin/python -c 'import json, pathlib; p=pathlib.Path("'"$BASE"'/phase5_4_round2_plan.json"); data=json.loads(p.read_text()) if p.exists() else {}; print("\n".join(data.get("recommended_profile_ids", [])))')

for profile in "${ROUND2_PROFILES[@]}"; do
  [[ -n "$profile" ]] || continue
  if run_train "$profile" refinement "$REFINEMENT_ITER" "$REFINEMENT_SAVE_INTERVAL"; then
    run_matched_eval "$profile" refinement || true
  fi
done

FINAL_SELECTION="$BASE/phase5_4_final_selection.json"
if [[ "${#ROUND2_PROFILES[@]}" -gt 0 ]]; then
  run_selector "$FINAL_SELECTION" round2_complete
else
  run_selector "$FINAL_SELECTION" diagnostic_stop
fi
write_selected_manifest "$FINAL_SELECTION"

echo "[PHASE54][DONE] completed_candidates=${completed_candidates[*]:-none} round2=${ROUND2_PROFILES[*]:-none}"

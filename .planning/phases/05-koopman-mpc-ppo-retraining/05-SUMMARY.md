# Phase 5 Summary: Koopman-MPC PPO Retraining Smoke

**Date:** 2026-07-04
**Status:** Complete for smoke evidence
**Branch:** `isaaclab2-migration`
**Server:** `agentic-AUV`
**Isaac stack:** Isaac Sim 5.0 + Isaac Lab 2.2.1

## Result

Phase 5 produced early retrained-policy smoke evidence for the Koopman-MPC control path.

The training run used RSL-RL PPO while `Phase5KoopmanReferenceWrapper.step(action_4d)` refreshed the Koopman reference through `heuristic_reference_delta_v0` before the underlying environment step. A checkpoint was generated, passed Phase 5 provenance validation and was loaded for a short `PPO -> adapter -> Koopman+MPC -> PWM` evaluation.

This is smoke evidence only. It is not PPO convergence evidence, not superiority over `legacy/Ssurface`, and not deployment evidence.

## Implemented

- `koopman/ppo_training_adapter.py`
  - Adds `Phase5KoopmanReferenceWrapper`.
  - Places adapter refresh on the RSL-RL `env.step(action_4d)` path.
  - Fails fast for `num_envs != 1` until vectorized refresh is tested.
- `workflows/train_ppo_koopman.py`
  - Adds the Phase 5 RSL-RL training entrypoint.
  - Uses `gym.make(...) -> Phase5KoopmanReferenceWrapper -> RslRlVecEnvWrapper -> OnPolicyRunner.learn(...)`.
  - Writes Phase 5 training summary and checkpoint provenance fields.
- `workflows/validate_phase5_checkpoint_provenance.py`
  - Rejects old Phase 4.6 legacy checkpoints for `retrained_policy_smoke`.
- `workflows/play_ppo_koopman.py`
  - Adds `--source_training_summary_path` and `--ppo_evidence_level`.
  - Validates Phase 5 provenance before Isaac startup for retrained-policy evaluation.
- `workflows/validate_ppo_koopman_log.py`
  - Requires provenance fields for `ppo_evidence_level=retrained_policy_smoke`.
- Tests:
  - `tests/test_phase5_training_contract.py`
  - `tests/test_phase5_checkpoint_provenance.py`
  - updated `tests/test_ppo_koopman_logging.py`

## Server Training Smoke

Command shape:

```bash
cd /root/IsaacLab
source /opt/conda/etc/profile.d/conda.sh
conda activate isaaclab
WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/train_ppo_koopman.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --max_iterations 1 \
  --save_interval 1 \
  --controller_mode koopman_mpc \
  --adapter_mode heuristic_reference_delta_v0 \
  --koopman_backend direct_state \
  --koopman_manifest_path /root/EASYkoopman/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json \
  --result_bucket retrained_ppo_koopman_mpc \
  --ppo_evidence_level retrained_policy_smoke \
  --reward_profile legacy_easyuuv_v0 \
  --phase5_summary_path /root/EASYkoopman/source/results/koopman_phase5/training_smoke_summary.json
```

Training summary:

```text
checkpoint_found: true
selected_checkpoint: /root/IsaacLab/logs/rsl_rl/easyuuv_koopman_mpc/2026-07-04_23-23-45/model_0.pt
selected_rule: latest_mtime_model_pt
checkpoint_provenance: phase5_train_koopman_mpc
training_iterations: 1
num_envs: 1
result_bucket: retrained_ppo_koopman_mpc
ppo_evidence_level: retrained_policy_smoke
reward_profile: legacy_easyuuv_v0
controller_path: koopman_mpc/direct_state
adapter_mode: heuristic_reference_delta_v0
koopman_backend: direct_state
observation_dim: 9
action_dim: 4
pwm_dim: 8
adapter_refresh_path: Phase5KoopmanReferenceWrapper.step
adapter_refresh_count: 24
adapter_refresh_before_env_step: true
base_reference_goal_match_max_error: 0.0
training policy_action_clip_rate: 0.5
```

Local copy:

```text
source/results/koopman_phase5/training_smoke_summary.json
```

## Provenance Gate

Command:

```bash
cd /root/EASYkoopman
/opt/conda/envs/isaaclab/bin/python workflows/validate_phase5_checkpoint_provenance.py \
  --checkpoint /root/IsaacLab/logs/rsl_rl/easyuuv_koopman_mpc/2026-07-04_23-23-45/model_0.pt \
  --source_training_summary_path /root/EASYkoopman/source/results/koopman_phase5/training_smoke_summary.json \
  --json
```

Result:

```text
checkpoint_provenance_valid: true
source_result_bucket: retrained_ppo_koopman_mpc
source_controller_path: koopman_mpc/direct_state
source_adapter_mode: heuristic_reference_delta_v0
source_koopman_backend: direct_state
source_reward_profile: legacy_easyuuv_v0
source_git_dirty: true
```

`source_git_dirty=true` is expected because the server received local uncommitted Phase 5 files by `scp`.

## Retrained Checkpoint Evaluation Smoke

Command shape:

```bash
cd /root/IsaacLab
source /opt/conda/etc/profile.d/conda.sh
conda activate isaaclab
WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_ppo_koopman.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --policy_mode checkpoint \
  --play_checkpoint /root/IsaacLab/logs/rsl_rl/easyuuv_koopman_mpc/2026-07-04_23-23-45/model_0.pt \
  --source_training_summary_path /root/EASYkoopman/source/results/koopman_phase5/training_smoke_summary.json \
  --controller_mode koopman_mpc \
  --koopman_manifest_path /root/EASYkoopman/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json \
  --trajectory_type step \
  --trajectory_cycles 1 \
  --max_goals 1 \
  --steps_per_action 2 \
  --result_bucket retrained_ppo_koopman_mpc \
  --ppo_evidence_level retrained_policy_smoke \
  --ppo_koopman_log_path /root/EASYkoopman/source/results/koopman_phase5/retrained_ppo_koopman_step.jsonl
```

Validation:

```text
OK: 2 PPO/Koopman samples
adapter_modes=heuristic_reference_delta_v0
ppo_evidence_levels=retrained_policy_smoke
policy_modes=checkpoint
backend_used=direct_state
controller_modes=koopman_mpc/Ssurface
```

Smoke summary:

```text
sample_count: 2
checkpoint_provenance_valid: true
policy_action_clip_rate_max: 0.0
fallback_rate: 0.0
latency_ms_mean: 11.496730614453554
latency_ms_max: 11.539035476744175
pwm_min: 0.6499999761581421
pwm_max: 1.0
```

Local copies:

```text
source/results/koopman_phase5/retrained_ppo_koopman_step.jsonl
source/results/koopman_phase5/server_smoke_summary.json
```

## Allowed Claims

- RSL-RL PPO can run inside the Koopman-MPC training path.
- The adapter refresh occurred on the training `env.step(action_4d)` path.
- A Phase 5 checkpoint was generated.
- The checkpoint passed provenance validation.
- The checkpoint loaded and produced a short bounded PPO/Koopman evaluation log.

## Disallowed Claims

- PPO has converged.
- PPO+Koopman-MPC is better than `legacy/Ssurface`.
- The policy is deployable.
- The old PPO semantics were losslessly migrated.
- The reward is final.

## Next Recommendation

Proceed to Phase 5.x before Phase 6 if the goal is performance:

```text
Phase 5.x:
  longer Koopman-MPC PPO training,
  reward-profile design,
  fallback/latency-aware penalties,
  matched evaluation against legacy and controller-only baselines.
```

The current Phase 5 checkpoint is useful as evidence that the training and evaluation chain exists. It should not be treated as a trained controller.

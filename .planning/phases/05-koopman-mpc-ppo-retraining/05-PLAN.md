---
phase: 05-koopman-mpc-ppo-retraining
status: planned
created: 2026-07-03
updated: 2026-07-04
target_branch: isaaclab2-migration
type: implementation
wave_count: 8
requirements: [RL-01, RL-02, RL-03, RL-04, MPC-05, EVAL-03]
---

# Phase 5: Koopman-MPC PPO Retraining - Plan

**Spec:** `.planning/phases/05-koopman-mpc-ppo-retraining/05-SPEC.md`
**Mode:** local source-contract changes first, then server Isaac training and evaluation
**Default PPO implementation:** RSL-RL PPO
**Default PPO observation/action:** EasyUUV 9D observation and 4D action
**Default low-level backend:** `direct_state` Koopman+MPC
**First reward profile:** `legacy_easyuuv_v0`

## Purpose

Train the PPO checkpoint that actually belongs to the Koopman-MPC architecture.

The planned progression is:

```text
1. preserve Phase 4.6 RSL-RL/checkpoint evidence
2. insert heuristic_reference_delta_v0 into the real RSL-RL env.step path
3. run a short Koopman-MPC PPO training smoke
4. generate and discover a retrained checkpoint with provenance
5. load the retrained checkpoint
6. run a short retrained-policy evaluation
7. compare only smoke-level diagnostics
```

This phase proves the correct training loop exists and can produce a loadable checkpoint. It does not prove convergence or superiority.

## Review-Carried Requirements

The Phase 5 control/RL review produced three requirements that are now hard gates:

1. Adapter refresh must live on the RSL-RL rollout `env.step(action_4d)` path.
2. Retrained checkpoints must pass a provenance gate so old Phase 4.6 checkpoints cannot be relabeled.
3. Phase 5 remains a short closed-loop smoke phase. Reward redesign, long training and performance ranking move to Phase 5.x.

## Non-Negotiable Boundaries

- Reuse RSL-RL PPO. Do not hand-write PPO.
- PPO observation remains 9D.
- PPO action remains 4D.
- PPO must not output 8D PWM.
- The training loop must execute `heuristic_reference_delta_v0` before every low-level Koopman-MPC step.
- `controller_mode=koopman_mpc` by itself is not enough.
- First reward profile remains `legacy_easyuuv_v0`.
- First backend remains `direct_state`.
- Old EASYUUV PPO checkpoints remain baselines or off-distribution smokes only.

## Wave 0: Contract And Documentation

Files:

- Update: `.planning/phases/05-koopman-mpc-ppo-retraining/05-SPEC.md`
- Update: `.planning/phases/05-koopman-mpc-ppo-retraining/05-PLAN.md`
- Update: `docs/phase5_koopman_mpc_ppo_training_strategy.md`
- Update: `.planning/ROADMAP.md`
- Update: `.planning/STATE.md`

Acceptance:

- Docs state that Koopman-MPC needs its own PPO checkpoint.
- Docs state that old checkpoints are not final Phase 5 evidence.
- Docs state that PPO algorithm code comes from RSL-RL.
- Docs state that adapter refresh must be in the RSL-RL `env.step` path.
- Docs state that Phase 5 is smoke-only.

Verification:

```powershell
git diff --check
```

## Wave 1: Adapter-In-Training-Loop Design

Likely files:

- Create: `koopman/ppo_training_adapter.py`
- Create: `tests/test_phase5_training_contract.py`
- Modify if needed: `easyuuv_env.py`
- Modify if needed: `koopman/policy_adapter.py`

Preferred implementation:

```text
gym.make(...)
  -> Phase5KoopmanReferenceWrapper.step(action_4d)
       -> build base_reference_5d
       -> adapt_policy_reference(action_4d, base_reference_5d)
       -> set env._koopman_reference_5d
       -> call underlying env.step(action_4d)
  -> RslRlVecEnvWrapper(...)
  -> OnPolicyRunner.learn(...)
```

Fallback implementation, only if the Gym wrapper breaks Isaac Lab wrapper expectations:

```text
EasyUUVEnv._pre_physics_step(action_4d)
  -> if controller_mode == koopman_mpc and rl_reference_adapter_mode enabled:
       adapt action_4d into _koopman_reference_5d
  -> continue existing Koopman-MPC action path
```

Either implementation must satisfy the same source contract:

```text
policy_output_4d -> heuristic_reference_delta_v0
                 -> _koopman_reference_5d refresh
                 -> env.step(action_4d)
                 -> Koopman+MPC
```

Required diagnostics:

```text
adapter_refresh_path
adapter_refresh_count
adapter_refresh_before_env_step
adapter_mode
policy_action_clip_rate
base_reference_goal_match_max_error
```

Acceptance:

- Test fails if a Koopman-MPC training command only sets `controller_mode`.
- Test passes only when adapter refresh is visible on the RSL-RL step path.
- Test verifies the adapter mode name is exactly `heuristic_reference_delta_v0`.
- Test verifies no path maps PPO action directly to 8D PWM.

## Wave 2: Training Entrypoint And Config Profile

Likely files:

- Create: `workflows/train_ppo_koopman.py`
- Modify if needed: `agents/rsl_rl_ppo_cfg.py`
- Modify: `workflows/discover_ppo_checkpoints.py`
- Test: `tests/test_phase5_training_contract.py`

Implementation intent:

- Start from the Phase 4.6 migrated `workflows/train.py`.
- Keep AppLauncher import order identical to Phase 4.6.
- Register EasyUUV after Isaac app startup.
- Configure env for Koopman-MPC:

```text
controller_mode = koopman_mpc
control_method = Ssurface
koopman_backend = direct_state
koopman_manifest_path = selected Phase 2.5 direct_state manifest
rl_reference_adapter_mode = heuristic_reference_delta_v0
```

- Add explicit CLI flags:

```text
--controller_mode koopman_mpc
--adapter_mode heuristic_reference_delta_v0
--koopman_manifest_path <path>
--koopman_backend direct_state
--result_bucket retrained_ppo_koopman_mpc
--ppo_evidence_level retrained_policy_smoke
--reward_profile legacy_easyuuv_v0
--save_interval 1
--phase5_summary_path <path>
```

- Keep run outputs separate from legacy PPO logs:

```text
logs/rsl_rl/easyuuv_koopman_mpc/<timestamp>/
source/results/koopman_phase5/
```

Acceptance:

- Local tests verify command defaults.
- Local tests verify `workflows/train_ppo_koopman.py` imports post-app Isaac modules only after AppLauncher.
- Local tests verify `RslRlVecEnvWrapper` still wraps the env before `OnPolicyRunner`.
- Checkpoint discovery can distinguish Phase 5 retrained checkpoints from Phase 4.6 legacy checkpoints.

## Wave 3: Checkpoint Provenance Gate

Likely files:

- Modify: `workflows/discover_ppo_checkpoints.py`
- Create: `workflows/validate_phase5_checkpoint_provenance.py`
- Modify: `workflows/play_ppo_koopman.py`
- Test: `tests/test_phase5_checkpoint_provenance.py`

Implementation intent:

- Require a source training summary for any checkpoint claimed as `retrained_policy_smoke`.
- Reject checkpoints whose source summary has:

```text
result_bucket != retrained_ppo_koopman_mpc
controller_path != koopman_mpc/direct_state
adapter_mode != heuristic_reference_delta_v0
checkpoint_provenance != phase5_train_koopman_mpc
```

- Add fields:

```text
source_training_summary_path
source_result_bucket
source_controller_path
source_adapter_mode
source_koopman_backend
source_reward_profile
source_log_dir
source_git_commit
source_checkpoint_mtime
```

Acceptance:

- A Phase 4.6 legacy checkpoint cannot be loaded with `ppo_evidence_level=retrained_policy_smoke`.
- A Phase 5 checkpoint can be selected only when its summary proves it came from the Koopman-MPC training path.
- The chosen `selected_rule` is deterministic, for example latest mtime among valid Phase 5 summaries.

## Wave 4: Server Training Smoke

Server command shape:

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

Acceptance:

- Isaac starts without import-order or CLI conflicts.
- RSL-RL runner starts.
- At least one training iteration completes, or a clear preflight failure explains why it cannot.
- Adapter refresh count is greater than zero.
- A checkpoint is written for the smoke run.
- Summary labels the run `checkpoint_provenance=phase5_train_koopman_mpc`.
- Summary labels the run `ppo_evidence_level=retrained_policy_smoke`.

Stop and ask the user if:

- Koopman-MPC fallback rate is so high that training cannot step meaningfully.
- Solver latency makes the training loop unusably slow.
- RSL-RL wrapper prevents the adapter refresh from being inserted cleanly.
- Reward changes appear necessary before a one-iteration smoke can complete.

## Wave 5: Retrained Checkpoint Evaluation

Likely files:

- Reuse or modify: `workflows/play_ppo_koopman.py`
- Modify: `workflows/validate_ppo_koopman_log.py`
- Create if needed: `workflows/write_phase5_ppo_summary.py`
- Test: `tests/test_ppo_koopman_logging.py`
- Test: `tests/test_phase5_checkpoint_provenance.py`

Server command shape:

```bash
cd /root/IsaacLab
SELECTED_CHECKPOINT=/path/to/phase5/model_*.pt
WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_ppo_koopman.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --policy_mode checkpoint \
  --play_checkpoint "$SELECTED_CHECKPOINT" \
  --source_training_summary_path /root/EASYkoopman/source/results/koopman_phase5/training_smoke_summary.json \
  --controller_mode koopman_mpc \
  --koopman_manifest_path /root/EASYkoopman/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json \
  --trajectory_type step \
  --trajectory_cycles 1 \
  --steps_per_action 50 \
  --result_bucket retrained_ppo_koopman_mpc \
  --ppo_evidence_level retrained_policy_smoke \
  --ppo_koopman_log_path /root/EASYkoopman/source/results/koopman_phase5/retrained_ppo_koopman_step.jsonl
```

Required labels:

```text
policy_mode = checkpoint
result_bucket = retrained_ppo_koopman_mpc
ppo_evidence_level = retrained_policy_smoke
checkpoint_provenance = phase5_train_koopman_mpc
adapter_mode = heuristic_reference_delta_v0
controller_path = koopman_mpc/direct_state
reward_profile = legacy_easyuuv_v0
```

Acceptance:

- Provenance validator passes before evaluation starts.
- JSONL validator passes after evaluation.
- PWM remains bounded.
- Summary reports fallback, latency, action clipping and tracking errors.
- Summary states no convergence or superiority claim.

## Wave 6: Smoke-Level Comparison

Inputs:

- Phase 4.5 stub-policy log.
- Phase 4.6 legacy PPO baseline summary.
- Phase 4.6 old-checkpoint adapter smoke if available.
- Phase 5 retrained PPO smoke log.

Implementation intent:

- Compare only smoke-level diagnostics:

```text
bounded PWM
fallback_rate
latency_ms_mean/max
action_clip_rate
depth/tracking short-run error
run completion status
```

- Do not rank policies as final performance.

Acceptance:

- Report identifies whether Phase 5 is ready for longer training/evaluation.
- Report recommends one of:

```text
continue_training_in_phase5x
fix_mpc_latency_or_fallback_first
revise_reward_profile_in_phase5x
revise_adapter_mapping_in_phase5x
```

## Wave 7: Summary, Verification And Handoff

Likely files:

- Create: `.planning/phases/05-koopman-mpc-ppo-retraining/05-SUMMARY.md`
- Create: `.planning/phases/05-koopman-mpc-ppo-retraining/05-VERIFICATION.md`
- Update: `.planning/STATE.md`
- Update if needed: `.planning/ROADMAP.md`

Final local verification:

```powershell
python -m pytest -q
python -m compileall __init__.py easyuuv_env.py koopman workflows tests
git diff --check
```

Final server verification:

```bash
cd /root/EASYkoopman
/opt/conda/envs/isaaclab/bin/python -m pytest -q
/opt/conda/envs/isaaclab/bin/python -m compileall __init__.py easyuuv_env.py koopman workflows tests
```

Summary must include:

```text
checkpoint_found
selected_checkpoint
selected_rule
checkpoint_provenance
source_training_summary_path
training_iterations
num_envs
result_bucket
ppo_evidence_level
reward_profile
controller_path
adapter_mode
koopman_backend
adapter_refresh_path
adapter_refresh_count
fallback_rate
latency
action_clip_rate
pwm_bounds
allowed_claims
disallowed_claims
next_phase_recommendation
```

## Recommended Completion Claim

```text
Phase 5 produced early retrained PPO evidence for the Koopman-MPC control path.
The policy was trained with RSL-RL while heuristic_reference_delta_v0 refreshed
the Koopman reference on the RSL-RL env.step path. A checkpoint was generated,
provenanced, loaded and evaluated through PPO -> adapter -> Koopman+MPC -> PWM.
The result is smoke evidence, not convergence or superiority evidence.
```

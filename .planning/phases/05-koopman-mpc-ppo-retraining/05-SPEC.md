---
phase: 05-koopman-mpc-ppo-retraining
plan: 05
subsystem: ppo-koopman-mpc-training
status: planned
created: 2026-07-03
updated: 2026-07-04
tags: [ppo, rsl-rl, koopman-mpc, adapter, isaaclab, retraining]
requires:
  - phase: 04.6-ppo-training-entrypoint-and-checkpoint-evidence-gate
provides:
  - Koopman-MPC-specific PPO training contract
  - adapter-in-training-loop evidence
  - retrained PPO checkpoint smoke
  - checkpoint provenance gate
  - retrained PPO evaluation boundary
requirements: [RL-01, RL-02, RL-03, RL-04, MPC-05, EVAL-03]
---

# Phase 5: Koopman-MPC PPO Retraining - Specification

**Created:** 2026-07-03
**Updated:** 2026-07-04
**Document type:** executable planning contract
**Audience:** project owner, implementation agent and Isaac server operator

## Goal

Train a PPO checkpoint that belongs to the Koopman-MPC control architecture.

Phase 4.6 proved that the RSL-RL training and checkpoint evidence chain can run again under Isaac Lab 2.2.1. It did not prove that PPO has been trained under Koopman-MPC. Phase 5 fills that gap.

The old EasyUUV PPO checkpoint was trained under:

```text
obs_9d -> PPO action_4d -> legacy/Ssurface -> pwm_8d -> next_state
```

The target architecture is:

```text
obs_9d -> PPO action_4d -> heuristic_reference_delta_v0
       -> koopman_reference_5d -> Koopman+MPC -> pwm_8d -> next_state
```

The USD asset may be the same, but the transition dynamics seen by PPO are different because the low-level controller changed. Therefore Phase 5 must generate its own checkpoint while the adapter and Koopman-MPC controller are inside the training loop.

## Required Claim Boundary

Phase 5 may claim:

```text
RSL-RL PPO can train inside the Koopman-MPC closed-loop path.
A retrained checkpoint can be generated, discovered and loaded.
The retrained checkpoint can run through PPO -> adapter -> Koopman+MPC -> PWM.
```

Phase 5 must not claim:

```text
The policy has converged.
The policy is deployable.
The policy is superior to legacy/Ssurface.
The old EASYUUV PPO semantics were losslessly migrated.
The reward design is final.
```

Long training, reward redesign, hyperparameter tuning and performance ranking belong in a later Phase 5.x.

## Algorithm Contract

The only valid first-pass training contract is:

```text
obs_9d
  -> RSL-RL PPO policy
  -> action_4d
  -> heuristic_reference_delta_v0
  -> koopman_reference_5d
  -> refresh env._koopman_reference_5d
  -> env.step(action_4d)
  -> Koopman+MPC
  -> pwm_8d
  -> EasyUUV physics
```

This contract has a strict placement requirement:

```text
The adapter refresh must happen on the RSL-RL rollout step path.
```

RSL-RL owns the rollout loop inside `OnPolicyRunner.learn()`. Therefore calling the adapter in an outer training script loop is not enough. Setting only `controller_mode = "koopman_mpc"` is also not enough.

Acceptable implementation points:

- A thin Gym/env wrapper inserted between `gym.make(...)` and `RslRlVecEnvWrapper(...)`, whose `step(action_4d)` refreshes the Koopman reference before delegating to the underlying env.
- An explicit EasyUUV environment hook called from the pre-physics/action path, enabled only for Koopman-MPC PPO training.

Unacceptable implementation points:

- Only changing `controller_mode`.
- Only reusing `workflows/play_ppo_koopman.py`, because it is an inference workflow, not the RSL-RL training rollout path.
- A script-level loop around `runner.learn()`, because `runner.learn()` owns the actual action collection.
- Any path where PPO directly outputs 8D PWM.

## Input And Output Contract

First pass PPO input remains EasyUUV's current 9D observation:

```text
obs_9d = [goal_quat_wxyz(4), current_depth_z(1), current_quat_wxyz(4)]
```

First pass PPO output remains 4D:

```text
action_4d = [roll_delta_cmd, pitch_delta_cmd, yaw_delta_cmd, depth_delta_cmd]
```

The adapter converts this to a 5D Koopman reference:

```text
base_reference_5d = [z_base, q_base_wxyz]
action_clipped = clip(action_4d, -policy_action_limit, policy_action_limit)
delta_q = quat_from_euler_xyz(
    roll_scale * action_clipped[0],
    pitch_scale * action_clipped[1],
    yaw_scale * action_clipped[2],
)
z_ref = clip(z_base + depth_scale * action_clipped[3], depth_min, depth_max)
q_ref = normalize(q_base * delta_q)
koopman_reference_5d = [z_ref, q_ref_w, q_ref_x, q_ref_y, q_ref_z]
```

The low-level controller consumes:

```text
koopman_state_11d
koopman_reference_5d
selected direct_state Koopman model
MPC settings
```

and emits:

```text
pwm_8d in bounded actuator range
```

Non-negotiable boundaries:

- PPO algorithm implementation is reused from RSL-RL.
- PPO observation remains 9D for Phase 5.
- PPO action remains 4D for Phase 5.
- PPO never outputs 8D PWM.
- The default Koopman backend is `direct_state`.
- `paper_lifted_edmd` remains a comparison backend until its depth error is diagnosed.
- The first adapter mode name remains exactly `heuristic_reference_delta_v0`.

## Checkpoint Provenance Gate

Phase 5 must prevent old checkpoints from being relabeled as retrained Koopman-MPC checkpoints.

A checkpoint may be reported as `ppo_evidence_level = "retrained_policy_smoke"` only if its source training summary proves all of the following:

```text
result_bucket = "retrained_ppo_koopman_mpc"
controller_path = "koopman_mpc/direct_state"
adapter_mode = "heuristic_reference_delta_v0"
reward_profile = "legacy_easyuuv_v0"
observation_dim = 9
action_dim = 4
checkpoint_provenance = "phase5_train_koopman_mpc"
```

Required provenance fields:

```text
checkpoint_found
checkpoint_path
selected_checkpoint
selected_rule
checkpoint_provenance
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

Old checkpoints remain allowed only under:

```text
result_bucket = "legacy_ppo_baseline"
result_bucket = "old_checkpoint_adapter_smoke"
ppo_evidence_level = "checkpoint_smoke"
```

They must not be promoted to `retrained_ppo_koopman_mpc`.

## Result And Evidence Fields

Required result bucket:

```text
result_bucket = "retrained_ppo_koopman_mpc"
```

Initial evidence level:

```text
ppo_evidence_level = "retrained_policy_smoke"
```

Required training summary fields:

```text
checkpoint_found
checkpoint_path
selected_checkpoint
selected_rule
checkpoint_provenance
training_iterations
num_envs
result_bucket
ppo_evidence_level
reward_profile
controller_path
adapter_mode
koopman_backend
koopman_manifest_path
observation_dim
action_dim
pwm_dim
adapter_refresh_path
adapter_refresh_count
adapter_refresh_before_env_step
action_clip_rate
fallback_rate
latency_ms_mean
latency_ms_max
pwm_min
pwm_max
allowed_claims
disallowed_claims
```

Required evaluation summary fields:

```text
selected_checkpoint
source_training_summary_path
checkpoint_provenance_valid
sample_count
trajectory_type
controller_path
adapter_mode
koopman_backend
action_clip_rate
fallback_rate
latency_ms_mean
latency_ms_max
pwm_min
pwm_max
depth_error_summary
attitude_error_summary
completion_status
allowed_claims
disallowed_claims
```

Do not add a stronger evidence label until the validators and phase docs are updated together.

## Reward Profile

The first Phase 5 pass keeps:

```text
reward_profile = "legacy_easyuuv_v0"
```

Reason: Phase 5 already changes the low-level controller path. Changing the reward at the same time makes attribution ambiguous.

Allowed future reward profiles must be explicitly versioned in a later phase, for example:

```text
koopman_mpc_v1_with_fallback_penalty
koopman_mpc_v1_with_latency_penalty
koopman_mpc_v1_tracking_energy_tradeoff
```

They are out of scope for the first Phase 5 smoke.

## In Scope

- Insert the adapter refresh into the RSL-RL training rollout step path.
- Reuse RSL-RL PPO and existing `agents/rsl_rl_ppo_cfg.py` defaults unless a change is explicitly versioned.
- Produce a short Koopman-MPC PPO training smoke on Isaac Lab 2.2.1.
- Generate a retrained PPO checkpoint.
- Discover and load the retrained checkpoint through a provenance gate.
- Run a short evaluation through `PPO -> adapter -> Koopman+MPC -> PWM`.
- Compare smoke-level statistics against Phase 4.5 stub and Phase 4.6 baselines.
- Record fallback, latency, action clipping and PWM bounds.

## Out Of Scope

- Hand-writing a PPO algorithm.
- Changing PPO observation to the 11D Koopman state.
- Changing PPO action to 8D PWM.
- LLM planning or tuning.
- Real hardware or Sim2Real claims.
- Promoting `paper_lifted_edmd` as the default low-level backend.
- Claiming convergence or superiority from a short smoke run.
- Large reward redesign without a versioned reward spec.
- Hyperparameter search or long training performance ranking.

## Acceptance Criteria

- [ ] `05-SPEC.md`, `05-PLAN.md` and the Phase 5 strategy document exist and state the updated contract.
- [ ] A local source-contract test proves the adapter refresh is placed on the RSL-RL `env.step(action_4d)` path.
- [ ] A local source-contract test fails if the Phase 5 training path only sets `controller_mode=koopman_mpc`.
- [ ] The training entrypoint uses RSL-RL PPO, not a custom PPO implementation.
- [ ] PPO observation remains 9D and action remains 4D.
- [ ] First smoke uses `reward_profile=legacy_easyuuv_v0`.
- [ ] First smoke uses `direct_state` Koopman+MPC.
- [ ] The first training smoke runs on the Isaac server with `num_envs=1`.
- [ ] A retrained checkpoint is generated and discovered with `selected_checkpoint` and `selected_rule`.
- [ ] The checkpoint provenance gate rejects Phase 4.6 legacy checkpoints for `retrained_policy_smoke`.
- [ ] A short evaluation loads the retrained checkpoint and runs through Koopman-MPC.
- [ ] Logs or sidecar summary include `result_bucket=retrained_ppo_koopman_mpc`.
- [ ] Logs or sidecar summary include `ppo_evidence_level=retrained_policy_smoke`.
- [ ] Summary reports fallback, latency, action clipping and PWM bounds.
- [ ] Summary separates allowed claims from disallowed claims.

## Stop Conditions

Stop and ask before expanding the phase if any of these occur:

- The RSL-RL training wrapper cannot observe and intercept actions before `env.step`.
- The only possible implementation requires changing PPO output to 8D PWM.
- The short training smoke cannot step because Koopman-MPC fallback dominates the rollout.
- Solver latency makes one-env smoke impractically slow.
- A reward redesign appears necessary to get even smoke-level stepping.
- Checkpoint provenance cannot distinguish Phase 5 retrained checkpoints from Phase 4.6 legacy checkpoints.

## Final Success Statement

Use this wording if the phase passes:

```text
Phase 5 trained and loaded a PPO checkpoint under the Koopman-MPC closed-loop
path. The training loop used RSL-RL PPO, refreshed the Koopman reference through
heuristic_reference_delta_v0 on the RSL-RL env.step path, and produced a bounded
short evaluation through PPO -> adapter -> Koopman+MPC -> PWM. This is early
retrained-policy smoke evidence, not a convergence or superiority claim.
```

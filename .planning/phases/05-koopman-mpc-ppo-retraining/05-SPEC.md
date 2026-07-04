---
phase: 05-koopman-mpc-ppo-retraining
plan: 05
subsystem: ppo-koopman-mpc-training
status: planned
created: 2026-07-03
tags: [ppo, rsl-rl, koopman-mpc, adapter, isaaclab, retraining]
requires:
  - phase: 04.6-ppo-training-entrypoint-and-checkpoint-evidence-gate
provides:
  - Koopman-MPC-specific PPO training contract
  - adapter-in-training-loop evidence
  - retrained PPO checkpoint smoke
  - retrained PPO evaluation boundary
requirements: [RL-01, RL-02, RL-03, RL-04, MPC-05, EVAL-03]
---

# Phase 5: Koopman-MPC PPO Retraining - Specification

**Created:** 2026-07-03
**Document type:** planning contract plus explanation
**Audience:** project owner, future implementation agent and Isaac server operator

## Goal

Train a PPO policy that belongs to the Koopman-MPC control architecture.

This phase exists because a PPO checkpoint trained under the original EasyUUV low-level controller learns a different transition map:

```text
obs -> PPO action -> legacy/Ssurface -> PWM -> next state
```

The new architecture has a different low-level controller and therefore a different MDP:

```text
obs -> PPO action -> heuristic_reference_delta_v0 -> Koopman+MPC -> PWM -> next state
```

Same USD asset does not mean same PPO problem. The required Phase 5 checkpoint must be trained while the adapter and Koopman-MPC controller are inside the training loop.

## Required Claim Boundary

Phase 5 may claim:

```text
RSL-RL PPO can train in the Koopman-MPC closed-loop path.
A retrained checkpoint can be generated, discovered and loaded.
The retrained checkpoint can run through PPO -> adapter -> Koopman+MPC -> PWM.
```

Phase 5 must not claim without later long evaluation evidence:

```text
The policy has converged.
The policy is deployable.
The policy is superior to legacy/Ssurface.
The old EASYUUV PPO semantics were losslessly migrated.
```

## Algorithm Contract

The first valid Phase 5 training path is:

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

Non-negotiable details:

- PPO algorithm implementation is reused from RSL-RL. We do not hand-write PPO.
- PPO observation remains 9D for the first pass.
- PPO action remains 4D for the first pass.
- PPO never outputs 8D PWM.
- `controller_mode = "koopman_mpc"` alone is not enough.
- The adapter reference refresh must happen before every training `env.step`.
- The default Koopman backend is `direct_state`; `paper_lifted_edmd` remains a comparison backend until its depth issue is fixed.

## Result And Evidence Fields

Required result bucket:

```text
result_bucket = "retrained_ppo_koopman_mpc"
```

Initial evidence level:

```text
ppo_evidence_level = "retrained_policy_smoke"
```

Required summary fields:

```text
checkpoint_found
checkpoint_path
selected_checkpoint
selected_rule
training_iterations
num_envs
result_bucket
ppo_evidence_level
reward_profile
controller_path
adapter_mode
koopman_backend
koopman_manifest_path
action_clip_rate
fallback_rate
latency_ms_mean
latency_ms_max
pwm_min
pwm_max
allowed_claims
disallowed_claims
```

Do not add a stronger evidence label until the validators and phase docs are updated together.

## Reward Profile

The first Phase 5 pass keeps:

```text
reward_profile = "legacy_easyuuv_v0"
```

Reason: the controller path is already changing. Changing reward at the same time makes attribution difficult.

Allowed future reward profiles must be explicitly versioned, for example:

```text
koopman_mpc_v1_with_fallback_penalty
koopman_mpc_v1_with_latency_penalty
koopman_mpc_v1_tracking_energy_tradeoff
```

## In Scope

- Create a training wrapper, environment hook or workflow that places the Phase 4.5 adapter in the RSL-RL training loop.
- Reuse RSL-RL PPO and existing `agents/rsl_rl_ppo_cfg.py` defaults unless a change is explicitly versioned.
- Produce a short Koopman-MPC PPO training smoke on Isaac Lab 2.2.1.
- Generate a retrained PPO checkpoint.
- Discover and load the retrained checkpoint.
- Run a short evaluation through `PPO -> adapter -> Koopman+MPC -> PWM`.
- Compare smoke-level statistics against Phase 4.5 stub and Phase 4.6 legacy PPO baseline.
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

## Acceptance Criteria

- [ ] `05-SPEC.md` and `05-PLAN.md` exist.
- [ ] A local source-contract test proves adapter reference refresh occurs before training `env.step`.
- [ ] The training entrypoint uses RSL-RL PPO, not a custom PPO implementation.
- [ ] PPO observation remains 9D and action remains 4D.
- [ ] The first training smoke runs on the Isaac server with `num_envs=1`.
- [ ] A retrained checkpoint is generated and discovered with `selected_checkpoint` and `selected_rule`.
- [ ] A short evaluation loads the retrained checkpoint and runs through Koopman-MPC.
- [ ] Logs or sidecar summary include `result_bucket=retrained_ppo_koopman_mpc`.
- [ ] Logs or sidecar summary include `ppo_evidence_level=retrained_policy_smoke`.
- [ ] Summary reports fallback, latency, action clipping and PWM bounds.
- [ ] Summary separates allowed claims from disallowed claims.

## Final Success Statement

Use this wording if the phase passes:

```text
Phase 5 trained and loaded a PPO checkpoint under the Koopman-MPC closed-loop
path. The training loop used RSL-RL PPO, refreshed the Koopman reference through
heuristic_reference_delta_v0 before each environment step, and produced a
bounded short evaluation through PPO -> adapter -> Koopman+MPC -> PWM. This is
early retrained-policy smoke evidence, not a convergence or superiority claim.
```

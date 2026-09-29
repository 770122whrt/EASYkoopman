# Phase 5 Koopman-MPC PPO Retraining Review For Agents

**Date:** 2026-07-04
**Document type:** audit report plus reviewer guidance
**Audience:** the next agent reviewing or implementing Phase 5
**Scope:** Phase 5 planning contract, current code support, and required gates before server execution

## 1. Review Verdict

**Verdict:** `PASS_WITH_MUST_FIXES_BEFORE_EXECUTION`

Phase 5 is directionally correct.

The current Phase 5 plan correctly states that the project needs a new PPO checkpoint trained inside the Koopman-MPC closed-loop path. It also correctly rejects these unsafe shortcuts:

```text
only setting controller_mode = koopman_mpc
relabeling Phase 4.6 legacy checkpoints as retrained Koopman-MPC PPO
claiming convergence or superiority from a short training smoke
changing reward, observation, action space and controller at the same time
```

The most important Phase 5 contract is:

```text
obs_9d
  -> RSL-RL PPO policy
  -> action_4d
  -> heuristic_reference_delta_v0
  -> refresh env._koopman_reference_5d
  -> env.step(action_4d)
  -> Koopman+MPC
  -> pwm_8d
```

This contract is correct, but it is still only a planning contract. The current code does not yet contain the Phase 5 training wrapper, provenance validator or retrained-checkpoint evaluation gate. The next agent must not mark Phase 5 complete until those gates exist and pass.

## 2. Source Map

### Phase 5 Planning Files

- `.planning/phases/05-koopman-mpc-ppo-retraining/05-SPEC.md`
- `.planning/phases/05-koopman-mpc-ppo-retraining/05-PLAN.md`
- `docs/phase5_koopman_mpc_ppo_training_strategy.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`

### Current Code Files

- `easyuuv_env.py`
- `koopman/policy_adapter.py`
- `workflows/train.py`
- `workflows/play_ppo_koopman.py`
- `workflows/discover_ppo_checkpoints.py`
- `workflows/validate_ppo_koopman_log.py`
- `workflows/play_eval.py`
- `agents/rsl_rl_ppo_cfg.py`

### Expected But Not Yet Present Phase 5 Files

At the time of this review, these Phase 5 files are planned but not present:

```text
workflows/train_ppo_koopman.py
koopman/ppo_training_adapter.py
workflows/validate_phase5_checkpoint_provenance.py
tests/test_phase5_training_contract.py
tests/test_phase5_checkpoint_provenance.py
```

This is acceptable for a planning stage, but it means Phase 5 has not yet produced implementation evidence.

## 3. Current Ground Truth

### 3.1 EasyUUV PPO Interface

Current environment contract:

```text
easyuuv_env.py:
num_actions = 4
num_observations = 9
```

The observation contains:

```text
[goal_quat_wxyz(4), current_depth_z(1), current_quat_wxyz(4)]
```

The action remains:

```text
[roll_cmd, pitch_cmd, yaw_cmd, depth_cmd]
```

Review implication:

Phase 5 is correct to keep PPO observation at 9D and PPO action at 4D for the first smoke. Changing either would create a new RL problem and should be moved to Phase 5.x or later.

### 3.2 Koopman-MPC Reference Path

Current environment logic:

```text
reference = env._koopman_reference_5d if present
otherwise reference = [0, env._goal]
```

Review implication:

If the Phase 5 training wrapper does not set `_koopman_reference_5d` before `env.step(action_4d)`, Koopman-MPC will either use a stale reference or the fallback `[0, _goal]` reference. That would not prove PPO action is driving the MPC target.

### 3.3 Existing Adapter

Current adapter mode:

```text
heuristic_reference_delta_v0
```

Supported evidence levels currently include:

```text
stub_only
checkpoint_smoke
training_entrypoint_only
retrained_policy_smoke
```

Review implication:

The enum already allows `retrained_policy_smoke`, but the code does not yet verify checkpoint provenance for that label. Do not treat the existence of the label as evidence that Phase 5 provenance is implemented.

### 3.4 Existing `play_ppo_koopman.py`

Current `play_ppo_koopman.py` supports:

```text
--policy_mode
--result_bucket
selected_checkpoint
checkpoint_smoke
```

Current gaps:

```text
no --source_training_summary_path
no Phase 5 provenance validator
checkpoint mode still returns ppo_evidence_level = checkpoint_smoke
result_bucket can be supplied without proving provenance
```

Review implication:

The Phase 5 evaluation command in the plan is not yet executable as written. The next agent must update the eval workflow or write a new Phase 5 eval workflow before claiming retrained checkpoint evaluation.

### 3.5 Existing `train.py`

Current `workflows/train.py` is now a Phase 4.6-style legacy PPO training/checkpoint path. It supports:

```text
--save_interval
--result_bucket
--ppo_evidence_level
--reward_profile
--phase46_summary_path
```

It configures:

```text
controller_path = legacy/Ssurface
```

Review implication:

Do not reuse `workflows/train.py` as the Phase 5 training proof unless it is extended or wrapped so that every `action_4d` updates `_koopman_reference_5d` before the underlying environment step. The planned `workflows/train_ppo_koopman.py` is the cleaner route.

## 4. Healthy Planning Points

### 4.1 Correct Phase Goal

Phase 5 is correctly defined as a Koopman-MPC-specific PPO short training smoke, not as convergence or performance proof.

This aligns with the project objective:

```text
PPO remains the high-level policy layer.
Koopman+MPC remains the low-level controller.
8D PWM is still produced by the controller, not directly by PPO.
```

### 4.2 Correct Adapter Placement Requirement

The plan correctly states that the adapter must run on the real RSL-RL rollout `env.step(action_4d)` path. This is the most important control/RL requirement.

Valid locations:

```text
Gym wrapper step(action_4d)
EasyUUVEnv hook called before low-level dynamics
```

Invalid locations:

```text
outer script loop around runner.learn()
inference-only play_ppo_koopman.py path
controller_mode-only config change
```

### 4.3 Correct Checkpoint Provenance Boundary

The plan correctly requires:

```text
checkpoint_provenance = phase5_train_koopman_mpc
result_bucket = retrained_ppo_koopman_mpc
controller_path = koopman_mpc/direct_state
adapter_mode = heuristic_reference_delta_v0
reward_profile = legacy_easyuuv_v0
```

This is necessary because Phase 4.6 generated or loaded legacy checkpoints, and those must not be relabeled as retrained Koopman-MPC checkpoints.

### 4.4 Correct Reward Boundary

The first Phase 5 pass keeps:

```text
reward_profile = legacy_easyuuv_v0
```

This is the right choice. Phase 5 already changes the low-level controller path. Changing reward in the same step would make attribution ambiguous.

## 5. Must-Fix Findings

### Finding 1: Adapter-In-Training-Loop Is Not Yet Proven

**Severity:** Must fix
**Category:** implementation evidence gap

The Phase 5 plan correctly requires:

```text
action_4d -> heuristic_reference_delta_v0 -> _koopman_reference_5d -> env.step(action_4d)
```

But the current codebase does not yet contain the planned training wrapper or hook:

```text
koopman/ppo_training_adapter.py
workflows/train_ppo_koopman.py
tests/test_phase5_training_contract.py
```

Required reviewer check:

The next agent must verify a source-contract test that fails if Phase 5 only sets:

```text
controller_mode = koopman_mpc
```

The test must pass only when adapter refresh is visibly in the RSL-RL step path before the underlying env step.

Minimum acceptable proof:

```text
Phase5KoopmanReferenceWrapper.step(action_4d)
  -> adapt_policy_reference(...)
  -> env.unwrapped._koopman_reference_5d = adapted_reference
  -> underlying_env.step(action_4d)
```

or an equivalent environment hook inside `EasyUUVEnv._pre_physics_step()` that is explicitly enabled only for Phase 5 training.

### Finding 2: Phase 5 Evaluation CLI Is Not Yet Implemented

**Severity:** Must fix
**Category:** command drift

The Phase 5 plan uses:

```text
--source_training_summary_path
--result_bucket retrained_ppo_koopman_mpc
--ppo_evidence_level retrained_policy_smoke
```

Current `play_ppo_koopman.py` does not expose `--source_training_summary_path` and does not allow the caller to select `ppo_evidence_level`. In checkpoint mode, it currently returns:

```text
ppo_evidence_level = checkpoint_smoke
```

Required reviewer check:

Before Phase 5 evaluation, confirm that either:

1. `play_ppo_koopman.py` has been extended with Phase 5 provenance fields and evidence-level validation, or
2. a new Phase 5 evaluation workflow exists.

Do not accept a run as `retrained_policy_smoke` if the workflow only passes `--result_bucket retrained_ppo_koopman_mpc` while leaving evidence level and provenance unchecked.

### Finding 3: Provenance Gate Is Not Yet Implemented

**Severity:** Must fix
**Category:** source-of-truth drift / safety gate gap

The SPEC requires a provenance gate, but the current code has no:

```text
workflows/validate_phase5_checkpoint_provenance.py
tests/test_phase5_checkpoint_provenance.py
```

Current checkpoint discovery can select a checkpoint, but it does not prove the checkpoint came from Phase 5 Koopman-MPC training.

Required reviewer check:

The provenance validator must reject any checkpoint unless its source training summary proves:

```text
result_bucket = retrained_ppo_koopman_mpc
controller_path = koopman_mpc/direct_state
adapter_mode = heuristic_reference_delta_v0
reward_profile = legacy_easyuuv_v0
checkpoint_provenance = phase5_train_koopman_mpc
observation_dim = 9
action_dim = 4
```

Also require:

```text
source_training_summary_path
selected_checkpoint
source_checkpoint_mtime
source_git_commit
source_git_dirty
```

`source_git_dirty` is not in the current plan but should be added because this project often has active uncommitted changes during server smoke work.

### Finding 4: `result_bucket` Is Too Easy To Spoof

**Severity:** Must fix
**Category:** evidence-label integrity

Current `play_ppo_koopman.py` accepts:

```text
--result_bucket <any string>
```

This is fine for Phase 4.5 and Phase 4.6 logging, but Phase 5 cannot allow `result_bucket=retrained_ppo_koopman_mpc` without provenance.

Required reviewer check:

If:

```text
result_bucket = retrained_ppo_koopman_mpc
```

then the workflow must require:

```text
source_training_summary_path
provenance validator pass
checkpoint_provenance = phase5_train_koopman_mpc
ppo_evidence_level = retrained_policy_smoke
```

Otherwise the workflow must exit before Isaac startup or before checkpoint evaluation.

### Finding 5: Base Reference Source Must Be Pinned

**Severity:** Must fix
**Category:** algorithm contract ambiguity

Phase 5 adapter logic uses:

```text
base_reference_5d = [z_base, q_base_wxyz]
```

The plan should make this invariant explicit:

```text
q_base must equal the goal quaternion used in the current PPO observation.
z_base must come from the same task/reference generator recorded in the training summary.
```

Why this matters:

PPO observes the target through `_goal`. Koopman-MPC tracks `_koopman_reference_5d`. If these are not same-step and same-source, PPO learns against one target while MPC follows another.

Required reviewer check:

Training summary must include:

```text
base_reference_source
base_reference_goal_match_max_error
depth_reference_source
adapter_refresh_count
adapter_refresh_before_env_step
```

For Phase 5 smoke, `base_reference_goal_match_max_error` should be zero or below a very small quaternion-equivalence-aware tolerance.

### Finding 6: Vectorization Boundary Is Not Explicit Enough

**Severity:** Must fix for any run with `num_envs > 1`
**Category:** rollout correctness risk

Phase 5 server smoke uses:

```text
--num_envs 1
```

This is appropriate for the first implementation. But RSL-RL normally supports many parallel environments, and a wrapper that only handles one env can silently mis-handle batched action/reference tensors if `num_envs` increases.

Required reviewer check:

The first wrapper should either:

```text
fail fast when num_envs != 1
```

or prove true vectorized behavior:

```text
action_4d shape = (N, 4)
base_reference_5d shape = (N, 5)
adapted_reference_5d shape = (N, 5)
env._koopman_reference_5d shape = (N, 5)
```

Do not let a Phase 5 smoke silently run with `num_envs > 1` unless the vectorized adapter path is tested.

## 6. Should-Fix Findings

### Finding 7: `controller_path` Needs Schema Support

**Severity:** Should fix
**Category:** terminology drift

Phase 5 uses:

```text
controller_path = koopman_mpc/direct_state
```

Current logs already include fields such as `controller_mode` and `backend_used`, but `controller_path` is a stronger Phase 5 provenance concept.

Recommendation:

Define `controller_path` in the Phase 5 summary schema as:

```text
controller_path = f"{controller_mode}/{koopman_backend}"
```

For Phase 5 first pass:

```text
koopman_mpc/direct_state
```

### Finding 8: `retrained_policy_smoke` Should Require Provenance In Validators

**Severity:** Should fix
**Category:** validator gap

Current validators can accept `retrained_policy_smoke` as a valid evidence label because the enum contains it. But a valid label is not the same as valid provenance.

Recommendation:

In `validate_ppo_koopman_log.py` or a Phase 5 validator:

```text
if ppo_evidence_level == retrained_policy_smoke:
    require checkpoint_provenance_valid == true
    require source_training_summary_path
    require result_bucket == retrained_ppo_koopman_mpc
```

### Finding 9: Stop Conditions Should Become Automated Exit Conditions

**Severity:** Should fix
**Category:** operational safety

The SPEC lists good stop conditions:

```text
fallback dominates rollout
solver latency makes one-env smoke impractically slow
reward redesign appears necessary
provenance cannot distinguish checkpoints
```

Recommendation:

Turn these into summary fields and thresholds:

```text
fallback_rate
latency_ms_mean
latency_ms_max
adapter_refresh_count
checkpoint_provenance_valid
completion_status
```

Even if thresholds are permissive for the first smoke, the fields should exist.

## 7. Required Audit Procedure For The Next Agent

The next agent should review Phase 5 in this order.

### Step 1: Confirm Scope

Verify Phase 5 still says:

```text
short closed-loop smoke only
no convergence claim
no superiority claim
no reward redesign
no PPO observation/action redesign
no LLM control loop
```

### Step 2: Confirm Training Path

Inspect the implementation and prove:

```text
RSL-RL OnPolicyRunner.learn()
  -> wrapped_env.step(action_4d)
  -> adapter refresh
  -> underlying env.step(action_4d)
```

Reject:

```text
adapter call outside runner.learn()
controller_mode-only changes
inference-only adapter proof
```

### Step 3: Confirm Checkpoint Generation

Verify training command includes:

```text
--save_interval 1
--result_bucket retrained_ppo_koopman_mpc
--ppo_evidence_level retrained_policy_smoke
--phase5_summary_path ...
```

Confirm the generated summary includes:

```text
checkpoint_found = true
selected_checkpoint
checkpoint_provenance = phase5_train_koopman_mpc
adapter_refresh_count > 0
adapter_refresh_before_env_step = true
```

### Step 4: Confirm Provenance

Run or inspect the provenance validator.

It must reject:

```text
Phase 4.6 legacy checkpoint
old_checkpoint_adapter_smoke
checkpoint with missing source_training_summary_path
checkpoint with wrong controller_path
checkpoint with wrong adapter_mode
checkpoint with wrong reward_profile
```

It may accept only:

```text
checkpoint whose source summary proves Phase 5 Koopman-MPC training path
```

### Step 5: Confirm Evaluation

The evaluation workflow must load the Phase 5 checkpoint only after provenance passes.

Required evaluation labels:

```text
policy_mode = checkpoint
result_bucket = retrained_ppo_koopman_mpc
ppo_evidence_level = retrained_policy_smoke
checkpoint_provenance = phase5_train_koopman_mpc
adapter_mode = heuristic_reference_delta_v0
controller_path = koopman_mpc/direct_state
reward_profile = legacy_easyuuv_v0
```

### Step 6: Confirm Claims

Allowed claim:

```text
Phase 5 produced early retrained-policy smoke evidence for the Koopman-MPC control path.
```

Disallowed claims:

```text
PPO converged
PPO+Koopman-MPC beats legacy
policy is deployable
reward is final
old checkpoint semantics migrated losslessly
```

## 8. Final Gate Checklist

### P0 Gates

- [ ] Phase 5 training wrapper or env hook exists.
- [ ] Source-contract test proves adapter refresh is on the RSL-RL `env.step(action_4d)` path.
- [ ] Test fails if only `controller_mode=koopman_mpc` is set.
- [ ] PPO observation remains 9D.
- [ ] PPO action remains 4D.
- [ ] PPO never outputs 8D PWM.
- [ ] First reward profile is `legacy_easyuuv_v0`.
- [ ] First backend is `direct_state`.

### P1 Gates

- [ ] Training smoke writes a Phase 5 summary.
- [ ] Summary includes `checkpoint_provenance=phase5_train_koopman_mpc`.
- [ ] Summary includes `adapter_refresh_count > 0`.
- [ ] Summary includes `adapter_refresh_before_env_step=true`.
- [ ] Summary includes `base_reference_goal_match_max_error`.
- [ ] Summary includes `source_git_commit` and `source_git_dirty`.
- [ ] Checkpoint discovery selects the new Phase 5 checkpoint.
- [ ] Provenance validator rejects Phase 4.6 legacy checkpoints.

### P2 Gates

- [ ] Evaluation workflow supports `source_training_summary_path`.
- [ ] Evaluation workflow refuses `retrained_policy_smoke` without provenance.
- [ ] Evaluation JSONL or sidecar includes fallback, latency, clipping and PWM bounds.
- [ ] Smoke-level comparison does not rank final performance.
- [ ] Summary recommends Phase 5.x action: continue training, revise reward, fix MPC latency/fallback, or revise adapter mapping.

## 9. Minimal Repair Plan Before Server Execution

The next agent should implement these before any Phase 5 server run:

1. Add `tests/test_phase5_training_contract.py`.
2. Add `koopman/ppo_training_adapter.py` or an explicit `EasyUUVEnv` training hook.
3. Add `workflows/train_ppo_koopman.py`.
4. Add `workflows/validate_phase5_checkpoint_provenance.py`.
5. Extend `workflows/play_ppo_koopman.py` or create a Phase 5 eval script that requires provenance for `retrained_policy_smoke`.
6. Add summary fields for `adapter_refresh_count`, `adapter_refresh_before_env_step`, `checkpoint_provenance`, `source_git_dirty`, `base_reference_source` and `depth_reference_source`.
7. Add a `num_envs=1` fail-fast check unless vectorized adapter tests exist.

## 10. Reviewer Final Wording

If the implementation passes the gates, the reviewer may write:

```text
Phase 5 has produced early Koopman-MPC PPO retraining smoke evidence.
The RSL-RL training rollout path refreshes the Koopman reference through
heuristic_reference_delta_v0 before env.step(action_4d). The generated
checkpoint has Phase 5 provenance and can be loaded for a bounded short
PPO -> adapter -> Koopman+MPC -> PWM evaluation. This is smoke evidence only,
not convergence, superiority or deployment evidence.
```

If only the planning docs exist, the reviewer must write:

```text
Phase 5 planning is algorithmically aligned, but implementation evidence is not
yet present. The training wrapper, provenance validator and retrained checkpoint
evaluation gate must be implemented before Phase 5 can be marked complete.
```

## 11. Bottom Line

The Phase 5 plan is solid and reflects the core algorithm boundary.

The next agent's job is not to debate whether PPO should be 9D/4D or whether reward should be redesigned. Those are intentionally fixed for the first smoke.

The next agent's job is to prove one thing:

```text
During RSL-RL training, every PPO action_4d becomes a Koopman-MPC reference
before the underlying environment step.
```

If that is true and checkpoint provenance is enforced, Phase 5 is a valid bridge toward later long training and performance evaluation.

## 12. 2026-07-04 Local Repair Note

The must-fix implementation gates from this review have now been repaired locally.

Implemented:

- `koopman/ppo_training_adapter.py`
  - Adds `Phase5KoopmanReferenceWrapper`.
  - Refreshes `_koopman_reference_5d` inside `step(action_4d)` before delegating to the underlying env.
  - Fails fast for `num_envs != 1` until vectorized adapter refresh is tested.
  - Keeps the `koopman/` module free of explicit Isaac, Gym and tensor-runtime imports so the Phase 2 offline contract remains valid.
- `workflows/train_ppo_koopman.py`
  - Adds the Phase 5 RSL-RL training entrypoint.
  - Wraps `gym.make(...)` with `Phase5KoopmanReferenceWrapper` before `RslRlVecEnvWrapper`.
  - Writes Phase 5 summary fields including `checkpoint_provenance`, `adapter_refresh_count`, `adapter_refresh_before_env_step`, `source_git_commit`, `source_git_dirty`, `base_reference_source` and `depth_reference_source`.
- `workflows/validate_phase5_checkpoint_provenance.py`
  - Accepts only summaries proving `result_bucket=retrained_ppo_koopman_mpc`, `controller_path=koopman_mpc/direct_state`, `adapter_mode=heuristic_reference_delta_v0`, `reward_profile=legacy_easyuuv_v0`, `checkpoint_provenance=phase5_train_koopman_mpc`, observation_dim=9 and action_dim=4.
  - Rejects Phase 4.6 legacy summaries and checkpoint mismatches.
- `workflows/play_ppo_koopman.py`
  - Adds `--source_training_summary_path` and `--ppo_evidence_level`.
  - Runs Phase 5 provenance validation before Isaac startup when `retrained_policy_smoke` or `result_bucket=retrained_ppo_koopman_mpc` is requested.
  - Adds provenance fields to retrained-policy JSONL samples.
- `workflows/validate_ppo_koopman_log.py`
  - Requires provenance fields whenever `ppo_evidence_level=retrained_policy_smoke`.
- Tests:
  - `tests/test_phase5_training_contract.py`
  - `tests/test_phase5_checkpoint_provenance.py`
  - updated `tests/test_ppo_koopman_logging.py`

Verified locally:

```text
python -m pytest -q
110 passed

python -m compileall __init__.py easyuuv_env.py koopman workflows tests
passed

git diff --check
passed with CRLF warnings only
```

Remaining gate:

```text
Run the Phase 5 one-env Isaac server smoke:
  train_ppo_koopman.py -> provenance validator -> play_ppo_koopman.py retrained_policy_smoke
```

Do not mark Phase 5 complete until the server smoke proves the wrapper works under Isaac Lab/RSL-RL, because the local tests prove the source contract but cannot step Isaac physics.

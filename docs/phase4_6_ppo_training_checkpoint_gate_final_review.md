# Phase 4.6 PPO Training Checkpoint Gate Final Review

**Date:** 2026-07-03  
**Document type:** audit report plus execution guidance  
**Audience:** project owner and the agent implementing Phase 4.6  
**Scope:** Phase 4.6 planning docs, current PPO/RSL-RL entrypoints, Phase 4.5 adapter evidence contract and checkpoint discovery path  

## 1. Review Verdict

**Verdict:** `PASS_WITH_MUST_FIXES_BEFORE_EXECUTION`

Phase 4.6 is necessary and well motivated.

Phase 4.5 proved the adapter path with a stub policy:

```text
stub policy -> heuristic_reference_delta_v0 -> direct_state Koopman+MPC -> 8D PWM
```

It did not prove real PPO execution because server checkpoint discovery found no PPO checkpoint. Therefore adding Phase 4.6 as a PPO training entrypoint and checkpoint evidence gate is the right next step.

The current 4.6 documents have the correct high-level boundary:

```text
restore PPO/RSL-RL training and checkpoint evidence
do not claim PPO convergence
do not claim PPO+Koopman superiority
keep PPO observation 9D
keep PPO action 4D
do not let PPO output 8D PWM
```

However, several doc-code contract issues must be fixed before execution. The most important ones are:

1. `--max_iterations 1` may not generate `model_*.pt` because the current PPO config uses `save_interval = 50`.
2. `legacy_ppo_baseline` is currently mixed between `result_bucket` and `ppo_evidence_level`, but the existing adapter and validator do not accept it as an evidence level.
3. The planned `play_eval.py --eval_name ...` command does not match the current `play_eval.py` CLI.
4. Legacy PPO eval logging does not yet guarantee the Phase 4.6 summary fields.

These are not objections to Phase 4.6. They are evidence-gate corrections that should be made before a server run is treated as meaningful.

## 2. Source Of Truth Inspected

### Planning Docs

- `.planning/phases/04.6-ppo-training-entrypoint-and-checkpoint-evidence-gate/04.6-SPEC.md`
- `.planning/phases/04.6-ppo-training-entrypoint-and-checkpoint-evidence-gate/04.6-PLAN.md`
- `docs/phase4_6_ppo_training_checkpoint_gate.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`

### Current Implementation

- `workflows/train.py`
- `workflows/play_eval.py`
- `workflows/gen_policy.py`
- `workflows/discover_ppo_checkpoints.py`
- `workflows/play_ppo_koopman.py`
- `workflows/validate_ppo_koopman_log.py`
- `agents/rsl_rl_ppo_cfg.py`
- `koopman/policy_adapter.py`
- `tests/test_ppo_koopman_logging.py`
- `tests/test_phase45_checkpoint_discovery.py`

### Relevant Prior Phase Contracts

- Phase 4.5 adapter mode: `heuristic_reference_delta_v0`
- Phase 4.5 policy evidence levels currently supported by code:

```text
stub_only
checkpoint_smoke
training_entrypoint_only
retrained_policy_smoke
```

Source: `koopman/policy_adapter.py`

## 3. Healthy Contract Points

### 3.1 Phase 4.6 Correctly Exists Because PPO Evidence Is Missing

The SPEC states that Phase 4.5 did not prove PPO inference or PPO training because no PPO checkpoint existed on the server. This is the right reason to add Phase 4.6.

Source:

- `04.6-SPEC.md:27-42`
- `STATE.md:369-384`
- `ROADMAP.md:335-338`

Review:

This is a strong correction. It prevents the project from treating a stub-policy Koopman smoke as PPO evidence.

### 3.2 The Three Result Buckets Are Conceptually Correct

The SPEC separates:

```text
legacy_ppo_baseline
old_checkpoint_adapter_smoke
retrained_ppo_koopman_mpc
```

Source:

- `04.6-SPEC.md:65-73`
- `04.6-PLAN.md:37-43`
- `docs/phase4_6_ppo_training_checkpoint_gate.md`

Review:

This separation is essential. It correctly distinguishes:

1. original EasyUUV PPO path,
2. old checkpoint compatibility smoke through the adapter,
3. future retrained PPO under Koopman-MPC.

### 3.3 The Plan Correctly Rejects `controller_mode = koopman_mpc` Alone

The plan states that Koopman-MPC PPO retraining must put the adapter in the training loop, not only in eval.

Source:

- `04.6-SPEC.md:113-122`
- `04.6-PLAN.md:214-241`
- `STATE.md:415-417`

Review:

This is exactly the right algorithmic boundary. RSL-RL calls `env.step(action)`. If the training wrapper does not convert `action_4d` into `_koopman_reference_5d` before each step, PPO is not really training against the intended Koopman-MPC reference path.

### 3.4 Reward Versioning Is Correct

The plan keeps:

```text
reward_profile = "legacy_easyuuv_v0"
```

Source:

- `04.6-SPEC.md:124-132`
- `04.6-PLAN.md:43`

Review:

This is appropriate. Phase 4.6 already changes the training/checkpoint evidence path. Changing reward at the same time would make results hard to attribute.

## 4. Must-Fix Findings

### Finding 1: `--max_iterations 1` May Not Produce A Checkpoint

**Severity:** Must fix  
**Category:** Command drift / evidence drift  
**Source:**

- `04.6-SPEC.md:83-92`
- `04.6-SPEC.md:176-180`
- `04.6-PLAN.md:82-99`
- `agents/rsl_rl_ppo_cfg.py`

Current code fact:

```text
EasyUUVPPORunnerCfg.save_interval = 50
EasyUUVPPORunnerCfg.max_iterations = 800
```

The plan says a one-env one-iteration smoke should run:

```text
--num_envs 1 --max_iterations 1 --headless
```

and the SPEC requires a short training run to produce at least one `model_*.pt`.

Risk:

If RSL-RL only saves on `save_interval`, a one-iteration run may start successfully but produce no checkpoint. In that case, Phase 4.6 would incorrectly fail the checkpoint gate even though the training entrypoint itself worked.

Required correction:

Split the gate into two separate checks:

```text
training_entrypoint_smoke:
  proves train.py starts and reaches runner creation or one learning iteration
  evidence_level = training_entrypoint_only
  checkpoint_required = false

checkpoint_generation_smoke:
  proves model_*.pt can be written
  must use save_interval = 1, an explicit runner.save(...), or enough iterations to trigger save_interval
  checkpoint_required = true
```

Recommended doc update:

```text
--max_iterations 1 proves entrypoint compatibility only.
Checkpoint generation requires --save_interval 1, an explicit final save,
or >= save_interval iterations.
```

Implementation options:

1. Add a `--save_interval` CLI override in `workflows/train.py`.
2. Add a Phase 4.6 smoke flag that sets `agent_cfg.save_interval = 1`.
3. Explicitly save a final smoke checkpoint after `runner.learn(...)`.
4. Run at least 50 iterations only if server time budget allows it.

Do not rely on `--max_iterations 1` alone as checkpoint evidence.

### Finding 2: `legacy_ppo_baseline` Is Mixed Between Evidence Level And Result Bucket

**Severity:** Must fix  
**Category:** Terminology drift / validator drift  
**Source:**

- `04.6-SPEC.md:65-73`
- `04.6-SPEC.md:134-144`
- `04.6-PLAN.md:197-204`
- `koopman/policy_adapter.py`
- `workflows/validate_ppo_koopman_log.py`

Current code fact:

`koopman/policy_adapter.py` defines valid PPO evidence levels as:

```text
stub_only
checkpoint_smoke
training_entrypoint_only
retrained_policy_smoke
```

The current SPEC lists:

```text
training_entrypoint_only
legacy_ppo_baseline
checkpoint_smoke
retrained_policy_smoke
```

Risk:

If `legacy_ppo_baseline` is written into `ppo_evidence_level`, current validators will reject it unless they are updated. More importantly, the concept is cleaner as a result bucket, not as an evidence level.

Required correction:

Use two fields consistently:

```text
ppo_evidence_level = "checkpoint_smoke"
result_bucket = "legacy_ppo_baseline"
```

or, if the team wants more precise evidence semantics:

```text
ppo_evidence_level = "checkpoint_loaded_legacy"
result_bucket = "legacy_ppo_baseline"
```

If the second option is chosen, update:

- `koopman/policy_adapter.py`
- `workflows/validate_ppo_koopman_log.py`
- `tests/test_ppo_koopman_logging.py`
- any Phase 4.6 validators

Recommended simpler option:

Keep the existing evidence levels and make `legacy_ppo_baseline` only a `result_bucket`.

### Finding 3: Planned `play_eval.py --eval_name` Does Not Match Current CLI

**Severity:** Must fix  
**Category:** Command drift  
**Source:**

- `04.6-PLAN.md:145-154`
- `workflows/play_eval.py`

The Phase 4.6 plan proposes:

```bash
./isaaclab.sh -p /root/EASYkoopman/workflows/play_eval.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --custom_weights /path/to/model_*.pt \
  --eval_name legacy_ppo_baseline_smoke
```

Current `play_eval.py` has `--custom_weights`, but it does not currently expose `--eval_name`.

Risk:

The planned Wave 3 command will fail at argument parsing unless `--eval_name` is added.

Required correction:

Choose one:

1. Add `--eval_name` to `workflows/play_eval.py` and use it in output paths/log labels.
2. Remove `--eval_name` from the documented command and use existing `--koopman_log_path`.

Recommended option:

Add explicit Phase 4.6 labels:

```text
--result_bucket legacy_ppo_baseline
--ppo_evidence_level checkpoint_smoke
--reward_profile legacy_easyuuv_v0
--controller_path legacy/Ssurface
```

If these flags are too much for `play_eval.py`, write a sidecar summary JSON after the smoke run.

### Finding 4: Legacy PPO Baseline Logging Is Not Yet Contracted

**Severity:** Must fix  
**Category:** Scope drift / logging contract drift  
**Source:**

- `04.6-SPEC.md:183`
- `04.6-PLAN.md:130-162`
- `workflows/play_eval.py`

Current `play_eval.py` logs Koopman samples with:

```text
action_4d=actions
controller_mode=f"legacy/{env_cfg.control_method}"
```

But Phase 4.6 requires summary fields such as:

```text
ppo_evidence_level
result_bucket
reward_profile
controller_path
checkpoint_path
action_clip_rate
fallback_rate
latency
bounded PWM status
```

Risk:

The legacy baseline smoke may run, but the result will not be auditable as Phase 4.6 evidence.

Required correction:

For `legacy_ppo_baseline`, create either:

1. an extended JSONL validator for PPO baseline logs, or
2. a `phase4_6_legacy_ppo_baseline_summary.json` sidecar.

Minimum required sidecar fields:

```json
{
  "result_bucket": "legacy_ppo_baseline",
  "ppo_evidence_level": "checkpoint_smoke",
  "reward_profile": "legacy_easyuuv_v0",
  "controller_path": "legacy/Ssurface",
  "checkpoint_path": "...",
  "training_iterations": 1,
  "checkpoint_found": true,
  "action_dim": 4,
  "observation_dim": 9,
  "pwm_dim": 8,
  "allowed_claims": [...],
  "disallowed_claims": [...]
}
```

### Finding 5: Checkpoint Discovery Needs A Selected Checkpoint Contract

**Severity:** Must fix before automated server execution  
**Category:** Source-of-truth drift / artifact selection drift  
**Source:**

- `04.6-SPEC.md:83-92`
- `04.6-PLAN.md:103-128`
- `workflows/discover_ppo_checkpoints.py`

Current discovery output includes:

```text
checkpoint_found
count
paths
search_roots
```

Risk:

When several `.pt` files exist, downstream commands need one explicit checkpoint path. A list is useful, but the gate should declare how `selected_checkpoint` is chosen.

Required correction:

Add to discovery output:

```json
{
  "selected_checkpoint": "...",
  "selected_rule": "latest_mtime_model_pt",
  "paths": [...]
}
```

Selection should prefer:

1. `model_*.pt` over generic `*.pt`,
2. latest modification time,
3. explicit `--play_checkpoint` over auto-discovery.

This prevents the agent from accidentally loading an export artifact or an old incompatible checkpoint.

## 5. Should-Fix Findings

### Finding 6: Isaac Lab 2 Import Migration Should Be More Explicit

**Severity:** Should fix  
**Category:** Responsibility drift  
**Source:**

- `04.6-SPEC.md:77-81`
- `04.6-PLAN.md:72-82`
- `workflows/train.py`
- `workflows/play_eval.py`
- `workflows/gen_policy.py`
- `agents/rsl_rl_ppo_cfg.py`

Current fact:

`agents/rsl_rl_ppo_cfg.py` already imports via `isaaclab_compat`, but `train.py`, `play_eval.py` and `gen_policy.py` still use older `omni.isaac.lab` imports and direct wrapper imports.

Recommendation:

Make Wave 1 explicit:

```text
Migrate train.py/play_eval.py/gen_policy.py to the same Isaac Lab 2 compatibility pattern used by agents/rsl_rl_ppo_cfg.py, or prove the old import path still works on the server.
```

Also add a source-contract test for:

```text
AppLauncher setup occurs before environment/task imports.
duplicate --cpu parser conflict is removed or guarded.
```

### Finding 7: Koopman-MPC PPO Retraining Is Larger Than A Checkpoint Gate

**Severity:** Should fix  
**Category:** Scope drift  
**Source:**

- `04.6-SPEC.md:113-122`
- `04.6-PLAN.md:214-241`

Phase 4.6 includes a Wave 5 for `train_ppo_koopman.py`. The concept is correct, but it is meaningfully larger than restoring checkpoint evidence.

Recommendation:

Treat Wave 5 as a contract or optional spike unless Phase 4.6 has time to implement and verify the training wrapper. The phase can pass without `retrained_policy_smoke` if it clearly restores:

1. training entrypoint,
2. checkpoint generation,
3. checkpoint discovery,
4. legacy checkpoint load,
5. optional old-checkpoint adapter smoke.

Do not let Wave 5 block the narrower checkpoint gate unless the project explicitly chooses to make Phase 4.6 a retraining-wrapper phase.

### Finding 8: `docs/phase4_6_ppo_training_checkpoint_gate.md` Is Useful But Needs Source References

**Severity:** Should fix  
**Category:** Source-of-truth drift  

The Chinese guide is clear and readable. It correctly explains why Phase 4.6 exists and why old checkpoints cannot prove Koopman-MPC PPO migration.

However, it currently reads as an explanation without direct source links or code path references. For future agents, add a short source map:

```text
workflows/train.py: PPO training entrypoint
agents/rsl_rl_ppo_cfg.py: max_iterations, save_interval, experiment_name
workflows/discover_ppo_checkpoints.py: checkpoint search roots
workflows/play_eval.py: legacy checkpoint eval path
workflows/play_ppo_koopman.py: old-checkpoint adapter smoke path
koopman/policy_adapter.py: adapter mode and ppo_evidence_level enum
```

## 6. Final Audit Gate For Phase 4.6

Use this as the final review checklist before marking Phase 4.6 complete.

### Gate A: Entrypoint Compatibility

- [ ] `workflows/train.py` starts under Isaac Lab 2.2.1.
- [ ] `AppLauncher` is initialized before task/environment imports.
- [ ] No duplicate `--cpu` parser conflict occurs.
- [ ] `--num_envs 1 --max_iterations 1 --headless` reaches runner creation or one learning iteration.
- [ ] Result is labeled `ppo_evidence_level=training_entrypoint_only` unless a checkpoint is actually generated.

### Gate B: Checkpoint Generation

- [ ] Checkpoint generation uses `save_interval=1`, explicit final save or enough iterations to trigger saving.
- [ ] At least one `model_*.pt` exists after the run.
- [ ] Discovery reports `checkpoint_found=true`.
- [ ] Discovery reports `selected_checkpoint`.
- [ ] The selected checkpoint path is passed explicitly to later eval commands.

### Gate C: Legacy PPO Baseline

- [ ] `play_eval.py` command matches actual CLI.
- [ ] Checkpoint loads through `OnPolicyRunner`.
- [ ] Inference policy returns 4D action.
- [ ] Environment uses `controller_mode=legacy` and `control_method=Ssurface`.
- [ ] Summary includes `result_bucket=legacy_ppo_baseline`.
- [ ] `legacy_ppo_baseline` is not used as `ppo_evidence_level` unless validators are updated.

### Gate D: Old Checkpoint Adapter Smoke

- [ ] `play_ppo_koopman.py --policy_mode checkpoint` starts only after checkpoint preflight passes.
- [ ] Adapter mode is `heuristic_reference_delta_v0`.
- [ ] `ppo_evidence_level=checkpoint_smoke`.
- [ ] `result_bucket=old_checkpoint_adapter_smoke`.
- [ ] Logs include `controller_swap_distribution_shift=true`.
- [ ] PWM remains bounded.
- [ ] Fallback and latency are reported.

### Gate E: Optional Koopman-MPC Retraining Wrapper

- [ ] Training wrapper calls adapter before `env.step(action_4d)`.
- [ ] `_koopman_reference_5d` is refreshed every step.
- [ ] Source-contract test proves the order.
- [ ] Result is labeled `ppo_evidence_level=retrained_policy_smoke`.
- [ ] Summary states no convergence claim.

### Gate F: Claims Discipline

- [ ] Allowed claims are listed.
- [ ] Disallowed claims are listed.
- [ ] No wording claims PPO superiority.
- [ ] No wording claims old checkpoint semantic equivalence.
- [ ] No wording claims one-iteration training is a useful policy.

## 7. Recommended Minimal Repair Plan

Before executing Phase 4.6 on the server, update the planning docs as follows.

1. Split "training entrypoint smoke" from "checkpoint generation smoke".
2. Add a save policy: `save_interval=1`, explicit final save or enough iterations.
3. Make `legacy_ppo_baseline` strictly a `result_bucket`, not a `ppo_evidence_level`.
4. Align all `ppo_evidence_level` values with `koopman/policy_adapter.py` and validators.
5. Fix the Wave 3 command by adding `--eval_name` to `play_eval.py` or removing it from the docs.
6. Require a summary sidecar for legacy PPO baseline smoke.
7. Add `selected_checkpoint` and `selected_rule` to checkpoint discovery.
8. Treat Koopman-MPC retraining as optional unless the training wrapper is actually implemented and tested.

## 8. Final Recommended Completion Wording

Use this only after Gates A-D pass:

```text
Phase 4.6 restored PPO/RSL-RL checkpoint evidence under Isaac Lab 2.2.1.
The training entrypoint starts, checkpoint generation is explicitly verified,
checkpoint discovery selects a concrete model_*.pt, and the checkpoint can be
loaded through the legacy PPO path. If routed through Koopman+MPC, the run is
labeled old_checkpoint_adapter_smoke and checkpoint_smoke, not a migrated or
performance-proven policy. Phase 4.6 makes no convergence or superiority claim.
```

Use this if only Gate A passes:

```text
Phase 4.6 has verified PPO training entrypoint compatibility only. It has not
yet produced checkpoint evidence, so checkpoint inference and PPO performance
claims remain blocked.
```

## 9. Bottom Line

Phase 4.6 is the right response to the missing PPO checkpoint problem.

It should proceed, but only after the checkpoint evidence contract is tightened. The single most important correction is to avoid treating a one-iteration training entrypoint smoke as checkpoint evidence. The second most important correction is to keep `result_bucket` and `ppo_evidence_level` separate.

Once those are fixed, Phase 4.6 will be a clean bridge between Phase 4.5 adapter plumbing and any later real PPO+Koopman-MPC training claim.


---
phase: 05-koopman-mpc-ppo-retraining
status: planned
created: 2026-07-03
target_branch: isaaclab2-migration
type: implementation
wave_count: 6
requirements: [RL-01, RL-02, RL-03, RL-04, MPC-05, EVAL-03]
---

# Phase 5: Koopman-MPC PPO Retraining - Plan

**Spec:** `.planning/phases/05-koopman-mpc-ppo-retraining/05-SPEC.md`
**Mode:** local source-contract changes first, then server Isaac training and evaluation
**Default PPO implementation:** RSL-RL PPO
**Default PPO observation/action:** EasyUUV 9D observation and 4D action
**Default low-level backend:** `direct_state` Koopman+MPC

## Purpose

Train the PPO checkpoint that actually belongs to the Koopman-MPC architecture.

The planned progression is:

```text
1. finish Phase 4.6 checkpoint evidence gate
2. implement adapter-in-training-loop contract
3. train a short Koopman-MPC PPO smoke checkpoint
4. discover and load the retrained checkpoint
5. run short retrained-policy evaluation
6. compare smoke statistics against Phase 4.5/4.6 baselines
```

This phase is still not a convergence phase. It proves that the correct training loop exists and produces a loadable checkpoint.

## Non-Negotiable Boundaries

- Reuse RSL-RL PPO. Do not hand-write PPO.
- PPO observation remains 9D.
- PPO action remains 4D.
- PPO must not output 8D PWM.
- The training loop must execute `heuristic_reference_delta_v0` before every `env.step`.
- `controller_mode=koopman_mpc` by itself is not enough.
- First reward profile remains `legacy_easyuuv_v0`.
- First backend remains `direct_state`.
- Old EASYUUV PPO checkpoints remain baselines or off-distribution smokes only.

## Wave 0: Contract And Documentation

Files:

- Create: `.planning/phases/05-koopman-mpc-ppo-retraining/05-SPEC.md`
- Create: `.planning/phases/05-koopman-mpc-ppo-retraining/05-PLAN.md`
- Create: `docs/phase5_koopman_mpc_ppo_training_strategy.md`
- Update: `.planning/ROADMAP.md`
- Update: `.planning/STATE.md`

Acceptance:

- The docs state that Koopman-MPC needs its own PPO checkpoint.
- The docs state that old checkpoints are not final evidence.
- The docs state that PPO algorithm code should come from RSL-RL.

Verification:

```powershell
git diff --check
```

## Wave 1: Adapter-In-Training-Loop Design

Likely files:

- Modify or create: `workflows/train_ppo_koopman.py`
- Modify if needed: `koopman/policy_adapter.py`
- Modify if needed: `easyuuv_env.py`
- Test: `tests/test_phase5_training_contract.py`

Implementation intent:

- Decide the smallest reliable integration point:
  - environment hook that interprets the PPO action before `_pre_physics_step`; or
  - wrapper around RSL-RL env step; or
  - dedicated train workflow that refreshes `_koopman_reference_5d` before stepping.
- Reuse the exact Phase 4.5 adapter mode name: `heuristic_reference_delta_v0`.
- Emit a training-loop diagnostic proving the adapter ran during training.

Required source-contract assertion:

```text
policy_output_4d -> heuristic_reference_delta_v0 -> _koopman_reference_5d refresh -> env.step(action_4d)
```

Acceptance:

- Test fails if a Koopman-MPC training command only sets `controller_mode`.
- Test passes only when adapter refresh is visibly in the training path.

## Wave 2: Training Entrypoint And Config Profile

Likely files:

- Create or modify: `workflows/train_ppo_koopman.py`
- Modify if needed: `agents/rsl_rl_ppo_cfg.py`
- Modify if needed: `workflows/discover_ppo_checkpoints.py`
- Test: `tests/test_phase5_training_contract.py`

Implementation intent:

- Start from the Phase 4.6 migrated `workflows/train.py`.
- Add explicit CLI flags:

```text
--controller_mode koopman_mpc
--adapter_mode heuristic_reference_delta_v0
--koopman_manifest_path <path>
--result_bucket retrained_ppo_koopman_mpc
--reward_profile legacy_easyuuv_v0
--save_interval 1 for smoke
```

- Keep run outputs separate from legacy PPO logs, for example:

```text
logs/rsl_rl/easyuuv_koopman_mpc/<timestamp>/
source/results/koopman_phase5/
```

Acceptance:

- Local tests verify command defaults.
- Local compile passes.
- Checkpoint discovery can distinguish Phase 5 retrained checkpoints from Phase 4.6 legacy checkpoints.

## Wave 3: Server Training Smoke

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
  --koopman_manifest_path /root/EASYkoopman/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json \
  --result_bucket retrained_ppo_koopman_mpc \
  --reward_profile legacy_easyuuv_v0
```

Acceptance:

- Isaac starts without import-order or CLI conflicts.
- RSL-RL runner starts.
- At least one training iteration completes, or a clear preflight failure explains why it cannot.
- A checkpoint is written for the smoke run.
- Summary labels the run `ppo_evidence_level=retrained_policy_smoke`.

Stop and ask the user if:

- Koopman-MPC fallback rate is so high that training cannot step meaningfully.
- Solver latency makes the training loop unusably slow.
- RSL-RL wrapper prevents the adapter refresh from being inserted cleanly.

## Wave 4: Retrained Checkpoint Evaluation

Likely files:

- Reuse or modify: `workflows/play_ppo_koopman.py`
- Modify: `workflows/validate_ppo_koopman_log.py`
- Create if needed: `workflows/write_phase5_ppo_summary.py`
- Test: `tests/test_ppo_koopman_logging.py`

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
  --controller_mode koopman_mpc \
  --koopman_manifest_path /root/EASYkoopman/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json \
  --trajectory_type step \
  --trajectory_cycles 1 \
  --steps_per_action 50 \
  --ppo_koopman_log_path /root/EASYkoopman/source/results/koopman_phase5/retrained_ppo_koopman_step.jsonl
```

Required labels:

```text
policy_mode = checkpoint
result_bucket = retrained_ppo_koopman_mpc
ppo_evidence_level = retrained_policy_smoke
adapter_mode = heuristic_reference_delta_v0
controller_path = koopman_mpc/direct_state
reward_profile = legacy_easyuuv_v0
```

Acceptance:

- JSONL validator passes.
- PWM remains bounded.
- Summary reports fallback, latency, action clipping and tracking errors.
- Summary states no convergence or superiority claim.

## Wave 5: Smoke-Level Comparison

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

- Do not rank policies as final performance unless a later long evaluation phase is created.

Acceptance:

- Report identifies whether Phase 5 is ready for longer training/evaluation.
- Report recommends one of:

```text
continue_training
fix_mpc_latency_or_fallback_first
revise_reward_profile
revise_adapter_mapping
```

## Wave 6: Summary, Verification And Handoff

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
training_iterations
num_envs
result_bucket
ppo_evidence_level
reward_profile
controller_path
adapter_mode
koopman_backend
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
the Koopman reference before environment steps. A checkpoint was generated,
loaded and evaluated through PPO -> adapter -> Koopman+MPC -> PWM. The result is
smoke evidence, not convergence or superiority evidence.
```

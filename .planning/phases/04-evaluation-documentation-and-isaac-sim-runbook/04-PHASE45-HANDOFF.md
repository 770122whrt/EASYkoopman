---
phase: 04-evaluation-documentation-and-isaac-sim-runbook
handoff_to: 04.5-ppo-rl-reference-adapter-integration
created: 2026-07-02
---

# Phase 4.5 Handoff: PPO/RL Reference Adapter

## 1. Baseline To Preserve

Phase 4.5 should treat Phase 4 as the controller-only baseline:

```text
scripted reference -> controller -> 8D PWM -> AUV
```

The next phase may add PPO/RL above the controller, but it must preserve the low-level control boundary:

```text
PPO/RL -> reference or 4D correction -> controller -> 8D PWM -> AUV
```

PPO must not bypass the controller and directly command 8D PWM in Phase 4.5.

## 2. Recommended Controller Baselines

| Role | Controller | Reason |
|---|---|---|
| Primary stability baseline | `legacy/Ssurface` | Best Phase 4 tracking, no fallback and bounded PWM. |
| Koopman engineering baseline | `direct_state` Koopman+MPC | Closed-loop runnable with bounded PWM, but needs fallback/latency tuning. |
| Research comparison only | `paper_lifted_edmd` Koopman+MPC | Paper-style backend ran, but depth RMSE is too high for default PPO integration. |

## 3. Logs PPO Should Compare Against

Use these Phase 4 logs as controller-only references:

```text
source/results/koopman_phase4/data/legacy_step_run01.jsonl
source/results/koopman_phase4/data/legacy_sine_run01.jsonl
source/results/koopman_phase4/data/legacy_irregular_run01.jsonl
source/results/koopman_phase4/data/direct_state_mpc_step_run01.jsonl
source/results/koopman_phase4/data/direct_state_mpc_sine_run01.jsonl
source/results/koopman_phase4/data/direct_state_mpc_irregular_run01.jsonl
```

Keep paper-lifted logs for research comparison:

```text
source/results/koopman_phase4/data/paper_lifted_mpc_step_run01.jsonl
source/results/koopman_phase4/data/paper_lifted_mpc_sine_run01.jsonl
source/results/koopman_phase4/data/paper_lifted_mpc_irregular_run01.jsonl
```

## 4. PPO Adapter Contract

Phase 4.5 should implement the adapter around one of two safe contracts:

```text
Option A:
  PPO outputs a bounded 4D correction
  adapter adds it to scripted/reference command
  Koopman+MPC produces 8D PWM

Option B:
  PPO outputs a bounded 5D target reference
  adapter validates and clips reference
  Koopman+MPC produces 8D PWM
```

Both options must log:

```text
policy_output
adapted_reference
controller_mode
backend_used
solver_diagnostics
pwm_8d
fallback
latency_ms
```

## 5. First Phase 4.5 Server Steps

Before trying full PPO inference:

1. Discover whether a PPO checkpoint exists under `logs/rsl_rl/easyuuv`.
2. Add local adapter tests for clipping, non-finite rejection and shape validation.
3. Run a deterministic stub-policy smoke:

```text
stub policy -> direct_state Koopman+MPC -> bounded 8D PWM
```

4. If a checkpoint exists, run a one-env short inference smoke.
5. If no checkpoint exists, run a small PPO training smoke only to prove the training entrypoint still works on Isaac Lab 2.2.1.

## 6. Success Boundary For Phase 4.5

Phase 4.5 should claim:

```text
PPO/RL can be reconnected above the controller boundary,
and the resulting chain logs policy output, adapted reference,
MPC diagnostics and bounded PWM.
```

It should not claim:

```text
PPO improves tracking over legacy
PPO is trained to convergence
LLM tuning is connected
paper_lifted_edmd is production-ready
```

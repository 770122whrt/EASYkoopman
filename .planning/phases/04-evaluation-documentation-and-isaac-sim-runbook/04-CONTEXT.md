---
phase: 04-evaluation-documentation-and-isaac-sim-runbook
status: planned
created: 2026-07-02
---

# Phase 4 Context

## Current State

Phase 3 and Phase 3.5 changed the project from "can train a Koopman model" to "can run a fallback-safe Koopman+MPC controller in Isaac smoke tests."

Current controller paths:

```text
legacy:
  scripted trajectory/reference -> 4D direct action -> Ssurface/PID -> 8D PWM

direct_state Koopman+MPC:
  scripted trajectory/reference -> Koopman+MPC -> 8D PWM

paper_lifted_edmd Koopman+MPC:
  scripted trajectory/reference -> paper-style lifted EDMD backend -> Koopman+MPC -> 8D PWM
```

Current important facts:

- `workflows/play_controller.py` is the correct Phase 4 entrypoint because it does not require PPO.
- `workflows/play_eval.py`, `workflows/play_eval_step.py` and `workflows/play_eval_task2.py` remain PPO-oriented and should not be the first Phase 4 baseline path.
- `workflows/validate_koopman_log.py` validates JSONL structure and dimensions.
- `workflows/run_koopman_mpc_offline.py` reports offline MPC boundedness, fallback and latency, but it is not a closed-loop evaluation aggregator.
- `source/results/koopman_phase3_5/` contains paper-lifted manifest and smoke logs, but these are experimental artifacts and may remain untracked.

## Locked Decisions

### D-01: Use `play_controller.py` For Matched Controller Runs

Phase 4 will use `workflows/play_controller.py` for legacy, direct-state and paper-lifted runs.

Reason:

- it already exposes `--controller_mode`, `--trajectory_type`, `--koopman_manifest_path`, MPC weights and output path;
- it avoids PPO checkpoint dependency;
- it logs the same Koopman JSONL schema for every controller.

### D-02: Controller-Only Before PPO

Phase 4 does not reconnect PPO.

The purpose is to measure the controller layer first:

```text
scripted reference -> controller -> PWM -> physics
```

Phase 4.5 will later measure:

```text
PPO/RL -> reference or 4D correction -> Koopman+MPC -> PWM -> physics
```

### D-03: Paper-Lifted Is A Comparison Backend

Paper-lifted EDMD should be included in Phase 4 if its manifest loads and smoke logs validate, but it is not automatically promoted to the primary controller.

The Phase 4 summary must distinguish:

```text
engineering baseline:
  direct_state Koopman+MPC

paper-aligned comparison:
  paper_lifted_edmd Koopman+MPC
```

### D-04: Metrics Must Be Isaac-Free

Metrics aggregation must be a local Python path that reads JSONL files only.

It must not import:

```text
isaaclab
isaaclab_tasks
omni
pxr
torch with Isaac runtime assumptions
```

This keeps analysis reproducible on the local workstation.

## Canonical References

### Controller Runtime

- `easyuuv_env.py` - controller mode switch, `_compute_dynamics()`, `_last_pwm_8d`, solver diagnostics.
- `workflows/play_controller.py` - controller-only server rollout entrypoint.
- `workflows/koopman_logging.py` - JSONL record shape and solver diagnostics passthrough.
- `koopman_data.py` - sample validation and JSONL loading.

### Koopman/MPC Backends

- `koopman/runtime.py` - manifest loader and backend selection contract.
- `koopman/mpc.py` - tracking cost, PWM bounds and solver behavior.
- `koopman/mpc_controller.py` - fallback-safe controller adapter.
- `workflows/run_koopman_mpc_offline.py` - existing offline MPC report schema.

### Prior Phase Artifacts

- `.planning/phases/03-koopman-mpc-controller-integration/03-SUMMARY.md` - Phase 3 completion evidence if present.
- `.planning/phases/03.5-paper-style-lifted-edmd-backend-qualification/03.5-SPEC.md`
- `.planning/phases/03.5-paper-style-lifted-edmd-backend-qualification/03.5-PLAN.md`
- `source/results/koopman_phase3_5/paper_lifted_manifest.json`
- `source/results/koopman_phase3_5/backend_prediction_comparison.json`
- `source/results/koopman_phase3_5/direct_state_offline_mpc_sine.json`
- `source/results/koopman_phase3_5/paper_lifted_offline_mpc_sine.json`

## Expected Output Layout

Phase 4 should write generated experiment artifacts under:

```text
source/results/koopman_phase4/
  data/
    legacy_step_run01.jsonl
    legacy_sine_run01.jsonl
    legacy_irregular_run01.jsonl
    direct_state_mpc_step_run01.jsonl
    direct_state_mpc_sine_run01.jsonl
    direct_state_mpc_irregular_run01.jsonl
    paper_lifted_mpc_step_run01.jsonl
    paper_lifted_mpc_sine_run01.jsonl
    paper_lifted_mpc_irregular_run01.jsonl
  reports/
    metrics_summary.json
    metrics_summary.md
    phase45_handoff.md
```

The exact number of repeated runs can be adjusted to server time, but the default plan should target one complete matched matrix first.

## Known Risks

- Paper-lifted smoke succeeded only for very short runs; longer runs may show high fallback or latency.
- Direct-state and paper-lifted may both saturate PWM; metrics must report saturation and smoothness, not only tracking error.
- `play_controller.py` generated references are scripted and not PPO policy outputs.
- Local result files under `source/` may be large or untracked; they should not be committed by default.
- If server TLS/Git transfer fails, sync should use archive, zip, bundle or scp instead of blocking Phase 4.

## Completion Shape

Phase 4 is complete when it can honestly say:

```text
We have a reproducible controller-only Isaac evaluation baseline for legacy,
direct-state Koopman+MPC and eligible paper-lifted Koopman+MPC, plus a local
metrics summary and runbook. PPO and LLM remain intentionally deferred.
```

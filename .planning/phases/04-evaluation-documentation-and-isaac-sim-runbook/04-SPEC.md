---
phase: 04-evaluation-documentation-and-isaac-sim-runbook
plan: 04
subsystem: evaluation-documentation
status: completed
created: 2026-07-02
tags: [evaluation, isaaclab, koopman-mpc, runbook, metrics]
requires:
  - phase: 03-koopman-mpc-controller-integration
  - phase: 03.5-paper-style-lifted-edmd-backend-qualification
provides:
  - controller-only evaluation matrix
  - comparable closed-loop metrics
  - Isaac server runbook
  - Phase 4.5 PPO handoff baseline
requirements: [EVAL-01, EVAL-02, DOC-01, DOC-02]
---

# Phase 4: Evaluation, Documentation And Isaac Sim Runbook - Specification

## Goal

Phase 4 produces a repeatable controller-only comparison between EasyUUV legacy control, direct-state Koopman+MPC and eligible paper-style lifted EDMD Koopman+MPC, then documents the Isaac Sim/Lab run procedure and limitations before PPO is reconnected in Phase 4.5.

## Background

The project now has:

- a working legacy `Ssurface` controller path;
- Koopman JSONL logging with `state`, `reference`, `action_4d`, `pwm_8d`, `next_state` and optional `solver_diagnostics`;
- a fallback-safe `koopman_mpc` controller mode;
- a selected direct-state model manifest;
- a paper-style lifted EDMD comparison manifest;
- short server Isaac smoke logs for paper-lifted step, sine and irregular trajectories.

The missing piece is not another controller. The missing piece is a fair evaluation layer. Today, logs and reports exist, but there is no single Phase 4 contract for:

```text
same trajectory settings
same controller entrypoint
same metrics schema
same output layout
same success/failure language
```

Phase 4 therefore freezes a controller-only baseline before Phase 4.5 adds PPO. This prevents policy defects, model defects and MPC defects from being mixed into one ambiguous experiment.

## Requirements

1. **Matched controller evaluation matrix**: The phase must define a matched server run matrix for legacy, direct-state Koopman+MPC and paper-lifted Koopman+MPC where paper-lifted remains eligible.
   - Current: `play_controller.py` can run legacy and `koopman_mpc`, but Phase 4 does not yet define one canonical matrix.
   - Target: Phase 4 has explicit commands for controller mode, trajectory type, manifest path, horizon, timeout, goals, steps and output path.
   - Acceptance: A verifier can list the expected JSONL outputs for every controller/trajectory pair before launching Isaac.

2. **Comparable metrics summary**: The phase must produce a local, Isaac-free metrics workflow for Phase 4 JSONL logs.
   - Current: JSONL validation exists, and offline MPC reports exist, but no unified closed-loop controller comparison report exists.
   - Target: A workflow reads one or more JSONL logs and writes a metrics JSON/Markdown report with the same fields for every run.
   - Acceptance: The workflow reports sample count, trajectory type, controller mode, backend, depth RMSE, attitude error, control energy, PWM smoothness, fallback rate, latency statistics and bounded PWM status.

3. **Paper-lifted eligibility boundary**: The phase must include paper-lifted in full evaluation only as a comparison backend, not as an automatic replacement for direct-state.
   - Current: Phase 3.5 smoke indicates paper-lifted is worth evaluating, but offline fallback and latency remain limitations.
   - Target: Phase 4 compares paper-lifted honestly when its manifest and smoke logs are valid, while preserving direct-state as the engineering baseline.
   - Acceptance: The Phase 4 report states whether paper-lifted was evaluated, why, and what limitations remain.

4. **Controller-only boundary before PPO**: The phase must not reconnect PPO or LLM.
   - Current: PPO training and inference scripts exist, but no reliable PPO checkpoint was assumed during Koopman+MPC work.
   - Target: Phase 4 uses `workflows/play_controller.py` for matched controller experiments and records PPO/LLM as out of scope.
   - Acceptance: No Phase 4 command requires `OnPolicyRunner`, PPO checkpoint loading, LLM API keys or external model calls.

5. **Isaac runbook**: The phase must document the exact server setup and command sequence needed to reproduce evaluation.
   - Current: server environment notes exist, and prior commands were shared in conversation, but there is no Phase 4 runbook.
   - Target: A document gives environment activation, repository sync notes, manifest paths, run commands, validation commands and artifact copy-back guidance.
   - Acceptance: A new Isaac user can follow the runbook from `/root/IsaacLab` and `/root/EASYkoopman` without guessing command flags.

6. **Phase 4.5 handoff**: The phase must end with a concise baseline that PPO integration can use.
   - Current: roadmap now says Phase 4.5 reconnects PPO/RL after Phase 4.
   - Target: Phase 4 produces a handoff table identifying the best current controller baseline, known failure modes and which logs should be reused for PPO comparison.
   - Acceptance: Phase 4.5 can cite the Phase 4 summary before adding PPO-generated references or 4D corrections.

## Boundaries

**In scope:**

- Controller-only evaluation using `workflows/play_controller.py`.
- Server Isaac runs for legacy, direct-state Koopman+MPC and eligible paper-lifted Koopman+MPC.
- Local metrics parsing from JSONL and solver diagnostics.
- Metrics JSON and Markdown summary.
- Isaac Sim/Lab runbook for Phase 4.
- Handoff baseline for PPO/RL integration in Phase 4.5.

**Out of scope:**

- PPO training or inference - Phase 4.5 owns PPO/RL reconnection.
- LLM planning or tuning - Phase 6 owns LLM supervision after Koopman-MPC PPO retraining.
- Online Kalman/RLS adaptation - Phase 6 owns online model adaptation.
- Changing thruster, hydrodynamics or USD assets - Phase 4 evaluates existing behavior.
- Replacing the MPC solver - Phase 4 may tune command-line weights for experiments only if explicitly recorded.
- Claiming final real-world performance - Phase 4 is Isaac simulation evidence.

## Constraints

- Local machine cannot run Isaac reliably; all Isaac rollouts run on the server.
- Phase 4 metrics tooling must run locally without importing Isaac, Omniverse or CUDA modules.
- JSONL logs must pass `workflows/validate_koopman_log.py` before metrics aggregation.
- Matched comparisons must use the same trajectory family and comparable `steps_per_action`, `max_goals`, `trajectory_cycles`, MPC horizon and MPC timeout.
- PWM bounds are hard safety constraints: all reported PWM values must stay in `[-1, 1]`.
- Quaternion attitude error calculations must respect `q` and `-q` equivalence.
- Phase 4 must preserve a controller-only baseline before PPO/LLM layers are added.

## Acceptance Criteria

- [x] A Phase 4 run matrix names every expected controller/trajectory JSONL artifact.
- [x] Server commands are documented for legacy, direct-state Koopman+MPC and eligible paper-lifted Koopman+MPC.
- [x] Every generated JSONL log is validated before being included in the summary.
- [x] Local metrics aggregation runs without Isaac imports.
- [x] Metrics report includes sample count, depth RMSE, attitude error, control energy, PWM smoothness, fallback rate, latency stats and bounded PWM status.
- [x] Report explicitly states whether paper-lifted was included in three-way comparison or treated as diagnostic/failure analysis.
- [x] Runbook documents server environment activation, run commands, validation commands and artifact copy-back.
- [x] Summary defines the Phase 4.5 PPO baseline and does not claim PPO or LLM integration.

## Ambiguity Report

| Dimension | Score | Min | Status | Notes |
|---|---:|---:|---|---|
| Goal Clarity | 0.90 | 0.75 | met | Controller-only comparison before PPO is explicit. |
| Boundary Clarity | 0.92 | 0.70 | met | PPO, LLM, online adaptation and solver replacement are out of scope. |
| Constraint Clarity | 0.84 | 0.65 | met | Server-only Isaac, local Isaac-free metrics and matched run constraints are stated. |
| Acceptance Criteria | 0.86 | 0.70 | met | Pass/fail checks cover logs, metrics, runbook and handoff. |
| **Ambiguity** | 0.12 | <= 0.20 | met | Auto-derived from roadmap, current code and prior Phase 3/3.5 artifacts. |

## Interview Log

| Round | Perspective | Question summary | Decision locked |
|---|---|---|---|
| 1 | Researcher | What exists today for Phase 4? | Legacy, direct-state MPC and paper-lifted MPC can be run through `play_controller.py`; unified metrics are missing. |
| 2 | Simplifier | What is the irreducible Phase 4 core? | Produce matched controller-only logs, metrics and runbook before PPO. |
| 3 | Boundary Keeper | What is not this phase? | PPO, LLM, online adaptation and solver replacement are deferred. |
| 4 | Failure Analyst | What would make Phase 4 misleading? | Mixing PPO with controller evaluation, using unmatched trajectories, or claiming paper superiority from smoke logs only. |

---

*Phase: 04-evaluation-documentation-and-isaac-sim-runbook*
*Spec created: 2026-07-02*
*Next step: create Phase 4 CONTEXT/RESEARCH/PLAN and then execute controller-only evaluation.*

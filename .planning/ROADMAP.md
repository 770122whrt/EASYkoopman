# Roadmap: EASYkoopman

## Milestones

- [x] **v1.0 Koopman-UUV Single-Configuration Control** - Phases 1 through 5.4, closed 2026-08-09. [Archive](milestones/v1.0-ROADMAP.md) | [Summary](reports/MILESTONE_SUMMARY-v1.0.md) | [Audit](milestones/v1.0-MILESTONE-AUDIT.md)

## Closed Phases

<details>
<summary>v1.0 Koopman-UUV Single-Configuration Control - SHIPPED AS RESEARCH BASELINE</summary>

- [x] Phase 1: Baseline Data And Controller Boundary
- [x] Phase 1.5: Isaac Lab 2.x Compatibility Migration
- [x] Phase 2: Offline Koopman Identification
- [x] Phase 2.5: Offline Koopman Model Qualification Gate
- [x] Phase 3: Koopman MPC Controller Integration
- [x] Phase 3.5: Paper-Style Lifted EDMD Backend Qualification
- [x] Phase 4: Controller-Only Evaluation And Isaac Runbook
- [x] Phase 4.5: PPO/RL Reference Adapter Integration
- [x] Phase 4.6: PPO Training Entrypoint And Checkpoint Evidence Gate
- [x] Phase 5: Koopman-MPC PPO Retraining Smoke
- [x] Phase 5.1: Koopman-MPC PPO Stability Training
- [x] Phase 5.2: Reward, Adapter And MPC Health Optimization
- [x] Phase 5.3: Cross-Combination PPO Health Screening
- [x] Phase 5.4: Dual-Track Reward/MPC Pareto Optimization

Final experimental status:

```text
Phase 5.4 selection_status = no_selection
single-configuration end-to-end pipeline = runnable
controller superiority = not established
deployment readiness = not established
```

</details>

## Current Planning Status

No active milestone or future phase plan is open.

Multi-configuration AUV involvement is the user-identified next direction, but this closeout deliberately does not define its requirements, phase numbering or implementation plan. Start it later through a separate milestone workflow.

## Deferred Context, Not An Active Roadmap

The following v1.0 findings may inform later planning but are not approved phases:

- configuration-aware asset, dynamics and actuator contracts;
- per-configuration versus shared Koopman model strategy;
- cross-configuration dataset splits and generalization gates;
- adapter/reference semantics diagnosis;
- fallback cost-margin diagnostics;
- online Koopman KF/RLS adaptation;
- final matched evidence across configurations;
- optional low-frequency LLM supervisor after the control core is qualified.

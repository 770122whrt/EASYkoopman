# EASYkoopman

## What This Is

EASYkoopman is an EasyUUV/Isaac research project for learning and controlling underwater-vehicle dynamics with Koopman models, model-predictive control and bounded higher-level supervisors.

Milestone v1.0 established the system on one EasyUUV configuration. Milestone v2.0 extends that evidence chain to multiple vehicle parameterizations and 4/6/8-thruster topologies, then adds environment-context estimation, guarded online Koopman updates and an auditable low-frequency Agent Supervisor.

## Core Value

Build control experiments whose model, checkpoint, controller path and evaluation evidence are explicit enough to reproduce, compare and reject safely.

## Current Milestone: v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control

**Goal:** Demonstrate whether one configuration-aware Koopman control architecture can transfer across the eight supported EasyUUV 2.0 configurations, adapt safely to environmental change and expose bounded decisions to an Agent Supervisor.

**Target features:**

- Qualified EasyUUV 2.0 configuration catalog with explicit thruster topology and controllable-degree-of-freedom metadata.
- Versioned cross-configuration data and control contract using fixed 4D virtual control before TAM allocation.
- Single-platform, pooled and conditional Koopman identification with held-out-configuration gates.
- Configuration-aware Koopman-MPC with masks, fallback and matched closed-loop evaluation.
- Environment-context estimation and rollback-protected RLS/KF online updates.
- Low-frequency Agent Supervisor that cannot directly command PWM or bypass safety gates.

## Requirements

### Validated

- ✓ A reproducible single-configuration JSONL → Koopman model → selected manifest → bounded MPC chain exists — v1.0.
- ✓ Legacy/S-Surface remains available as a matched baseline and fallback — v1.0.
- ✓ PPO integration, checkpoint provenance and evidence-level separation exist — v1.0.
- ✓ The eight CLI-supported EasyUUV 2.0 configurations have a provenance-bound package/catalog/topology contract and real Isaac server smoke evidence — Phase 6.

### Active

- [x] Import and qualify the eight CLI-supported EasyUUV 2.0 configurations without rewriting v1.0 evidence.
- [ ] Establish a topology-independent Koopman/data/control contract for 4, 6 and 8 thrusters.
- [ ] Measure held-out-configuration Koopman prediction and closed-loop transfer against explicit baselines.
- [ ] Estimate environment context and allow only bounded, reversible online model updates.
- [ ] Evaluate a low-frequency Agent Supervisor against no-supervisor and rule-supervisor baselines.
- [ ] Produce server-verifiable evidence with clear smoke, training, matched-evaluation and promotion levels.

### Out of Scope

- Sim2Real or hardware-success claims — v2.0 remains simulation research unless a later milestone adds hardware evidence.
- Eight distinct vehicle appearance/CAD assets — current configurations share one USD appearance and differ in dynamics or thruster topology.
- Direct PWM generation by PPO, Agent or LLM — all high-level decisions remain above bounded low-level control.
- End-to-end LLM control or an unrestricted autonomous agent — Phase 11 exposes only allow-listed low-frequency decisions.
- Immediate PPO retraining during Phase 6 intake — qualification precedes learning and controller integration.

## Current State

**Shipped research milestone:** `v1.0 Koopman-UUV Single-Configuration Control`

The implemented chain is:

```text
observation_9d
  -> RSL-RL PPO
  -> action_4d
  -> heuristic_reference_delta_v0
  -> reference_5d
  -> direct_state Koopman + bounded MPC
  -> PWM_8d
  -> EasyUUV Isaac physics
```

Validated in v1.0:

- Isaac Sim 5.0 + Isaac Lab 2.2.1 direct and PPO-integrated workflows;
- step/sine/irregular JSONL data collection;
- offline direct-state and paper-style lifted EDMD model tooling;
- selected-model manifest and prediction-quality gate;
- bounded 8D PWM Koopman-MPC with timeout/fallback diagnostics;
- controller-only matched evaluation;
- PPO adapter, retraining path and checkpoint provenance;
- stability, one-factor, cross-combination and 11-profile Pareto experiments;
- 175 local tests passing at milestone close.

The final Phase 5.4 selector returned `no_selection`. v1.0 therefore remains a reproducible research baseline rather than a performance-superiority or deployment release.

## Known Limitations

- Legacy/S-Surface remains the strongest nominal controller baseline.
- `heuristic_reference_delta_v0` is an explicit engineering assumption, not a lossless action-semantics migration.
- `no_cost_improvement` fallback needs cost-margin and prediction-error diagnosis.
- `paper_lifted_edmd` has large depth error and is research-only.
- Koopman models are trained offline and remain fixed online.
- Koopman performance evidence still covers the v1.0 single configuration; Phase 6 adds eight-configuration simulator qualification, not Koopman transfer evidence.
- No LLM runtime, Sim2Real, hardware deployment or broad 6-DOF claim exists.
- Several historical phases lack standard GSD verification artifacts; see the milestone audit.

## Milestone Transition

v1.0 is frozen at tag `v1.0`. v2.0 continues phase numbering at Phase 6 and treats the received `easyuuv_v2-main/` tree as a provenance-preserving simulator snapshot. Integration changes, archived server evidence and planning documents remain separate commits and push boundaries.

## Constraints That Remain Valid

- Isaac-dependent validation runs on the server; local development must retain Isaac-free tests where possible.
- PWM commands must stay in `[-1, 1]` and pass through the existing thruster/hydrodynamic plant.
- Legacy control must remain available as a matched baseline and fallback.
- PPO or a future LLM cannot silently bypass the low-level controller to command PWM.
- Model and checkpoint selection must be provenance-checked and fail closed.
- Claims must distinguish smoke, stable training, matched evaluation and performance promotion.
- Cross-configuration control uses `virtual_control_4 = [roll, pitch, yaw, depth]`; padded PWM is diagnostic data, not the default learned-control meaning.
- `uuv4*` yaw underactuation must be represented explicitly and cannot be scored as a feasible yaw-tracking target.
- Online model updates require bounded parameters, non-finite rejection, a frozen prior and rollback.
- Local work owns Isaac-free contracts and tests; server work owns Isaac physics rollout and matched evaluation.

## Key Decisions

| Decision | Rationale | Outcome |
|---|---|---|
| Preserve Isaac Lab `DirectRLEnv` and EasyUUV physics | Limit simultaneous migration and algorithm risk | Good |
| Build the data seam before EDMD/MPC | Identification needs reproducible transitions | Good |
| Split datasets by log, not row | Avoid temporal leakage | Good |
| Use selected manifests at runtime | Prevent stale or unsupported models entering control | Good |
| Keep direct-state engineering and paper-lifted comparison distinct | Avoid overstating paper alignment | Good |
| Optimize model-consistent 8D PWM in the first MPC | Match the identified control input | Good |
| Put PPO above Koopman-MPC through a versioned adapter | Preserve layered control architecture | Revisit adapter semantics |
| Reuse RSL-RL PPO | Focus effort on MDP and controller integration | Good |
| Add checkpoint provenance/evidence levels | Prevent relabeling and unsupported claims | Good |
| Close Phase 5.4 with `no_selection` | Preserve a valid negative result | Good |
| Defer online adaptation and LLM | Finish the core control evidence first | Still valid |
| Continue v2.0 at Phase 6 | Preserve the v1.0 historical phase identity | Good — Phase 6 verified |
| Use fixed 4D virtual control before TAM allocation | Give 4/6/8-thruster platforms one controller-facing meaning | Contract qualified; Phase 7 integration pending |
| Treat `uuv4*` yaw as explicitly unavailable | Avoid impossible tracking claims on underactuated configurations | Good — rank/mask and server smoke verified |
| Restrict Agent to an allow-listed low-frequency supervisor | Preserve deterministic low-level control and fail-closed behavior | Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**

1. Move verified active requirements to Validated with the phase reference.
2. Move invalidated requirements to Out of Scope with the reason.
3. Record new requirements and decisions without rewriting frozen v1.0 conclusions.
4. Re-check that the project description and core value still match the evidence.

**After each milestone:**

1. Audit every requirement against implementation and verification artifacts.
2. Re-check the core value and all explicit exclusions.
3. Update context, constraints and decision outcomes from measured results.

## Canonical Records

- `.planning/reports/MILESTONE_SUMMARY-v1.0.md`
- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- `docs/Agentic_AUV_project_handover.md`
- `docs/project_parameters_and_work_summary_2026_07_05.md`

---

*Last updated: 2026-08-11 after Phase 6 verification*

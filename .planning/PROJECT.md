# EASYkoopman

## What This Is

EASYkoopman is an EasyUUV/Isaac research project for learning and controlling underwater-vehicle dynamics with Koopman models, model-predictive control and a higher-level PPO policy.

Milestone v1.0 established the system on one EasyUUV configuration. It preserves the original thruster and hydrodynamic plant while adding data collection, offline Koopman identification, bounded MPC, PPO reference adaptation, checkpoint provenance and matched evaluation.

## Core Value

Build control experiments whose model, checkpoint, controller path and evaluation evidence are explicit enough to reproduce, compare and reject safely.

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
- Evidence covers one EasyUUV configuration only.
- No LLM runtime, Sim2Real, hardware deployment or broad 6-DOF claim exists.
- Several historical phases lack standard GSD verification artifacts; see the milestone audit.

## Next Milestone Status

No next milestone has been created. The user has identified multi-configuration AUV involvement as the likely next direction, but its scope, requirements and roadmap are intentionally left undefined by this closeout.

## Constraints That Remain Valid

- Isaac-dependent validation runs on the server; local development must retain Isaac-free tests where possible.
- PWM commands must stay in `[-1, 1]` and pass through the existing thruster/hydrodynamic plant.
- Legacy control must remain available as a matched baseline and fallback.
- PPO or a future LLM cannot silently bypass the low-level controller to command PWM.
- Model and checkpoint selection must be provenance-checked and fail closed.
- Claims must distinguish smoke, stable training, matched evaluation and performance promotion.

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

## Canonical Records

- `.planning/reports/MILESTONE_SUMMARY-v1.0.md`
- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- `docs/Agentic_AUV_project_handover.md`
- `docs/project_parameters_and_work_summary_2026_07_05.md`

---

*Last updated: 2026-08-09 after v1.0 milestone close*

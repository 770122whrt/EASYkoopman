---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Multi-Configuration Koopman Transfer and Environment-Aware Control
status: planning
last_updated: "2026-08-09T07:23:27.510Z"
last_activity: 2026-08-09 — v2.0 roadmap approved; Phase 6 ready for specification and planning
progress:
  total_phases: 7
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State: EASYkoopman

**Updated:** 2026-08-09
**Current focus:** Phase 6 — EasyUUV 2.0 Intake and Multi-Configuration Qualification
**Active milestone:** `v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control`
**Branch:** `v2.0-multi-configuration`

## Project Reference

See `.planning/PROJECT.md`.

**Core value:** Build control experiments whose model, checkpoint, controller path and evaluation evidence are explicit enough to reproduce, compare and reject safely.

## Current Position

Phase: 6 — EasyUUV 2.0 Intake and Multi-Configuration Qualification
Plan: —
Status: Ready for specification and planning
Last activity: 2026-08-09 — v2.0 roadmap approved

## Milestone Goal

Qualify the eight supported EasyUUV 2.0 configurations, establish a topology-independent Koopman control/data contract, then evaluate cross-configuration transfer, guarded environment adaptation and a bounded Agent Supervisor.

## Inherited v1.0 Baseline

v1.0 remains frozen at tag `v1.0`, covering Phase 1 through Phase 5.4. Its accepted closeout records are:

- `.planning/reports/MILESTONE_SUMMARY-v1.0.md`
- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- `.planning/MILESTONES.md`
- `.planning/RETROSPECTIVE.md`

Verified at v1.0 close:

```text
python -m pytest -q --basetemp .pytest-milestone-v1
175 passed

python -m compileall __init__.py easyuuv_env.py koopman workflows tests
passed
```

Server evidence accumulated during v1.0 includes:

- Isaac Sim 5.0 + Isaac Lab 2.2.1 direct-controller rollout;
- validated step/sine/irregular Koopman logs;
- Phase 2.5 direct-state model gate pass;
- Phase 3 bounded Koopman-MPC smoke;
- controller-only three-backend matched evaluation;
- Koopman-MPC-conditioned PPO checkpoint smoke;
- Phase 5.1 stable-training candidate;
- Phase 5.2 one-factor, Phase 5.3 cross-combination and Phase 5.4 Pareto experiments.

Frozen conclusions carried into v2.0:

- The single-configuration end-to-end control/retraining/evaluation chain runs.
- `direct_state` is the engineering Koopman backend for v1.0.
- `paper_lifted_edmd` is a research comparison and is not the default controller.
- Legacy/S-Surface remains the strongest nominal baseline.
- Phase 5.4 completed 11/11 sentinels and 11/11 matched candidates but selected no profile.
- Latency was not the primary Phase 5.4 bottleneck.
- Adapter/reference semantics and `no_cost_improvement` fallback are stronger hypotheses than further broad reward/MPC micro-tuning.
- No online Koopman learning or LLM runtime is present.

## Locked v2.0 Decisions

| Decision | State |
|---|---|
| Phase numbering | Continue at Phase 6; do not restore Phase 5.5/5.6. |
| New simulator source | Import `easyuuv_v2-main/` as an isolated received snapshot before integration changes. |
| Supported configurations | `base`, `long_body`, `heavy_moderate`, `asymmetric`, `uuv6`, `uuv6_angled`, `uuv4`, `uuv4_angled`. |
| Cross-configuration control | `virtual_control_4 = [roll, pitch, yaw, depth]` before TAM allocation. |
| Underactuation | `uuv4*` yaw is explicitly unavailable and excluded from feasible yaw tracking. |
| Online adaptation | RLS/KF only behind bounds, non-finite rejection, frozen prior and rollback. |
| Agent boundary | Low-frequency allow-listed supervisor; no direct PWM or real-time `env.step()` loop. |
| Evidence | Local contract tests and server Isaac evidence remain separate and level-labelled. |
| Promotion | `no_selection` is a valid outcome when no candidate passes every gate. |

## Git Delivery Boundaries

1. New EasyUUV 2.0 simulator snapshot.
2. v1.0 server experiment evidence plus an explicit manifest.
3. v2.0 PROJECT, REQUIREMENTS, ROADMAP, STATE, Phase 6 SPEC/PLAN and supporting design documents.

The design-review commit remains local until the clean delivery history is assembled. No remote force-push is planned.

## Open Planning Work

- Create the Phase 6 falsifiable specification.
- Research Phase 6 integration details and create checker-approved execution plans.
- Update `docs/Agentic_AUV_next_steps_plan.md` to match the canonical roadmap and push boundaries.

## Next Action

Run the Phase 6 spec and plan workflows. Do not modify the untracked simulator snapshot or experiment evidence during planning.

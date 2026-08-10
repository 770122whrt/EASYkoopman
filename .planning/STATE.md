---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Multi-Configuration Koopman Transfer and Environment-Aware Control
status: in_progress
last_updated: "2026-08-10T08:22:41.447Z"
last_activity: 2026-08-10 -- Wave 2 complete with independent validator audit fixes
progress:
  total_phases: 7
  completed_phases: 0
  total_plans: 4
  completed_plans: 3
  percent: 75
---

# Project State: EASYkoopman

**Updated:** 2026-08-10
**Current focus:** Phase 6 — EasyUUV 2.0 Intake and Multi-Configuration Qualification
**Active milestone:** `v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control`
**Branch:** `v2.0-multi-configuration`

## Project Reference

See `.planning/PROJECT.md`.

**Core value:** Build control experiments whose model, checkpoint, controller path and evaluation evidence are explicit enough to reproduce, compare and reject safely.

## Current Position

Phase: 6 — EasyUUV 2.0 Intake and Multi-Configuration Qualification
Plan: 06-03 complete — 3 of 4 plans
Status: In progress — Wave 2 complete; server checkpoint remains
Last activity: 2026-08-10 -- canonical catalog/TAM and strict qualification artifact gate verified locally

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

All three boundaries are visible on `origin/v2.0-multi-configuration`: simulator snapshot `7ba2499`, v1 evidence `7147379`, and planning head `c8b9c70`. Phase execution commits remain later local commits; no remote force-push was used.

## Planning Result

- Phase 6 SPEC ambiguity gate passed at `0.08` with QUAL-01..08 locked.
- Research and pattern mapping are complete.
- Four execution plans cover 8/8 QUAL requirements and 14/14 locked D-ID decisions.
- Wave 1 establishes package/provenance; Wave 2 runs catalog and validator TDD in parallel; Wave 3 blocks on actual eight-configuration Isaac evidence.
- Plan 06-01 completed with canonical `easyuuv_nc` packaging, package-confined USD lookup, a local `.venv` workflow and 21 passing package/v1 source-contract tests.
- Plan 06-02 completed with one exact eight-name catalog, an Isaac-free 8/6/4-thruster TAM report, explicit `uuv4*` yaw underactuation and snapshot-backed zero-drift proof.
- Plan 06-03 completed with a strict versioned artifact schema, exact-set/topology/safety/evidence gates and a deterministic CLI; independent audit added fixed-baseline, strict-mask-type and ordered-extrema gates, bringing the mutation suite to 55 passes.
- Wave 2 integration passes 84 tests across the catalog, artifact validator and existing v1 source contracts; compileall and `pip check` are clean, and importing the gate loads no Omni modules.
- A pure JSON artifact cannot authenticate where it was produced. The `server_pass` result proves schema/content conformance only until Plan 06-04 anchors it to the actual server runner, command log, pullback hash and blocking human checkpoint.

## Next Action

Execute `06-04-PLAN.md`: connect the catalog and validator to the Isaac runner/runbook, run the full local regression, then stop at the blocking eight-configuration server checkpoint. Preserve local-contract versus server-Isaac evidence labels; do not begin Phase 7 before Phase 6 server verification.

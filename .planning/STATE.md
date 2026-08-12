---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Multi-Configuration Koopman Transfer and Environment-Aware Control
status: executing
last_updated: "2026-08-12T09:29:12+08:00"
last_activity: 2026-08-12 -- Phase 7 Wave 2 runtime Bridge and dual-version data contracts completed and independently revalidated
progress:
  total_phases: 7
  completed_phases: 1
  total_plans: 8
  completed_plans: 7
  percent: 88
---

# Project State: EASYkoopman

**Updated:** 2026-08-12
**Current focus:** Phase 7 — Wave 3 local evidence chain before server execution
**Active milestone:** `v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control`
**Branch:** `v2.0-multi-configuration`

## Project Reference

See `.planning/PROJECT.md`.

**Core value:** Build control experiments whose model, checkpoint, controller path and evaluation evidence are explicit enough to reproduce, compare and reject safely.

## Current Position

Phase: 7 (Cross-Configuration Koopman Data and Control Contract) — EXECUTING
Plan: 07-01 through 07-03 complete — 3 of 4 Phase 7 plans
Status: Wave 2 verified — 07-04 local preflight ready
Last activity: 2026-08-12 -- 07-02 passed 208 Bridge/Phase 6 regressions; 07-03 passed 123 schema/data/v1 model-MPC regressions

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
- Plan 06-04 completed the deterministic Isaac runner, exact-eight merger, offline bundle/bootstrap, semantic process/log/row gates, strict provenance validator and staged pullback chain.
- The tested source commit `e24f76a` ran on the isolated server path `/root/EASYkoopman-phase6-v2`; `base` completed 64 steps and the other seven public configurations completed 8 steps each.
- The actual Isaac Sim 5.0 / Isaac Lab 2.2.1 artifact passed as `server_isaac_smoke` with 8/8 configurations, zero non-finite values, zero dimension mismatches and SHA-256 `6cb83fcb63fc7bd33ffcfa678d09f3e128fcf6f6380ee3b948541814421a1a92`.
- The 64-file server evidence package is isolated in commit `7670f66`; Phase 6 SUMMARY, SERVER-EVIDENCE and VERIFICATION provide the planning handoff.
- Phase 6 qualifies simulator/configuration behavior only. Koopman transfer, MPC integration, environment adaptation and Agent effectiveness remain Phase 7–12 work.
- Phase 7 SPEC ambiguity is `0.14`; it locks schema v2 field semantics, additive v1 isolation, actual post-actuator wrench, oracle/estimated context separation and a three-topology server completion gate.
- Phase 7 research and pattern mapping identify the exact control/dynamics capture points: explicit catalog-derived yaw mask before TAM, actual thruster wrench before environmental forces, and same-step fluid/efficiency caches.
- Four plans cover CONT-01..05 and D-01..16 with dependency graph `07-01 -> {07-02,07-03} -> 07-04`.
- Independent plan checking converged from five blocking findings to zero remaining issues. It corrected the per-episode fixture boundary, real Phase 6 script path, aggregate validator, executable full local preflight and resolved research questions.
- Phase 7 planning does not mark any CONT requirement complete and does not create or claim server evidence. Existing v1 `U=PWM_8` model/MPC defaults remain frozen.
- Plan 07-01 completed strict schema v2 transition/context validation, contiguous episode JSONL/manifest/hash and a pure-Python validator CLI through two explicit RED→GREEN cycles (`aba86e6`→`0bb631c`, `788f451`→`89491fa`).
- Independent Wave 1 rerun passed 179 tests with `.pytest-tmp/phase7-wave1-root`; the first unisolated rerun exposed only a Windows `%TEMP%` permission error before project code, which the planned repository-local basetemp resolved.
- Plan 07-02 added catalog-masked post-PID/pre-TAM virtual control, post-actuator thruster-only wrench, same-call fluid/efficiency telemetry and a one-step/one-token strict Bridge; independent serial rerun passed 208 tests and both mandatory key links.
- Plan 07-03 added immutable `U=virtual_control_4` DatasetV2 plus named diagnostics and a non-promoting v1 compatibility view; independent rerun passed 123 tests while frozen v1 model/MPC defaults remained 8D.

## Next Action

Execute the local portion of 07-04: implement the three-topology server runner, aggregate validator, offline transfer and pullback chain; run the complete local preflight and commit a clean tested HEAD before connecting to the already-started server.

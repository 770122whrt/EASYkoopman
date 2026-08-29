---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Multi-Configuration Koopman Transfer and Environment-Aware Control
status: executing
last_updated: "2026-08-29T14:40:03Z"
last_activity: 2026-08-29 -- Plan 08-04 completed with the approved exact-eight 96-episode real-server dataset and validated pullback
progress:
  total_phases: 7
  completed_phases: 2
  total_plans: 13
  completed_plans: 12
  percent: 92
---

# Project State: EASYkoopman

**Updated:** 2026-08-29
**Current focus:** Phase 08 — multi-configuration-koopman-identification-and-ood-gate
**Active milestone:** `v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control`
**Branch:** `v2.0-multi-configuration`

## Project Reference

See `.planning/PROJECT.md`.

**Core value:** Build control experiments whose model, checkpoint, controller path and evaluation evidence are explicit enough to reproduce, compare and reject safely.

## Current Position

Phase: 08 (multi-configuration-koopman-identification-and-ood-gate) — EXECUTING
Plan: 5 of 5
Status: Ready to execute
Last activity: 2026-08-29 -- Plan 08-04 completed; Plan 08-05 is next

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
- Plan 07-04 added the exact-three collector/merger/validator, full local preflight, offline bundle/bootstrap and staged pullback chain; final pre-transfer gates passed 222 Phase 7 tests and 559 full-suite tests with one Windows-only symlink skip.
- Tested source `a36689a` ran on the unchanged Isaac server in isolated `/root/EASYkoopman-phase7-v2`; `base`, `uuv6` and `uuv4` each produced 8 contiguous strict schema-v2 transitions.
- All three native/tee/semantic gates passed. `uuv4` recorded two nonzero raw-yaw probes and zero virtual-yaw leaks, confirming the catalog mask before TAM in the real runtime chain.
- The aggregate passed server and pullback validators with `warnings=[]`, source/runtime provenance matched, SHA-256 `2f07a6835f0b32fe0277fd819394580f261b6028dc3d07520e70b124e0758463`, and all 44 server-authored files passed the self-excluding relative-path inventory validator on server and pullback.
- Server evidence is isolated in commit `1c0a6ca`; `07-SERVER-EVIDENCE.md`, `07-04-SUMMARY.md` and `07-VERIFICATION.md` close CONT-01..05 without claiming Koopman prediction, OOD transfer or MPC effectiveness.
- Phase 8 SPEC now distinguishes persistence/simple-linear baselines, per-configuration/pooled/conditional regimes and the non-promoting expert role; its ambiguity score is `0.10`.
- An independent contract audit corrected transductive pilot leakage: pilot is collection-health-only, while every model-affecting decision is pre-registered or fold-local over exactly seven source configurations.
- Five plans cover KID-01..05 and D-01..23 in dependency order `08-01 -> 08-02 -> 08-03 -> 08-04 -> 08-05`, with one explicit D-23 user protocol approval before main-server collection.
- Phase 8 evidence uses external `qualification_level` envelopes without extending or relabelling the frozen Phase 7 transition `evidence_level` enum.
- Evaluation and terminal selection/no-selection use separate immutable roots; a selected final refit reruns the registered inner algorithm on all eight fit+validation roles only, while refit failure atomically yields `no_selection` with no model path.
- The approved plan set initially marked no KID requirement complete and created no success artifact. Phase 8 will close only after an independent goal-backward `08-VERIFICATION.md` passes KID-01..05.
- Plan 08-01 completed the additive Phase 8 evidence/protocol layer and fail-closed local/server/pullback chain without changing the frozen Phase 7 transition evidence enum.
- Real Isaac Sim 5.0 / Isaac Lab 2.2.1 pilot evidence contains exactly eight configurations, two episodes per configuration and 128 transitions per episode: 16 episodes, 16 manifests, 16 logs and 2048 strict rows.
- The pulled envelope passed both operational-policy and external-evidence validators with `warnings=[]`; resumed closeout passed 53 Phase 8 server-contract tests and the full suite as `638 passed, 1 skipped`.
- This is collection-health evidence only. KID-01..05, model quality, LOCO OOD transfer, selection and Koopman-MPC effectiveness remain unproven.
- Plan 08-02 added a local-contract-only immutable multi-episode inventory, exactly eight seven-source LOCO fold manifests, distinct non-promoting expert views and dynamic opened-byte leakage audits.
- Physical conditioning is identity-free and fold-local: each normalizer binds the exact seven source configurations, source episode hashes and feature schema hash; no global or held-out statistics are accepted.
- Independent closeout passed 55 focused tests, 210 Phase 8/schema/pilot tests and the full repository suite as `675 passed, 1 skipped`; both declared key links and protected paths passed.
- The 8x12 main role protocol remains `pending_d23`. No real main dataset or fitted model exists, so KID-01..05 remain incomplete.
- Plan 08-03 added one additive `ControlledEDMDV2` backend, state_11/control_4 persistence and simple-linear baselines, exact identity/kinematic observable schemas and fold-fitted platform-affine Kronecker conditioning.
- Recursive evaluation is episode-local at one-step/5/20/60/full horizons; official attitude is sign-invariant normalized SO(3) geodesic radians, with per-configuration, equal-macro and worst-configuration aggregates.
- Every synthetic fold decision evaluates the frozen 108-candidate local grid from exactly seven source configurations, records every opened episode/statistic and seals before held-out test access; only pooled/conditional result types are eligible.
- Independent closeout passed 396 broad tests plus one existing skip and the final full suite as `733 passed, 1 skipped`; compileall, standalone diff-check, key links, protected paths and forbidden-root absence passed.
- Plan 08-03 is `local_contract` only. Its policy fixture is not D-23 approval, no real main/evaluation/selection root exists and KID-01..05 remain incomplete.
- Plan 08-04 froze the explicitly approved D-23 role/action and analysis-policy hashes, then ran the exact protocol from tested source `a7e8198` in isolated `/root/EASYkoopman-phase8-main-v2` on the unchanged Isaac server.
- The successful server chain completed 8/8 native, tee and semantic gates and produced exactly 96 episode JSONL, 96 manifests, 96 logs, zero `.part` files and 49,152 transitions: each configuration has six fit, three validation and three test episodes of 512 transitions.
- The post-collection inventory, exact-eight LOCO split and external envelope were built only after the exact set completed. Server and local validators returned `phase8_external_evidence_valid`, 293 referenced files and `warnings=[]`; envelope SHA-256 is `46d02531457123f2a1dfda3b16159b359a6caff2d90b14283094a349647a1b04`.
- Random-staging pullback validated all 294 canonical files, exact protocol/source/runtime hashes and all process statuses before atomic promotion. Evidence is isolated in commit `98dbd76`, and Git text conversion is disabled only for that immutable dataset subtree.
- Three failed server attempts were preserved and never promoted or appended: missing non-interactive Conda activation, native 178-step timeout, and postprocessing hash contamination. The successful attempt used a fresh bundle/checkout/result root and completed with `bootstrap.exit=0`.
- Plan 08-04 proves exact-eight dataset and LOCO-split readiness only. No model has been fitted or selected and no held-out prediction, OOD transfer, MPC, environment-adaptation or Agentic claim is supported. KID-01 data and KID-02/03/05 prerequisites are ready, but formal KID completion remains pending 08-05 and independent verification.

## Next Action

Execute `08-05-PLAN.md`: run the one frozen exact-eight LOCO evaluation against the canonical 08-04 dataset. Machine-verify that each fold's primary model and all model-affecting choices are sealed before held-out test access; test outcomes may not alter fitting or candidate selection. Emit separate immutable evaluation and selection/no-selection roots, then perform independent goal-backward Phase 8 verification.

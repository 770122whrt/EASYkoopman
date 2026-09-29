---
phase: 08-multi-configuration-koopman-identification-and-ood-gate
plan: "05"
subsystem: exact-eight-loco-evaluation-and-terminal-gate
tags: [koopman, loco, pre-test-freeze, so3, no-selection, independent-verification]
requires:
  - phase: 08-multi-configuration-koopman-identification-and-ood-gate
    plan: "04"
    provides: approved D-23 protocols and immutable exact-eight server dataset
provides:
  - exact-eight source-only LOCO candidate selection and held-out evaluation
  - machine-enforced pre-test freeze and held-out test-access boundary
  - complete six-role one-step/5/20/60/full prediction evidence
  - independently verified pathless frozen no-selection terminal result
affects: [phase-9]
tech-stack:
  added: []
  patterns: [family-local-candidate-freeze, token-gated-heldout-access, reason-coded-role-failure, atomic-terminal-no-selection]
key-files:
  created:
    - koopman/evaluation_v2.py
    - workflows/select_koopman_v2.py
    - tests/test_phase8_ood_evaluation_contract.py
    - source/results/koopman_phase8_evaluation/
    - source/results/koopman_phase8_selection/
    - .planning/phases/08-multi-configuration-koopman-identification-and-ood-gate/08-OOD-EVALUATION.md
    - .planning/phases/08-multi-configuration-koopman-identification-and-ood-gate/08-VERIFICATION.md
  modified:
    - koopman/loco_v2.py
    - koopman/model_v2.py
    - koopman/platform_features_v2.py
    - koopman/protocol_v2.py
    - koopman/selection_v2.py
    - protocols/phase8/analysis_policy.json
    - workflows/run_koopman_v2_loco.py
    - tests/test_koopman_loco_v2.py
    - tests/test_koopman_platform_features_v2.py
    - tests/test_koopman_selection_v2.py
key-decisions:
  - "Six primary metrics independently participate in the robust relative source-score maximum, with no manual weights."
  - "Every pooled and conditional candidate is selected independently from seven source configurations and frozen before held-out test access."
  - "A failed required family remains present and reason-coded; it is never omitted, repaired from held-out outcomes or promoted by fallback."
  - "The frozen result is no_selection: pooled equals simple-linear and conditional is incomplete due three projection failures."
requirements-completed: [KID-01, KID-02, KID-03, KID-04, KID-05]
completed: 2026-08-30
---

# Phase 8 Plan 05: Exact-Eight LOCO Evaluation and Terminal Gate Summary

**Eight source-only LOCO folds completed with a machine-enforced pre-test freeze,
the immutable evaluation and terminal envelopes validated, and an independent
verifier accepted the scientifically valid negative result
`PASS_VALID_FROZEN_NO_SELECTION`.**

## Outcome

- All eight held-out configurations completed one frozen fold.
- Every fold selected/fitted/normalized from the other seven configurations only.
- Every freeze records `test_open_count_at_freeze=0` and
  `post_test_mutation_count=0`; no leakage or post-test retune was found.
- All six required roles exist in each fold with one-step, 5, 20, 60 and full
  evidence or a stable reason-coded failure.
- Pooled Koopman is numerically identical to simple linear on all official
  aggregates and does not satisfy the frozen improvement/bootstrap gates.
- Conditional Koopman fails closed on `heavy_moderate`, `uuv4` and
  `uuv4_angled` because of `quaternion_projection_limit`.
- The only terminal artifact is `no_selection`; `selected_family` and
  `selected_model_path` are null. No final refit was invoked.

This closes the Phase 8 research/evidence contract but does not provide a model
for Phase 9 Koopman-MPC.

## Task Commits

1. `7d88f00` — RED freeze and strict selector contracts.
2. `9e61631` — GREEN immutable pre-test freeze and strict selection.
3. `6333480` — D-23 robust relative six-metric source-score semantics.
4. `06344b6` — independent pooled/conditional candidate freeze.
5. `dffd098` — freeze-token requirement for held-out test access.
6. `8a42f35` — exact-eight evaluator and official leaf/aggregate evidence path.
7. `cdfe726` — preserve unavailable/failed source family as reason-coded evidence.
8. `c7ee70f` — batch source validation without numerical drift.
9. `a07f75d` — immutable canonical exact-eight evaluation evidence.
10. `983a6bb` — atomic terminal selection/no-selection publisher.
11. `39ed224` — frozen canonical `no_selection` evidence.
12. `b4797ed` — complete OOD evaluation report.

Verification and planning closeout are committed separately from implementation,
evaluation and terminal evidence.

## Frozen Evidence

| Artifact | SHA-256 / result |
|---|---|
| Role protocol | `499b79089a4bfb0769ce6a902ad676f09e9c64190069a0bf5b51cd76f1d6cf26` |
| Analysis policy | `0d95edaf3d2511a7b0ca0440698c5e22fff51881076422ecef1712fe23c1b401` |
| Dataset envelope | `46d02531457123f2a1dfda3b16159b359a6caff2d90b14283094a349647a1b04` |
| Evaluation envelope | `5c776002d4d849f8504badbfe00fe564a82b7107a05992b26469a8a2df1f4181` |
| Selection result | `a7585fb8acdcb3f0b3a55cb94ce7413070aa4ceea5f060d824aa5c12ce3e23a9` |
| Selection envelope | `5e30db3ce2889eafa8338a4537abaa2352974b106db3ed8e7781b40d88b3eba4` |
| Evaluation validation | 106 references, `phase8_external_evidence_valid`, `warnings=[]` |
| Terminal validation | qualification `no_selection`, 1 reference, valid, `warnings=[]` |

## Main Aggregate Result

Full-rollout equal-configuration macro, ordered as
`depth / linear velocity / angular velocity / SO(3) mean / SO(3) RMSE / SO(3) max`:

| Role | Full-rollout macro |
|---|---|
| persistence | `0.484308 / 0.088792 / 0.815882 / 1.10347 / 1.17156 / 1.75121` |
| simple linear | `0.548999 / 0.094032 / 0.746932 / 1.34336 / 1.43057 / 2.08663` |
| pooled Koopman | `0.548999 / 0.094032 / 0.746932 / 1.34336 / 1.43057 / 2.08663` |
| conditional Koopman | unavailable due required-fold failures |
| non-promoting held-out expert | `0.137724 / 0.076179 / 0.536121 / 1.23987 / 1.35483 / 2.07016` |

The expert is an upper-bound diagnostic and was never promotion eligible. The
complete one-step/5/20/60/full per-configuration, macro and worst-configuration
tables are in `08-OOD-EVALUATION.md`.

## Verification

- Targeted selector/evaluator suite: `20 passed`.
- Relevant selector/LOCO/metric regression: `58 passed`.
- Canonical evaluator implementation regression before the formal run:
  `73 passed`; the wider affected Phase 8 set previously passed `82 passed`.
- Compileall and native selector CLI help: pass.
- Independent verifier reran four Phase 8 evidence qualifications, an exact
  structural JSON audit, and the relevant selector/evaluator/LOCO/metric suite:
  `64 passed in 5.08s`.
- Independent terminal verdict: `PASS_VALID_FROZEN_NO_SELECTION`, 5/5 KID
  requirements verified.

The full repository suite and the 08-04 294-file hash sweep were not mechanically
repeated. The user's risk-driven instruction limited validation to changed 08-05
code/evidence and relevant regressions; all canonical envelopes were independently
revalidated.

## Real Bugs Fixed Before the Canonical Run

- Read-only descriptor containers were canonicalized before hashing.
- Candidate selection was separated by Koopman family instead of accidentally
  sharing one family's candidate.
- Held-out access now requires a token bound to the immutable freeze state.
- An unavailable conditional candidate remains explicit and cannot invalidate or
  silently replace the pooled family.
- Source validation rollouts were batched; a direct equivalence check measured
  maximum absolute delta `0.0`.

Two noncanonical staging attempts are preserved for audit. Both stopped before a
decision freeze and before held-out test access; neither is promotion evidence.

## Requirements and Threat Disposition

| Requirement/threat | Disposition |
|---|---|
| KID-01 | PASS: exact configuration/episode-isolated dataset and eight LOCO folds. |
| KID-02 | PASS: comparable complete-or-reason-coded six-role matrix. |
| KID-03 | PASS: one-step, 5/20/60/full held-out results and configuration-balanced aggregates. |
| KID-04 | PASS: sign-invariant normalized SO(3) geodesic radians and strict invalid handling. |
| KID-05 | PASS: provenance-checked atomic pathless `no_selection`. |
| Test leakage/post-test retune | No occurrence; source hashes and freeze/test counters pass in all folds. |
| Expert/diagnostic promotion | Structurally forbidden and not observed. |
| Incomplete family hidden by aggregation | Failed conditional roles remain explicit and force ineligibility. |
| Stale selected model on negative outcome | Impossible in the typed result and absent from the terminal root. |

## Deviations and Claim Boundary

No protocol deviation.

Phase 8 proves that the server-origin exact-eight dataset, source-only LOCO
selection, held-out evaluation and frozen promotion gate operate together. It
also rejects the tested pooled/conditional candidates under that gate. It does
not prove closed-loop Koopman-MPC, environment transfer, online adaptation,
Agentic behavior, Sim2Real or hardware validity.

No Phase 9 handoff model exists. Any later identification attempt must use a new
versioned experiment and must not rewrite or retune this frozen result.

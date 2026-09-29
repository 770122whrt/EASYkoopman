---
phase: 08-multi-configuration-koopman-identification-and-ood-gate
plan: "03"
subsystem: controlled-edmd-v2-local-core
tags: [koopman, controlled-edmd, loco, so3, heldout-sealing, local-contract]
requires:
  - phase: 08-multi-configuration-koopman-identification-and-ood-gate
    plan: "02"
    provides: immutable multi-episode inventory, typed exact-eight LOCO views and fold-local physical descriptors
provides:
  - one additive controlled-EDMD v2 backend for per-configuration, pooled and conditional regimes
  - v2 persistence and simple-linear baselines over state_11 plus virtual_control_4
  - episode-safe recursive rollouts with quaternion-correct SO(3) and configuration-balanced metrics
  - sealed seven-source fold decisions, six typed roles and non-promoting expert/reference diagnostics
affects: [08-04, 08-05, phase-9]
tech-stack:
  added: []
  patterns: [source-only-fold-decision, platform-affine-kronecker-design, episode-recursive-evaluation, role-derived-eligibility]
key-files:
  created:
    - koopman/preprocessing_v2.py
    - koopman/baselines_v2.py
    - koopman/model_v2.py
    - koopman/metrics_v2.py
    - koopman/loco_v2.py
    - workflows/run_koopman_v2_loco.py
    - tests/test_koopman_model_v2.py
    - tests/test_koopman_metrics_v2.py
    - tests/test_koopman_loco_v2.py
    - tests/fixtures/koopman_phase8_synthetic_system/known_controlled_system_v1.json
    - tests/fixtures/koopman_phase8_synthetic_system/analysis_policy_v1.json
  modified:
    - koopman/protocol_v2.py
key-decisions:
  - "Per-configuration, pooled and conditional are fitting regimes of one ControlledEDMDV2 backend; they are not separate algorithms."
  - "The eligible design is exactly state_11, virtual_control_4 and an optional fold-fitted physical descriptor with platform-affine Kronecker interactions."
  - "A fold decision is sealed from all and only seven source configurations before outer-test data can open; every episode/statistic access is recorded."
  - "Only pooled and conditional role-result types are eligible; expert and reference-conditioned results are structurally diagnostic-only."
  - "Official attitude error is normalized, sign-invariant SO(3) geodesic radians, and every rollout is recursive within one episode."
patterns-established:
  - "Decision/fit/test-open separation: post-test retuning and test-before-decision are stable fail-closed states."
  - "Hash-bound artifacts: preprocessing, observable schema, normalizers, model coefficients, policy, budget and fold decision all carry deterministic hashes."
requirements-completed: []
duration: 53 min
completed: 2026-08-24
---

# Phase 8 Plan 03: Controlled EDMD, SO(3) Metrics and Sealed LOCO Core Summary

**One additive controlled-EDMD v2 backend with exact platform-affine design, recursive episode-safe SO(3) evaluation, and eight synthetic seven-source decisions sealed before held-out access—all proven at `local_contract` only.**

## Performance

- **Duration:** 53 min
- **Started:** 2026-08-23T18:05:03Z
- **Completed:** 2026-08-23T18:58:00Z
- **Tasks:** 3
- **Files modified/created:** 12 implementation/test/fixture files, plus this summary and normal planning-state updates

## Accomplishments

- Added `ControlledEDMDV2` as the only v2 algorithmic backend. Per-configuration, pooled and conditional behavior is expressed through data/fold/conditioning arguments; persistence and simple-linear remain explicit baselines.
- Restricted every eligible fit/predict design to `state_11 + virtual_control_4` and, for conditional runs, a fold-fitted physical descriptor. The design order is exactly `[phi(x), u, p, kron(p, [phi(x), u])]` and exposes no configuration identity, reference, PWM, wrench or environment oracle.
- Added copy-on-preprocess quaternion sign alignment and deterministic provenance hashing without mutating input arrays.
- Added true recursive, episode-local rollouts for one-step, 5/20/60/full horizons. Official orientation is normalized sign-invariant SO(3) geodesic radians; invalid, projected, nonfinite and divergent outcomes are counted and reason-coded.
- Added per-configuration metrics plus equal-configuration macro and worst-configuration aggregates. Row-weighted results are diagnostic-only.
- Added a strict local `phase8-analysis-policy-v1` fixture, a deterministic 108-point candidate grid, exact seven-source decision sealing and typed six-role results. Outer test, expert fit/validation and optional reference diagnostics cannot affect the primary decision.
- Added a local CLI that binds inventory/split/policy/fold inputs to a fresh output root and atomically records their complete hashes. It contains no final-selection implementation.

## Task Commits

1. **Task 1 — controlled-EDMD v2, preprocessing and baselines**
   - `f0dda0c` — RED: failing exact model/preprocessing/baseline contracts (`koopman.baselines_v2` absent)
   - `686fc5d` — GREEN: controlled-EDMD v2, quaternion preprocessing, persistence/simple-linear baselines and hash-bound serialization
2. **Task 2 — recursive rollout and SO(3) metric semantics**
   - `9db4932` — RED: failing episode-safe metric contracts (`koopman.metrics_v2` absent)
   - `5709b4d` — GREEN: true recursive horizons, official SO(3) error, failure accounting and configuration-balanced aggregates
3. **Task 3 — sealed LOCO decisions and role isolation**
   - `68276c6` — RED: failing seven-source/policy/role contracts (`koopman.loco_v2` absent)
   - `7604888` — GREEN: strict analysis policy, candidate grid, fold state machine, six-role matrix and local CLI

Additional verified fix:

- `6bde49e` — expose the planned stable `fold_protocol_decision.json` artifact name without changing decision semantics

## Exact Versions and Dimensions

| Contract | Version / exact dimension |
|---|---|
| Controlled model | `phase8-controlled-edmd-v2` / state 11 / control 4 |
| Observable schema | `phase8-observable-schema-v1` |
| Identity observable | `identity_v1`: 12 features; pooled design width 16 |
| Kinematic observable | `auv_kinematic_v1`: 40 features; pooled design width 44 |
| Compact physical descriptor | `platform_physical_compact_v1`: 11 features |
| Core physical descriptor | `platform_physical_core_v1`: 19 features |
| Identity conditional widths | compact 203; core 339 |
| Kinematic conditional widths | compact 539; core 899 |
| Quaternion preprocessing | `phase8-quaternion-sign-preprocessor-v1` |
| Array normalization | `phase8-array-normalizer-v1` |
| Baselines | `phase8-koopman-baselines-v1` |
| Metric schema | `phase8-episode-metrics-v1` |
| Rollout policy | `phase8-rollout-analysis-policy-v1` |
| Analysis policy | `phase8-analysis-policy-v1` |
| Fold decision | `phase8-fold-protocol-decision-v1` / `fold_protocol_decision.json` |

Conditional width follows `b + p + p*b`, where base width `b = observable + 4` and physical dimension is `p`. The implementation and tests assert exact feature order, not only shape.

## Serialization and Fixture Hash Evidence

| Artifact | SHA-256 / binding |
|---|---|
| `known_controlled_system_v1.json` bytes | `fe0631b4fdbc90bd118ac2b88cd24ec8c5c5f484843bc8c03abb3af2ea981b68` |
| `analysis_policy_v1.json` bytes | `97a60e5e239bd30f5a52b8fb1b3c56052737502f6fb8aa0475d4428e06dd24e1` |
| Canonical parsed analysis policy | `fa75a5ba7855e26838aadc07500851c1d731efc2224590c2ebe29bd4420e1cab` |

Model round-trip tests bind and revalidate the observable-schema hash, preprocessing hash, input/target normalizer hashes, optional platform-normalizer hash, coefficient payload and final model hash. Wrong schema, changed coefficients, stale normalizer and fold-binding mutations fail closed instead of loading a semantically different model.

## Synthetic-System Results

- Identity controlled EDMD recovers the known 11-state/4-control system with maximum next-state error below `1e-9` and deterministic `solve` diagnostics at full rank 16.
- Rank-deficient fitting deterministically uses `pinv`; repeated fits produce byte-identical coefficient arrays.
- The seven-source conditional fixture recovers its physical-control interaction below `1e-8` without configuration identity.
- Quaternion preprocessing proves `q`/`-q` equivalence, input immutability and reproducible hashes. Invalid/nonfinite/zero-norm quaternions fail with stable reasons.
- Rollout tests prove each horizon recurses from one true initial state, never teacher-forces, never crosses episode boundaries and reports 5/20/60/full results only when that episode supports them.
- Equal-configuration macro and worst-configuration tests deliberately use unequal row counts and a weak configuration; neither aggregate can hide the weak configuration through row weighting.

## Fold Access Evidence

The synthetic inventory contains one fit, one validation and one test episode for each of the eight public configurations. For every one of the eight complementary folds:

- the decision view opens exactly 14 fit/validation episode artifacts from exactly seven source configurations;
- opened episode IDs and transition hashes equal the fold manifest exactly;
- 108 policy candidates are evaluated under one metric/budget contract, producing 756 source-statistic access records per fold;
- the deterministic preferred test candidate is prefix 4, `identity_v1`, ridge `1e-8`, normalization `none`, compact physical schema, with design rank/width 203;
- the decision records seven source configurations/hashes, rank, width, condition number, source macro/worst values, numeric gates and policy/budget/metric/normalizer hashes;
- `test_open_count_at_seal` is zero and all eight decision hashes are unique;
- test-before-decision, post-test retune, held-out statistic access, different budget, policy drift, stale normalizer and wrong model binding fail with stable nonzero reasons.

## Role and Eligibility Matrix

| Role | Backend/regime | Result namespace | Eligible |
|---|---|---|---|
| Persistence | v2 baseline | primary diagnostic | No |
| Simple linear | v2 baseline | primary diagnostic | No |
| Source per-configuration | `ControlledEDMDV2`, per-source regime | ID diagnostic | No |
| Pooled | `ControlledEDMDV2`, pooled regime | primary | Yes |
| Conditional | `ControlledEDMDV2`, platform-affine regime | primary | Yes |
| Held-out expert upper bound | `ControlledEDMDV2`, held-out fit/validation only | expert diagnostic | No |
| Optional reference-conditioned | diagnostic model only | `diagnostic/reference_conditioned_v2` | No |

Eligibility is enforced by result type plus role enum. Constructing an expert as eligible fails `expert_promotion_forbidden`; constructing reference diagnostic as eligible fails `reference_diagnostic_not_eligible`. Every ordinary role result is either success or a reason-coded failure under the same policy, budget, metric and sealed decision hashes.

## Verification

- All three RED gates failed for their intended missing module before implementation.
- Task 1 focused suite: `32 passed`; adjacent v1 EDMD/baseline/runtime/MPC suite: `17 passed`.
- Task 2 focused suite: `23 passed`; combined model/metric suite: `44 passed`.
- Task 3 focused GREEN suite: `58 passed`; adjacent LOCO/model/metrics/platform/split suite: `83 passed`.
- Post-fix LOCO suite: `14 passed`.
- Broad Phase 7/8/v2/v1-compatibility matrix: `396 passed, 1 skipped`.
- Final full repository suite from final implementation HEAD: `733 passed, 1 skipped` in 251.46 seconds. The existing environment-dependent skip is outside the new 08-03 contract tests.
- `.venv\Scripts\python.exe -m compileall -q koopman workflows tests`: passed.
- Standalone `git diff --check`: passed; its only output is the pre-existing unrelated `.gitignore` CRLF warning.
- Both declared key links resolve: `LOCOFoldManifestV2` in `loco_v2.py` and `PlatformFeatureNormalizerV2` in `model_v2.py`; the stable `fold_protocol_decision` key also resolves.
- Protected diff from pre-plan `f83aff7` over v1 model/EDMD/baseline/lifting/evaluation/sweep/selection/MPC/normalization/schema files and Phase 7/Phase 8 pilot evidence roots: empty.
- `source/results/koopman_phase8_main`, `source/results/koopman_phase8_evaluation` and `source/results/koopman_phase8_selection` are absent; no `source/results` file changed.
- Unrelated user-owned `.gitignore` and untracked `AGENTS.md` remained untouched and uncommitted.

## Decisions Made

- Keep role semantics orthogonal to the algorithm implementation. One controlled backend plus two baselines is sufficient for all six required roles.
- Make held-out access a state transition, not a caller convention: an outer test loader is unavailable until the decision object exists, and any later decision attempt fails.
- Keep the 08-03 analysis policy explicitly `local_fixture_only_not_d23`; the user-approved canonical policy remains 08-04 work.
- Restrict the CLI to fresh local run-contract binding and fold scoping. It records complete input hashes but deliberately does not add final promotion logic.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Made the local workflow directly executable**
- **Found during:** Task 3 first GREEN run
- **Issue:** running `python workflows/run_koopman_v2_loco.py --help` placed `workflows/` rather than the repository root on `sys.path`, so importing `koopman` failed.
- **Fix:** adopted the existing workflow pattern that inserts the resolved project root before repository imports.
- **Verification:** second GREEN run `58 passed`; adjacent suite `83 passed`; final full suite `733 passed, 1 skipped`.
- **Committed in:** `7604888`

**2. [Rule 2 - Missing Critical Functionality] Exposed the planned stable decision artifact name**
- **Found during:** plan-level key-link verification
- **Issue:** atomic decision writing existed, but the source did not expose the required stable `fold_protocol_decision` artifact name.
- **Fix:** added versioned `FOLD_PROTOCOL_DECISION_FILENAME_V1 = "fold_protocol_decision.json"` without altering hashes or state-machine behavior.
- **Verification:** post-fix LOCO suite `14 passed`, key-link grep passed and final full suite remained green.
- **Committed in:** `6bde49e`

**Total deviations:** 2 auto-fixed (1 blocking direct-execution issue, 1 missing artifact-name contract). **Impact:** both fixes complete planned interfaces without expanding the modeling or scientific claim.

## Issues Encountered

- `gsd-sdk` was not installed under repository `node_modules` and was not available on `PATH`; planning state was updated directly and minimally, matching the 08-02 fallback.
- One initially requested adjacent-test filename did not exist; the command was corrected to the repository's actual split/platform test files before recording any result.
- No unresolved implementation or validation issue remains.

## Known Stubs

None. The plan-touched source/test/fixture files contain no TODO, FIXME, placeholder, coming-soon or not-available implementation stub. Empty collections are local accumulators; `None` metric values are explicit reason-coded failed/unsupported horizon results, not UI placeholders.

## Threat Dispositions

| Threat | Disposition and evidence |
|---|---|
| Forbidden v1/PWM/reference/diagnostic input enters eligible design | Mitigated by exact design signatures, forbidden-input policy mutation tests and v1 protected diff |
| Platform identity or held-out-normalizer leakage | Mitigated by physical-only descriptor schemas, exact source-fold normalizer binding and stale-normalizer mutations |
| Outer-test influence or post-test refit | Mitigated by separate sealed state transitions, dynamic open/statistic audit and post-test-retune rejection |
| Teacher forcing, episode crossing or quaternion-component attitude claim | Mitigated by recursive episode objects, horizon/property tests and normalized sign-invariant SO(3) radians |
| Expert/reference promotion | Mitigated by enum-derived typed results and negative construction tests |

No unplanned network endpoint, authentication path, external file boundary or schema trust boundary was introduced. The only new file I/O is the planned bounded local policy/inventory/split input and fresh atomic output contract.

## Claim Boundary

This plan proves implementation contracts and synthetic/local behavior only. The known system, eight folds, analysis policy and role outcomes are `local_contract` fixtures; they are not main-experiment data, not D-23 approval and not production/OOD evidence. No real Phase 8 main dataset was opened or collected, no canonical evaluation or promotion root exists, and no empirical winner, OOD transfer, MPC or Phase 9 closed-loop claim is supported. `KID-02`, `KID-03` and `KID-04` therefore remain formally incomplete pending the approved policy, real main collection and one-shot evaluation in later plans.

## Next Phase Readiness

- 08-04 can replace the local fixture with the user-approved canonical analysis/collection policy while reusing the strict parser and source-only candidate grid.
- 08-05 can bind real inventory/split artifacts to the sealed fold state machine, execute identical-role budgets and open each held-out test only after decision sealing.
- Any later promotion must consume only pooled/conditional eligible result types; expert/reference results remain diagnostic by construction.

## Self-Check: PASSED

- Verified all 12 implementation/test/fixture files exist and all seven RED/GREEN/fix commits are present in Git history.
- Reran focused, adjacent, broad and final full repository suites from the final implementation state.
- Verified exact versions/dimensions, candidate count/policy hash, key links, standalone diff-check, compileall, v1/protected paths and absence of forbidden canonical roots.
- Verified no generated/untracked plan output remains; only the explicitly out-of-scope user-owned `.gitignore` and `AGENTS.md` are dirty.

---
*Phase: 08-multi-configuration-koopman-identification-and-ood-gate*
*Completed: 2026-08-24*

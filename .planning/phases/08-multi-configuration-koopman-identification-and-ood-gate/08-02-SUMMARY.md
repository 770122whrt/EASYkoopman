---
phase: 08-multi-configuration-koopman-identification-and-ood-gate
plan: "02"
subsystem: identification-data-isolation
tags: [koopman, exact-eight, loco, leakage-audit, physical-features, local-contract]
requires:
  - phase: 08-multi-configuration-koopman-identification-and-ood-gate
    plan: "01"
    provides: additive Phase 8 evidence vocabulary and collection-health-only exact-eight pilot
provides:
  - immutable multi-episode collection and actual-byte dataset inventory
  - pending-D23 exact 8x12 whole-episode main role proposal
  - exactly eight complementary seven-source LOCO manifests and dynamic opened-artifact audit
  - non-convertible expert namespace and fold-local physical feature normalizer
affects: [08-03, 08-04, 08-05, phase-9]
tech-stack:
  added: []
  patterns: [precollection-intent-versus-postcollection-fact, sealed-heldout-access, source-fold-normalizer]
key-files:
  created:
    - koopman/collection_v2.py
    - koopman/splits_v2.py
    - koopman/platform_features_v2.py
    - workflows/build_koopman_v2_inventory.py
    - workflows/build_koopman_v2_splits.py
    - tests/test_koopman_collection_v2.py
    - tests/test_koopman_splits_v2.py
    - tests/test_koopman_platform_features_v2.py
    - tests/fixtures/koopman_phase8_multi_episode/
  modified:
    - koopman/protocol_v2.py
key-decisions:
  - "Primary fold decisions are derived from inventory/protocol IDs and expose exactly seven source configurations; no caller path list is accepted."
  - "Held-out fit/validation lives only in a distinct non-promoting expert type; primary decisions retain only sealed held-out test IDs and digest."
  - "Platform conditioning uses versioned physical facts only, with one normalizer artifact per exact source fold and no global statistics."
patterns-established:
  - "Whole-episode source of truth: concatenated rows are available only through a view that returns explicit episode boundaries."
  - "Opened-byte proof: every primary open records episode ID, configuration and transition hash for exact-set validation."
requirements-completed: []
duration: 52 min
completed: 2026-08-24
---

# Phase 8 Plan 02: Multi-Episode Inventory, Exact-Eight LOCO and Physical Features Summary

**Immutable whole-episode inventories, eight seven-source LOCO folds with dynamic byte-access proof, and identity-free fold-local platform conditioning—all at `local_contract` only.**

## Performance

- **Duration:** 52 min
- **Started:** 2026-08-23T17:09:38Z
- **Completed:** 2026-08-23T18:01:08Z
- **Tasks:** 3
- **Files modified/created:** 28

## Accomplishments

- Added a tuple/index-based `KoopmanDatasetCollectionV2` that retains nine fixture episode objects and requires explicit boundary metadata for any row view.
- Added `phase8-dataset-inventory-v1`, built only from an exact actual-byte set after collection and bound to role intent, source/runtime/envelope provenance, record invariants and aggregate hash.
- Added the pending-D23 `phase8-main-role-protocol-v1` proposal: eight configurations, twelve 512-transition episodes each, roles 6 fit / 3 validation / 3 test, and three role-separated excitation families.
- Derived exactly eight LOCO folds. Each primary decision view contains 63 fit/validation episodes from the complementary seven configurations; each held-out configuration contributes three sealed outer-test IDs, while its nine fit/validation episodes exist only in the non-promoting expert namespace.
- Added two physical-only descriptor schemas and a per-fold normalizer that binds the exact seven source configurations, source episode hashes and feature schema hash.

## Task Commits

1. **Task 1 — immutable collection and actual-byte inventory**
   - `76efef2` — RED: failing multi-episode inventory contracts
   - `cdfdfbc` — GREEN: immutable collection, inventory and atomic CLI
2. **Task 2 — exact-eight roles, LOCO and opened-artifact audit**
   - `f51fe2b` — RED: failing exact-eight LOCO contracts
   - `e5e2241` — GREEN: main role proposal, eight folds, typed views and audited loader
3. **Task 3 — physical descriptors and fold-local normalizer**
   - `8f45f1a` — RED: failing physical platform feature contracts
   - `7912c15` — GREEN: identity-free schemas, descriptors and normalizer provenance

Additional verified fixes:

- `bfa2a6d` — preserve standalone 08-01 pilot protocol validation through a lazy main-role adapter import
- `86add70` — RED regression for relative inventory roots
- `f8db5cc` — normalize confined relative scan roots
- `de73df9` — exercise symlink rejection even when Windows cannot create a real symlink
- `2776a40` — remove trailing blank lines found by an independent `git diff --check`

## Fixture and Inventory Hashes

The one-time fixture generator used `KoopmanEpisodeLoggerV2` and was deleted before the RED commit. All nine transition/manifest pairs validate as `local_contract`; no fixture is promotion-eligible.

| Fixture fact | SHA-256 |
|---|---|
| Complete 19-file fixture tree | `9122d6646759ca359da056b52d1cc322f466d07f2ae26bfcbcb66557c7c97826` |
| `role_intent.json` | `6ea1cc2b48c11b72bf2c04076e80aa5938739fc8ad03c3aae432f28323ca8053` |
| Actual-byte local inventory | `59221fecd47bc96b6bb71ee3e502950af67c36e7c9fd1fc5d67695b3841ab870` |
| Main protocol local test vector | `635c7646a82f82da954f95a3d74deb5b881805ab6a31865ca27ddd1c5942edd6` |
| Exact-eight LOCO local test vector | `163fb1b53d8b54a06a2cb790d3831704155c893de45132383351506685b3aede` |

| Episode JSONL | SHA-256 |
|---|---|
| `base/fit` | `12fbdb25a810ba4cd689cc0d4e785932baac7471a63c77a2f9ac31edec2099ab` |
| `base/validation` | `a7350164f88e18cf7ce2ec621553e1f0bd9a4217e208958d06465d77b577081b` |
| `base/test` | `823e092bdae3c992cbf5b7a3aea769f5a547428a9477bb5d6fed4f084b249349` |
| `uuv6/fit` | `8cc78e003a859605da49946ed7fed78c4e4780c98d79ab08d28c3757e52a1999` |
| `uuv6/validation` | `58b559563516015acc8dd15df216b825d489e0ec9b10c0d31882cfb48e1ac401` |
| `uuv6/test` | `67dbae965f3995e33573e0fbcb21190fd26b0ab8087017278badb3d32a734aeb` |
| `uuv4/fit` | `793097491f6892ffeb0e3cdbde6d5ad0f23bab0372716c27b1f31454a80ef472` |
| `uuv4/validation` | `e69ca97d9cc43a78da1c3a4816078eb516ebb82b097ef7566da9e55446199d28` |
| `uuv4/test` | `eee4c50fc1a95dec22bdfe7b7f59984fc2a22212f084bff8d2b0e17287375462` |

## Exact Fold Sets

| Holdout | Exact primary source configurations |
|---|---|
| `base` | `long_body, heavy_moderate, asymmetric, uuv6, uuv6_angled, uuv4, uuv4_angled` |
| `long_body` | `base, heavy_moderate, asymmetric, uuv6, uuv6_angled, uuv4, uuv4_angled` |
| `heavy_moderate` | `base, long_body, asymmetric, uuv6, uuv6_angled, uuv4, uuv4_angled` |
| `asymmetric` | `base, long_body, heavy_moderate, uuv6, uuv6_angled, uuv4, uuv4_angled` |
| `uuv6` | `base, long_body, heavy_moderate, asymmetric, uuv6_angled, uuv4, uuv4_angled` |
| `uuv6_angled` | `base, long_body, heavy_moderate, asymmetric, uuv6, uuv4, uuv4_angled` |
| `uuv4` | `base, long_body, heavy_moderate, asymmetric, uuv6, uuv6_angled, uuv4_angled` |
| `uuv4_angled` | `base, long_body, heavy_moderate, asymmetric, uuv6, uuv6_angled, uuv4` |

For every fold, primary decision input is `7 × (6 fit + 3 validation) = 63` complete episodes. Held-out primary outer test is three complete test episodes. Expert decision input is the held-out configuration's six fit plus three validation episodes, with the same three held-out test episodes in a separate namespace.

## Leakage Evidence

- Structural validation recomputes all episode/configuration/role sets from protocol plus inventory; no API accepts arbitrary caller path lists.
- The dynamic recording opener captures every opened episode ID, configuration and transition hash. The expected audit is exactly 63 source opens, seven source configurations and zero held-out fit/validation/test opens during primary decision construction.
- A forged primary source ID referencing held-out fit data fails as `heldout_design_leakage` before the opener is invoked.
- Row-level fields, episode overlap, role edits, missing/extra configurations, unequal matrices, pilot/main ID reuse, order/hash drift and timestamp inversion all have stable fail-closed reasons.
- Path escape, symlink, stale/extra files, modified bytes, record-count drift and invariant drift are rejected before inventory/collection eligibility.
- `server_isaac_smoke`, `server_isaac_identification_pilot` and `local_contract` all fail the main-dataset qualification gate.

## Physical Feature Schema and Provenance

| Schema | Dimension | SHA-256 | Content |
|---|---:|---|---|
| `platform_physical_core_v1` | 19 | `72cb7e327740a989bb5169ab60260b728234c4ed4c5c7dd3ce006dcff6633227` | log mass/volume/inertia/drag/time constant; COM-CBO offset; normalized count/rank; control mask; fixed allocation-mode descriptor |
| `platform_physical_compact_v1` | 11 | `98ce9b2e9a9546a54fd201547038f6cad73d3f814a2b406166c7b72c39e5981a` | log mass/volume; normalized count/rank; control mask; fixed allocation-mode descriptor |

Feature-schema selection is separate from extraction. Configuration is retained only on the descriptor as provenance and is absent from feature names/values. Schema construction rejects configuration name/identity/one-hot/hash fields. Every normalizer records fold ID, holdout, exact seven source configurations, exact source episode hashes, feature schema/hash, mean/scale, deterministic `unit_scale` handling and its own canonical hash. A frozen schema/normalizer can transform all eight declared physical platforms, but cannot be reused for a different fold.

## Verification

- RED gates failed for the intended missing modules/symbols before each GREEN implementation.
- Final focused data/split/feature suite: `55 passed`.
- Broader Phase 8/schema/pilot regression matrix independently rerun as `210 passed` with no skip.
- Full repository suite independently rerun as `675 passed, 1 skipped`; the single skip is the existing Windows symlink capability case outside the host-independent 08-02 mutation path.
- `python -m compileall koopman workflows tests`: passed.
- Protected diff from pre-plan `1781660` over `koopman/model.py`, `koopman/mpc.py`, `koopman/normalization.py`, `koopman/schema_v2.py` and all `source/results/`: empty.
- Only the pre-existing `source/results/koopman_phase8_pilot` root exists; no main/evaluation/selection success root was created.

## Decisions Made

- Keep actual artifact paths in the immutable inventory and keep LOCO fold manifests path-free; consumers resolve entries through inventory IDs only.
- Represent primary and expert views with distinct frozen classes. The expert type has no conversion API and fails `require_primary_view_v2` as `expert_promotion_forbidden`.
- Fit physical normalization with one equal-weight descriptor per exact source configuration and bind every source episode hash used by the fold.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserved standalone pilot protocol validation**
- **Found during:** plan-level broader regression
- **Issue:** the new main-role adapter imported `collection_v2` at module import time, breaking the minimal copied 08-01 pilot validator closure.
- **Fix:** moved the adapter dependency behind `TYPE_CHECKING` and a function-local import.
- **Verification:** 12/12 pullback dynamic mutation/promotion tests and the final 213-test matrix passed.
- **Committed in:** `bfa2a6d`

**2. [Rule 1 - Bug] Normalized relative inventory roots**
- **Found during:** summary hash reproduction through the public builder form
- **Issue:** a relative root mixed relative scanned paths with an absolute resolved root and raised before validation.
- **Fix:** normalize scanned candidates to confined absolute paths without resolving away symlink identity.
- **Verification:** RED `86add70`, GREEN `f8db5cc`, then 29/29 collection+dataset and 213/213 broader tests passed.

**3. [Rule 3 - Blocking] Made symlink mutation host-independent**
- **Found during:** first broader Windows run
- **Issue:** this host could not create an unprivileged file symlink, so the real-symlink mutation was skipped.
- **Fix:** retain the real symlink path when available and instrument `Path.is_symlink` only when Windows privilege blocks creation.
- **Verification:** final focused and 213-test matrices ran with no skip.
- **Committed in:** `de73df9`

**4. [Rule 1 - Formatting] Made the plan-wide diff gate truthful**
- **Found during:** independent orchestrator closeout
- **Issue:** a compound shell command masked `git diff --check` output for three trailing blank lines even though the final subcommand exited zero.
- **Fix:** removed only the trailing blank lines and reran `git diff --check` as a standalone blocking command.
- **Verification:** focused `55 passed`, broad `210 passed`, full `675 passed, 1 skipped`.
- **Committed in:** `2776a40`

**Total deviations:** 4 auto-fixed (2 bugs, 1 blocking test-environment issue, 1 formatting-gate issue). **Impact:** all fixes preserve the planned API and strengthen compatibility/path evidence without expanding the scientific claim.

## Issues Encountered

- `gsd-sdk` was not installed in the repository and was not available on `PATH`; plan tracking was updated directly and minimally in the checked-in planning files.
- No unresolved implementation or validation issue remains.

## Known Stubs

None. The plan-touched source/test files contain no TODO, FIXME, placeholder, coming-soon or not-available stub. `pending_d23` is an intentional non-approved protocol state, not an implementation stub.

## Claim Boundary

This plan proves local schemas, immutable inventory/split behavior, dynamic access-leakage gates and physical feature provenance only. The 8x12 protocol and exact-eight split hashes above are deterministic local test vectors, not an approved or collected main experiment. No real main dataset exists, no model was fitted, and no Koopman prediction, OOD transfer, selection, MPC or closed-loop claim is supported. `KID-01` and `KID-02` therefore remain incomplete.

## Next Phase Readiness

- 08-03 can consume only typed primary seven-source views and fold-bound physical descriptors/normalizers.
- The main 8x12 role proposal remains `pending_d23`; approval and real collection belong to 08-04.
- Phase 8 remains executing, with no promotion artifact and no requirement completion update.

## Self-Check: PASSED

- Verified all created source, workflow, test and fixture paths exist and all eleven RED/GREEN/fix/style commits are in history.
- Independently reran the focused, broad and full repository suites from the current HEAD.
- Verified both declared cross-plan key links, standalone diff-check, compileall, protected paths and absence of main/evaluation/selection canonical roots.
- Recomputed the locked fixture tree through its public test contract and confirmed all fixtures remain `local_contract` and non-promoting.

---
*Phase: 08-multi-configuration-koopman-identification-and-ood-gate*
*Completed: 2026-08-24*

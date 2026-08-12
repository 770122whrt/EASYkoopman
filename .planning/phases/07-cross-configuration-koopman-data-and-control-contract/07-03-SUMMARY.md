---
phase: 07-cross-configuration-koopman-data-and-control-contract
plan: "03"
subsystem: data-access
tags: [koopman, dataset-v2, virtual-control, v1-compatibility, immutable-data]

requires:
  - phase: 07-cross-configuration-koopman-data-and-control-contract
    plan: "01"
    provides: strict transition/episode/manifest schema-v2 validation
provides:
  - immutable KoopmanDatasetV2 whose model-facing U is exclusively virtual_control_4
  - named actuator diagnostics separated from learned control
  - strict local-contract fixtures for 8/6/4-thruster topology episodes
  - explicit read-only V1CompatibilityView with false v2 training eligibility
affects: [phase-08-identification, phase-09-mpc-migration, 07-04-server-evidence]

tech-stack:
  added: []
  patterns: [strict artifact-to-array conversion, read-only NumPy storage, recursively frozen metadata, non-promoting compatibility view]

key-files:
  created:
    - koopman/dataset_v2.py
    - koopman/v1_compatibility.py
    - tests/test_koopman_dataset_v2.py
    - tests/test_koopman_v1_compatibility.py
    - tests/fixtures/koopman_v2_three_topologies/
  modified: []

key-decisions:
  - "KoopmanDatasetV2.U is an identity property over read-only virtual_control_4 with exact width 4; no action/control/PWM alias exists."
  - "Padded PWM, mask, applied wrench, saturation ratio and energy proxy exist only under ActuatorDiagnostics."
  - "V1CompatibilityView delegates validation to load_koopman_samples, preserves v1 field names and exposes no to_v2, promotion, writer or inference path."
  - "Three topology fixtures are separate immutable local_contract episodes; they are not combined into one episode or labelled server evidence."

patterns-established:
  - "Model-facing arrays are copied to canonical NumPy dtypes and set write-protected; nested context/provenance is recursively frozen."
  - "Legacy evidence is readable through a named compatibility boundary whose eligibility check always fails closed."

requirements-completed: [CONT-02, CONT-03, CONT-05]

duration: 12 min
completed: 2026-08-12
---

# Phase 07 Plan 03: Dataset v2 and Explicit v1 Compatibility Summary

**A strict immutable DatasetV2 now exposes universal 4D virtual control while actuator diagnostics remain named and separate, and v1 PWM8 evidence stays readable only through an explicitly ineligible non-promoting compatibility view.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-08-12T01:14:00Z
- **Completed:** 2026-08-12T01:25:36Z
- **Tasks:** 3/3
- **Files modified:** 11 created, 0 existing production files modified
- **Task 1 tests:** 15 passed
- **Task 2 target tests:** 19 passed
- **Full plan regression matrix:** 123 passed

## Accomplishments

- Added `KoopmanDatasetV2` with exact arrays `X=(n,11)`, `U=(n,4)`, `R=(n,5)`, `Y=(n,11)`. Its `.U` property is exactly the stored `virtual_control_4` array.
- Added `ActuatorDiagnostics` with read-only padded PWM `(n,8)`, topology mask `(n,8)`, applied wrench `(n,6)`, saturation ratio and squared-PWM energy proxy; none is exposed through an `action`, `control` or positional alias.
- Preserved row-addressable configuration, episode ID, step index, platform context, oracle/estimated context and complete provenance using recursively frozen structures.
- Added separately validated `base`, `uuv6` and `uuv4` local-contract episode/manifest pairs, proving a common 4D learned-control meaning alongside 8/6/4 actuator diagnostics.
- Added `V1CompatibilityView`, which calls the existing strict v1 loader, deep-freezes a copy of the original fields and explicitly reports `source_schema="v1"`, false cross-configuration training eligibility and the missing-v2 field set.
- Kept all v1 data, dataset, model, lifted EDMD, MPC and controller files untouched; behavior tests retain `U=PWM_8` while v2 remains `U=virtual_control_4`.

## Task Commits

1. **Task 1 RED - DatasetV2 and three-topology fixture contracts:** `7888fb3` (`test`)
   - Test syntax compiled, then pytest failed at collection with `ModuleNotFoundError: No module named 'koopman.dataset_v2'`.
2. **Task 1 GREEN - immutable 4D DatasetV2 and diagnostics:** `dc8fc09` (`feat`)
   - DatasetV2 suite passed 15 tests; schema key link was verified.
3. **Task 2 RED - explicit v1 non-promotion contracts:** `2faf255` (`test`)
   - Test syntax compiled, then pytest failed at collection with `ModuleNotFoundError: No module named 'koopman.v1_compatibility'`.
4. **Task 2 GREEN - frozen v1 compatibility view:** `72c8cf4` (`feat`)
   - Target compatibility plus existing v1 data suite passed 19 tests; joint v1/v2 data suites passed 36 tests.
5. **Task 3 - dual-version isolation and protected regressions:** `241a4ca` (`test`)
   - The complete schema/v2/compatibility/v1 model/MPC matrix passed 123 tests.

## Files Created

- `koopman/dataset_v2.py` - strict artifact loader, immutable DatasetV2 and separated actuator diagnostics.
- `koopman/v1_compatibility.py` - named read-only v1 view and fail-closed eligibility check.
- `tests/test_koopman_dataset_v2.py` - fixture/hash, U=4, diagnostics, immutability, metadata and dual-version tests.
- `tests/test_koopman_v1_compatibility.py` - loader delegation, non-promotion, corrupt-v1 parity and v1 hash tests.
- `tests/fixtures/koopman_v2_three_topologies/` - three separately validated two-row local-contract artifact pairs.

## Fixture Hash Evidence

| Artifact | SHA-256 |
|---|---|
| `base.jsonl` | `1167f0e4bb8ffcc31f9260495273798cdb11bc40e068008a9f258899bc198259` |
| `base.manifest.json` | `b99f0f241a72200677a13d5a2b2368e6f5c2cf473e79038ba7ce8d965a1fd837` |
| `uuv6.jsonl` | `b0bafce33b04fdfd300292b218f6e8c93300515f1a23ba91e54a306e793443b5` |
| `uuv6.manifest.json` | `9bcc58e755aa291209ca20b6a841cd9520d2ae10b215b3ef113c7d0c9b314c33` |
| `uuv4.jsonl` | `ac6d161e8d292420fd9773cb28fc2125723d508c5995288662c01405b4faf0a8` |
| `uuv4.manifest.json` | `c0cc803423a3ca03c027aebe4b51612d60eff241a8567a4ccffb030bbd36052b` |
| canonical v1 `koopman_step_small.jsonl` | `c1fcb16c9d3d7828a57f2790509b35a60f1f8d59bf60abf7fcdeb0ae1c51f955` |

Each v2 manifest records exactly two contiguous rows, the matching transition hash, its own configuration and `local_contract` evidence. `validate_episode_artifact_v2` passes for each pair independently.

## U=4 / U=8 Evidence

| Data path | Learned-control field | Executable shape evidence | Status |
|---|---|---|---|
| v2 `KoopmanDatasetV2` | `virtual_control_4` | `(2,4)` for base/uuv6/uuv4 | PASS |
| v2 diagnostics | padded PWM + mask | `(2,8)` with exact 8/6/4 masks/padding | PASS, diagnostics only |
| v1 `KoopmanDataset` | `pwm_8d` | canonical fixture `(4,8)` | PASS, unchanged |
| v1 `KoopmanModel` | `control_dim=PWM_DIM` | default `8` | PASS, unchanged |
| v1 `LiftedEDMDModel` | `control_dim=PWM_DIM` | default `8` | PASS, unchanged |
| v1 MPC | PWM vector | accepts 8D and rejects 4D | PASS, unchanged |

No v1 model, lifted EDMD, MPC or controller imports or calls `DatasetV2`; Phase 8/9 retain ownership of consumer migration.

## v1 Non-Promotion Evidence

- The compatibility entry point calls `koopman_data.load_koopman_samples`; malformed/missing PWM, wrong dimension and non-finite time still fail through the existing v1 validator.
- Returned samples retain the exact v1 field set. `action_4d` is not renamed as virtual control, `pwm_8d` is not inverted into control/wrench, and configuration/context/provenance are not guessed.
- The view exposes no `to_v2`, `promote`, v2 builder, logger or writer API.
- Raw v1 records and compatibility samples both fail strict schema-v2 validation and DatasetV2 construction.
- `require_v2_training_eligibility()` always raises `v1_not_v2_training_eligible` for a valid compatibility view.

## Decisions Made

- Used strict episode/manifest validation before file-to-array conversion and strict episode validation before in-memory record conversion.
- Chose `float64` model arrays, `int8` masks and `int64` step indices, all copied and marked non-writeable.
- Derived saturation ratio and energy proxy only as diagnostics from validated PWM; neither can be selected as `.U`.
- Used immutable mapping proxies and tuple sequences so caller mutation of source records cannot change stored dataset evidence.
- Kept v1 compatibility free of any import from `schema_v2` or `dataset_v2`, preventing an accidental promotion dependency.

## Threat Disposition

| Threat | Disposition | Evidence |
|---|---|---|
| Padded PWM silently returned as v2 U/action/control | MITIGATED | `.U is virtual_control_4`, exact width 4; no `action`/`control`/iteration alias; PWM only under diagnostics. |
| v1 action/PWM relabelled or inferred as v2 truth | MITIGATED | Adapter preserves exact v1 fields, imports no v2 builder and exposes explicit unavailable fields. |
| v1 model/MPC defaults changed prematurely | MITIGATED | Protected files untouched; executable defaults remain PWM_DIM=8 and MPC rejects 4D. |
| Conversion drops grouping/context provenance | MITIGATED | Configuration, episode, step, both contexts and full provenance remain row-addressable and frozen. |
| Frozen objects retain mutable buffers | MITIGATED | All arrays are copied/write-protected; nested dict/list metadata becomes mapping-proxy/tuple storage. |

No HIGH threat assigned to this plan remains unresolved.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The one-time fixture generator initially lacked the repository root on `sys.path`; it failed before writing any fixture. The path was corrected, the six planned files were generated through `KoopmanEpisodeLoggerV2`, and the generator was deleted before the RED commit. Only the planned committed fixtures remain.
- Two initial GREEN expectation mismatches were tightened to accept the upstream strict validator's more specific existing reason classifications (`dataset_shape_invalid` for a row-count-implied shape mismatch and `type_invalid` for missing episode provenance during ordering precheck). No production behavior was weakened.

## TDD Gate Compliance

| Task | RED | GREEN | Result |
|---|---|---|---|
| Task 1 DatasetV2 | `7888fb3` | `dc8fc09` | PASS - RED failed only for missing DatasetV2 module after test syntax compiled. |
| Task 2 v1 compatibility | `2faf255` | `72c8cf4` | PASS - RED failed only for missing compatibility module after test syntax compiled. |
| Task 3 isolation | not TDD | `241a4ca` test-only | PASS - task was declared `type=auto` without `tdd=true`. |

## Verification Evidence

- Plan-prescribed schema/v2/compatibility/v1 data/dataset/model/MPC suite: **123 passed**, no warnings.
- Task 1 DatasetV2 suite: **15 passed**.
- Task 2 compatibility plus v1 data: **19 passed**.
- Joint v1/v2 data suites: **36 passed**.
- `gsd-sdk query verify.key-links 07-03-PLAN.md`: **2/2 verified**, `all_verified=true`.
- Cold imports of DatasetV2 and compatibility modules: **PASS**, no Torch, Gymnasium, Omni or Isaac Lab modules loaded.
- `compileall`: **PASS**.
- `git diff --check`: **PASS**.
- Protected v1 model/lifted/MPC/controller and planning history diff from `v1.0`: **empty**.
- All seven fixture hashes: **PASS**.
- `source/results/koopman_phase7`: **absent**.

## Known Stubs

None. The unavailable v2 fields listed by the v1 view are intentional evidence limitations, not placeholders; no inference or estimator is implemented.

## Threat Flags

None. File reading uses the pre-existing strict bounded v2 loader/manifest validator or existing v1 loader. No writer, network, server, authentication or evidence-promotion surface was introduced.

## User Setup Required

None. This plan adds no dependencies, credentials, server requirement or Isaac runtime requirement.

## Next Phase Readiness

- Phase 8 can consume an explicit U=4 dataset while retaining grouping/context needed for configuration-aware splits.
- v1 evidence remains available for reproducibility comparisons but cannot satisfy v2 cross-configuration eligibility.
- 07-04 still must collect and validate real `base/uuv6/uuv4` Bridge episodes before Phase 7 can claim real runtime integration.
- No Koopman prediction-quality or MPC migration claim is made by this plan.

## Self-Check: PASSED

- All declared modules, tests and six v2 fixture artifacts exist.
- RED/GREEN/regression commits `7888fb3`, `dc8fc09`, `2faf255`, `72c8cf4`, `241a4ca` exist in the required order.
- All 3 tasks, two key links and local verification gates passed.
- No v1 model/MPC/archive, Phase 6 evidence or Phase 7 result directory changed.

---
*Phase: 07-cross-configuration-koopman-data-and-control-contract*
*Plan: 03*
*Completed: 2026-08-12*

---
phase: 07-cross-configuration-koopman-data-and-control-contract
plan: "01"
subsystem: data-contract
tags: [koopman, schema-v2, jsonl, provenance, tdd]

requires:
  - phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification
    provides: canonical exact-eight catalog, topology masks and qualification_record
provides:
  - exact 13-field Koopman transition schema v2 with reason-coded validation
  - contiguous episode JSONL logger/loader and SHA-256 manifest contract
  - deterministic pure-Python validator CLI that cannot promote local evidence
affects: [07-02-runtime-bridge, 07-03-dataset-v1-compatibility, 07-04-server-evidence, phase-08-identification]

tech-stack:
  added: []
  patterns: [pure-stdlib schema core, lazy catalog validation, canonical JSONL, retained part file, atomic manifest promotion]

key-files:
  created:
    - koopman/schema_v2.py
    - workflows/validate_koopman_v2.py
    - tests/test_koopman_schema_v2.py
  modified: []

key-decisions:
  - "Transition identity is exact equality against easyuuv-koopman-transition-v2; prefixes, numeric versions and future variants fail closed."
  - "Topology identity is loaded lazily from qualification_record; schema code contains no copied eight-configuration table."
  - "KoopmanEpisodeLoggerV2 writes local_contract only, retains failed .part files and refuses append/reuse of canonical artifacts."
  - "Episode order failures have distinct duplicate, reordered and missing-step reason codes before numeric-tolerance checks."

patterns-established:
  - "Validators inspect caller-owned mappings without mutation and raise ValueError(reason:detail)."
  - "One JSONL file is one immutable episode; only a validated episode plus byte-exact SHA-256 manifest becomes canonical."

requirements-completed: [CONT-01, CONT-04]

duration: 16 min
completed: 2026-08-12
---

# Phase 07 Plan 01: Pure Schema v2 and Episode Contract Summary

**Pure-Python transition/episode validation now locks exact-eight topology, separated context provenance, contiguous JSONL semantics and local-only artifact promotion without changing v1 PWM8 consumers.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-08-12T00:27:23Z
- **Completed:** 2026-08-12T00:43:34Z
- **Tasks:** 3/3
- **Files modified:** 3 created, 0 existing product files modified
- **Schema tests:** 78 passed
- **Targeted schema/v1/Phase 6 regression:** 179 passed

## Accomplishments

- Added the one exact transition identifier `easyuuv-koopman-transition-v2`, 13 exact top-level fields, exact nested platform/context/provenance fields and fixed vector widths `11/5/4/4/8/8/6/11`.
- Enforced exact public catalog topology, right-padding, binary masks, `uuv4*` zero virtual yaw, finite/range checks, non-bool integers, 40-hex source commit and local/server evidence vocabulary without importing Isaac/Torch/Gym at module import.
- Kept oracle and estimated context as disjoint objects. Estimated-unavailable is explicit and legal; available estimates require deployable method/version/signals; oracle alias/copy attempts fail closed.
- Added bounded UTF-8 JSONL loading with duplicate-key, JSON constant, byte/line/count and `.part` rejection.
- Added one-episode continuity validation for invariants, exact step order, time progression, platform digest and `next_state_11 -> state_11` continuity.
- Added deterministic canonical JSONL, retained failure `.part`, same-directory fsync/temp files, SHA-256 manifest and an exact-pair CLI whose success gate is schema validity rather than a server-origin claim.

## Task Commits

1. **Task 1 RED — exact transition/context contract:** `aba86e6` (`test`)
   - Confirmed failing collection with `ModuleNotFoundError: No module named 'koopman.schema_v2'`.
2. **Task 1 GREEN — strict transition validator:** `0bb631c` (`feat`)
   - 58 tests passed after the minimal transition/context implementation.
3. **Task 2 RED — episode/manifest/CLI contract:** `788f451` (`test`)
   - Confirmed failing collection because `KOOPMAN_EPISODE_MANIFEST_V1` and episode APIs did not exist.
4. **Task 2 GREEN — episode artifacts and CLI:** `89491fa` (`feat`)
   - Full schema file reached 76 passing tests.
5. **Task 3 — pure imports and frozen v1 defaults:** `a661858` (`test`)
   - Added subprocess import and executable PWM8 dataset/model/MPC isolation locks.

## Files Created

- `koopman/schema_v2.py` — pure-stdlib transition, context, episode, manifest, logger/loader and artifact-pair validators.
- `workflows/validate_koopman_v2.py` — deterministic `--jsonl/--manifest/--json` CLI with stable nonzero error behavior and no evidence-upgrade flag.
- `tests/test_koopman_schema_v2.py` — exact-eight positives, mutation matrix, episode/file-safety tests, CLI tests and v1 isolation regression.

## Stable Reason-Code Coverage

The core contains 47 direct `_fail()` reason families plus parameterized bounds and parser/UTF-8 families. Executable negatives cover, among others:

- schema/type: `schema_version_mismatch`, `field_set_mismatch`, `type_invalid`, `shape_invalid`, `nonfinite_value`;
- control/topology: `control_out_of_bounds`, `pwm_out_of_bounds`, `configuration_unknown`, `topology_mismatch`, `mask_mismatch`, `padding_nonzero`, `underactuated_yaw_nonzero`;
- context/provenance: `context_unavailable_invalid`, `context_provenance_invalid`, `oracle_as_estimate`, `source_commit_invalid`, `evidence_level_invalid`, `local_evidence_required`;
- episode: `step_duplicate`, `step_reordered`, `step_discontinuity`, `time_discontinuity`, `state_transition_discontinuity`, `episode_invariant_drift`, `platform_context_drift`;
- artifact safety: `duplicate_json_key`, `nonfinite_json_constant`, `artifact_too_large`, `line_too_large`, `line_count_exceeded`, `partial_artifact_refused`, `manifest_hash_mismatch`.

## Decisions Made

- Kept schema v2 additive: no change was made to `koopman_data.py`, `koopman/dataset.py`, `koopman/model.py` or `koopman/mpc.py`.
- Required at least two rows for canonical episode promotion so continuity is actually observable.
- Classified step order with integer logic before numeric tolerance, so a large tolerance cannot hide a duplicate, reorder or missing step.
- Used `validation_gate=schema_v2_episode_valid`; the local CLI reports the artifact's declared level but never emits `server_pass` or offers a flag to upgrade evidence.

## Threat Disposition

| Threat | Disposition | Evidence |
|---|---|---|
| Partial/v1/hand-written row accepted as v2 | MITIGATED | Exact top-level/nested fields and exact identifier; missing/extra/version mutation tests pass. |
| Local fixture self-labels as server proof | MITIGATED FOR THIS PLAN | Local builder/logger force `local_contract`; CLI has no server/evidence upgrade and makes only a schema-valid claim. External server-origin authentication remains deliberately in 07-04. |
| Valid rows hide duplicate/reordered/discontinuous episode | MITIGATED | Distinct order reasons, invariant/digest/time/state continuity tests and manifest cross-checks pass. |
| NaN/Infinity, duplicate key, bool-as-int or oversized input bypass | MITIGATED | Strict numeric helpers and bounded JSON parser mutation tests pass. |
| Failed finalize overwrites a valid canonical artifact | MITIGATED | Logger refuses reuse, validates before promotion, preserves failed `.part`, and writes/fsyncs manifest temp before atomic replace. |

No HIGH threat assigned to this plan remains unresolved.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Constrained pytest basetemp to the writable repository**

- **Found during:** Task 3 targeted regression.
- **Issue:** The managed Windows environment denied access to pytest's default user temp root after 178 tests had passed; this was not a code failure.
- **Fix:** Re-ran the same suite with `--basetemp .pytest-tmp/07-01-targeted`, matching the repository's established Phase 6 pattern.
- **Files modified:** None.
- **Verification:** 179 passed in 4.76 s.
- **Committed in:** Not applicable; execution-command correction only.

**Total deviations:** 1 auto-fixed (1 blocking environment issue). **Impact on plan:** no scope or code change; verification used a repository-confined writable temp root.

## Issues Encountered

None remaining. Git emitted a sandbox warning while reading the user's global ignore file, but all explicitly staged commits and repository-local status checks completed normally.

## TDD Gate Compliance

| Task | RED | GREEN | Result |
|---|---|---|---|
| Task 1 transition/context | `aba86e6` | `0bb631c` | PASS — RED failed for the intended missing module. |
| Task 2 episode/manifest/CLI | `788f451` | `89491fa` | PASS — RED failed for the intended missing episode API. |
| Task 3 regression lock | not TDD | `a661858` test-only | PASS — task was declared `type=auto` without `tdd=true`. |

## Verification Evidence

- `tests/test_koopman_schema_v2.py`: **78 passed**.
- New/v1/Phase 6 targeted suite: **179 passed**.
- Cold schema + CLI subprocess import: **PASS**, no `torch`, `gymnasium`, `omni` or `easyuuv_nc.env` modules loaded.
- `python -m compileall` for all three created files: **PASS**.
- `git diff v1.0 -- .planning/milestones .planning/reports koopman/model.py koopman/mpc.py`: **empty**.
- `git diff --check`: **PASS**.
- `source/results/koopman_phase7`: **absent**.

## Known Stubs

None. The intentionally unavailable estimated-context state is a locked schema value, not an implementation placeholder; estimator implementation remains Phase 10.

## Threat Flags

None. New file-reading and schema-boundary surfaces are all present in the plan threat model and covered by bounded-input tests.

## User Setup Required

None. This plan adds no dependency, credential, server connection or Isaac requirement.

## Next Phase Readiness

- 07-02 can build real runtime telemetry and the atomic Bridge against `validate_transition_v2`.
- 07-03 can consume only validated episode artifacts and preserve the frozen v1 PWM8 path.
- This plan proves the local data contract only. It does not prove real Isaac telemetry integration, Koopman prediction quality or cross-configuration control effectiveness.

## Self-Check: PASSED

- All three declared artifact files exist.
- RED/GREEN/Task 3 commits `aba86e6`, `0bb631c`, `788f451`, `89491fa`, `a661858` exist in history in the required order.
- 3/3 tasks and every plan-level local verification gate passed.
- No untracked/generated artifact remains and no protected or server-result path changed.

---
*Phase: 07-cross-configuration-koopman-data-and-control-contract*
*Plan: 01*
*Completed: 2026-08-12*

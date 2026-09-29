---
phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification
plan: "03"
subsystem: qualification-artifact-gate
tags: [json, schema, validator, cli, tdd, isaac-free]

requires:
  - phase: 06-01
    provides: canonical editable EasyUUV v2 package and immutable source provenance
  - phase: 06-02
    provides: lazy canonical eight-configuration topology catalog
provides:
  - strict versioned qualification JSON contract with bounded UTF-8 loading
  - exact-set, topology, physics-smoke and normalized-control hard gates
  - separate local-contract and server-Isaac evidence levels
  - deterministic CLI and file-level validation API
affects: [06-04, phase-7, server-qualification, koopman-bridge]

tech-stack:
  added: []
  patterns: [strict artifact boundary, lazy catalog dependency, stable reason codes, deterministic JSON CLI]

key-files:
  created: [workflows/easyuuv_v2_qualification_artifact.py, workflows/validate_easyuuv_v2_qualification.py, tests/test_easyuuv_v2_qualification.py]
  modified: []

key-decisions:
  - "D-04/D-08: a pass requires the exact eight unique public names and the exact catalog topology for each row."
  - "D-10: non-finite values, values outside 1+1e-6 and motor-dimension mismatches are hard failures with distinct reason codes."
  - "D-11: local_contract can pass only with explicit catalog-only mode and can never claim a server pass."
  - "D-13: the qualification gate is a deterministic, versioned, machine-readable artifact rather than console interpretation."

patterns-established:
  - "Importing the validator is Isaac-free; canonical topology is loaded lazily only when no fixture is injected."
  - "The CLI calls only validate_qualification_file and maps every OSError/ValueError contract failure to stderr plus exit 1."
  - "Qualification tests keep temporary artifacts in the ignored repository-local .pytest-tmp directory on restricted Windows runners."

requirements-completed: [QUAL-02, QUAL-04, QUAL-06, QUAL-08]

duration: 25min
completed: 2026-08-10
---

# Phase 6 Plan 03: Strict Qualification Artifact Gate Summary

**A versioned JSON validator now enforces separate local/server evidence contracts and rejects hidden, duplicated, non-finite, out-of-bounds, inverted-range or topology-inconsistent configuration results.**

## Performance

- **Duration:** approximately 25 min
- **Started:** 2026-08-10T15:58:00+08:00
- **Completed:** 2026-08-10T16:22:41+08:00
- **Tasks:** 3 TDD gates plus one isolated test-runner repair
- **Files modified:** 3 unique production/test files

## Accomplishments

- Defined `easyuuv-v2-qualification-v1` with explicit top-level and per-row required fields, a 10 MiB regular-file limit, strict UTF-8 JSON parsing and textual `NaN`/`Infinity` rejection.
- Enforced exact equality with the eight public configurations, duplicate detection before aggregate evaluation and per-configuration thruster count, channel order, control mask and declared rank.
- Enforced real server-smoke facts: `server_isaac_smoke`, matching actual/expected Isaac versions, successful environment/reset, at least 64 base steps and at least 8 steps for every other configuration.
- Enforced finite normalized action/motor ranges, tolerance `1e-6`, exact motor-vector length and zero non-finite/dimension-mismatch counters.
- Added a deterministic CLI with separate `server_pass` and `local_contract_pass` outcomes; an unchanged local-contract artifact cannot pass normal server-contract validation.
- Pinned artifact expectations to Isaac Sim 5.0 and Isaac Lab 2.2.1, rejected Boolean masks that compare equal to integer masks in Python and required `min <= max` for action/motor extrema.

## Hard-Gate Matrix

| Contract area | Stable failure evidence |
|---|---|
| Missing/extra/duplicate public configuration | `configuration_set_mismatch`, `duplicate_configuration` |
| Thruster count/channels/mask/rank | topology-specific mismatch reason |
| Server provenance and versions | `server_evidence_required`, `actual_version_missing`, `actual_version_mismatch` |
| Environment/reset/minimum rollout length | `environment_not_created`, `reset_failed`, `insufficient_steps` |
| Parsed and textual non-finite values | `nonfinite_control`, `nonfinite_json_constant:<token>` |
| Normalized bounds and vector shape | `control_out_of_bounds`, `motor_dimension_mismatch` |
| Expected baseline, mask types and extrema order | `expected_version_mismatch`, `control_mask_mismatch`, `control_range_inverted` |
| Producer-side counters and row status | nonzero-count/status/reason-code hard failures |
| Unsafe file input | missing/non-file/oversize/invalid-UTF-8/invalid-JSON hard failures |

## Task Commits

1. **RED: Specify every qualification hard gate** - `2c3cf47` (`test`); failed as intended because `workflows.easyuuv_v2_qualification_artifact` did not exist.
2. **Test runner repair: Keep scratch artifacts inside the repository** - `cfe074e` (`test`).
3. **GREEN: Implement strict schema, pure validator and CLI** - `985f630` (`feat`); the complete mutation suite passed `49 passed`.
4. **REFACTOR: Prove deterministic CLI output** - `0779cda` (`refactor`); the expanded suite passed twice at `50 passed` each.
5. **Independent audit RED/GREEN: Close expected-version and Boolean-mask bypasses** - `2ff592b` (`test`) then `b85fbbc` (`fix`).
6. **Independent audit RED/GREEN: Reject inverted action/motor extrema** - `0e08e8b` (`test`) then `ffa2e26` (`fix`).

## Files Created/Modified

- `workflows/easyuuv_v2_qualification_artifact.py` - schema constants, strict loader, lazy topology link, payload/file validators and deterministic result summary.
- `workflows/validate_easyuuv_v2_qualification.py` - Isaac-free CLI with catalog-only and JSON modes.
- `tests/test_easyuuv_v2_qualification.py` - independent exact topology fixture and 55 positive/mutation/CLI determinism tests.

## Verification Evidence

- `.venv\Scripts\python.exe -m pytest -q tests/test_easyuuv_v2_qualification.py` - **55 passed** after both audit fixes.
- Wave 2 integration (`catalog + qualification + two v1 source-contract files`) - **84 passed**.
- The same valid fixture emitted byte-identical UTF-8 `--json` stdout across two CLI calls.
- `.venv\Scripts\python.exe -m compileall workflows/easyuuv_v2_qualification_artifact.py workflows/validate_easyuuv_v2_qualification.py` - exit **0**.
- CLI source imports and invokes only `validate_qualification_file`; Isaac/Omni is never imported at module import time.

## Threat-Model Disposition

| Threat | Result | Evidence |
|---|---|---|
| Omitted or duplicated failed configurations | Mitigated | uniqueness is checked before exact set equality; mutations fail. |
| Python accepts non-standard JSON NaN/Infinity | Mitigated | `parse_constant` rejects all three textual constants; parsed non-finite floats also fail. |
| Unchanged local artifact is presented as server evidence | Mitigated at schema boundary | normal mode requires `server_isaac_smoke`, pinned actual versions and server-only row facts. |
| Rewritten local fixture self-asserts all server fields | Deferred to the real evidence boundary | pure JSON cannot authenticate process origin; 06-04 must anchor runner commands, server output, pullback hash and human checkpoint. |
| Unbounded/non-file input consumes uncontrolled resources | Mitigated | regular-file and 10 MiB checks occur before parsing. |

All machine-checkable Plan 06-03 hard gates are resolved. Process-origin authenticity is explicitly outside a self-asserted JSON validator and remains a blocking Phase 6 evidence item in Plan 06-04.

## Decisions Made

- **D-04/D-08:** validate identity and topology, not merely an eight-row count; `uuv4*` must remain mask `[1,1,0,1]` and rank 3.
- **D-10:** every safety defect remains a hard failure; the validator does not downgrade any bound, finite or shape defect to a warning.
- **D-11:** local qualification is useful for schema/catalog work but is deliberately unable to produce `server_pass`.
- **D-13:** stable reason strings, sorted deterministic output and a single file-level API make the artifact usable as the Phase 6 promotion gate.
- **D-12:** the validator pins the expected baseline to Isaac Sim 5.0 and Isaac Lab 2.2.1; matching arbitrary self-declared versions no longer pass.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pytest could not create its user-profile temporary directory**

- **Found during:** GREEN verification after 40 validation tests had already passed.
- **Issue:** nine file/CLI tests failed during `tmp_path` fixture setup with `PermissionError` under the restricted Windows sandbox; validator code was not involved.
- **Fix:** added a test-only fixture under the ignored repository-local `.pytest-tmp` directory.
- **Files modified:** `tests/test_easyuuv_v2_qualification.py`.
- **Verification:** the original plan command, without `--basetemp`, completed with 49 passes and later 50 passes.
- **Committed in:** `cfe074e`.

**Total deviations:** 1 blocking test-environment issue auto-fixed. **Impact:** no artifact schema or validation semantics changed.

## Issues Encountered

- Initial GREEN execution produced `40 passed, 9 errors`; systematic diagnosis showed every error originated in pytest temporary-directory setup. Moving only the test scratch location resolved all nine without touching production logic.
- Independent audit reproduced three semantic bypasses: arbitrary matching expected/actual versions, Boolean masks accepted as integer masks and inverted min/max extrema. Each received a failing regression test before the minimal production fix.
- The audit also proved that a maliciously rewritten local fixture can self-assert every server field. No pure JSON schema can authenticate process origin, so Plan 06-04 retains a mandatory server runner/log/hash/human-checkpoint evidence chain.

## User Setup Required

None for local validation. Isaac Sim 5.0 and Isaac Lab 2.2.1 remain server-side prerequisites for producing the later `server_isaac_smoke` artifact.

## Self-Check

- RED `2c3cf47` precedes GREEN `985f630`; deterministic REFACTOR `0779cda` follows.
- All 55 targeted tests pass after the audit fixes and both production modules compile.
- D-04, D-08, D-10, D-11 and D-13 each have executable evidence.
- The validator is import-time Isaac-free and the CLI has exactly one file-level validation dependency.
- No server physics success is claimed by this local plan.
- Result: **PASSED**.

## Next Phase Readiness

- `06-04` can generate an eight-row artifact on the Isaac server and validate it locally with this exact gate.
- Phase 6 remains open until the server checkpoint, full regression and phase verification are complete.
- `requirements-completed` records this plan's implementation contribution; milestone requirement checkboxes remain open until end-to-end evidence exists.

---
*Phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification*
*Completed: 2026-08-10*

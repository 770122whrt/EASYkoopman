---
phase: 07-cross-configuration-koopman-data-and-control-contract
plan: "02"
subsystem: runtime-bridge
tags: [koopman, runtime-telemetry, atomic-step, thrust-allocation, tdd]

requires:
  - phase: 07-cross-configuration-koopman-data-and-control-contract
    plan: "01"
    provides: strict transition schema v2, exact-eight topology validation and separated context envelopes
provides:
  - post-mask/pre-TAM virtual-control telemetry derived from the canonical catalog
  - post-actuator thruster-only wrench and same-dynamics-call oracle context caches
  - clone-only freshness snapshots with reset invalidation and monotonic runtime tokens
  - batch-safe one-step Koopman Bridge v2 with strict pre-write validation
  - named build_koopman_transition_v2 key link from Bridge assembly to schema_v2 validation
affects: [07-03-server-runner, 07-04-real-server-evidence, phase-08-identification]

tech-stack:
  added: []
  patterns: [additive runtime truth cache, clone-only telemetry snapshot, one-step one-token bridge, fail-closed batch extraction]

key-files:
  created:
    - workflows/koopman_bridge_v2.py
    - tests/test_koopman_bridge_v2.py
  modified:
    - easyuuv_nc/env/easyuuv_env.py

key-decisions:
  - "Preserve _last_pid_value as legacy telemetry and expose post-mask/pre-TAM control separately as _last_virtual_control_4."
  - "Capture applied_wrench_6 from summed per-thruster body force/torque before hydrodynamic, buoyancy, boundary and pulse forces are added."
  - "Require a caller-selected env index and a strictly newer complete runtime token; never substitute catalog defaults, desired wrench or zeros for missing live facts."
  - "Reuse the existing 11D state and 5D reference extractors so Phase 7 does not redefine the v1 coordinate order."

patterns-established:
  - "Runtime truth: cache immutable snapshots at the physical calculation site, not by reconstructing values downstream."
  - "Atomic Bridge: capture pre-state/reference/token, call env.step exactly once, require a fresh complete snapshot, then validate before returning or writing."

requirements-completed: [CONT-01, CONT-02, CONT-04]

duration: 21 min
completed: 2026-08-12
---

# Phase 07 Plan 02: Runtime Truth and Atomic Koopman Bridge Summary

**EasyUUV now exposes post-mask control, actual thruster-only wrench and same-step context through a fresh read-only snapshot, while KoopmanBridgeV2 binds exactly one selected batched environment step into one strict schema-v2 transition.**

## Performance

- **Duration:** 21 min
- **Started:** 2026-08-12T00:44:00Z
- **Completed:** 2026-08-12T01:05:05Z
- **Tasks:** 3/3
- **Files modified:** 3
- **Bridge suite:** 46 passed after post-verification fix
- **Plan regression matrix:** 208 passed after post-verification fix

## Accomplishments

- Added catalog-derived `control_mask_4` to the live control path after PID/deadband/priority processing and before TAM. The exact same masked tensor is cached as `virtual_control_4` and consumed by both configuration-driven and legacy allocation.
- Preserved `_last_pid_value` for Phase 6/v1 consumers while adding raw-action, virtual-control, clipped N-channel PWM, actual body wrench, fluid velocity, actuator efficiency and live platform buffers to a clone-only snapshot.
- Captured actual actuator wrench immediately after per-thruster conversion, dynamics, runtime efficiency and force/torque summation, before hydrodynamic, buoyancy, boundary or torque-pulse contributions are mixed into total force.
- Added reset invalidation and per-environment freshness tokens so no transition can silently consume pre-reset or stale telemetry.
- Added `KoopmanBridgeV2`, which selects an explicit env index, captures pre-state/reference, calls `env.step` once, requires a strictly newer complete token, reads live platform/oracle values and validates schema v2 before return or logger write.
- Kept estimated context explicitly unavailable and made no server, real-Isaac or Koopman-model-effectiveness claim.

## Task Commits

1. **Task 1 RED - runtime truth telemetry contracts:** `f53fa3f` (`test`)
   - RED collected successfully: 10 tests passed and 6 failed because raw-action capture, catalog mask insertion, actual-wrench/context caches, clone snapshot, reset invalidation and freshness token did not exist.
2. **Task 1 GREEN - additive environment telemetry:** `7de6ce0` (`feat`)
   - Task filter passed 16 tests; Bridge/Phase 6 catalog/qualification subset passed 104 tests.
3. **Task 2 RED - atomic Bridge contracts:** `a320bdb` (`test`)
   - Test file compiled, then pytest failed at collection with `ModuleNotFoundError: No module named 'workflows.koopman_bridge_v2'`.
4. **Task 2 GREEN - one-step Koopman Bridge:** `7ecb01b` (`feat`)
   - Bridge suite passed 34 tests; Bridge plus schema-v2 regression passed 112 tests.
5. **Task 3 - allocation, import and frozen-path regressions:** `39f9b52` (`test`)
   - The complete plan matrix passed 204 tests.
6. **Post-verification RED - named schema-builder key link:** `7eec9c5` (`test`)
   - Test syntax compiled, then pytest failed at collection with `ImportError: cannot import name 'build_koopman_transition_v2'`.
7. **Post-verification GREEN - named schema-builder key link:** `efa0e61` (`fix`)
   - Bridge suite passed 46 tests and the expanded complete regression matrix passed 208 tests.

## Files Created/Modified

- `easyuuv_nc/env/easyuuv_env.py` - minimally adds catalog mask application, runtime truth caches, clone-only snapshot and reset/freshness semantics without splitting the environment config or changing task registration.
- `workflows/koopman_bridge_v2.py` - validates batch/action/provenance inputs, performs one atomic step, extracts one explicit env index and builds strict v2 platform/oracle/provenance objects.
- `tests/test_koopman_bridge_v2.py` - exact-eight topology/allocation tests, source capture-point contracts, fake-batched atomic-step tests, stable failure cases and Phase 6/v1 isolation locks.

## Runtime Capture-Point Evidence

| Field | Capture point | Excluded interpretation |
|---|---|---|
| `raw_action_4` | `_pre_physics_step`, before `_actions` overwrite and clipping | clipped action or controller output |
| `virtual_control_4` | `_pid_control`, after priority/deadband/sign processing and catalog mask, before TAM | raw action or unmasked `_last_pid_value` |
| `motor_pwm_padded_8` source | existing `_last_motor_values_clipped`, actual N channels before Bridge padding | raw allocation or fabricated eight-channel actuator set |
| `applied_wrench_6` | `_compute_dynamics`, after conversion/first-order dynamics/efficiency and per-thruster sum | desired TAM wrench or total environmental wrench |
| oracle fluid/efficiency | cached in the same `_compute_dynamics` call | step-after recomputation or catalog defaults |
| freshness | token advances only after wrench, fluid and efficiency caches are complete | reset/stale partial telemetry |

## Exact-Eight and uuv4 Results

- All eight public configurations retain the fixed `[roll,pitch,yaw,depth]` four-channel order and allocate to their canonical `8/6/4` motor widths.
- The six fully controllable configurations have an all-one mask, so masked and previous allocation inputs are byte-for-value equivalent.
- `uuv4` and `uuv4_angled` accept nonzero raw/PID yaw, expose exact zero virtual yaw before TAM and preserve the prior WLS motor result within `1e-6`; the change makes an already physically ignored DOF explicit rather than changing reachable output.
- Legacy `_last_pid_value` and `_last_motor_values_clipped` remain present and retain their consumer-facing roles.

## Atomic Bridge Failure Evidence

Executable tests reject:

- missing snapshot fields and absent getter (`bridge_telemetry_missing`);
- stale token or invalid snapshot (`bridge_telemetry_stale`, `bridge_telemetry_invalid`);
- wrong batch/field shape and non-finite telemetry (`bridge_telemetry_shape`, `bridge_telemetry_nonfinite`);
- env-index escape and malformed/non-finite action batches;
- active/snapshot configuration drift;
- raw-action substitution and control-mask semantic swaps;
- pre-step state or reference dimension drift before `env.step` is called.

The positive fake-runtime path proves exactly one `env.step` call, selected-env extraction, consecutive `next_state_11 -> state_11` equality, exact step/time continuity, live platform values, separate unavailable estimated context and strict validation before logger write.

## Decisions Made

- Used the environment's active catalog identity for topology but read mass, inertia, COM/COB offset, volume, drag and actuator time constant from the live per-env snapshot.
- Made the Bridge consume the complete snapshot API instead of writable `_last_*` references; all tensor fields returned by the environment are detached clones.
- Used a strictly newer-token gate rather than requiring `+1`, because one control step may contain multiple physics substeps while still producing a single final atomic transition.
- Kept the Bridge itself free of Torch/Isaac imports; tensor conversion uses duck typing and cold import loads neither Torch nor Isaac modules.

## Threat Disposition

| Threat | Disposition | Evidence |
|---|---|---|
| `_last_pid_value` incorrectly relabelled as virtual control | MITIGATED | Separate post-mask `_last_virtual_control_4`; uuv4 nonzero-yaw tests pass. |
| Desired or total wrench recorded as actuator wrench | MITIGATED | Cache occurs after actuator effects/per-thruster sum and before all environmental additions; fake Bridge also distinguishes a sentinel desired wrench. |
| Off-by-one or stale transition assembly | MITIGATED LOCALLY | Pre-token, exactly one step, strictly newer complete post-token and two-row episode continuity tests pass. Real Isaac execution remains 07-04 evidence. |
| Telemetry changes Phase 6 allocation behavior | MITIGATED LOCALLY | Exact-eight equivalence tests and Phase 6/v1 regression matrix pass. |
| Bridge silently reads env 0 or fills missing facts | MITIGATED | Explicit env index, exact batch shapes and hard missing/stale/nonfinite failures; live env-index-1 values are asserted. |

No HIGH threat assigned to this plan remains unresolved at the local-contract level.

## Deviations from Plan

### Post-Verification Contract Fixes

**1. [Rule 1 - Contract bug] Closed the mandatory named schema-builder key link**

- **Found during:** Root plan verification after the original 07-02 summary.
- **Issue:** `KoopmanBridgeV2.step_and_record` assembled a correct transition and called `validate_transition_v2` directly, but the plan's mandatory `workflows/koopman_bridge_v2.py -> koopman/schema_v2.py` link required the explicit pattern `build_koopman_transition_v2`. Automated key-link verification therefore reported only 1/2 links despite passing behavior tests.
- **Fix:** Added the thin public `build_koopman_transition_v2(fields)` helper. It deep-copies caller data, invokes the imported strict schema validator and returns only after validation; `step_and_record` routes through it before any logger write.
- **Files modified:** `workflows/koopman_bridge_v2.py`, `tests/test_koopman_bridge_v2.py`.
- **RED evidence:** `7eec9c5` - import failed for the missing named symbol after test syntax compiled.
- **GREEN evidence:** `efa0e61` - symbol/call-path/strict-rejection/no-invalid-write tests pass.

**Total deviations:** 1 post-verification contract fix. **Impact on plan:** no transition field, public Bridge method, failure reason, runtime behavior or evidence boundary changed; the fix makes the planned schema-validation link explicit and machine-verifiable.

## Issues Encountered

- The first Task 1 GREEN run produced 15 passes and one intentional source-contract mismatch: catalog mask construction was delegated to the telemetry initializer rather than visible directly in `apply_embodiment_config`. The minimal implementation was tightened so active-configuration application itself retains the catalog-derived assignment. The rerun passed all 16 Task 1 tests.
- Repository-confined `--basetemp` was used proactively, following the established Phase 6/07-01 Windows sandbox pattern; no production or test semantics changed.

## TDD Gate Compliance

| Task | RED | GREEN | Result |
|---|---|---|---|
| Task 1 runtime telemetry | `f53fa3f` | `7de6ce0` | PASS - six production-semantic absences failed while ten pure topology tests already passed. |
| Task 2 atomic Bridge | `a320bdb` | `7ecb01b` | PASS - test syntax compiled, then collection failed only because the production Bridge module was absent. |
| Task 3 regressions | not TDD | `39f9b52` test-only | PASS - task was declared `type=auto` without `tdd=true`. |
| Post-verification named builder | `7eec9c5` | `efa0e61` | PASS - RED failed for the missing symbol; GREEN validates before return/write and closes the planned key link. |

## Verification Evidence

- `tests/test_koopman_bridge_v2.py`: **46 passed** after the post-verification key-link fix.
- Plan-prescribed Bridge + Phase 6 package/catalog/qualification/runner + v1 source suite: **208 passed** after the post-verification key-link fix (the original matrix was 204/204 before four new contract cases).
- Bridge + schema-v2 joint regression during Task 2: **112 passed**.
- `gsd-sdk query verify.key-links 07-02-PLAN.md`: **2/2 verified**, `all_verified=true`.
- `compileall` for environment, Bridge and Bridge tests: **PASS**.
- Bridge cold import: **PASS**, without Torch, Gymnasium, Omni or Isaac Lab modules.
- `git diff --check`: **PASS**.
- `git diff v1.0 -- .planning/milestones .planning/reports koopman/model.py koopman/mpc.py`: **empty**.
- `source/results/koopman_phase7`: **absent**.

## Known Stubs

None introduced. Two pre-existing TODO comments in the environment's actuator conversion path remain unchanged in meaning and do not represent Phase 7 placeholder outputs.

## Threat Flags

None. The new runtime snapshot is read-only and process-local; it adds no network endpoint, authentication path or file-writing surface. All new runtime trust boundaries were declared in the plan threat model.

## User Setup Required

None. This plan requires no server connection, credential, dependency or Isaac installation locally.

## Next Phase Readiness

- 07-03 can build the real runner/evidence workflow on the atomic Bridge and stable failure behavior.
- 07-04 must still execute `base`, `uuv6` and `uuv4` against the target Isaac runtime before any real-telemetry integration claim is promoted.
- This plan does not train a Koopman model, prove cross-configuration prediction quality or migrate MPC to 4D control; those remain later phases.

## Self-Check: PASSED

- All three declared implementation/test files exist.
- RED/GREEN/regression commits `f53fa3f`, `7de6ce0`, `a320bdb`, `7ecb01b`, `39f9b52`, plus post-verification RED/GREEN `7eec9c5`, `efa0e61`, exist in the required order.
- All 3 tasks and local verification gates passed.
- No protected archive/model/MPC path, Phase 6 evidence or Phase 7 result directory changed.

---
*Phase: 07-cross-configuration-koopman-data-and-control-contract*
*Plan: 02*
*Completed: 2026-08-12*

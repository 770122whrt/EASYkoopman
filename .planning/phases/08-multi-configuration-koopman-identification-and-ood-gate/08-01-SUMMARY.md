---
phase: 08-multi-configuration-koopman-identification-and-ood-gate
plan: "01"
subsystem: evidence-and-server-collection
tags: [koopman, isaac-sim, exact-eight, provenance, pilot-health]
requires:
  - phase: 07-cross-configuration-koopman-data-and-control-contract
    provides: frozen transition schema v2, Bridge and locked Isaac runtime provenance
provides:
  - additive Phase 8 external qualification envelope without Phase 7 evidence enum drift
  - pre-registered exact-eight collection-health policy and model-free auditor
  - fail-closed offline server/bootstrap/run/pullback chain
  - real 8x2x128 pilot collection-health evidence at one tested source/runtime
affects: [08-02, 08-04, phase-9]
tech-stack:
  added: []
  patterns: [external qualification envelope, precollection intent versus postcollection inventory, staged atomic pullback]
key-files:
  created:
    - koopman/evidence_v2.py
    - koopman/protocol_v2.py
    - protocols/phase8/pilot_collection_policy.json
    - workflows/audit_koopman_v2_pilot.py
    - workflows/collect_koopman_v2_identification.py
    - workflows/validate_phase8_evidence.py
    - workflows/validate_phase8_pilot_policy.py
    - source/results/koopman_phase8_pilot/pilot_envelope.json
    - .planning/phases/08-multi-configuration-koopman-identification-and-ood-gate/08-PILOT-EVIDENCE.md
  modified: []
key-decisions:
  - "Pilot qualification remains an external envelope; transition rows retain server_isaac_smoke origin."
  - "The exact-eight pilot proves collection health only and cannot select or evaluate a model."
  - "Only a fresh staged pullback passing source, runtime, policy, status, inventory, hash and local validator gates may create canonical evidence."
patterns-established:
  - "Intent/fact split: committed policy predates collection; inventory and hashes are server-authored facts."
  - "Atomic evidence promotion: copy to ignored staging, validate every referenced byte, then move into an absent canonical root."
requirements-completed: []
duration: "10h 7m active execution plus resumed closeout"
completed: 2026-08-24
---

# Phase 8 Plan 01: Exact-Eight Identification Pilot Summary

**A strict additive evidence layer and real Isaac 8x2x128 collection-health pilot, with byte-level staged pullback and no identification, OOD, model or MPC claim.**

## Performance

- **Duration:** 10h 7m active execution plus resumed closeout
- **Started:** 2026-08-12T18:31:14Z
- **Completed:** 2026-08-23T17:03:56Z
- **Tasks:** 3
- **Files modified/created:** 68

## Accomplishments

- Added a Phase 8 envelope and policy vocabulary that leaves the frozen Phase 7 transition `evidence_level` unchanged.
- Built a policy-driven collector, model-free health auditor, runtime policy validator, offline bundle/bootstrap/server chain and staged pullback with fail-closed mutation coverage.
- Collected and independently promoted exactly 16 episodes, 16 manifests and 16 logs across eight configurations, two policies and 128 transitions per episode: 2048 strict rows total.
- Proved signed controllable-channel coverage and real-runtime `uuv4*` masking: both variants record 160 nonzero raw-yaw probes and zero nonzero virtual-yaw values.

## Task Commits

Every implementation task was committed atomically. RED and GREEN/fix commits are intentionally retained as separate gates.

1. **Task 1 — evidence envelope, policy and model-free audit**
   - `eebe2c5` — `test(08-01): add failing Phase 8 pilot evidence contracts` (RED)
   - `23887d9` — `feat(08-01): add strict Phase 8 pilot evidence layer` (GREEN)
2. **Task 2 — exact-policy collector and fail-closed server chain**
   - `e0a214b` — `test(08-01): add failing Phase 8 pilot server contracts` (RED)
   - `de540d4` — `feat(08-01): add exact Phase 8 pilot server chain` (GREEN)
   - `24c5322` — `test(08-01): add failing runtime policy boundary contracts` (RED)
   - `dbf7481` — `test(08-01): require pullback runtime policy validation` (RED extension)
   - `109b165` — `feat(08-01): enforce operational pilot runtime boundary` (GREEN)
   - `c45e8d8` — `test(08-01): reproduce protected diff argument binding failure` (RED)
   - `48ca5a0` — `fix(08-01): pass protected git arguments explicitly` (GREEN)
   - `39a754e` — `test(08-01): reproduce non-repository bundle verification failure` (RED)
   - `f5de721` — `fix(08-01): verify bundle in isolated Git context` (GREEN)
   - `50f7ca5` — `test(08-01): reproduce pilot log finalization failure` (RED)
   - `e7672fb` — `fix(08-01): finalize real pilot episode logs` (GREEN)
3. **Task 3 — real server pullback and evidence record**
   - `3cbba1e` — `feat(08-01): archive exact-eight pilot evidence`
   - `c6206f6` — `fix(08-01): isolate Windows PowerShell module path`

## Local Preflight and Bundle

The clean tested source and transfer sidecar both identified `e7672fb54ca310797484ae5a6723bf1193ebaf0c`. The verified transfer set was:

| File | Size | SHA-256 |
|---|---:|---|
| `EasyUUV-phase8-pilot-v2.bundle` | 134804077 bytes | `3f0373dc3c77668075a3bd37f487917aa4a0a65d8fb74a989add9883c945e27f` |
| `expected-source-commit.txt` | 41 bytes | `9deb539a4f5dc158b26a500c132e641007ea861af35e937dcde4c57a0785c66e` |
| `phase8_pilot_server_bootstrap.sh` | 1714 bytes | `371e1ad7a2ddabdf568d1b50766e09745d5f8b61efc126dc4530b46e2f3344a2` |

Fresh closeout verification collected 639 tests, ran the full suite as `638 passed, 1 skipped`, compiled `koopman`, `easyuuv_nc`, `workflows`, `scripts` and `tests` successfully, and reported no broken Python requirements.

## Server Execution and Pullback

The agent connected to explicit `root@183.147.142.40:31348` using the provided key, BatchMode and strict host-key checking. The successful target was `/root/EASYkoopman-phase8-pilot-v2`; the failed target `/root/EASYkoopman-phase8-pilot-v2-failed-f5de721-missing-logs` remains preserved.

Server commands were the committed bootstrap and runner chain described in `08-PILOT-EVIDENCE.md`; collection files span 2026-08-13T04:16:38.941Z to 2026-08-13T04:18:35.495Z and the envelope was written at 2026-08-13T04:18:38.283Z.

| Provenance fact | Value |
|---|---|
| Source commit | `e7672fb54ca310797484ae5a6723bf1193ebaf0c` |
| Isaac Sim / Isaac Lab | `5.0` / `2.2.1` |
| Isaac Lab release | `v2.2.1` / `0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20` |
| Isaac Lab repo / parent | `c91a125c73c8b574878419a9583afc0b63b99f0a` / `0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20` |
| Locked patch SHA-256 | `d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079` |
| Runtime object SHA-256 | `21cfb69aafb3f04f338af6211cf87646176f49ab86abb2448f36702226f3a62a` |
| Policy SHA-256 | `d437e3f3040714469951fcf50d9f3d9bd47a117f6b61c7236be545ba7402ab93` |
| Inventory SHA-256 | `d25d2fb3ba6d13284e1e03b30eeb8ac7d8d7d8350c1da432b1ba34e7810cab2d` |
| Decision SHA-256 | `a26c05f597768c1b2eac375d89e771a84cfc6100d362cd599b27f02971279a3d` |
| Envelope SHA-256 | `6052570ebf24f14d1ef39b057bd2aee8796ad7d5b7e5ffd70622778281b82155` |

All eight configurations had native `0`, tee `0`, semantic `pass`. The server and pullback inventory revalidated 52 files; the envelope revalidated 51 referenced files and itself matched the server SHA. The local operational policy and external evidence validators both returned exit 0 with `warnings=[]`, after which staging was atomically promoted into the previously absent canonical root.

## Exact Pilot Result

| Measure | Result |
|---|---:|
| Configurations | 8 |
| Policies per configuration | 2 (`axis_pulse` seed 8101; `bounded_multisine` seed 8102) |
| Transitions per episode | 128 |
| Total episodes / manifests / logs | 16 / 16 / 16 |
| Total transitions | 2048 |
| Canonical files | 52 |
| Envelope referenced files | 51 |

For the six fully actuated configurations, signed virtual-control counts were negative `[87,79,78,78]` and positive `[73,81,82,82]`. For `uuv4` and `uuv4_angled`, counts were negative `[87,79,0,78]`, positive `[73,81,0,82]`, raw-yaw nonzero `160`, and virtual-yaw nonzero `0`.

## Files Created/Modified

- `koopman/evidence_v2.py`, `koopman/protocol_v2.py` — strict additive envelope/policy contracts.
- `workflows/audit_koopman_v2_pilot.py`, `workflows/validate_phase8_evidence.py`, `workflows/validate_phase8_pilot_policy.py` — model-free evidence and runtime-policy gates.
- `workflows/collect_koopman_v2_identification.py`, `scripts/phase8_pilot_*` — exact-policy collection, offline server execution and staged promotion.
- `source/results/koopman_phase8_pilot/` — canonical real-server exact-eight evidence.
- `08-PILOT-EVIDENCE.md` — commands, full per-episode hashes, underactuation evidence and claim boundary.

## Decisions Made

- Kept Phase 8 qualification in an external envelope while every row retains `server_isaac_smoke` origin.
- Treated the pilot strictly as collection-health evidence; it cannot choose a feature, horizon, backend, model or threshold.
- Required exact source/runtime/policy/status/inventory/hash agreement and local revalidation before atomic canonical promotion.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Corrected protected-diff PowerShell argument binding**
- **Found during:** Task 2 clean preflight
- **Issue:** PowerShell bound protected Git arguments ambiguously and prevented the required clean gate.
- **Fix:** Added RED `c45e8d8` and explicit argument passing in GREEN `48ca5a0`.
- **Files modified:** `tests/test_phase8_pilot_server_contract.py`, `scripts/phase8_pilot_local_preflight.ps1`

**2. [Rule 3 - Blocking] Verified the Git bundle from an isolated repository**
- **Found during:** Task 2 server bootstrap
- **Issue:** Bundle verification incorrectly depended on a surrounding repository context.
- **Fix:** Added RED `39a754e` and isolated verification in GREEN `f5de721`.
- **Files modified:** `tests/test_phase8_pilot_server_contract.py`, `scripts/phase8_pilot_server_bootstrap.sh`

**3. [Rule 1 - Bug] Finalized per-episode logs before audit**
- **Found during:** Task 3 first server attempt
- **Issue:** The simulation data completed but all expected final log artifacts were absent, so the strict audit failed closed.
- **Fix:** Preserved the failed server target, added RED `50f7ca5`, then finalized fresh logs before inventory/envelope generation in GREEN `e7672fb`.
- **Files modified:** `tests/test_phase8_pilot_server_contract.py`, `workflows/collect_koopman_v2_identification.py`

**4. [Rule 3 - Blocking] Isolated Windows PowerShell module discovery in dynamic pullback tests**
- **Found during:** resumed closeout full-suite verification
- **Issue:** Python inherited PowerShell 7's Core-only `PSMODULEPATH` while launching Windows PowerShell 5.1, so the incompatible Utility 7.0 module shadowed the built-in Utility 3.1 module and `Get-FileHash` was unavailable.
- **Fix:** Kept the committed fail-closed pullback behavior unchanged and made the Windows PowerShell test subprocess rebuild its interpreter-native module path; the dynamic contract then passed 53/53 and the full suite passed 638/638 runnable tests with one platform skip.
- **Files modified:** `tests/test_phase8_pilot_server_contract.py`

The simulation was not rerun during pullback. One auxiliary read-only timestamp query used an incorrectly escaped shell format and was repeated correctly; it changed no local or remote state.

## Authentication Gates

None. The supplied explicit SSH key and host-key policy worked non-interactively.

## Known Stubs

None. A scan of all 68 plan-touched files found no TODO, FIXME, placeholder, coming-soon or not-available stub.

## Claim Boundary

This plan proves only that the exact-eight collection chain is healthy at one tested source/runtime. It does not prove Koopman identifiability, model quality, feature/horizon/backend/rank/condition selection, prediction or rollout performance, OOD generalization, or MPC/closed-loop effectiveness. KID-01 and KID-05 therefore remain incomplete pending later Phase 8 plans.

## Next Phase Readiness

- Exact canonical pilot evidence and the external evidence vocabulary are available for 08-02 protocol/inventory work.
- Main role collection and all model-affecting decisions remain blocked on the later frozen protocol checkpoint.
- No Phase 8 requirement was marked complete and Phase 8 remains executing.

## Self-Check: PASSED

- Verified all named implementation/evidence files exist.
- Verified RED/GREEN/fix/evidence commits `eebe2c5` through `c6206f6` exist in history.
- Verified canonical exact counts, full suite, validators, protected paths and claim boundaries from fresh commands.

---
*Phase: 08-multi-configuration-koopman-identification-and-ood-gate*
*Completed: 2026-08-24*

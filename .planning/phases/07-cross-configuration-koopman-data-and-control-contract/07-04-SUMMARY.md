---
phase: 07-cross-configuration-koopman-data-and-control-contract
plan: "04"
subsystem: server-evidence
tags: [koopman, isaac-sim, bridge-v2, offline-evidence, exact-three]

requires:
  - phase: 07-cross-configuration-koopman-data-and-control-contract
    plan: "02"
    provides: atomic runtime telemetry and KoopmanBridgeV2
  - phase: 07-cross-configuration-koopman-data-and-control-contract
    plan: "03"
    provides: immutable DatasetV2 and v1 compatibility boundary
provides:
  - exact-three base/uuv6/uuv4 server collector and aggregate validator
  - fail-closed local preflight, offline bundle/bootstrap and staged pullback
  - real Isaac Sim 5.0 / Isaac Lab 2.2.1 schema-v2 evidence
  - source/runtime/log/hash-bound Phase 7 completion record
affects: [phase-08-identification, phase-09-mpc-migration]

tech-stack:
  added: []
  patterns: [one-process-per-topology, atomic JSONL manifest pair, flat aggregate evidence root, fail-closed provenance promotion]

key-files:
  created:
    - workflows/collect_koopman_v2_smoke.py
    - workflows/merge_koopman_v2_evidence.py
    - scripts/phase7_local_preflight.ps1
    - scripts/phase7_prepare_bundle.ps1
    - scripts/phase7_server_bootstrap.sh
    - scripts/phase7_server_smoke.sh
    - scripts/phase7_pullback.ps1
    - tests/test_phase7_server_evidence_contract.py
    - docs/phase7_koopman_v2_runbook.md
    - source/results/koopman_phase7/
    - .planning/phases/07-cross-configuration-koopman-data-and-control-contract/07-SERVER-EVIDENCE.md
  modified:
    - workflows/validate_koopman_v2.py
    - tests/test_easyuuv_v2_qualification_runner.py

key-decisions:
  - "Server success requires exact base/uuv6/uuv4 evidence; local/mock rows cannot be promoted."
  - "Each topology runs in a separate Isaac process, while merger and validator consume one flat immutable evidence root."
  - "The unchanged server is identified by IsaacLab VERSION, release identity, repo HEAD/parent, exact dirty-file set and patch SHA-256."
  - "Phase 7 proves the schema/Bridge runtime chain only; Koopman prediction/OOD and MPC effectiveness remain Phase 8/9 work."

requirements-completed: [CONT-01, CONT-02, CONT-03, CONT-04, CONT-05]
completed: 2026-08-12
---

# Phase 07 Plan 04: Exact-Three Real-Server Evidence Summary

**The Phase 7 data/control contract now runs end to end on real 8-, 6- and 4-thruster Isaac environments, with exact source/runtime provenance, strict per-episode validation and hash-bound pullback.**

## Accomplishments

- Added a one-configuration collector that launches Isaac before environment imports, executes a deterministic 4D action sequence through `KoopmanBridgeV2`, and writes an atomic schema-v2 JSONL/manifest pair.
- Added an exact-three merger and aggregate validator that require `base`, `uuv6`, `uuv4`, at least 8 contiguous rows each, matching source/runtime/log hashes, and server-only provenance.
- Added one fail-closed local entry chain: complete preflight → verified offline Git bundle and sidecar → isolated server bootstrap → three independent Isaac processes → aggregate validation → staged SCP/hash/provenance validation → canonical promotion.
- Bound the unchanged Isaac server to its real conda Python, Isaac Sim `5.0`, Isaac Lab VERSION `2.2.1`, release commit, fixed server HEAD/parent, exact dirty file set and patch hash without modifying `/root/IsaacLab`.
- Produced 24 real transitions and a strict aggregate. `uuv4` contains two nonzero raw-yaw probes whose post-mask virtual yaw is exactly zero.
- Kept implementation, server result and planning closure auditable: tested source `a36689a`, promoted-directory audit helper `21b4b77`, separate evidence commit `1c0a6ca`, then this planning closure.

## TDD and Implementation History

### Core collector and evidence chain

1. `c1240ae` — RED contracts for exact-three collector/merger/validator behavior.
2. `0566056` — GREEN collector, exact-three aggregate and strict validator.
3. `2c71325` — RED contracts for offline preflight/bootstrap/pullback failure modes.
4. `f628a71` — GREEN fail-closed offline server chain and runbook.

### Local/server hardening

- PowerShell default-root, Git Bash and stderr handling were reproduced and fixed through `1b08989`→`820fbce`, `c83a667`→`1b8bb4a`, `451ab20`→`7ea86eb`, and `a02e583`→`a83af53`.
- Phase 6 evidence protection was locked through `5942ec3`→`ca0808b`.
- Real-server provenance and startup failures were fixed through strict TDD: unchanged IsaacLab binding (`f4d6aa1`→`88c9139`), conda activation (`186dcd4`→`6154c56`), self-result/SystemExit handling (`8b6b2be`→`17745a9`), repeated preflight isolation (`3fc1936` through `e364f68`), canonical Sim version normalization (`9edc06f`→`801a43d`) and flat aggregate layout (`e567c85`→`eb4669d`).
- Final evidence audit then reproduced and fixed a self-referential file-inventory defect (`8996b37`→`a36689a`) and added a narrow completion-state revalidation mode for the locally generated pullback verdict (`836687d`→`21b4b77`). The `eb4669d`/`b16fb89` result was archived and the server run was repeated from scratch.

No failed artifact was relabelled as success. Each real-server failure was preserved outside the canonical location and led to a new test before its fix.

## Local Verification Before Transfer

| Gate | Result |
|---|---|
| Phase 7 targeted suite | `224 passed, 1 skipped in 40.36s` |
| Full collect-only | `562 collected` |
| Full pytest | `561 passed, 1 skipped in 69.78s` |
| compileall | pass |
| pip check | `No broken requirements found.` |
| Phase 7 Bash parse | pass |
| Phase 7 PowerShell parse | pass |
| protected v1/Phase 6 diff | pass |
| clean tested worktree | pass |
| canonical Phase 7 evidence absent | pass |

The single skip is the Windows host's inability to create a symlink in that test context. Production path-confinement/symlink checks remain fail closed and are covered by the rest of the contract suite.

## Bundle and Server Execution

- Tested source commit: `a36689abeee00c98eb480ebcdf02e147edcaa6e3`.
- Bundle SHA-256: `ae0cdfb789d23dff6922c63269b847db0485ab1bde57e8a6450da1c337dd6131`.
- Server checkout: `/root/EASYkoopman-phase7-v2`.
- Server command: `bash /root/phase7_server_bootstrap.sh`.
- Runtime: Isaac Sim `5.0`, Isaac Lab `2.2.1`, `/opt/conda/envs/isaaclab/bin/python`, RTX 4090 via Vulkan/PhysX.
- Result: exit 0; `base`, `uuv6`, `uuv4` each produced 8 strict transitions; all nine native/tee/semantic topology gates passed.
- Aggregate SHA-256: `2f07a6835f0b32fe0277fd819394580f261b6028dc3d07520e70b124e0758463`.
- Exact inventory: 44 server-authored files, relative paths, self excluded, validated both on server and before pullback promotion.
- Pullback: exit 0; local strict validator returned `koopman_v2_exact_three_server_evidence_valid`, 3 configurations and no warnings.
- Evidence commit: `1c0a6cabe82d4153efd9a8e60485f2423ddd4f41`.

## Three-Topology Semantic Evidence

| Configuration | Thrusters | Control mask | Rows | Actual wrench | Environment context | Special gate |
|---|---:|---|---:|---|---|---|
| `base` | 8 | `[1,1,1,1]` | 8 | 8/8 nonzero | 8/8 same-step oracle | full-rank baseline |
| `uuv6` | 6 | `[1,1,1,1]` | 8 | 8/8 nonzero | 8/8 same-step oracle | `pinv` allocation |
| `uuv4` | 4 | `[1,1,0,1]` | 8 | 6/8 nonzero | 8/8 same-step oracle | 2 raw-yaw probes, 0 leaks |

All 24 rows distinguish raw action, virtual control, padded PWM/mask and actual wrench. Estimated environment context is explicitly unavailable rather than copied from oracle truth.

## Deviations Resolved

The unchanged server exposed four substantive assumptions that local mocks could not prove:

1. Isaac execution required explicit activation of the fixed `isaaclab` conda runtime.
2. An in-repository evidence directory must be allowed as explicit runner output without relaxing tracked-source cleanliness.
3. Isaac Sim's canonical contract string is `5.0`, while distribution metadata is `5.0.0.0`.
4. The strict merger requires topology artifacts in one flat aggregate root.
5. A full-file inventory cannot hash itself while being written; it must exclude itself, use relative paths and be independently validated before promotion.

Each deviation was resolved with a failing regression test and an atomic fix. The final successful run used only the final tested bundle; no prior row was reused.

## Requirement Closure

| Requirement | Result | Closure |
|---|---|---|
| CONT-01 | PASS | Strict schema-v2 and 24 real rows cover every required state/control/PWM/wrench/context/provenance field. |
| CONT-02 | PASS | Bridge/DatasetV2 use one 4D pre-TAM meaning; real uuv4 mask proves yaw removal before allocation. |
| CONT-03 | PASS | PWM8 remains named diagnostics and cannot silently become DatasetV2 `.U`. |
| CONT-04 | PASS | Oracle and estimated context are independently typed and represented in every real row. |
| CONT-05 | PASS | Explicit non-promoting v1 adapter remains readable; v1 model/MPC defaults stay PWM8. |

## Limitations and Handoff

- Eight-step deterministic episodes are interface/semantic evidence, not a training dataset or long-horizon stability result.
- Phase 7 did not identify a Koopman model, compare prediction metrics, test a held-out configuration or run 4D Koopman-MPC.
- Phase 8 should build configuration/episode-level splits and compare model families using the v2 interface; it must preserve `no_selection` if no candidate passes every OOD gate.
- Phase 9, not Phase 7, is responsible for migrating the actual MPC optimization/control path from the frozen v1 PWM8 contract to the 4D virtual-control contract.

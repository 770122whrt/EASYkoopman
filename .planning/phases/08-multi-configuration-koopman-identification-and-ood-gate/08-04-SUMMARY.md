---
phase: 08-multi-configuration-koopman-identification-and-ood-gate
plan: "04"
subsystem: exact-eight-main-identification-dataset
tags: [koopman, isaac-sim, exact-eight, loco, server-evidence, immutable-dataset]
requires:
  - phase: 08-multi-configuration-koopman-identification-and-ood-gate
    plan: "03"
    provides: frozen controlled-EDMD candidates, metrics and sealed seven-source decision contracts
provides:
  - user-approved immutable D-23 role/action and analysis policy hashes
  - real-server exact-eight 96-episode and 49152-transition main dataset
  - actual-byte inventory, eight configuration-held-out LOCO folds and external evidence envelope
  - staged pullback with exact file/hash/runtime/status validation and byte-preserving Git attributes
affects: [08-05, phase-9]
tech-stack:
  added: []
  patterns: [fresh-attempt-only-server-evidence, exact-per-configuration-gate, direct-python-postprocessing, byte-preserving-evidence-archive]
key-files:
  created:
    - source/results/koopman_phase8_dataset/
    - .planning/phases/08-multi-configuration-koopman-identification-and-ood-gate/08-MAIN-DATA-EVIDENCE.md
  modified:
    - protocols/phase8/main_role_assignment_protocol.json
    - protocols/phase8/analysis_policy.json
    - workflows/collect_koopman_v2_identification.py
    - scripts/phase8_main_server_run.sh
    - scripts/phase8_main_local_preflight.ps1
    - scripts/phase8_main_prepare_bundle.ps1
    - scripts/phase8_main_server_bootstrap.sh
    - scripts/phase8_main_pullback.ps1
    - tests/test_phase8_main_server_contract.py
    - docs/phase8_koopman_identification_runbook.md
    - .gitattributes
key-decisions:
  - "D-23 approval binds the exact protocol file bytes; the approved files are not edited after approval."
  - "A failed server process or postprocessing gate is preserved and followed by a fresh checkout/result root; completed rows from a failed attempt are never resumed or promoted."
  - "The 512-transition main collector owns the episode time boundary while per-configuration exact-12 and no-part gates fail closed."
  - "Evidence-only postprocessing uses the locked Conda Python directly so launcher banners cannot corrupt captured hashes or swallow Python exit status."
  - "The canonical server bytes are archived with Git text conversion disabled for the dataset subtree."
patterns-established:
  - "Dataset-before-model boundary: main fit/validation/test bytes and LOCO folds are immutable before 08-05 opens any model test result."
  - "Server completion requires 8/8 native, tee and semantic gates plus exact 96/96/96 artifacts, zero parts, validator pass and all-file hashes."
requirements-completed: []
completed: 2026-08-29
---

# Phase 8 Plan 04: Exact-Eight Main Dataset Summary

**The approved exact-eight experiment produced a real-server, independently pulled, exact-byte main identification dataset: 96 episodes, 49,152 transitions, eight configuration-held-out LOCO folds and a warning-free external evidence envelope. This is dataset readiness, not a Koopman performance result.**

## Performance

- **Elapsed:** resumed execution across D-23 review, server startup and four isolated server attempts
- **Completed:** 2026-08-29T14:40:03Z
- **Tasks:** D-23 approval, local operational implementation/preflight, real server collection, staged pullback and evidence closeout
- **Canonical dataset:** 294 files / 151.71 MiB

## Accomplishments

- Froze and preserved the user-approved D-23 hashes:
  - role/action protocol `499b79089a4bfb0769ce6a902ad676f09e9c64190069a0bf5b51cd76f1d6cf26`;
  - analysis policy `4083e6ef7c63aaf44c0eba98e13b40ceb8d6387ef818d3f90a88ac96aa6d0090`.
- Ran the final successful bundle from source commit `a7e819848ffc1c621fbeeff971063f1cdbeac0b3` in isolated `/root/EASYkoopman-phase8-main-v2` without editing `/root/IsaacLab`.
- Collected all eight configurations with six fit, three validation and three test episodes per configuration; every episode contains exactly 512 transitions.
- Passed all eight native status, all eight tee status and all eight semantic status gates; produced 96 JSONL, 96 manifests, 96 episode logs and zero retained `.part` files.
- Built the post-collection actual-byte inventory and eight-fold LOCO split only after the exact set completed.
- Produced external envelope SHA-256 `46d02531457123f2a1dfda3b16159b359a6caff2d90b14283094a349647a1b04`; server and local validators both returned `phase8_external_evidence_valid`, 293 referenced files and `warnings=[]`.
- Pulled through random staging, validated 294/294 server inventory files and atomically promoted into the previously absent canonical root.
- Verified the main and retained pilot datasets have zero episode-ID overlap and zero transition-hash overlap.
- Disabled Git text conversion for only the canonical dataset subtree and verified 294/294 staged Git blobs equal the original working-tree bytes.

## Task Commits

1. `f65b64b` — RED: exact main experiment and operational failure contracts.
2. `83fce7e` — GREEN: frozen proposal, collector, server/bundle/pullback chain and runbook.
3. `7ec7eb6`, `fccdf42` — deterministic Windows Git stderr/argument handling in the clean preflight.
4. `25b3ba2` — minimal D-23 semantic corrections for strict LOCO, bootstrap and seed semantics; final approved hashes originate here.
5. `01e9da6` — non-interactive activation and verification of the locked server Conda/Isaac runtime.
6. `647b65f` — 512-transition episode-boundary ownership and exact-12/no-part configuration gate.
7. `a7e8198` — pure locked-Python evidence postprocessing with faithful hash and exit semantics.
8. `98dbd76` — independently pulled exact-eight server dataset, evidence record and byte-preserving archive.
9. `f954c71` — post-promotion test lifecycle fix: retain preflight fail-closed tokens without requiring canonical evidence to remain absent forever.

## Exact Server and Dataset Evidence

| Evidence | Result |
|---|---|
| Successful server completion | `bootstrap.exit=0`, `2026-08-29T14:19:54Z` |
| Source commit | `a7e819848ffc1c621fbeeff971063f1cdbeac0b3` |
| Runtime | Isaac Sim `5.0.0.0`; Isaac Lab version file `2.2.1` |
| Configurations | exact `base`, `long_body`, `heavy_moderate`, `asymmetric`, `uuv6`, `uuv6_angled`, `uuv4`, `uuv4_angled` |
| Roles per configuration | fit `6`, validation `3`, test `3` |
| Episodes / transitions | `96` / `49,152` |
| JSONL / manifests / logs / parts | `96 / 96 / 96 / 0` |
| Native / tee / semantic gates | `8/8 zero`, `8/8 zero`, `8/8 pass` |
| LOCO folds | `8`, each holds out one complete configuration |
| Runtime SHA-256 | `1d5afae47ae18524a3cd9645dfb9b94adc81346d143684a6584c23e2e09591c2` |
| Inventory file SHA-256 | `cfac12d15f062c9f330d2acf6381d341769e989dc35cd00ae29759a6f94f395b` |
| Split file SHA-256 | `0e245dfa238df252145e99751be8dcc9ed6a1ef340f382428f6fd3c86db5d8ed` |
| Envelope SHA-256 | `46d02531457123f2a1dfda3b16159b359a6caff2d90b14283094a349647a1b04` |
| Server all-file inventory | `294/294`, sidecar SHA-256 `a7d3633498b93ed9308dd61eafed84d15fc3500d9ec400c57b39532294cf0a0a` |

Detailed commands, seed/action matrix, runtime hashes, KID data mapping and claim boundary are recorded in `08-MAIN-DATA-EVIDENCE.md`.

## Verification

- Final clean local preflight at `a7e8198`: `118 passed` targeted; full suite `743 passed, 1 skipped`; compileall, pip check, Bash/PowerShell parse, protected/pilot/canonical-absence and Git task-file gates passed.
- Final bundle SHA-256 `50417e356c19e31f46e4674a5a1440834ab3954e17db09c42334e1cdab0708e5`; local and remote `git bundle verify` passed.
- Server exact-set check: 96 episode JSONL, 96 manifests, 96 logs, 49,152 total lines, zero `.part`.
- Server validator and post-pullback local validator both exited zero with the same source commit, qualification, referenced-file count and no warnings.
- Canonical inventory has 96 entries, exactly 12 per configuration; split has exactly eight folds.
- Git evidence preservation check: `index_raw_byte_mismatches=0` across all 294 canonical data files.

## Deviations and Preserved Failures

Three failed attempts were never promoted or reused:

1. `25b3ba2`: zero episodes; non-interactive shell lacked locked Conda activation. Preserved as `failed-25b3ba2-python-runtime`.
2. `01e9da6`: zero finalized episodes and eight 178-row `.part` files; native three-second time cap split the frozen 512-step block. Preserved as `failed-01e9da6-native-timeout`.
3. `647b65f`: all 96 episodes completed, but the Isaac launcher banner contaminated captured `runtime_sha`; inventory failed closed. The rows were not resumed or promoted. Preserved as `failed-647b65f-postprocess-runtime-hash`.

The fourth attempt `a7e8198` started from a fresh bundle, checkout and result root and completed with `bootstrap.exit=0`. Fixes were covered by RED→GREEN tests and did not alter the approved experiment ID or either D-23 protocol hash.

## Threat Dispositions

| Threat | Disposition |
|---|---|
| Protocol/role/action drift after approval | Approved file hashes match bundle, server status, canonical copies and envelope |
| Partial/stale episode promotion | Fresh roots, exact per-configuration gate, exact 96 aggregate and zero `.part`; failed attempts isolated |
| Pilot rows relabelled as main | Disjoint roots/IDs/seeds; measured zero ID and transition-hash overlap |
| Runtime/source drift | Server HEAD, local HEAD, inventory/envelope source commit and locked runtime provenance match |
| Hash or newline mutation during pullback/Git | Staged all-file verification plus subtree `-text`; 294/294 index blobs equal source bytes |
| Dataset evidence inflated into model claim | Envelope and evidence record allow dataset/split readiness only; model/OOD/MPC claims remain disallowed |

## Requirement Boundary

- `KID-01`: real exact-eight data and whole-configuration LOCO split portions pass.
- `KID-02`, `KID-03`, `KID-05`: immutable data/policy prerequisites pass, but model comparison, held-out prediction metrics and terminal selection/no-selection have not run.
- No KID requirement is marked milestone-complete in this summary; the one frozen 08-05 evaluation and independent Phase 8 verification remain required.

## Claim Boundary and Next Action

Plan 08-04 proves that the approved multi-configuration identification dataset exists, is complete, immutable, server-origin and ready for the frozen LOCO workflow. It does not prove that Koopman predicts a held-out configuration well, beats persistence/simple-linear baselines, or improves MPC/closed-loop/environment-adaptation/Agentic behavior.

Next execute `08-05-PLAN.md`. Before any held-out test data is opened, the implementation must machine-verify that each fold's primary candidate/model, feature/normalization choices, gates and provenance are sealed; test results may not influence fitting or candidate selection.

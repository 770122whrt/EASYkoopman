---
phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification
fixed_at: 2026-08-10T10:24:39Z
review_path: .planning/phases/06-easyuuv-2-0-intake-and-multi-configuration-qualification/06-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 10
skipped: 0
postfix_findings_fixed: 7
postfix_verified_at: 2026-08-11T00:06:38+08:00
status: all_fixed
---

# Phase 06: Code Review Fix Report

**Fixed at:** 2026-08-10T10:24:39Z
**Source review:** `.planning/phases/06-easyuuv-2-0-intake-and-multi-configuration-qualification/06-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 10
- Fixed: 10
- Skipped: 0

Latest local verification after the postfix fixes: Phase 6 targeted tests
`145 passed`; full collection `320`; full suite `320 passed`; `compileall`,
`pip check`, Git-for-Windows Bash parse, PowerShell parse, `git diff --check`,
and protected-v1 path checks all exited zero. The canonical qualification JSON,
server evidence, and 06-04 summary remain absent. Server runtime verification
remains the blocking Task 4 checkpoint and was not fabricated.

## Fixed Issues

### CR-01: Non-finite telemetry destroys the failure artifact it is supposed to preserve

**Status:** fixed: requires human verification
**Files modified:** `workflows/qualify_easyuuv_v2.py`, `tests/test_easyuuv_v2_qualification_runner.py`
**Commit:** `2a268c1`
**Applied fix:** Extrema now aggregate finite values only, use a documented
finite `0.0` sentinel when no finite sample exists, preserve the authoritative
non-finite count/reason, and prove strict-JSON write/reload of the failed row.

### CR-02: The eight server commands bypass the server's required IsaacLab launcher

**Status:** fixed: requires human verification
**Files modified:** `.gitattributes`, `scripts/phase6_server_qualification.sh`, `docs/phase6_easyuuv_v2_qualification_runbook.md`, `tests/test_easyuuv_v2_qualification_runner.py`
**Commit:** `07af9b7`
**Applied fix:** All eight server smokes use `/root/IsaacLab/isaaclab.sh -p`
with absolute runner/result/log paths; LF endings are enforced for Bash files.

### CR-03: A pulled artifact can pass the strict validator after provenance is removed

**Status:** fixed: requires human verification
**Files modified:** `workflows/easyuuv_v2_qualification_artifact.py`, `workflows/validate_easyuuv_v2_qualification.py`, `tests/test_easyuuv_v2_qualification.py`
**Commits:** `be4b91a`, `f53a275`, `ce3e34b`
**Applied fix:** Server-mode public validation now requires the exact runtime
provenance shape and validates Sim distribution, Lab distribution/tag/commit,
while catalog-only evidence remains valid without it. Optional external commit
and tag sidecars bind detached pulled JSON to tested source and server records.

### CR-04: Claimed server setup gates do not stop the shell

**Status:** fixed: requires human verification
**Files modified:** `scripts/phase6_server_bootstrap.sh`, `scripts/phase6_server_qualification.sh`, `scripts/phase6_prepare_bundle.ps1`, `docs/phase6_easyuuv_v2_qualification_runbook.md`, `tests/test_easyuuv_v2_qualification_runner.py`
**Commit:** `72a223b`
**Applied fix:** The canonical server path is a `set -Eeuo pipefail` bootstrap
and qualification chain. It rejects an existing target, validates bundle/sidecar,
requires a clean clone and pinned runtime, records all runner exits, and blocks
merge/validator/hash after any failed smoke.

### CR-05: `source_commit` does not attest the code that was tested or executed

**Status:** fixed: requires human verification
**Files modified:** `workflows/qualify_easyuuv_v2.py`, `scripts/phase6_prepare_bundle.ps1`, `scripts/phase6_server_bootstrap.sh`, `tests/test_easyuuv_v2_qualification_runner.py`
**Commits:** `c090898`, `72a223b`
**Applied fix:** Runner rejects tracked drift. Bundle preparation binds current
branch tip, tested HEAD, bundle ref, and sidecar; server bootstrap requires that
sidecar to equal clone HEAD before execution and requires the initial clone to
be completely clean, including untracked files.

### CR-06: Pullback can validate stale local evidence and never asserts hash equality

**Status:** fixed: requires human verification
**Files modified:** `scripts/phase6_pullback.ps1`, `scripts/phase6_server_qualification.sh`, `workflows/easyuuv_v2_qualification_artifact.py`, `workflows/validate_easyuuv_v2_qualification.py`, `docs/phase6_easyuuv_v2_qualification_runbook.md`, `tests/test_easyuuv_v2_qualification.py`, `tests/test_easyuuv_v2_qualification_runner.py`
**Commits:** `f53a275`, `ce3e34b`
**Applied fix:** Pullback uses a new GUID staging directory, checks native SCP
and validator exits, requires one valid server SHA-256 and exact local equality,
binds source/Lab commit/tag sidecars to JSON, refuses an existing canonical
directory, and promotes only after every gate passes.

### WR-01: The server probe does not prove the four registered Gym task IDs

**Status:** fixed: requires human verification
**Files modified:** `scripts/phase6_probe_gym_tasks.py`, `scripts/phase6_server_qualification.sh`, `tests/test_easyuuv_v2_qualification_runner.py`
**Commits:** `5050651`, `005f46c`
**Applied fix:** A self-contained server probe starts AppLauncher before Gym and
`easyuuv_nc`, validates the shared USD, and resolves all four canonical IDs via
`gym.spec`; the qualification script runs it through IsaacLab and captures output.

### WR-02: An `env.close()` exception prevents simulator cleanup and row persistence

**Status:** fixed: requires human verification
**Files modified:** `workflows/qualify_easyuuv_v2.py`, `tests/test_easyuuv_v2_qualification_runner.py`
**Commit:** `b2cae7d`
**Applied fix:** Nested cleanup always attempts simulator close; cleanup failures
become stable row reason codes and force exit 1 without replacing an existing
payload or primary failure evidence.

### WR-03: Early provenance failures cannot produce the promised partial row

**Status:** fixed: requires human verification
**Files modified:** `workflows/qualify_easyuuv_v2.py`, `tests/test_easyuuv_v2_qualification_runner.py`
**Commit:** `54da926`
**Applied fix:** Failures before valid runtime/source provenance write a distinct
strict-JSON `preflight_failure` envelope marked `eligible_for_merge: false`;
post-environment partial rows retain the normal row schema.

### WR-04: Output confinement has a symlink time-of-check/time-of-use gap

**Status:** fixed: requires human verification
**Files modified:** `workflows/qualify_easyuuv_v2.py`, `tests/test_easyuuv_v2_qualification_runner.py`
**Commit:** `a137cb8`
**Applied fix:** Output resolution rejects lexical/resolved escapes and existing
symlink components, then repeats confinement validation immediately before the
atomic write while retaining Windows compatibility.

## Additional Contract Correction

`37c43f4` corrects Task 4's machine validator expectation from `pass` to the
actual `server_pass`; the separate evidence-document contract remains
`qualification_gate: pass` only after every QUAL requirement has evidence.

## Postfix Review Fixes

The postfix review was applied linearly in commit range `62050d1..5bf8a59`.

### PF-01: Full-suite basetemp escaped the ignored test-output root

**Status:** fixed: requires human verification
**Commit:** `6a3c7e5`
**Applied fix:** The runbook now uses
`.pytest-tmp/phase6-full-suite`; a static contract rejects the former
unignored `.pytest-phase6` path.

### PF-02: Server version preflight failures had no durable expected/actual evidence

**Status:** fixed: requires human verification
**Commit:** `5c7c69f`
**Applied fix:** Lab-tag and Isaac-Sim checks create the preflight/log root first,
capture command status and actual values, and persist `preflight_failure.txt`.
A dynamic Bash test proves mismatch evidence survives process failure.

### PF-03: Cached pre-AppLauncher package import could suppress Gym registration

**Status:** fixed: requires human verification
**Commit:** `82ed327`
**Applied fix:** `easyuuv_nc` is now a stdlib-only facade with explicit,
post-AppLauncher, idempotent `register_gym_tasks()`. Existing registrations are
accepted only when entry point and critical kwargs match exactly; conflicts fail
closed. The runner no longer imports Torch indirectly through the catalog, and
all app-started Gym consumers explicitly register after the launcher while v1
consumers retain their original callable entry point.

### PF-04: Editable install could contact an external package index

**Status:** fixed: requires human verification
**Commits:** `6f20141`, `5bf8a59`
**Applied fix:** The server records the Isaac-Python setuptools distribution and
runs editable install with `--no-deps --no-build-isolation --no-index`. Dynamic
fake-launcher coverage proves install failures persist command status and the
offline flags; the follow-up contract tracks the extracted helper.

### PF-05: Pullback was not bound to the current clean tested HEAD

**Status:** fixed: requires human verification
**Commit:** `b939b45`
**Applied fix:** Before staging or SCP, pullback requires local HEAD to equal the
expected commit sidecar and rejects tracked drift. Temp-repository tests prove
both failures occur before the fake SCP can execute.

### PF-06: Bundle preparation ignored untracked source and configuration files

**Status:** fixed: requires human verification
**Commit:** `164ac8b`
**Applied fix:** Bundle preparation uses default `git status --porcelain=v1`,
thereby rejecting every unignored worktree change while allowing ignored venv,
pytest, and transfer roots. A dynamic PowerShell temp-repository test proves an
untracked config blocks bundle creation.

### PF-07: Pullback clean gate still ignored untracked source files

**Status:** fixed: requires human verification
**Commit:** `82dc702`
**Applied fix:** Pullback also uses default porcelain status. Its dynamic test
commits the transfer ignore contract, leaves an untracked source/config file,
and proves rejection occurs before SCP.

### Postfix Verification Evidence

- Phase 6 targeted: `145 passed in 17.87s`
- Full collection: `320 tests collected in 7.94s`
- Full suite: `320 passed in 20.40s`
- `compileall`: exit 0
- `pip check`: `No broken requirements found.`
- Bash parse: five Phase 6 scripts passed using Git-for-Windows Bash
- PowerShell parse: prepare and pullback scripts passed
- Git: `git diff --check` passed; protected v1 paths had no diff
- Canonical server qualification/evidence/summary: all absent locally

## Skipped Issues

None.

---

_Fixed: 2026-08-10T10:24:39Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_

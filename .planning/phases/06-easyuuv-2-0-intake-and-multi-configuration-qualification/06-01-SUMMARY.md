---
phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification
plan: "01"
subsystem: packaging
tags: [setuptools, editable-install, asset-resolution, provenance, pytest, venv]

requires:
  - phase: v1.0
    provides: frozen single-configuration Koopman/PWM baseline and archived planning records
provides:
  - independently verifiable received-snapshot provenance
  - canonical editable `easyuuv_nc` package contract
  - package-confined shared USD resolver
  - Isaac-free package and v1-isolation tests
  - project-local `.venv` requirements workflow
affects: [06-02, 06-03, 06-04, phase-7]

tech-stack:
  added: [setuptools, pytest]
  patterns: [editable package discovery, package-root asset resolution, local Isaac-free venv]

key-files:
  created: [pyproject.toml, requirements-dev.txt, easyuuv_nc/package_paths.py, easyuuv_nc/SNAPSHOT_PROVENANCE.md, tests/test_easyuuv_v2_package.py]
  modified: [.gitignore, easyuuv_nc/env/assets/warpauv.py]

key-decisions:
  - "Use easyuuv_nc as the only physical package/import identity after the immutable snapshot commit."
  - "Resolve assets from PACKAGE_ROOT and reject absolute paths or resolved traversal."
  - "Keep local dependencies in .venv through requirements-dev.txt; provision Isaac separately on the server."

patterns-established:
  - "Received snapshot first, integration commit later: provenance is a Git boundary, not a comment-only claim."
  - "Package assets are resolved from __file__, never from the process current working directory."
  - "Local Phase 6 validation remains Isaac-free and cannot be labelled as server physics evidence."

requirements-completed: [QUAL-01, QUAL-03, QUAL-07]

duration: 23min
completed: 2026-08-09
---

# Phase 6 Plan 01: EasyUUV Package Intake Summary

**The received simulator is now an auditable `easyuuv_nc` editable package with package-confined USD lookup, local venv setup and executable v1-isolation contracts.**

## Performance

- **Duration:** 23 min
- **Started:** 2026-08-09T16:35:12+08:00
- **Completed:** 2026-08-09T16:58:02+08:00
- **Tasks:** 3
- **Files modified:** 142 tracked paths (136 exact renames, 5 additions and package/config modifications)

## Accomplishments

- Proved snapshot commit `7ba24993663e1603f5d10c7bd624c8d0f203ed8d` adds exactly 136 files and no path outside `easyuuv_v2-main/`, then normalized that tracked tree with `git mv`.
- Added a reproducible setuptools editable-install contract for only `easyuuv_nc*`, with explicit embodiment USD/YAML package data.
- Replaced current-working-directory-dependent USD lookup with an absolute, package-confined resolver that rejects absolute paths and parent traversal.
- Added a project-local `.venv` workflow through `requirements-dev.txt`; Isaac Sim and Isaac Lab remain separately provisioned server dependencies.
- Locked four Gym IDs and the unchanged v1 `PWM_DIM`/`[-1,1]` MPC contract with Isaac-free tests.

## Task Commits

1. **Task 1: Verify snapshot boundary and normalize the tracked directory** — `f2e660e` (chore)
2. **Task 2/3 TDD RED: Lock the package, asset and v1-isolation contract** — `8b8c7e0` (test)
3. **Task 2 GREEN: Add canonical packaging and package-confined asset resolution** — `d916a12` (feat)

_Task 3's committed RED contract was rerun after the GREEN implementation; TDD intentionally places its test commit before production code._

## Files Created/Modified

- `easyuuv_nc/SNAPSHOT_PROVENANCE.md` — records received path, canonical path and the 40-character immutable snapshot commit.
- `pyproject.toml` — defines `easyuuv-nc` 2.0.0 and `easyuuv_nc*` editable package discovery.
- `requirements-dev.txt` — installs the editable package and pytest into the local, Isaac-free venv.
- `.gitignore` — excludes `.venv`, local pytest scratch data and editable-install metadata.
- `easyuuv_nc/package_paths.py` — resolves existing package assets and rejects path escape.
- `easyuuv_nc/env/assets/warpauv.py` — passes the canonical absolute USD path to `UsdFileCfg`.
- `tests/test_easyuuv_v2_package.py` — verifies packaging, cross-cwd import/asset behavior, Gym IDs and v1 isolation.

## Verification Evidence

- `.venv\Scripts\python.exe -m pip install -e . --no-deps` — passed; editable location is the repository root.
- Repository-root package probe — `easyuuv_nc/__init__.py` and `easyuuv_nc/data/embodiment/embodiment.usd` resolved successfully.
- External-cwd probe with `python -E` — passed without `PYTHONPATH`; the same canonical package and USD paths resolved.
- `.venv\Scripts\python.exe -m pytest -q tests/test_easyuuv_v2_package.py` — `7 passed`.
- Package test plus v1 source contracts — `21 passed`.
- `.venv\Scripts\python.exe -m compileall easyuuv_nc tests/test_easyuuv_v2_package.py` — passed with bytecode redirected to ignored local scratch storage.
- `git diff v1.0 -- .planning/milestones .planning/reports koopman/model.py koopman/mpc.py` — empty.

## Threat-Model Disposition

| Threat | Disposition | Evidence |
|---|---|---|
| Integration mixed into the received snapshot | Mitigated | Snapshot commit has exactly 136 paths, all under `easyuuv_v2-main/`; normalization is later commit `f2e660e`. |
| Broad move/delete damages retained evidence | Mitigated | Exact absolute paths were checked, destination was absent, `git mv` was used, and the commit reports 136 100% renames with no deletions. |
| Asset path escapes the package or depends on cwd | Mitigated | Resolver rejects absolute/traversal paths; package and USD resolve from an external cwd. |
| Packaging captures source/results/planning/v1 modules | Mitigated | setuptools discovery is restricted to `include = ["easyuuv_nc*"]` and executable tests inspect the contract. |

No HIGH threat remains unresolved.

## Decisions Made

- Used a conventional root `pyproject.toml` editable install because it gives the server one explicit package identity and keeps asset paths tied to the installed source tree.
- Kept local requirements intentionally small and Isaac-free. A successful local install/test is package-contract evidence, not an Isaac rollout.
- Kept the v1 8D PWM model/MPC files untouched; cross-configuration 4D virtual control remains deferred to Phase 7.

## Deviations from Plan

### Execution-order adjustment

- **Reason:** The project has TDD mode enabled and the selected TDD workflow requires a failing behavior contract before production code.
- **Adjustment:** Wrote and committed the Task 3 package contract before implementing Task 2, then reran it after GREEN.
- **Impact:** No functional scope change; the same planned files and acceptance criteria were delivered.

### User-directed local environment setup

- **Reason:** A global/user-site editable install is not a reproducible project boundary, and the user requested a local venv plus requirements configuration.
- **Adjustment:** Added `.venv` ignore rules and `requirements-dev.txt`, then installed and verified inside the project venv.
- **Impact:** Improves reproducibility without adding Isaac or runtime dependencies to the package.

### Auto-fixed blocking test environment

- **Rule 3 — Blocking issue:** The sandbox denied pytest's default Windows system-temp directory.
- **Fix:** The cross-cwd test uses ignored repository-local `.pytest-tmp` storage and cleans its temporary child directory.
- **Committed in:** `8b8c7e0`.

**Total deviations:** 3 (1 TDD order adjustment, 1 user-directed environment addition, 1 blocking test-environment fix). No architecture or research-scope change.

## Issues Encountered

- A first sandboxed requirements install could not reach PyPI; after scoped network approval, installation into `.venv` succeeded.
- Generic `python` resolution was inconsistent across shell working directories. All authoritative verification now calls the project venv interpreter explicitly.
- The received snapshot contains existing whitespace warnings and tracked bytecode; these were preserved in the immutable snapshot rather than silently reformatted or deleted.

## User Setup Required

For local Phase 6 package-contract work:

```powershell
E:\anaconda\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

No external service configuration is required. Isaac Sim/Isaac Lab setup remains part of the later server runbook and is not satisfied by this local venv.

## Self-Check

- All declared created/modified files exist.
- Task commits `f2e660e`, `8b8c7e0` and `d916a12` exist.
- Git worktree is clean after tests and compileall.
- Snapshot hash and protected v1 paths were revalidated.
- Result: **PASS**.

## Next Phase Readiness

- Wave 1 is complete; `06-02-PLAN.md` and `06-03-PLAN.md` are unblocked for catalog/TAM and artifact-validator TDD.
- No Isaac physics evidence was generated or claimed. Phase 6 remains open until Wave 3 server evidence and final verification are complete.

---
*Phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification*
*Completed: 2026-08-09*

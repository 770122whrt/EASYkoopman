---
phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification
plan: "02"
subsystem: embodiment-catalog-and-thrust-allocation
tags: [torch, tam, controllability, catalog, tdd, isaac-free]

requires:
  - phase: 06-01
    provides: canonical editable easyuuv_nc package, immutable snapshot provenance and local venv
provides:
  - exact eight-name public embodiment catalog with heavy_duty retained as internal-only
  - Isaac-free 8/6/4-thruster topology, control-mask and declared-control-rank report
  - one shared configuration source consumed by the environment and both public CLIs
  - executable deep-equality proof against the immutable received snapshot
affects: [06-03, 06-04, phase-7, koopman-bridge]

tech-stack:
  added: [torch-2.8.0, numpy-1.26.4]
  patterns: [single-source embodiment catalog, pure Torch TAM API, compatibility re-export, snapshot-backed drift test]

key-files:
  created: [easyuuv_nc/embodiments.py, easyuuv_nc/thrust_allocation.py, tests/test_easyuuv_v2_catalog.py]
  modified: [easyuuv_nc/env/thrust_allocation.py, easyuuv_nc/env/easyuuv_env.py, easyuuv_nc/workflows/train.py, easyuuv_nc/workflows/adapt.py, requirements-dev.txt]

key-decisions:
  - "D-04/D-07: expose exactly eight public names in roll,pitch,yaw,depth qualification order; keep heavy_duty internal."
  - "D-08/D-09: derive counts, masks and ranks from actual legacy mixing or declared TAM geometry; uuv4 yaw remains unavailable."
  - "D-14: move configuration ownership only; do not alter v1 Koopman state/reference/PWM semantics."
  - "Pin local contract verification to Torch 2.8.0 and NumPy 1.26.4 after the unconstrained Torch wheel failed DLL initialization."

patterns-established:
  - "Runtime and CLIs import embodiment facts from easyuuv_nc.embodiments instead of duplicating literal lists."
  - "Qualification uses easyuuv_nc.thrust_allocation without importing Isaac/Omni."
  - "Configuration extraction is accepted only when all nine payloads deep-equal the Git snapshot source."

requirements-completed: [QUAL-02, QUAL-04, QUAL-07]

duration: 35min active across 2 sessions
completed: 2026-08-10
---

# Phase 6 Plan 02: Canonical Embodiment Catalog and TAM Summary

**All eight public EasyUUV 2.0 configurations now share one catalog and an Isaac-free topology report that proves exact 8/6/4 motor counts and explicit `uuv4*` yaw underactuation without changing the v1 Koopman contract.**

## Performance

- **Duration:** approximately 35 min active across two sessions
- **Started:** 2026-08-09T17:37:58+08:00
- **Completed:** 2026-08-10T15:58:44+08:00
- **Tasks:** 3 TDD gates
- **Files modified:** 8 unique source/test/dependency files

## Accomplishments

- Extracted all nine received payloads into `EMBODIMENT_CONFIGS`, while exposing the exact eight public configurations through `SUPPORTED_EMBODIMENTS` and keeping `heavy_duty` internal.
- Moved the Torch-only thrust-allocation implementation to a top-level Isaac-free module and retained `easyuuv_nc.env.thrust_allocation` as compatibility re-exports only.
- Rewired `EasyUUVEnvCfg`, `train.py` and `adapt.py` to the same catalog, removing the duplicated public CLI list.
- Added deterministic records for motor count, allocation mode, channel order, control mask and declared-control rank.
- Added a Git-backed AST comparison proving every scalar, list and nested `thrust_allocation` value equals the immutable snapshot commit.

## Exact Qualification Matrix

| Configuration | Thrusters | Mask `[roll,pitch,yaw,depth]` | Declared rank |
|---|---:|---|---:|
| `base` | 8 | `[1,1,1,1]` | 4 |
| `long_body` | 8 | `[1,1,1,1]` | 4 |
| `heavy_moderate` | 8 | `[1,1,1,1]` | 4 |
| `asymmetric` | 8 | `[1,1,1,1]` | 4 |
| `uuv6` | 6 | `[1,1,1,1]` | 4 |
| `uuv6_angled` | 6 | `[1,1,1,1]` | 4 |
| `uuv4` | 4 | `[1,1,0,1]` | 3 |
| `uuv4_angled` | 4 | `[1,1,0,1]` | 3 |

## Task Commits

1. **RED: Specify exact catalog, topology and consumer behavior** — `9237e3c` (`test`); failed as intended with `ModuleNotFoundError: easyuuv_nc.embodiments`.
2. **GREEN: Extract the catalog/TAM and wire all consumers** — `fcd804a` (`feat`); targeted catalog suite passed `13 passed`.
3. **REFACTOR: Prove zero configuration drift and returned-record isolation** — `0dc2dc1` (`refactor`); final catalog plus source-contract suite passed `29 passed`.

## Files Created/Modified

- `easyuuv_nc/embodiments.py` — canonical public/internal names, all nine received payloads and qualification records.
- `easyuuv_nc/thrust_allocation.py` — pure Torch quaternion, TAM, allocation and declared-rank APIs.
- `easyuuv_nc/env/thrust_allocation.py` — compatibility re-exports; no duplicate implementation remains.
- `easyuuv_nc/env/easyuuv_env.py` — assigns `EasyUUVEnvCfg.embodiment_configs = EMBODIMENT_CONFIGS`.
- `easyuuv_nc/workflows/train.py` and `adapt.py` — use `choices=SUPPORTED_EMBODIMENTS`.
- `tests/test_easyuuv_v2_catalog.py` — exact matrix, consumer, snapshot equality and mutation-isolation contracts.
- `requirements-dev.txt` — explicit local Torch 2.8.0 and NumPy 1.26.4 dependencies.

## Verification Evidence

- `.venv\Scripts\python.exe -m pytest -q tests/test_easyuuv_v2_catalog.py` — **15 passed** after REFACTOR.
- `.venv\Scripts\python.exe -m pytest -q tests/test_easyuuv_v2_catalog.py tests/test_isaaclab2_source_contract.py tests/test_phase1_source_contract.py` — **29 passed**.
- `.venv\Scripts\python.exe -m pip check` — **No broken requirements found**.
- `.venv` imports `torch 2.8.0+cpu` from `.venv\Lib\site-packages`, not the user site.
- `rg -F 'choices=["base", "long_body"' easyuuv_nc/workflows` — no matches.
- `git diff 1161341..HEAD -- koopman/model.py koopman/mpc.py .planning/milestones .planning/reports` — empty.

## Threat-Model Disposition

| Threat | Result | Evidence |
|---|---|---|
| Numeric payload drift during extraction | Mitigated | Snapshot-backed deep equality covers all nine payloads. |
| `uuv4*` reported with yaw/rank 4 | Mitigated | Exact matrix requires mask `[1,1,0,1]` and rank 3. |
| `heavy_duty` exposed publicly | Mitigated | Exact public/internal assertions and CLI shared tuple. |
| Pure qualification accidentally depends on Isaac | Mitigated locally | The 29-test command runs without Isaac/Omni installed. |

No HIGH plan threat remains open at the local-contract evidence level.

## Decisions Made

- Used the actual legacy 8x4 motor mixing matrix for the four legacy payloads and the actual `thrust_allocation.specs` geometry for 6/4-thruster payloads; ranks are computed, not hard-coded.
- Preserved `env.thrust_allocation` imports through explicit re-exports so existing consumers remain compatible while new qualification code imports the pure top-level module.
- Kept local Torch/NumPy pins in `requirements-dev.txt`; Isaac server dependency versions remain governed separately by the server environment.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Local venv omitted the planned Torch dependency**
- **Found during:** GREEN verification.
- **Issue:** `.venv` could not import `easyuuv_nc.thrust_allocation` because `requirements-dev.txt` contained only pytest.
- **Fix:** Declared and installed Torch 2.8.0 plus NumPy 1.26.4 inside the isolated project venv.
- **Files modified:** `requirements-dev.txt`.
- **Verification:** Torch resolves from `.venv`; `pip check` is clean; all targeted tests pass without warnings.
- **Committed in:** `fcd804a`.

**2. [Rule 3 — Blocking] Unbounded Torch selection installed a DLL-incompatible future wheel**
- **Found during:** dependency repair verification.
- **Issue:** Torch 2.13.0 installed successfully but failed at runtime with Windows `c10.dll` error 1114.
- **Fix:** Pinned the already proven local-compatible `torch==2.8.0`; added matching tested NumPy.
- **Verification:** `torch 2.8.0+cpu` imports from `.venv`, `pip check` reports no broken requirements and tests pass.
- **Committed in:** `fcd804a`.

**Total deviations:** 2 blocking environment issues auto-fixed. **Impact:** local reproducibility improved; no architecture, simulator physics or Koopman scope was added.

## Issues Encountered

- LunaMax routing still rejected `gpt-5.6-luna`; the Terra executor completed RED but then hit its usage limit. The main executor continued from the committed RED and audited the partial GREEN files before accepting them.
- The first long pip install outlived the outer command timeout; completion was tracked by the actual child process before any verification was attempted.

## User Setup Required

None for local contract work. Recreate the environment with:

```powershell
E:\anaconda\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Isaac Sim/Isaac Lab remain separate server dependencies and are not implied by these local tests.

## Self-Check

- RED `9237e3c` precedes GREEN `fcd804a`; REFACTOR `0dc2dc1` follows.
- All three created files exist.
- All task acceptance criteria and plan verification commands pass.
- v1 Koopman model/MPC and frozen archives are absent from the plan diff.
- Git worktree was clean before this summary was created.
- Result: **PASSED**.

## Next Phase Readiness

- `06-03` can consume the exact catalog constants while defining strict qualification artifact validation.
- `06-04` can later attach server Isaac telemetry to these topology facts; no server physics evidence is claimed here.
- `requirements-completed` records this plan's local contribution only; Phase 6 remains open until the server checkpoint and phase verification succeed.

---
*Phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification*
*Completed: 2026-08-10*

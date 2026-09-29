---
phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification
reviewed: 2026-08-10T09:42:01Z
depth: deep
files_reviewed: 4
files_reviewed_list:
  - workflows/qualify_easyuuv_v2.py
  - workflows/merge_easyuuv_v2_qualification.py
  - tests/test_easyuuv_v2_qualification_runner.py
  - docs/phase6_easyuuv_v2_qualification_runbook.md
findings:
  critical: 6
  warning: 4
  info: 0
  total: 10
status: issues_found
---

# Phase 06-04: Code Review Report

**Reviewed:** 2026-08-10T09:42:01Z
**Depth:** deep
**Files Reviewed:** 4 primary files, with runner-to-validator and server-runbook dependencies traced
**Status:** issues_found

## Summary

The exact-eight set checks and the normal finite success path are present, but the submitted implementation is not ready for the one-shot unchanged-server run. Six blockers can either lose mandatory failure evidence, run the wrong server entrypoint/content, or let the pullback gate validate evidence without the promised provenance chain. Four additional robustness and contract gaps should also be closed before requesting server power-on.

Two behaviors were reproduced independently during review:

- A telemetry summary containing `inf` reports `nonfinite_count > 0` but then fails `json.dumps(..., allow_nan=False)`, so the intended failure row cannot be written.
- Removing `runtime_provenance` from an otherwise valid exact-eight artifact still makes the public strict validator return `qualification_gate=server_pass`.

## Critical Issues

### CR-01 (BLOCKER): Non-finite telemetry destroys the failure artifact it is supposed to preserve

**File:** `workflows/qualify_easyuuv_v2.py:134-146`

**Issue:** `summarize_actual_telemetry` counts NaN/Inf, but also feeds those values directly into `min`/`max`. For an infinite motor value the returned `motor_max` is `inf`; `_merge_step_summary` stores it in the row, then `run_isaac_qualification` marks the row failed. The later atomic writer uses `allow_nan=False` at line 245, raises `ValueError`, and writes no JSON. This violates the plan and runbook requirement to preserve every failed/partial row. The existing test at `tests/test_easyuuv_v2_qualification_runner.py:183` asserts only the count and therefore misses the serialization failure.

**Fix:** Separate detection from serializable aggregation: compute extrema only over finite values, use a documented finite sentinel when no finite sample exists, preserve the non-finite count/reason, and add an end-to-end test that writes and reloads a failed row containing injected NaN/Inf telemetry.

### CR-02 (BLOCKER): The eight server commands bypass the server's required IsaacLab launcher

**File:** `docs/phase6_easyuuv_v2_qualification_runbook.md:78-84`

**Issue:** The runbook activates Conda and invokes bare `python` for installation/probes and all eight smokes (lines 104-125). The repository's established unchanged-server contract explicitly requires running Isaac workloads from `/root/IsaacLab` via `./isaaclab.sh -p`; prior validation documents bare-Python failures involving missing `omni` bootstrap state. These commands therefore are not copyable against the server the user said must remain unchanged.

**Fix:** Use `/root/IsaacLab/isaaclab.sh -p` for the package probe and all eight runner invocations. Because the wrapper is launched outside the project checkout, pass the runner, result root, row output and log paths as absolute `/root/EASYkoopman-phase6-v2/...` paths. Add a static contract test that rejects bare `python ...qualify_easyuuv_v2.py` server commands.

### CR-03 (BLOCKER): A pulled artifact can pass the strict validator after provenance is removed

**File:** `workflows/merge_easyuuv_v2_qualification.py:151-161`

**Issue:** The merger validates `runtime_provenance` before writing, but then delegates the final gate to `validate_qualification_payload`, whose required top-level fields and checks do not include `runtime_provenance`. Consequently the second, independent pullback validation is not actually independent: an artifact with the complete provenance object deleted still returns `server_pass` (reproduced during review). In addition, the merger's own check establishes only syntactic/self-consistency of tag, distribution and a 40-hex commit; it cannot prove server origin once the JSON is detached from the Git repository.

**Fix:** Make `runtime_provenance` required and structurally validated by the public strict validator, including the release-tag/semantic-version relationship. Preserve the trust limit explicitly: bind the artifact to the transferred expected source commit and server-recorded IsaacLab tag commit/hash, then verify those values again after pullback instead of treating self-declared JSON as non-forgeable.

### CR-04 (BLOCKER): Claimed server setup gates do not stop the shell

**File:** `docs/phase6_easyuuv_v2_qualification_runbook.md:71-84`

**Issue:** `test ! -e`, both version `test` commands, clone, `cd`, install and probes are independent interactive-shell commands. There is no `set -euo pipefail`, guarded function, or `&&` chain. A failed isolation check can therefore be followed by a failed clone and then a `cd` into a pre-existing checkout; version-gate failures can also be followed by qualification commands. This contradicts the text that calls them blocking gates and can run evidence from stale server content.

**Fix:** Package setup/execution as a fail-closed Bash script (`set -euo pipefail`) or check every exit explicitly. Refuse an existing target directory unless it has been inspected and its exact expected commit is supplied; never continue after clone, `cd`, version, install or package-probe failure.

### CR-05 (BLOCKER): `source_commit` does not attest the code that was tested or executed

**File:** `workflows/qualify_easyuuv_v2.py:224-231`

**Issue:** The runner records only `git rev-parse HEAD`; it never rejects tracked modifications. The local runbook merely prints `git status --short` before bundling (lines 52-55), while the server also merely prints status/HEAD (lines 75-76). It never proves that the branch bundled equals the locally tested HEAD or that the isolated server HEAD equals that expected commit. A dirty editable checkout can therefore execute changed Python/assets while recording an unrelated clean commit hash, and a stale branch ref can be bundled despite tests having run against working-tree changes.

**Fix:** Fail the runner on tracked worktree changes, make local preflight assert a clean tree and `HEAD == v2.0-multi-configuration`, transfer the expected commit in a sidecar, and require the server clone's `HEAD` to equal it before install or execution. Record the same value in every row and evidence file.

### CR-06 (BLOCKER): Pullback can validate stale local evidence and never asserts hash equality

**File:** `docs/phase6_easyuuv_v2_qualification_runbook.md:163-166`

**Issue:** PowerShell does not automatically stop on a native `scp` failure. The runbook copies into a reusable `source/results/koopman_phase6` path, prints the local hash and server hash file, and then validates whatever file is present. It never compares the two hashes programmatically. If transfer fails or partially updates an existing directory, the following commands can hash and validate a stale artifact and satisfy the visible gate.

**Fix:** Pull into a new, empty staging directory, check `$LASTEXITCODE` after `scp` and validator commands, parse both SHA-256 values, and `throw` unless they are identical. Only promote the staged directory to the canonical evidence path after hash equality and strict validation both pass.

## Warnings

### WR-01 (WARNING): The server probe does not prove the four registered Gym task IDs

**File:** `docs/phase6_easyuuv_v2_qualification_runbook.md:83-84`

**Issue:** The probe proves only importability and the shared USD file. The Phase 6 verification contract explicitly requires confirming all four registered Gym IDs on the server, but no server command enumerates or resolves them. Eight runs of one task ID do not prove the other three registrations.

**Fix:** After AppLauncher startup through `isaaclab.sh -p`, import `easyuuv_nc` and assert `gym.spec(...)` succeeds for all four required IDs; capture that output in the evidence directory.

### WR-02 (WARNING): An `env.close()` exception prevents simulator cleanup and row persistence

**File:** `workflows/qualify_easyuuv_v2.py:369-372`

**Issue:** `env.close()` and `simulation_app.close()` are sequential in one `finally`. If the environment close raises, the simulator close is skipped and the pending function return is replaced by the cleanup exception, so even an already-constructed pass/fail payload is never written by `main`.

**Fix:** Use nested `try/finally` so `simulation_app.close()` always runs, preserve the primary result/error, and convert cleanup failure into a serializable row reason or stderr diagnostic without losing existing evidence.

### WR-03 (WARNING): Early provenance failures cannot produce the promised partial row

**File:** `workflows/qualify_easyuuv_v2.py:314-322`

**Issue:** Runtime provenance and source-commit detection execute before `_empty_row` and outside the inner exception handler. Missing metadata, an unexpected tag, or source Git failure exits through `main` with only stderr; no per-configuration JSON exists even though the runbook says version drift and partial rows are preserved as failure evidence.

**Fix:** Construct the catalog row before fallible provenance checks and write a failure envelope with explicit provenance/source reason codes when possible. If the schema intentionally forbids such a row, revise the runbook to distinguish preflight failures from post-environment partial rows and capture a machine-readable preflight-failure artifact.

### WR-04 (WARNING): Output confinement has a symlink time-of-check/time-of-use gap

**File:** `workflows/qualify_easyuuv_v2.py:84-92`

**Issue:** The path is resolved and checked once, then its parent is created and used later by `_atomic_write_json`. A writable parent component can be swapped for a symlink after validation, causing the temporary file and replacement to land outside the approved result root. Fixed runbook paths reduce exposure, but the CLI threat boundary explicitly includes output paths.

**Fix:** Revalidate the parent immediately before writing and use directory-handle-relative operations with no-follow semantics where available; at minimum reject symlinked components and keep creation/write within a trusted, non-user-writable result root.

---

_Reviewed: 2026-08-10T09:42:01Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_

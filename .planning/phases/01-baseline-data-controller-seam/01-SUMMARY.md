---
phase: 01-baseline-data-controller-seam
plan: 01
subsystem: control-data
tags: [easyuuv, koopman, mpc, isaac, jsonl, controller-boundary]
status: local_ready_isaac_gate_pending

requires: []
provides:
  - legacy controller boundary with explicit controller_mode
  - pre-thrust 8D PWM cache
  - offline-readable Koopman JSONL data schema
  - direct-controller data collection path without PPO checkpoint
  - trajectory logging hooks for step, sine and irregular workflows
affects: [phase-2-offline-koopman-identification, phase-3-koopman-mpc-controller]

tech-stack:
  added: [python-jsonl, pytest]
  patterns: [offline-first schema helper, Isaac-gated workflow logging]

key-files:
  created:
    - koopman_data.py
    - workflows/koopman_logging.py
    - tests/test_koopman_data.py
    - tests/test_phase1_source_contract.py
  modified:
    - easyuuv_env.py
    - workflows/play_controller.py
    - workflows/play_eval.py
    - workflows/play_eval_step.py
    - workflows/play_eval_task2.py
    - docs/koopman_mpc_migration_plan.md

key-decisions:
  - "Phase 1 keeps controller_mode='legacy' as the default and reserves koopman_mpc for Phase 3."
  - "Koopman logs use pre-thrust PWM as u_k so Phase 2 can train from actuator commands without Isaac imports."
  - "play_controller.py is the first server data path and no longer requires a PPO checkpoint."

patterns-established:
  - "Pure Python data helpers are tested locally; Isaac rollout remains a server gate."
  - "Workflow logs all emit the same JSONL schema across trajectory types."

requirements-completed: []
requirements-local-ready: [BASE-01, BASE-02, BASE-03, BASE-04, DATA-01, DATA-02, DATA-03]

duration: 1h
completed: 2026-06-29
---

# Phase 1 Plan 1: Baseline Data And Controller Boundary Summary

**Legacy EasyUUV control is now wrapped with an explicit boundary and an offline-readable Koopman data schema, ready for the first Isaac server rollout.**

## Status

- **Local status:** Ready at Isaac Gate.
- **Phase status:** Not fully complete until a server Isaac rollout produces at least one real JSONL log.
- **Started:** 2026-06-29T21:29:15+08:00
- **Completed local work:** 2026-06-29T22:34:44+08:00
- **Tasks addressed locally:** 5/5
- **Files modified:** 11

## Accomplishments

- Preserved legacy `Ssurface` / `PID` behavior by keeping `control_method` intact and adding `controller_mode = 'legacy'` above it.
- Cached `_last_pwm_8d` before dead-zone and thrust-polynomial conversion in `_compute_dynamics()`.
- Added `koopman_data.py` for JSONL sample construction, validation, loading and `(x_k, u_k, r_k, x_{k+1})` replay.
- Added `workflows/koopman_logging.py` so direct and PPO workflows share the same state/reference/PWM logging path.
- Changed `workflows/play_controller.py` into a direct-controller rollout path that does not load PPO checkpoints.
- Added consistent Koopman logging hooks to the sine, step and irregular evaluation scripts.

## Verification

Local checks run:

```powershell
python -m pytest -p no:cacheprovider --capture=no tests -q
# 5 passed in 0.05s
```

```powershell
python -m compileall -q easyuuv_env.py koopman_data.py workflows\koopman_logging.py workflows\play_controller.py workflows\play_eval.py workflows\play_eval_step.py workflows\play_eval_task2.py
# exit code 0
```

Isaac checks not run locally:

```bash
./isaaclab.sh -p <EasyUUV-path>/workflows/play_controller.py --task EasyUUV-Direct-v1 --num_envs 1 --headless
```

Reason: local workstation cannot run Isaac Sim/Lab reliably. This is the intended Isaac Gate.

## Files Created/Modified

- `koopman_data.py` - Pure Python Koopman sample schema, JSONL writer/reader and replay tuple reconstruction.
- `workflows/koopman_logging.py` - Isaac workflow adapter for state/reference/PWM logging.
- `tests/test_koopman_data.py` - Local schema round-trip and control length tests.
- `tests/test_phase1_source_contract.py` - Local source-contract guard for controller boundary and workflow logging hooks.
- `easyuuv_env.py` - Added `controller_mode` and `_last_pwm_8d` cache before thrust conversion.
- `workflows/play_controller.py` - Direct-controller JSONL logging without PPO checkpoint load.
- `workflows/play_eval.py` - Sine trajectory JSONL logging.
- `workflows/play_eval_step.py` - Step trajectory JSONL logging.
- `workflows/play_eval_task2.py` - Irregular trajectory JSONL logging.
- `docs/koopman_mpc_migration_plan.md` - Updated Phase 1 local handoff and Isaac Gate notes.

## Deviations from Plan

None - implementation stayed inside Phase 1 boundaries. EDMD, MPC and Kalman update were not implemented.

## Issues Encountered

- Local pytest initially failed because the restricted sandbox could not create temporary files. Re-ran pytest with approved escalation and captured the intended RED failure (`ModuleNotFoundError: No module named 'koopman_data'`) before implementing the helper.
- Isaac rollout was not attempted locally by design.

## Isaac Gate

Run on the server:

```bash
./isaaclab.sh -p <EasyUUV-path>/workflows/play_controller.py --task EasyUUV-Direct-v1 --num_envs 1 --headless
```

Expected artifact:

```text
source/results/direct_controller/<eval_controller_timestamp>/koopman_step.jsonl
```

Then verify offline:

```python
from koopman_data import load_koopman_samples, reconstruct_training_tuples

samples = load_koopman_samples("path/to/koopman_step.jsonl")
tuples = reconstruct_training_tuples(samples)
```

## Next Phase Readiness

Phase 2 can begin EDMD code once the server produces at least one real JSONL log. Until that happens, only synthetic/local schema tests are validated.

---
*Phase: 01-baseline-data-controller-seam*
*Local handoff completed: 2026-06-29*

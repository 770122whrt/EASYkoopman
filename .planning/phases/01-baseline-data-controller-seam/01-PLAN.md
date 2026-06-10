---
phase: 1
plan: 1
title: "Baseline Data And Controller Boundary"
type: implementation
wave: 1
depends_on: []
files_modified:
  - easyuuv_env.py
  - workflows/play_controller.py
  - workflows/play_eval.py
  - workflows/play_eval_step.py
  - workflows/play_eval_task2.py
  - docs/koopman_mpc_migration_plan.md
autonomous: true
requirements:
  - BASE-01
  - BASE-02
  - BASE-03
  - BASE-04
  - DATA-01
  - DATA-02
  - DATA-03
---

<objective>
Prepare EasyUUV for Koopman+MPC by preserving the legacy controller baseline, exposing a safe controller boundary, and defining a consistent data collection path for offline Koopman identification.
</objective>

<context>
Phase 1 intentionally does not implement EDMD, MPC, or online Kalman updates. It creates the stable seam needed for later phases. The current code already has the critical physics path in `easyuuv_env.py`: 4D action -> `_pid_control()` -> 8D PWM -> `_compute_dynamics()` -> Isaac force/torque.
</context>

<tasks>

## Task 1 - Document and protect the legacy controller path

**Type:** audit + regression guard  
**Files:** `easyuuv_env.py`, `docs/koopman_mpc_migration_plan.md`

**Action:**
1. Identify the exact legacy control semantics for `Ssurface` and `PID`.
2. Document the 4D action meaning and 8D thruster order.
3. Add the smallest possible internal structure needed to avoid changing legacy output while making future controller modes explicit.

**Verify:**
- Inspect that legacy `control_method = 'Ssurface'` remains the default.
- Confirm 8D PWM clipping remains `[-1, 1]`.
- Confirm `_compute_dynamics()` still applies the original dead zone and thrust polynomial.

**Acceptance criteria:**
- Legacy path can still be followed from `_pre_physics_step()` to `_apply_action()`.
- No water dynamics or thruster geometry behavior is changed in this task.

## Task 2 - Define controller mode and PWM visibility

**Type:** implementation  
**Files:** `easyuuv_env.py`

**Action:**
1. Add a controller-mode boundary that can later route to legacy or Koopman+MPC.
2. Cache current-step 8D PWM before thrust polynomial conversion.
3. Keep legacy mode as the only active implementation in Phase 1 if Koopman+MPC is not ready.

**Verify:**
- One simulation step produces a cached PWM tensor with shape `(num_envs, 8)`.
- Cached PWM values are before dead-zone and thrust-polynomial conversion.
- Legacy `Ssurface` behavior remains selected by default.

**Acceptance criteria:**
- Future Koopman+MPC can return 8D PWM without rewriting `_compute_dynamics()`.
- Data logger can read the PWM for each step.

## Task 3 - Define and implement the data logging schema

**Type:** implementation  
**Files:** `workflows/play_controller.py`, optional shared workflow helper

**Action:**
1. Define a row schema with `t`, `state`, `reference`, `action_4d`, `pwm_8d`, `next_state`.
2. Start with `play_controller.py` because it does not require PPO checkpoint loading.
3. Save logs in a deterministic location under `source/results` or a project-local `logs/koopman_data` path.

**Verify:**
- Run a short direct-controller rollout in an Isaac Lab environment.
- Confirm the output file contains all required fields.
- Confirm consecutive rows can reconstruct `(x_k, u_k, r_k, x_{k+1})`.

**Acceptance criteria:**
- A downstream EDMD script can load the file without needing Isaac Sim.
- Logs include both current state and next state.

## Task 4 - Extend trajectory coverage plan

**Type:** implementation + documentation  
**Files:** `workflows/play_eval.py`, `workflows/play_eval_step.py`, `workflows/play_eval_task2.py`, `docs/koopman_mpc_migration_plan.md`

**Action:**
1. Reuse existing sine, step and irregular goal generation.
2. Make all three paths emit the same data schema.
3. Document which trajectory is intended for baseline, excitation and stress testing.

**Verify:**
- Each workflow has a documented path to produce the same schema.
- Field names remain consistent across all trajectories.

**Acceptance criteria:**
- Phase 2 can train on multiple trajectory types without per-file adapters.

## Task 5 - Phase 1 verification summary

**Type:** verification  
**Files:** `.planning/phases/01-baseline-data-controller-seam/01-SUMMARY.md`

**Action:**
1. Summarize code changes and data schema.
2. Record commands that were run and commands that require Isaac Sim/Lab.
3. Mark unresolved environment dependencies as `待确认`.

**Verify:**
- Summary lists pass/fail status for all Phase 1 acceptance criteria.
- Any unrun Isaac command is explicitly marked with reason.

**Acceptance criteria:**
- Phase 2 can begin from the summary without rediscovering Phase 1 decisions.

</tasks>

<verification>
Run lightweight static checks first:

```powershell
python -m py_compile easyuuv_env.py workflows\play_controller.py workflows\play_eval.py workflows\play_eval_step.py workflows\play_eval_task2.py
```

Expected result: Python syntax succeeds in the active environment. If Isaac imports are unavailable outside Isaac Lab, document the limitation and run syntax checks inside the Isaac Lab Python environment instead.

Run Isaac validation when the simulator environment is available:

```bash
./isaaclab.sh -p source/standalone/workflows/rsl_rl/train.py --task EasyUUV-Direct-v1 --num_envs 4 --headless --max_iterations 1
```

Expected result: Environment can instantiate and step without breaking the legacy controller path.

Run direct data collection when Phase 1 logging is implemented:

```bash
./isaaclab.sh -p <EasyUUV-path>/workflows/play_controller.py --task EasyUUV-Direct-v1 --num_envs 1 --headless
```

Expected result: A data log is produced with the Phase 1 schema.
</verification>

<success_criteria>
- Legacy controller behavior remains available and default.
- Controller boundary is explicit enough for Phase 3 Koopman+MPC integration.
- PWM is observable before thrust conversion.
- Data schema supports offline EDMD training.
- Direct controller path can generate data without PPO.
- All limitations are documented instead of hidden.
</success_criteria>

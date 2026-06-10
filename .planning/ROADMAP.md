# Roadmap: EASYkoopman

**Created:** 2026-06-10  
**Planning style:** Coarse phases, each phase must preserve a runnable baseline.

## Phase 1: Baseline Data And Controller Boundary

**Goal:** Preserve EasyUUV legacy control behavior while creating the controller boundary and data collection path required by Koopman identification.

**Requirement coverage:** BASE-01, BASE-02, BASE-03, BASE-04, DATA-01, DATA-02, DATA-03

**Canonical refs:**
- `easyuuv_env.py` - `_pid_control()`, `_compute_dynamics()`, `_apply_action()`
- `thruster_dynamics.py` - 8 thruster order and geometry
- `rigid_body_hydrodynamics.py` - buoyancy, quadratic drag, linear viscous forces
- `workflows/play_controller.py` - direct controller evaluation without PPO
- `workflows/play_eval.py`, `workflows/play_eval_step.py`, `workflows/play_eval_task2.py` - trajectory evaluation workloads

**Deliverables:**
- Legacy controller behavior documented and protected.
- Configurable controller mode.
- Data collection schema and logging path.
- Baseline logs from existing step/sine/irregular workflows.

**Verification:**
- Legacy `Ssurface` path still produces 8D PWM in `[-1, 1]`.
- Data logs contain state, reference, action, PWM, next state and timestamp.
- Existing evaluation scripts remain usable.

## Phase 2: Offline Koopman Identification

**Goal:** Train and validate an offline Koopman model for EasyUUV attitude/depth dynamics from Isaac simulation data.

**Requirement coverage:** KOOP-01, KOOP-02, KOOP-03

**Canonical refs:**
- `docs/koopman_mpc_migration_plan.md`
- Phase 1 data schema and collected logs
- Koopman-Sim2Real paper notes in `../Research/agentic-auv`

**Deliverables:**
- `koopman/lifting.py`
- `koopman/edmd.py`
- Model save/load format.
- Prediction evaluation report.

**Verification:**
- EDMD training runs offline on Phase 1 logs.
- Saved model reloads and reproduces prediction metrics.
- One-step and multi-step prediction errors are reported.

## Phase 3: Koopman MPC Controller Integration

**Goal:** Add a Koopman+MPC controller mode that runs in EasyUUV Isaac Lab simulation and controls attitude/depth through the existing actuator pipeline.

**Requirement coverage:** MPC-01, MPC-02, MPC-03, MPC-04

**Canonical refs:**
- `easyuuv_env.py`
- `koopman/` modules from Phase 2
- `workflows/play_controller.py`

**Deliverables:**
- MPC solver module.
- Controller adapter connecting current sim state, reference, Koopman model and PWM output.
- Runtime fallback if solver fails or exceeds time budget.

**Verification:**
- Koopman+MPC can run at the configured control rate for a single environment.
- PWM output remains bounded.
- Solver latency is logged.
- Step trajectory can complete without Isaac simulation crash.

## Phase 4: Evaluation, Documentation And Isaac Sim Runbook

**Goal:** Produce a repeatable comparison between legacy controller and Koopman+MPC and document how to run the project on Isaac Sim/Lab.

**Requirement coverage:** EVAL-01, EVAL-02, DOC-01, DOC-02

**Canonical refs:**
- `workflows/play_eval.py`
- `workflows/play_eval_step.py`
- `workflows/play_eval_task2.py`
- `README.md`
- `docs/koopman_mpc_migration_plan.md`

**Deliverables:**
- Unified evaluation command set.
- Metrics summary format.
- Updated README or runbook.
- Known limitations and next-step Sim2Real notes.

**Verification:**
- Each evaluation script produces comparable legacy and Koopman+MPC logs.
- Documentation commands point to files that exist.
-待确认 Isaac Sim/Lab local version is documented.

## Phase 5: Online Adaptation And Sim2Real Readiness

**Goal:** Prepare the controller for model drift and eventual real-world data adaptation.

**Requirement coverage:** ADAPT-01, ADAPT-02, ADAPT-03, ADAPT-04

**Status:** Deferred to v2.

**Deliverables:**
- Kalman or RLS online update design.
- Real log replay format.
- 6-DOF/8D PWM expansion plan.
- Optional LLM low-frequency tuning interface.

**Verification:**
- Online update can be replayed offline without destabilizing the saved model.
- Sim and real log schemas are compatible.

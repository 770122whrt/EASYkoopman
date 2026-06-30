# Roadmap: EASYkoopman

**Created:** 2026-06-10  
**Planning style:** Coarse phases, each phase must preserve a runnable baseline.

## Execution Environment Strategy

This roadmap separates local development from Isaac Sim/Lab validation because the local workstation cannot run Isaac reliably.

**Local-first work:**
- Code structure changes that do not require stepping Isaac physics.
- Pure Python modules for data schema, logging helpers, Koopman lifting, EDMD training, model save/load, offline prediction metrics and MPC solver unit tests.
- Documentation, GSD planning, result analysis and plotting from server-generated logs.

**Server / Isaac-required work:**
- Environment instantiation, rollout, reset and force/torque application checks.
- Legacy `Ssurface` / `PID` baseline logs.
- Simulation data collection for Koopman training.
- Koopman+MPC closed-loop control in Isaac.
- Final comparison experiments across step, sine and irregular trajectories.

**Next coding target before Isaac is needed:** implement the controller boundary, data schema and offline-capable helper modules locally, then stop at the Phase 1 Isaac Gate where a server rollout must produce the first real logs.

## Phase 1: Baseline Data And Controller Boundary

**Goal:** Preserve EasyUUV legacy control behavior while creating the controller boundary and data collection path required by Koopman identification.

**Execution:** Local code writing first; server Isaac is required only for rollout verification and real data generation.

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
- Offline-loadable log writer/reader helpers that can be syntax-checked locally.
- Baseline logs from existing step/sine/irregular workflows.

**Verification:**
- Local: Python syntax/import-light checks for modified helper modules.
- Local: schema unit checks can construct and read a sample record without Isaac.
- Isaac Gate: server runs `play_controller.py` to produce the first direct-controller data log.
- Legacy `Ssurface` path still produces 8D PWM in `[-1, 1]`.
- Data logs contain state, reference, action, PWM, next state and timestamp.
- Existing evaluation scripts remain usable.

## Phase 1.5: Isaac Lab 2.x Compatibility Migration

**Goal:** Make the Phase 1 direct-controller data path runnable on the confirmed server stack: Isaac Sim 5.0 + Isaac Lab 2.2.1.

**Execution:** Local code changes and source-contract tests first; server Isaac is required for final task creation and rollout verification.

**Requirement coverage:** COMPAT-01, COMPAT-02, COMPAT-03, COMPAT-04, BASE-04, DATA-01, DATA-02

**Canonical refs:**
- `docs/isaaclab2_server_environment.md` - confirmed server environment and import-order findings
- `workflows/play_controller.py` - first direct controller rollout entrypoint
- `easyuuv_env.py`, `assets/easyuuv.py`, `rigid_body_hydrodynamics.py`, `thruster_dynamics.py` - Isaac Lab API surface
- `koopman_data.py`, `workflows/koopman_logging.py` - Phase 1 JSONL data path

**Deliverables:**
- Compatibility import layer for Isaac Lab 2.x with old `omni.isaac.lab` fallback where practical.
- Valid Gym task registration that does not depend on the legacy `omni.isaac.lab_tasks.direct.EasyUUV-Isaac-Simulation` module path.
- `play_controller.py` direct-controller rollout path that does not require PPO/RSL-RL wrapping.
- Local source-contract tests covering import migration, task registration and direct rollout structure.
- Server verification commands for pulling the branch and generating a Koopman JSONL sample.

**Verification:**
- Local: source-contract tests pass without Isaac installed.
- Local: Python compile check passes for modified Python files.
- Isaac Gate: server runs `workflows/play_controller.py --task EasyUUV-Direct-v1 --headless` through `/root/IsaacLab/isaaclab.sh`.
- Isaac Gate: generated JSONL contains Phase 1 Koopman records from the legacy controller path.

## Phase 2: Offline Koopman Identification

**Goal:** Train and validate an offline Koopman model for EasyUUV attitude/depth dynamics from Isaac simulation data.

**Execution:** Mostly local after Phase 1 server logs exist. Isaac is not required for EDMD training itself.

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
- Local: EDMD trains on a small fixture log without Isaac.
- EDMD training runs offline on Phase 1 logs.
- Saved model reloads and reproduces prediction metrics.
- One-step and multi-step prediction errors are reported.

## Phase 3: Koopman MPC Controller Integration

**Goal:** Add a Koopman+MPC controller mode that runs in EasyUUV Isaac Lab simulation and controls attitude/depth through the existing actuator pipeline.

**Execution:** Hybrid. MPC solver and adapter tests are local; closed-loop validation requires server Isaac.

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
- Local: MPC solver can run against saved Koopman model and replayed states.
- Local: controller adapter returns bounded commands for fixture states.
- Isaac Gate: server runs the first `koopman_mpc` closed-loop rollout.
- Koopman+MPC can run at the configured control rate for a single environment.
- PWM output remains bounded.
- Solver latency is logged.
- Step trajectory can complete without Isaac simulation crash.

## Phase 4: Evaluation, Documentation And Isaac Sim Runbook

**Goal:** Produce a repeatable comparison between legacy controller and Koopman+MPC and document how to run the project on Isaac Sim/Lab.

**Execution:** Server runs Isaac experiments; local analyzes exported logs and writes documentation.

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
- Server: run legacy and Koopman+MPC on step, sine and irregular trajectories.
- Local: regenerate metrics/plots from exported logs without Isaac.
- Each evaluation script produces comparable legacy and Koopman+MPC logs.
- Documentation commands point to files that exist.
-待确认 Isaac Sim/Lab local version is documented.

## Phase 5: Online Adaptation And Sim2Real Readiness

**Goal:** Prepare the controller for model drift and eventual real-world data adaptation.

**Requirement coverage:** ADAPT-01, ADAPT-02, ADAPT-03, ADAPT-04

**Status:** Deferred to v2.

**Execution:** Local algorithm work first; server Isaac required for online closed-loop disturbance tests.

**Deliverables:**
- Kalman or RLS online update design.
- Real log replay format.
- 6-DOF/8D PWM expansion plan.
- Optional LLM low-frequency tuning interface.

**Verification:**
- Online update can be replayed offline without destabilizing the saved model.
- Sim and real log schemas are compatible.

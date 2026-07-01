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

**Next coding target:** Phase 4 evaluation tooling and matched Isaac experiments for legacy vs Koopman MPC.

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

## Phase 2.5: Offline Koopman Model Qualification Gate

**Goal:** Qualify one Koopman model as stable, generalizable, reproducible and sufficiently aligned with Koopman-Sim2Real before Phase 3 uses it inside MPC.

**Execution:** Mostly local analysis and tooling. Server Isaac is required only to collect longer step/sine/irregular logs, preferably with varied initial conditions or repeated runs.

**Requirement coverage:** QUAL-01, QUAL-02, QUAL-03, QUAL-04, QUAL-05, QUAL-06, DATA-03, KOOP-03

**Canonical refs:**
- `koopman/dataset.py` - JSONL to matrix conversion.
- `koopman/edmd.py` - ridge EDMD fitting.
- `koopman/evaluation.py` - one-step and multi-step prediction metrics.
- `workflows/train_koopman.py`, `workflows/evaluate_koopman.py` - current offline workflow commands.
- `workflows/play_controller.py` - known-good server collection path.
- `docs/phase2_5_koopman_model_gate_recommendations.md` - model qualification recommendations and gate criteria.

**Deliverables:**
- Train/validation/test log split workflow.
- Multi-log training and evaluation workflow.
- Candidate model sweep including current direct-state predictor, paper-style lifted-space EDMD and baselines.
- Normalization-aware ridge/lifting sweep workflow that produces comparable model artifacts and metrics.
- Rollout stability report over horizons longer than the MPC horizon, including divergence rates.
- Selected model manifest that Phase 3 consumes.
- Gate report with pass/fail decision, known limitations and recommendation.

**Verification:**
- Local: split workflow creates disjoint train/validation/test manifests.
- Local: sweep workflow trains direct-state and paper-style lifted EDMD candidates without Isaac imports.
- Local: persistence and simple linear baselines are evaluated on the same validation/test splits.
- Local: comparison output ranks models by validation multi-step RMSE at multiple horizons and flags rollout divergence.
- Local: selected model reloads and evaluates on held-out test logs.
- Server data gate: at least step, sine and irregular logs are validated before model selection.
- Phase 3 does not begin until a selected model manifest and gate report both state pass.

## Phase 3: Koopman MPC Controller Integration

**Goal:** Add a Koopman+MPC controller mode that runs in EasyUUV Isaac Lab simulation and controls attitude/depth through the existing actuator pipeline.

**Execution:** Hybrid. MPC solver and adapter tests are local; closed-loop validation requires server Isaac.

**Requirement coverage:** MPC-01, MPC-02, MPC-03, MPC-04

**Canonical refs:**
- `.planning/phases/03-koopman-mpc-controller-integration/03-SPEC.md` - locked Phase 3 scope and acceptance criteria.
- `.planning/phases/03-koopman-mpc-controller-integration/03-CONTEXT.md` - implementation decisions and canonical refs.
- `.planning/phases/03-koopman-mpc-controller-integration/03-RESEARCH.md` - EasyUUV and Koopman-Sim2Real article mapping.
- `docs/phase2_5_consolidation_report.md` - selected model gate result and limitations.
- `docs/phase3_algorithm_alignment_review.md` - algorithm contract review distinguishing engineering integration from full paper-style lifted EDMD control.
- `source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json` - default Phase 3 model input.
- `easyuuv_env.py` - `controller_mode`, `_compute_dynamics()` and `_last_pwm_8d` controller seam.
- `koopman/model.py`, `koopman/lifted_edmd.py` - loadable prediction model contracts.
- `workflows/play_controller.py` - first direct-controller and Koopman MPC smoke entrypoint.

**Deliverables:**
- Manifest-first Koopman runtime loader that rejects non-pass or stale selected models.
- Offline backend check comparing selected `direct_state` with best passing `paper_lifted_edmd`.
- Pure NumPy first-pass MPC problem and bounded 8D PWM solver.
- Offline MPC replay workflow that runs without Isaac.
- Controller adapter connecting current sim state, reference, Koopman model and PWM output.
- `koopman_mpc` branch in `easyuuv_env.py` that preserves existing thruster and hydrodynamic logic.
- Runtime fallback if solver fails, returns non-finite commands or exceeds time budget.
- Solver diagnostics in logs: latency, status, cost and fallback flag.

**Verification:**
- Local: manifest loader rejects `gate_status != pass`, missing model paths and unsupported model classes.
- Local: prediction wrapper can run against the Phase 2.5 selected model and produce finite 11D predictions.
- Local: backend check reports whether first Isaac smoke uses `direct_state` or `paper_lifted_edmd` and why.
- Local: MPC solver can run against saved Koopman model and replayed states.
- Local: controller adapter returns bounded 8D PWM for fixture states.
- Local: `python -m pytest -q`, `python -m compileall __init__.py easyuuv_env.py koopman workflows tests` and `git diff --check` pass.
- Isaac Gate: server runs the first `koopman_mpc` closed-loop rollout via `workflows/play_controller.py`.
- Isaac Gate: PWM output remains bounded, solver latency is logged and fallback count is reported.
- Isaac Gate: run summary states backend used, backend reason, fallback rate, latency budget status and limitations.
- Step smoke trajectory can complete without Isaac simulation crash.

**Phase 3 plan artifacts:**
- `.planning/phases/03-koopman-mpc-controller-integration/03-SPEC.md`
- `.planning/phases/03-koopman-mpc-controller-integration/03-CONTEXT.md`
- `.planning/phases/03-koopman-mpc-controller-integration/03-RESEARCH.md`
- `.planning/phases/03-koopman-mpc-controller-integration/03-PLAN.md`
- `.planning/phases/03-koopman-mpc-controller-integration/03-SUMMARY.md`
- `.planning/phases/03-koopman-mpc-controller-integration/03-VERIFICATION.md`

**Completion status:** Complete on 2026-07-02.

**Completion evidence:**
- Local tests: `python -m pytest -q` -> 63 passed.
- Local compile: `python -m compileall __init__.py easyuuv_env.py koopman workflows tests` -> passed.
- Local hygiene: `git diff --check` -> passed.
- Server tests: `/opt/conda/envs/isaaclab/bin/python -m pytest -q` -> 63 passed.
- Server compile: `/opt/conda/envs/isaaclab/bin/python -m compileall __init__.py easyuuv_env.py koopman workflows tests` -> passed.
- Isaac smoke: `workflows/play_controller.py --controller_mode koopman_mpc` completed one-env step smoke and produced a valid Koopman JSONL.

**Phase 3 result boundary:** This is a fallback-safe Koopman-MPC engineering integration using the Phase 2.5 selected `direct_state` backend. It does not yet prove performance superiority or full paper-style lifted EDMD equivalence; those claims move to Phase 4.

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

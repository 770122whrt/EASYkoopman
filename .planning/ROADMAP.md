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

**Original next step after Phase 3.5:** Phase 4 evaluation, documentation and Isaac Sim runbook. This would compare legacy control, direct-state Koopman+MPC and paper-style lifted EDMD Koopman+MPC before adding higher-level intelligence.

**Updated next coding target:** Phase 4.5 PPO/RL reference adapter, after preserving enough Phase 4 smoke/evaluation evidence to avoid mixing controller defects with policy defects. The roadmap now makes PPO integration explicit before the LLM tuning layer.

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

## Phase 3.5: Paper-Style Lifted EDMD Backend Qualification

**Goal:** Promote `paper_lifted_edmd` from a hidden sweep candidate into a formal research comparison backend, then decide whether it is eligible for Phase 4 closed-loop evaluation.

**Execution:** Local-first for manifest selection, reports and offline MPC replay; server Isaac is required for repeated smoke runs and optional additional simulation data collection.

**Requirement coverage:** PLED-01, PLED-02, PLED-03, PLED-04, PLED-05, PLED-06

**Canonical refs:**
- `.planning/phases/03.5-paper-style-lifted-edmd-backend-qualification/03.5-SPEC.md` - phase contract and acceptance criteria.
- `.planning/phases/03.5-paper-style-lifted-edmd-backend-qualification/03.5-CONTEXT.md` - current code contracts and review carry-forward.
- `.planning/phases/03.5-paper-style-lifted-edmd-backend-qualification/03.5-RESEARCH.md` - relation to EasyUUV and Koopman-Sim2Real papers.
- `.planning/phases/03.5-paper-style-lifted-edmd-backend-qualification/03.5-PLAN.md` - execution waves and server commands.
- `docs/phase2_5_koopman_model_gate_recommendations.md` - paper-style lifted EDMD recommendation.
- `docs/phase3_algorithm_alignment_review.md` - warning that Phase 3 direct-state smoke is not full paper-style lifted EDMD control.
- `koopman/lifted_edmd.py`, `koopman/observables.py`, `koopman/sweep.py` - current paper-style backend implementation.
- `workflows/play_controller.py` - repeated Isaac smoke/data collection entrypoint.

**Deliverables:**
- Separate `paper_lifted_edmd` manifest for comparison.
- Offline direct-state vs paper-lifted prediction report.
- Offline direct-state vs paper-lifted MPC replay report.
- Repeated Isaac smoke logs for `paper_lifted_edmd` where feasible.
- Phase 4 handoff stating whether to run a three-way evaluation or record paper-lifted failure analysis.

**Verification:**
- Local: selected paper-lifted manifest reloads through `koopman.runtime`.
- Local: prediction metrics and divergence status are reported side by side with direct-state.
- Local: offline MPC commands stay bounded and report fallback/latency.
- Server: at least one `paper_lifted_edmd` step smoke completes through `play_controller.py`.
- Server: additional sine/irregular smoke or data runs are collected if server time permits.
- Handoff explicitly states paper-aligned claims and limitations.

## Phase 4: Evaluation, Documentation And Isaac Sim Runbook

**Goal:** Produce a repeatable comparison between legacy controller, direct-state Koopman+MPC and, if Phase 3.5 passes, paper-style lifted EDMD Koopman+MPC; document how to run the project on Isaac Sim/Lab. After the 2026-07-02 roadmap update, this phase should at minimum preserve a short, comparable controller-only evaluation baseline before Phase 4.5 reconnects PPO.

**Execution:** Server runs Isaac experiments; local analyzes exported logs and writes documentation.

**Requirement coverage:** EVAL-01, EVAL-02, DOC-01, DOC-02

**Canonical refs:**
- `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-SPEC.md` - locked Phase 4 scope and acceptance criteria.
- `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-CONTEXT.md` - controller-only evaluation decisions and boundaries.
- `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-RESEARCH.md` - metrics and run-matrix research.
- `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-PLAN.md` - executable Phase 4 waves.
- `docs/phase4_controller_evaluation_runbook.md` - server Isaac command matrix and artifact pullback procedure.
- `workflows/play_eval.py`
- `workflows/play_eval_step.py`
- `workflows/play_eval_task2.py`
- `workflows/play_controller.py`
- `README.md`
- `docs/koopman_mpc_migration_plan.md`
- `.planning/phases/03.5-paper-style-lifted-edmd-backend-qualification/03.5-SUMMARY.md` once Phase 3.5 is complete.

**Deliverables:**
- Unified evaluation command set for legacy, direct-state MPC and eligible paper-lifted MPC.
- Metrics summary format.
- Updated README or runbook.
- Known limitations and next-step Sim2Real notes.

**Verification:**
- Server: run legacy, direct-state Koopman+MPC and eligible paper-lifted Koopman+MPC on step, sine and irregular trajectories.
- Local: regenerate metrics/plots from exported logs without Isaac.
- Each evaluation script produces comparable legacy and Koopman+MPC logs.
- Documentation commands point to files that exist.
- Isaac Sim/Lab server version is documented.

**Completion status:** Complete on 2026-07-02.

**Completion evidence:**
- Server matrix: 9/9 controller-only Isaac runs completed on `agentic-AUV`.
- Controllers: `legacy/Ssurface`, `direct_state` Koopman+MPC and `paper_lifted_edmd` Koopman+MPC.
- Trajectories: `step`, `sine` and `irregular`.
- Log validation: all 9 logs passed `workflows/validate_koopman_log.py`.
- Metrics: `source/results/koopman_phase4/reports/metrics_summary.json` and `.md` generated.
- Server tests after sync: `70 passed`; compileall passed.
- Local docs: `04-SUMMARY.md`, `04-VERIFICATION.md` and `04-PHASE45-HANDOFF.md` written.

**Phase 4 result boundary:** Legacy is the strongest controller-only baseline. Direct-state Koopman+MPC is a bounded, runnable Koopman baseline but not yet superior to legacy. Paper-lifted EDMD is included as a paper-style comparison backend, but its depth RMSE is too high to promote as the default controller for Phase 4.5.

## Phase 4.5: PPO/RL Reference Adapter Integration

**Goal:** Reconnect the EasyUUV PPO/RSL-RL policy path above Koopman+MPC so the policy outputs a high-level 4D correction or reference while Koopman+MPC remains the low-level real-time controller that produces bounded 8D PWM.

**Execution:** Hybrid. Local work defines the adapter contract, source-compatible scripts and unit tests; server Isaac is required for PPO checkpoint discovery, short PPO inference smoke and any PPO retraining.

**Requirement coverage:** RL-01, RL-02, RL-03, MPC-05, EVAL-03

**Canonical refs:**
- `workflows/train.py` - RSL-RL PPO training entrypoint.
- `workflows/gen_policy.py` - checkpoint export path.
- `workflows/play_eval.py`, `workflows/play_eval_step.py`, `workflows/play_eval_task2.py` - current PPO inference/evaluation path.
- `agents/rsl_rl_ppo_cfg.py` - PPO runner, policy and algorithm configuration.
- `easyuuv_task_registration.py` - Gym task registration and `rsl_rl_cfg_entry_point`.
- `easyuuv_env.py` - 4D action interface, observation contract and Koopman+MPC controller mode.
- `workflows/play_controller.py` - current controller-only Koopman+MPC smoke path.

**Deliverables:**
- Policy adapter contract that converts PPO output into either the existing 4D correction or a 5D Koopman reference.
- Inference workflow that can run `PPO -> Koopman+MPC -> 8D PWM` without allowing PPO to directly command thrusters.
- Compatibility path for missing checkpoints: fail clearly, or run a smoke with a deterministic stub policy before training.
- Optional short PPO retraining command set on Isaac Lab 2.2.1 if no usable checkpoint exists.
- JSONL/CSV logs that record policy output, Koopman reference, MPC diagnostics, fallback usage and final PWM.
- Comparison note against controller-only Phase 4 results so instability can be attributed to policy, model or solver.

**Verification:**
- Local: adapter unit tests cover 4D correction, 5D reference conversion, clipping and non-finite input rejection.
- Local: scripts compile without Isaac imports where practical.
- Server: PPO checkpoint discovery command reports whether a checkpoint exists under `logs/rsl_rl/easyuuv`.
- Server: if a checkpoint exists, short one-env inference smoke runs `PPO -> Koopman+MPC`.
- Server: if no checkpoint exists, a short PPO training smoke runs with small `num_envs` and `max_iterations` to prove the training path still works.
- Server: resulting logs keep PWM bounded and include solver fallback/latency diagnostics.

**Boundary:** PPO is a high-level policy layer. It must not bypass Koopman+MPC to send direct 8D PWM in this phase.

**Phase 4.5 plan artifacts:**
- `.planning/phases/04.5-ppo-rl-reference-adapter-integration/04.5-SPEC.md`
- `.planning/phases/04.5-ppo-rl-reference-adapter-integration/04.5-PLAN.md`

**Planning status:** Planned on 2026-07-03.

**Planning decision:** Follow the control expert review: do not connect PPO by merely flipping `play_eval.py` to `controller_mode=koopman_mpc`. The first implementation must introduce an adapter that converts PPO's current 4D output into a bounded 5D Koopman reference/correction. Use `direct_state` as the default Koopman backend; keep `paper_lifted_edmd` research-only until its depth mismatch is diagnosed.

## Phase 5: LLM Low-Frequency Planning And Tuning Interface

**Goal:** Add a low-frequency LLM supervisor that analyzes task intent, logs and controller metrics, then proposes reference plans or safe tuning suggestions without entering the real-time control loop.

**Execution:** Local-first for interface design, prompt contract and offline log analysis. Server Isaac is required only for validation runs that apply approved tuning suggestions.

**Requirement coverage:** LLM-01, LLM-02, LLM-03, SAFE-01

**Canonical refs:**
- `docs/koopman_mpc_migration_plan.md` - layered EasyUUV interpretation: PPO high-level policy, low-level controller, LLM tuning outside real-time control.
- External EasyUUV deployment repository - hardware-side LLM configuration pattern (`enable_LLM`, API endpoint, prompt file and main process).
- Phase 4/4.5 logs - metrics consumed by the LLM supervisor.

**Deliverables:**
- LLM interface contract for reading experiment summaries and proposing bounded tuning changes.
- Prompt/input schema that separates task planning, MPC parameter suggestions and policy-level reference envelopes.
- Human-approval gate for applying any LLM-suggested controller or policy change.
- Offline dry-run workflow that generates recommendations from existing logs without launching Isaac.
- Server validation runbook for applying one approved tuning profile and comparing against baseline.

**Verification:**
- Local: schema validation rejects direct PWM commands, real-time loop calls and unsafe parameter ranges.
- Local: dry-run recommendation can be generated from saved Phase 4/4.5 logs.
- Server: optional approved-tuning smoke produces comparable logs without increasing fallback rate beyond the accepted threshold.

**Boundary:** LLM is a low-frequency supervisor. It may propose task plans, references or tuning parameters, but it must not directly control `env.step()`, PPO actions or 8D PWM.

## Phase 6: Online Adaptation And Sim2Real Readiness

**Goal:** Prepare the controller for model drift and eventual real-world data adaptation.

**Requirement coverage:** ADAPT-01, ADAPT-02, ADAPT-03, ADAPT-04

**Status:** Deferred to v2.

**Execution:** Local algorithm work first; server Isaac required for online closed-loop disturbance tests.

**Deliverables:**
- Kalman or RLS online update design.
- Real log replay format.
- 6-DOF/8D PWM expansion plan.
- Integration notes for how online adaptation interacts with the Phase 5 LLM tuning supervisor.

**Verification:**
- Online update can be replayed offline without destabilizing the saved model.
- Sim and real log schemas are compatible.

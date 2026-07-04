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

**Updated next coding target:** Phase 4.6 PPO training entrypoint and checkpoint evidence gate, followed by Phase 5 Koopman-MPC PPO retraining. Phase 4.5 proved the adapter/control chain with a stub policy, but no PPO checkpoint existed on the server. Phase 4.6 restores checkpoint evidence; Phase 5 trains the PPO policy that actually belongs to the Koopman-MPC closed loop. LLM integration moves after that.

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

**Requirement coverage:** RL-01, RL-02, RL-03, RL-04, MPC-05, EVAL-03

**Canonical refs:**
- `workflows/train.py` - RSL-RL PPO training entrypoint.
- `workflows/gen_policy.py` - checkpoint export path.
- `workflows/play_eval.py`, `workflows/play_eval_step.py`, `workflows/play_eval_task2.py` - current PPO inference/evaluation path.
- `agents/rsl_rl_ppo_cfg.py` - PPO runner, policy and algorithm configuration.
- `easyuuv_task_registration.py` - Gym task registration and `rsl_rl_cfg_entry_point`.
- `easyuuv_env.py` - 4D action interface, observation contract and Koopman+MPC controller mode.
- `workflows/play_controller.py` - current controller-only Koopman+MPC smoke path.

**Deliverables:**
- Policy adapter contract named `heuristic_reference_delta_v0` that interprets PPO 4D output as a bounded reference delta and converts it into a 5D Koopman reference.
- Inference workflow that can run `PPO -> Koopman+MPC -> 8D PWM` without allowing PPO to directly command thrusters.
- Compatibility path for missing checkpoints: fail clearly, or run a smoke with a deterministic stub policy before training.
- Optional short PPO retraining command set on Isaac Lab 2.2.1 if no usable checkpoint exists.
- JSONL/CSV logs that record policy output, action semantics, evidence level, adapter quaternion convention, goal/reference matching error, Koopman reference, MPC diagnostics, fallback usage and final PWM.
- Comparison note against controller-only Phase 4 results so instability can be attributed to policy, model or solver.

**Verification:**
- Local: adapter unit tests cover `heuristic_reference_delta_v0`, 4D correction, 5D reference conversion, clipping, quaternion normalization and non-finite input rejection.
- Local: scripts compile without Isaac imports where practical.
- Server: PPO checkpoint discovery command reports whether a checkpoint exists under `logs/rsl_rl/easyuuv`.
- Server: if a checkpoint exists, short one-env inference smoke runs `PPO -> Koopman+MPC`.
- Server: if no checkpoint exists, a short PPO training smoke runs with small `num_envs` and `max_iterations` to prove the training path still works.
- Server: resulting logs keep PWM bounded and include solver fallback/latency diagnostics plus `ppo_evidence_level`.

**Boundary:** PPO is a high-level policy layer. It must not bypass Koopman+MPC to send direct 8D PWM in this phase. The first adapter is a guarded heuristic bridge, not proof that PPO's original legacy-controller action semantics are losslessly preserved.

**Phase 4.5 plan artifacts:**
- `.planning/phases/04.5-ppo-rl-reference-adapter-integration/04.5-SPEC.md`
- `.planning/phases/04.5-ppo-rl-reference-adapter-integration/04.5-PLAN.md`

**Planning status:** Planned on 2026-07-03.

**Completion status:** Complete on 2026-07-04.

**Completion evidence:**
- Local pytest: `100 passed`.
- Local compileall: passed.
- Local diff hygiene: `git diff --check` passed with CRLF warnings only.
- Server pytest: `102 passed`.
- Server compileall: passed.
- Server training entrypoint smoke: passed.
- Server checkpoint generation smoke: produced `/root/IsaacLab/logs/rsl_rl/easyuuv/2026-07-04_12-01-58/model_0.pt`.
- Server checkpoint discovery: `checkpoint_found=true`, `selected_rule=latest_mtime_model_pt`.
- Server legacy PPO baseline smoke: `OK: 2 samples`, `controller_modes=legacy/Ssurface`.
- Server old-checkpoint adapter smoke: `OK: 2 PPO/Koopman samples`, `adapter_modes=heuristic_reference_delta_v0`, `backend_used=direct_state`.

**Phase 4.6 result boundary:** PPO/RSL-RL checkpoint evidence is restored under Isaac Lab 2.2.1. The generated one-iteration checkpoint is only checkpoint smoke evidence; it does not prove PPO convergence or Koopman-MPC PPO performance. Phase 5 must train the Koopman-MPC-specific PPO policy.

**Planning decision:** Follow the control expert review and Phase 4.5 adapter review: do not connect PPO by merely flipping `play_eval.py` to `controller_mode=koopman_mpc`. The first implementation must introduce `heuristic_reference_delta_v0`, an adapter that treats PPO's current 4D output as a bounded reference delta under an explicit assumption, then converts it into a 5D Koopman reference/correction. Use `direct_state` as the default Koopman backend; keep `paper_lifted_edmd` research-only until its depth mismatch is diagnosed. Checkpoint inference is a guarded smoke under this adapter assumption, not a performance or semantic-equivalence claim.

**Completion status:** Complete on 2026-07-03.

**Completion evidence:**
- Local tests: `python -m pytest -q` -> 92 passed.
- Local compile: `python -m compileall __init__.py easyuuv_env.py koopman workflows tests` -> passed.
- Server tests: `/opt/conda/envs/isaaclab/bin/python -m pytest -q` -> 92 passed.
- Server compile: passed.
- Server Isaac stub smoke: `stub policy -> heuristic_reference_delta_v0 -> direct_state Koopman+MPC -> 8D PWM` completed with 350 validated samples.
- Checkpoint discovery: `checkpoint_found=false`, `count=0`.
- Missing checkpoint mode exits before Isaac startup with exit code 2 and a clear message.

**Phase 4.5 result boundary:** Adapter plumbing is verified with a stub policy. PPO performance is not verified because no PPO checkpoint exists on the server.

## Phase 4.6: PPO Training Entrypoint And Checkpoint Evidence Gate

**Goal:** Restore the PPO/RSL-RL training, checkpoint generation, checkpoint discovery and checkpoint loading workflow under Isaac Lab 2.2.1, while keeping all PPO claims evidence-labeled and separated from Koopman+MPC performance claims. This phase is the evidence bridge into Phase 5; it is not a substitute for training a Koopman-MPC-specific PPO policy.

**Execution:** Hybrid. Local work writes source-contract tests, migrates train/eval/export entrypoints and updates docs; server Isaac is required for the short training smoke, checkpoint creation and checkpoint loading.

**Requirement coverage:** COMPAT-04, RL-03, RL-04, MPC-05, EVAL-03

**Canonical refs:**
- `.planning/phases/04.6-ppo-training-entrypoint-and-checkpoint-evidence-gate/04.6-SPEC.md`
- `.planning/phases/04.6-ppo-training-entrypoint-and-checkpoint-evidence-gate/04.6-PLAN.md`
- `docs/phase4_6_ppo_training_checkpoint_gate.md`
- `workflows/train.py` - RSL-RL PPO training entrypoint to migrate.
- `workflows/play_eval.py` and `workflows/gen_policy.py` - checkpoint loading/export paths.
- `workflows/discover_ppo_checkpoints.py` - checkpoint discovery gate.
- `workflows/play_ppo_koopman.py` - guarded old-checkpoint adapter smoke path.
- `agents/rsl_rl_ppo_cfg.py` - PPO runner configuration.
- `easyuuv_env.py` - 9D observation, 4D action, legacy controller and Koopman-MPC controller path.

**Deliverables:**
- Isaac Lab 2.2.1 compatible PPO training entrypoint smoke command.
- Separate checkpoint generation smoke using `save_interval=1`, explicit final save or enough iterations to trigger saving.
- Checkpoint discovery report with `selected_checkpoint` and `selected_rule`.
- Legacy PPO baseline smoke using `legacy/Ssurface`.
- Legacy PPO baseline summary sidecar with `result_bucket=legacy_ppo_baseline` and `ppo_evidence_level=checkpoint_smoke`.
- Old-checkpoint adapter smoke through `heuristic_reference_delta_v0` only when a checkpoint exists.
- Phase 5 Koopman-MPC PPO retraining handoff contract proving adapter reference refresh must be in the training loop before any retrained-policy claim.
- Summary that separates `legacy_ppo_baseline`, `old_checkpoint_adapter_smoke` and `retrained_ppo_koopman_mpc`.

**Verification:**
- Local: source-contract tests cover AppLauncher order, Isaac Lab 2 import paths, checkpoint discovery behavior and evidence-level labels.
- Local: `python -m pytest -q`, compileall and `git diff --check` pass.
- Server: `workflows/train.py --num_envs 1 --max_iterations 1 --headless` starts as `training_entrypoint_only`; this does not require checkpoint generation.
- Server: checkpoint generation uses an explicit save policy and produces at least one `model_*.pt`.
- Server: checkpoint discovery reports `checkpoint_found=true`, `selected_checkpoint` and `selected_rule` after successful checkpoint generation.
- Server: generated checkpoint loads through legacy PPO eval/export.
- Server: optional old-checkpoint adapter smoke logs `ppo_evidence_level=checkpoint_smoke` and `result_bucket=old_checkpoint_adapter_smoke`.

**Boundary:** Phase 4.6 restores checkpoint evidence. It does not claim PPO convergence, PPO superiority over legacy, lossless migration of old PPO semantics to Koopman+MPC, or completion of the required Koopman-MPC-specific PPO training. That training is Phase 5.

**Phase 4.6 plan artifacts:**
- `.planning/phases/04.6-ppo-training-entrypoint-and-checkpoint-evidence-gate/04.6-SPEC.md`
- `.planning/phases/04.6-ppo-training-entrypoint-and-checkpoint-evidence-gate/04.6-PLAN.md`
- `docs/phase4_6_ppo_training_checkpoint_gate.md`

**Planning status:** Planned on 2026-07-03.

## Phase 5: Koopman-MPC PPO Retraining And Evaluation

**Goal:** Train a new PPO policy whose training-time transition dynamics include `heuristic_reference_delta_v0` and the Koopman-MPC low-level controller. This is the required PPO for the Koopman-MPC architecture; old EASYUUV PPO checkpoints remain baselines or smoke tests only.

**Execution:** Hybrid. Local work defines the training wrapper, evidence schema, config profile and source-contract tests. Server Isaac is required for every real training run and policy evaluation.

**Requirement coverage:** RL-01, RL-02, RL-03, RL-04, MPC-05, EVAL-03

**Canonical refs:**
- `.planning/phases/05-koopman-mpc-ppo-retraining/05-SPEC.md`
- `.planning/phases/05-koopman-mpc-ppo-retraining/05-PLAN.md`
- `docs/phase5_koopman_mpc_ppo_training_strategy.md`
- `workflows/train.py` - restored RSL-RL training baseline from Phase 4.6.
- `workflows/play_ppo_koopman.py` - Phase 4.5 inference adapter path.
- `koopman/policy_adapter.py` - `heuristic_reference_delta_v0`.
- `easyuuv_env.py` - 9D observation, 4D action and Koopman-MPC controller path.
- `agents/rsl_rl_ppo_cfg.py` - PPO runner defaults to reuse rather than rewriting PPO.

**Deliverables:**
- Koopman-MPC PPO training wrapper or environment hook where each policy action refreshes the 5D Koopman reference before `env.step`.
- Dedicated training command, for example `workflows/train_ppo_koopman.py`, that uses RSL-RL PPO and does not hand-roll PPO.
- Training summary that labels `result_bucket=retrained_ppo_koopman_mpc`, `ppo_evidence_level=retrained_policy_smoke` for short smoke or stronger labels only after later evidence exists.
- Checkpoint output and discovery path for the newly trained Koopman-MPC PPO checkpoint.
- Evaluation command comparing `legacy_ppo_baseline`, pure `koopman_mpc`, old-checkpoint adapter smoke and retrained Koopman-MPC PPO.
- Logging of action clipping, adapter reference, fallback rate, solver latency, PWM bounds and reward profile.
- Clear reward-profile versioning. The first pass should keep `legacy_easyuuv_v0` unless a new reward is deliberately versioned.

**Verification:**
- Local: source-contract test proves `policy_output_4d -> heuristic_reference_delta_v0 -> _koopman_reference_5d refresh -> env.step(action_4d)` is the training path.
- Local: PPO observation remains 9D and action remains 4D unless a later spec changes them.
- Local: scripts compile without requiring Isaac imports before `AppLauncher`.
- Server: one-env short training smoke starts under Isaac Lab 2.2.1 and writes a checkpoint under the Koopman-MPC PPO result bucket.
- Server: checkpoint discovery reports the retrained checkpoint with `selected_checkpoint` and deterministic `selected_rule`.
- Server: short evaluation loads the retrained checkpoint and runs `PPO -> adapter -> Koopman+MPC -> PWM` with bounded PWM.
- Server: summary compares fallback/latency/action statistics against Phase 4.5 stub and Phase 4.6 legacy PPO baseline.

**Boundary:** Phase 5 trains and smokes the required Koopman-MPC-specific PPO policy. It may report early training/evaluation evidence, but it still must not claim superiority, convergence or deployability until longer matched evaluations prove those claims.

## Phase 6: LLM Low-Frequency Planning And Tuning Interface

**Goal:** Add a low-frequency LLM supervisor that analyzes task intent, logs and controller metrics, then proposes reference plans or safe tuning suggestions without entering the real-time control loop.

**Execution:** Local-first for interface design, prompt contract and offline log analysis. Server Isaac is required only for validation runs that apply approved tuning suggestions.

**Requirement coverage:** LLM-01, LLM-02, LLM-03, SAFE-01

**Canonical refs:**
- `docs/koopman_mpc_migration_plan.md` - layered EasyUUV interpretation: PPO high-level policy, low-level controller, LLM tuning outside real-time control.
- External EasyUUV deployment repository - hardware-side LLM configuration pattern (`enable_LLM`, API endpoint, prompt file and main process).
- Phase 4/4.5/4.6/5 logs - metrics consumed by the LLM supervisor.

**Deliverables:**
- LLM interface contract for reading experiment summaries and proposing bounded tuning changes.
- Prompt/input schema that separates task planning, MPC parameter suggestions and policy-level reference envelopes.
- Human-approval gate for applying any LLM-suggested controller or policy change.
- Offline dry-run workflow that generates recommendations from existing logs without launching Isaac.
- Server validation runbook for applying one approved tuning profile and comparing against baseline.

**Verification:**
- Local: schema validation rejects direct PWM commands, real-time loop calls and unsafe parameter ranges.
- Local: dry-run recommendation can be generated from saved Phase 4/4.5/4.6/5 logs.
- Server: optional approved-tuning smoke produces comparable logs without increasing fallback rate beyond the accepted threshold.

**Boundary:** LLM is a low-frequency supervisor. It may propose task plans, references or tuning parameters, but it must not directly control `env.step()`, PPO actions or 8D PWM.

## Phase 7: Online Adaptation And Sim2Real Readiness

**Goal:** Prepare the controller for model drift and eventual real-world data adaptation.

**Requirement coverage:** ADAPT-01, ADAPT-02, ADAPT-03, ADAPT-04

**Status:** Deferred to v2.

**Execution:** Local algorithm work first; server Isaac required for online closed-loop disturbance tests.

**Deliverables:**
- Kalman or RLS online update design.
- Real log replay format.
- 6-DOF/8D PWM expansion plan.
- Integration notes for how online adaptation interacts with the Phase 6 LLM tuning supervisor.

**Verification:**
- Online update can be replayed offline without destabilizing the saved model.
- Sim and real log schemas are compatible.

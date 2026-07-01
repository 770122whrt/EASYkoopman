# Phase 3: Koopman MPC Controller Integration - Plan

**Spec:** `.planning/phases/03-koopman-mpc-controller-integration/03-SPEC.md`  
**Context:** `.planning/phases/03-koopman-mpc-controller-integration/03-CONTEXT.md`  
**Research:** `.planning/phases/03-koopman-mpc-controller-integration/03-RESEARCH.md`  
**Target branch:** `isaaclab2-migration`  
**Mode:** local-first implementation with server Isaac smoke gate  
**Primary model manifest:** `source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json`

## Purpose

Phase 3 turns the Phase 2.5 selected Koopman model into a first closed-loop controller mode.

The phase should end with:

- a local offline MPC path that can load the selected manifest and produce bounded PWM;
- a `koopman_mpc` branch in `easyuuv_env.py`;
- a server Isaac smoke run proving the controller can step the simulation without crashing;
- clear latency/fallback logging.

It should not claim final performance superiority. That belongs to Phase 4.

## Key Design Decisions

- Use the selected model manifest as the only runtime model contract.
- Optimize 8D PWM in the first version because the selected Koopman model was trained on `pwm_8d`.
- Preserve the existing thrust and hydrodynamics pipeline.
- Keep the first solver a pure NumPy first-pass receding-horizon optimizer, not a claim of full paper-equivalent CasADi MPC.
- Add fallback before any server closed-loop test.
- Use `workflows/play_controller.py` as the first Isaac entrypoint; do not require PPO.
- Compare the selected `direct_state` backend with the best passing `paper_lifted_edmd` backend offline before the Isaac smoke.
- Preserve a state/reference-based adapter so future PPO/RL outputs can become references without bypassing the controller safety boundary.

<threat_model>
## Threat Model

| Threat | Severity | Mitigation |
|---|---|---|
| Solver outputs unbounded PWM | HIGH | Clip to `[-1, 1]`, test bounded output, record `_last_pwm_8d` |
| Solver stalls and misses 60 Hz budget | HIGH | timeout, latency logging, fallback to previous PWM or legacy |
| Bad or stale model manifest enters closed loop | HIGH | fail closed unless `gate_status = pass` and model artifact exists |
| Controller breaks legacy baseline | HIGH | leave legacy branch unchanged; tests assert legacy path still present |
| Quaternion sign ambiguity causes wrong tracking cost | MEDIUM | align quaternion sign before cost calculation |
| Isaac-only failure hidden by local tests | MEDIUM | final server smoke is mandatory |
</threat_model>

## Wave 1: Manifest Runtime Contract

Create:

- `koopman/runtime.py`
- `tests/test_koopman_runtime.py`

Tasks:

- Implement a loader for `selected_model_manifest.json`.
- Validate:
  - `gate_status == "pass"`;
  - `model_path` exists;
  - `state_dim == 11`;
  - `reference_dim == 5`;
  - `control_dim == 8`;
  - `dt > 0`;
  - `model_class` is supported.
- Load `direct_state` via `KoopmanModel.load()`.
- Load `paper_lifted_edmd` via `LiftedEDMDModel.load()` for future compatibility.
- Return a small runtime object with `predict_next(state, pwm, reference)`.

Verification:

```powershell
python -m pytest tests\test_koopman_runtime.py -q
python -m compileall koopman
```

Acceptance criteria:

- A valid Phase 2.5 manifest loads.
- A `gate_status = fail` fixture is rejected.
- Missing model path is rejected.
- Prediction returns finite shape `(11,)`.
- Runtime exposes backend metadata for Phase 3 summary: `backend_used`, `model_class`, `known_limitations`.

## Wave 1.5: Core Algorithm Backend Check

Create:

- `workflows/check_koopman_mpc_backend.py`
- `tests/test_koopman_mpc_backend_check.py` or source-contract equivalent

Tasks:

- Load the Phase 2.5 selected `direct_state` model from `selected_model_manifest.json`.
- Read `sweep_results.json` and find the best passing `paper_lifted_edmd` candidate.
- Run the same offline replay samples through both backends.
- Compare:
  - prediction finite-value status;
  - predicted horizon cost;
  - command boundedness under the same MPC configuration;
  - fallback-needed status;
  - latency if the full MPC solver is used in the check.
- Keep `direct_state` for the first Isaac smoke only if it is clearly safer or if `paper_lifted_edmd` fails the backend check.
- Write a backend decision report containing:

```text
backend_used
backend_reason
direct_state_metrics
paper_lifted_edmd_metrics
paper_alignment_note
known_limitations
```

Verification:

```powershell
python workflows\check_koopman_mpc_backend.py --help
python workflows\check_koopman_mpc_backend.py ^
  --manifest source\results\koopman_phase2_5_verify_20260701_231802\selected_model_manifest.json ^
  --sweep_results source\results\koopman_phase2_5_verify_20260701_231802\sweep\sweep_results.json ^
  --log source\results\koopman_phase1\smoke_reverify_20260701_231917.jsonl ^
  --output source\results\koopman_phase3\backend_check.json
```

Acceptance criteria:

- The backend check is Isaac-free.
- The report states whether the first Isaac smoke will use `direct_state` or `paper_lifted_edmd`.
- The report states that a `direct_state` smoke is an engineering integration, not a full paper-style lifted EDMD replication.

## Wave 2: MPC Problem, Cost And Solver

Create:

- `koopman/mpc.py`
- `tests/test_koopman_mpc.py`

Tasks:

- Define dataclasses:
  - `MPCWeights`
  - `MPCBounds`
  - `MPCConfig`
  - `MPCResult`
- Implement tracking cost over `[z, quat_wxyz]`.
- Align quaternion sign before computing quaternion error, only inside the cost function.
- Preserve model input quaternion convention exactly as logged in the training data.
- Record predicted quaternion norm in diagnostics.
- Add control energy and smoothness terms.
- Implement first-pass receding-horizon optimizer as pure NumPy:
  - short horizon, default 5;
  - bounded candidate/control sequence generation;
  - optional coordinate refinement if simple enough;
  - projection to `[-1, 1]`;
  - `delta_pwm_limit`;
  - latency measurement.
- Compare optimized sequence cost against hold-previous-PWM baseline and prefer fallback if it cannot improve predicted horizon cost.
- Return first PWM command and diagnostic metadata.

Verification:

```powershell
python -m pytest tests\test_koopman_mpc.py -q
```

Acceptance criteria:

- Zero tracking error has lower cost than large tracking error.
- Larger PWM magnitude increases energy cost.
- Abrupt PWM changes increase smoothness cost.
- Solver returns 8D bounded PWM.
- Solver reports status, cost, latency and fallback-needed flag.
- Solver either beats hold-previous-PWM predicted horizon cost or returns a fallback-preferred status.

## Wave 3: Offline MPC Replay Workflow

Create:

- `workflows/run_koopman_mpc_offline.py`
- `tests/test_koopman_mpc_offline_cli.py` or source-contract equivalent

Tasks:

- Load selected manifest.
- Load one or more Koopman JSONL logs.
- For a small number of samples, run MPC using logged state/reference.
- Write an offline report containing:
  - selected manifest path;
  - backend used and backend reason;
  - horizon;
  - average latency;
  - max latency;
  - fallback count;
  - PWM min/max;
  - mean tracking cost;
  - first few commands.
- Make this workflow Isaac-free.

Verification:

```powershell
python workflows\run_koopman_mpc_offline.py --help
python workflows\run_koopman_mpc_offline.py ^
  --manifest source\results\koopman_phase2_5_verify_20260701_231802\selected_model_manifest.json ^
  --log source\results\koopman_phase1\smoke_reverify_20260701_231917.jsonl ^
  --max_samples 2 ^
  --output source\results\koopman_phase3\offline_smoke.json
```

Acceptance criteria:

- The offline workflow completes without Isaac.
- Output PWM is bounded.
- Report records latency and fallback count.
- Report records `backend_used`, `backend_reason` and `known_limitations`.

## Wave 4: EasyUUV Controller Adapter

Create:

- `koopman/mpc_controller.py`
- `tests/test_koopman_mpc_controller.py`
- source-contract tests for `easyuuv_env.py` and `workflows/play_controller.py`

Modify:

- `easyuuv_env.py`
- `workflows/play_controller.py`
- possibly `workflows/koopman_logging.py` if solver diagnostics need JSONL support

Tasks:

- Add config fields to `EasyUUVEnvCfg`:
  - `koopman_manifest_path`;
  - `mpc_horizon`;
  - `mpc_timeout_ms`;
  - `mpc_delta_pwm_limit`;
  - cost weights.
- Initialize Koopman MPC controller only when `controller_mode == "koopman_mpc"`.
- Build current 11D state and 5D reference from existing env tensors.
- Keep adapter input state/reference based so future PPO-generated 4D corrections can be converted into references before MPC, preserving the EasyUUV layered architecture.
- In `_compute_dynamics()`:
  - keep legacy branch unchanged;
  - replace `NotImplementedError` with adapter call;
  - compute legacy PWM as fallback candidate;
  - ensure `_last_pwm_8d` records actual selected PWM.
- Extend `play_controller.py` with:
  - `--controller_mode`;
  - `--koopman_manifest_path`;
  - `--mpc_horizon`;
  - `--mpc_timeout_ms`.
- Log solver diagnostics to CSV and JSONL where practical.

Verification:

```powershell
python -m pytest tests\test_koopman_mpc_controller.py tests\test_isaaclab2_source_contract.py -q
python -m compileall easyuuv_env.py workflows\play_controller.py koopman
```

Acceptance criteria:

- `koopman_mpc` branch no longer raises `NotImplementedError`.
- Legacy branch remains present.
- Adapter returns bounded PWM or fallback PWM.
- `play_controller.py --help` includes the MPC flags.
- Source-contract tests show future PPO/RL can remain outside the real-time actuator loop by targeting the same reference interface.

## Wave 5: Server Isaac Smoke Gate

Server command shape:

```bash
cd /root/IsaacLab
source /opt/conda/etc/profile.d/conda.sh
conda activate isaaclab

WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_controller.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --controller_mode koopman_mpc \
  --koopman_manifest_path /root/EASYkoopman/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json \
  --mpc_horizon 5 \
  --mpc_timeout_ms 12 \
  --steps_per_action 2 \
  --max_goals 1 \
  --trajectory_type step \
  --koopman_log_path /root/EASYkoopman/source/results/koopman_phase3/smoke_koopman_mpc.jsonl
```

Then validate:

```bash
cd /root/EASYkoopman
python workflows/validate_koopman_log.py source/results/koopman_phase3/smoke_koopman_mpc.jsonl
```

Acceptance criteria:

- Isaac app starts.
- Gym env is created.
- Rollout finishes without simulation crash.
- JSONL exists and passes schema validation.
- PWM min/max remains inside `[-1, 1]`.
- Solver latency and fallback count are reported.
- The run summary reports `backend_used`, `backend_reason`, `fallback_rate`, `latency_budget_met` and known limitations.

## Final Verification

Local:

```powershell
python -m pytest -q
python -m compileall __init__.py easyuuv_env.py koopman workflows tests
git diff --check
```

Server:

```bash
python -m pytest -q
python -m compileall __init__.py easyuuv_env.py koopman workflows tests
```

Isaac:

```bash
WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_controller.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --controller_mode koopman_mpc \
  --koopman_manifest_path /root/EASYkoopman/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json \
  --mpc_horizon 5 \
  --mpc_timeout_ms 12 \
  --steps_per_action 2 \
  --max_goals 1 \
  --trajectory_type step \
  --koopman_log_path /root/EASYkoopman/source/results/koopman_phase3/smoke_koopman_mpc.jsonl
```

## Expected End State

At the end of Phase 3:

- `koopman_mpc` is a real controller mode.
- The selected Koopman model is loaded through a manifest contract.
- MPC produces bounded 8D PWM and logs diagnostics.
- Runtime fallback prevents solver failure from crashing control.
- The first Isaac smoke run proves the loop can execute.
- The summary states whether the smoke used `direct_state` or `paper_lifted_edmd`.
- The summary does not claim final performance superiority or full paper-style lifted EDMD control unless the backend check and server results support it.
- Phase 4 can then compare legacy and Koopman+MPC across step, sine and irregular trajectories.

---
phase: 03-koopman-mpc-controller-integration
plan: 03
subsystem: control
status: complete
completed: 2026-07-02
tags: [koopman, mpc, isaaclab, pwm, direct_state]
requires:
  - phase: 02.5-offline-koopman-model-qualification-gate
    artifact: source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json
provides:
  - manifest-first Koopman runtime loader
  - bounded 8D PWM MPC solver
  - koopman_mpc controller branch in EasyUUV
  - offline backend/offline smoke workflows
  - server Isaac smoke result
requirements-completed: [MPC-01, MPC-02, MPC-03, MPC-04]
key-files:
  created:
    - koopman/runtime.py
    - koopman/mpc.py
    - koopman/mpc_controller.py
    - workflows/check_koopman_mpc_backend.py
    - workflows/run_koopman_mpc_offline.py
    - tests/test_koopman_runtime.py
    - tests/test_koopman_mpc.py
    - tests/test_koopman_mpc_controller.py
    - tests/test_koopman_mpc_workflows.py
  modified:
    - easyuuv_env.py
    - workflows/play_controller.py
    - workflows/koopman_logging.py
    - koopman/__init__.py
---

# Phase 3 Summary: Koopman MPC Controller Integration

## Purpose

Phase 3 turns the Phase 2.5 selected Koopman model into the first runnable closed-loop controller mode for EasyUUV.

The practical target is:

```text
logged Isaac data -> offline Koopman model -> finite-horizon MPC -> bounded 8D PWM -> existing EasyUUV thrust/hydrodynamics pipeline
```

This phase proves the controller seam, runtime safety checks, bounded actuator output, fallback behavior, diagnostics, and a short Isaac closed-loop smoke run.

It does not yet claim that Koopman MPC outperforms the legacy controller. That comparison is Phase 4.

## Algorithm Link

Phase 2.5 selected a `direct_state` Koopman-style predictor:

```text
x[k+1] = W * [phi(x[k], r[k]), u[k]]
```

where:

- `x[k]` is the 11D EasyUUV state used by the Koopman logs.
- `r[k]` is the 5D reference `[z_ref, q_ref_w, q_ref_x, q_ref_y, q_ref_z]`.
- `u[k]` is the 8D PWM command.
- `phi(...)` is the learned feature/lifting vector from the Phase 2/2.5 model artifact.

The MPC layer solves a short receding-horizon problem over 8D PWM:

```text
minimize sum_t (
  tracking_cost(x_t, r_t)
  + control_energy_cost(u_t)
  + control_smoothness_cost(u_t - u_{t-1})
)

subject to:
  x[t+1] = KoopmanPredict(x[t], u[t], r[t])
  -1 <= u[t,i] <= 1
  |u[t,i] - u[t-1,i]| <= delta_pwm_limit
```

The tracking term uses `state[0:5] = [z, quat_wxyz]`. Quaternion sign equivalence is handled only inside the cost calculation, so `q` and `-q` are treated as the same attitude error without changing the quaternion passed into the Koopman model.

## Paper Alignment

This phase implements the engineering structure shared with Koopman-MPC style papers:

- offline EDMD/Koopman identification;
- model predictive control on top of the learned dynamics;
- bounded actuator commands;
- runtime fallback when the optimizer is unsafe.

The first Isaac smoke uses the Phase 2.5 selected `direct_state` backend. That is a fallback-safe Koopman-MPC integration, not a full reproduction of a paper-style lifted EDMD transition such as:

```text
f[k+1] = Theta^T * f[k]
```

The runtime supports `paper_lifted_edmd`, and Phase 3 added an offline backend check comparing the selected `direct_state` model with the best passing `paper_lifted_edmd` candidate. Full closed-loop comparison is deferred to Phase 4.

## Implemented Components

`koopman/runtime.py` provides a manifest-first runtime loader. It rejects stale or unsafe models before control starts:

- `gate_status` must be `pass`;
- model artifact path must exist;
- state/reference/control dimensions must be `11/5/8`;
- `dt` must be positive;
- model class must be supported.

`koopman/mpc.py` provides the first pure NumPy MPC solver:

- bounded 8D PWM output;
- `delta_pwm_limit`;
- tracking, energy and smoothness costs;
- hold-previous-PWM baseline comparison;
- timeout/fallback diagnostics;
- predicted quaternion norm diagnostics.

`koopman/mpc_controller.py` adapts the solver into a controller object:

- loads the Koopman runtime;
- accepts current state, reference, previous PWM and legacy fallback PWM;
- returns bounded PWM plus diagnostics;
- fills known limitations when Phase 2.5 metadata is empty.

`easyuuv_env.py` now has a real `controller_mode == "koopman_mpc"` branch. It keeps the existing thruster and hydrodynamic post-processing intact; only the pre-thruster PWM selection is replaced.

`workflows/play_controller.py` now accepts Koopman MPC flags:

```text
--controller_mode koopman_mpc
--koopman_manifest_path ...
--mpc_horizon ...
--mpc_timeout_ms ...
--mpc_delta_pwm_limit ...
```

It also forwards solver diagnostics into CSV/JSONL logs.

## Workflow Usage

Offline backend check:

```powershell
python workflows\check_koopman_mpc_backend.py `
  --manifest source\results\koopman_phase2_5_verify_20260701_231802\selected_model_manifest.json `
  --sweep_results source\results\koopman_phase2_5_verify_20260701_231802\sweep\sweep_results.json `
  --log source\results\koopman_phase1\smoke_reverify_20260701_231917.jsonl `
  --max_samples 5 `
  --output source\results\koopman_phase3\backend_check.json
```

Offline MPC replay:

```powershell
python workflows\run_koopman_mpc_offline.py `
  --manifest source\results\koopman_phase2_5_verify_20260701_231802\selected_model_manifest.json `
  --log source\results\koopman_phase1\smoke_reverify_20260701_231917.jsonl `
  --max_samples 5 `
  --output source\results\koopman_phase3\offline_smoke.json
```

Server Isaac smoke:

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

Validate the generated log:

```bash
cd /root/EASYkoopman
python workflows/validate_koopman_log.py source/results/koopman_phase3/smoke_koopman_mpc.jsonl
```

## Verified Result

Local verification:

```text
python -m pytest -q
63 passed in 4.66s

python -m compileall __init__.py easyuuv_env.py koopman workflows tests
passed

git diff --check
passed
```

Server verification:

```text
/opt/conda/envs/isaaclab/bin/python -m pytest -q
63 passed in 0.65s

/opt/conda/envs/isaaclab/bin/python -m compileall __init__.py easyuuv_env.py koopman workflows tests
passed
```

Isaac smoke result:

```text
samples = 2
controller_modes = koopman_mpc/Ssurface
backend_used = direct_state
fallback_count = 0
fallback_rate = 0.0
pwm_min = 0.6499999761581421
pwm_max = 1.0
latency_max_ms = 11.896302923560143
latency_avg_ms = 11.857652105391026
latency_budget_met = true for both samples
status = ok for both samples
```

The smoke trajectory completed without Isaac simulation crash, and the Koopman JSONL passed schema validation.

## Known Limitations

- The first closed-loop smoke used `direct_state`, not a full paper-style lifted EDMD backend.
- The smoke run is intentionally short: one env, one goal, two logged samples.
- Phase 3 proves integration safety and logging, not control superiority.
- Phase 4 must compare legacy and Koopman MPC across step, sine and irregular trajectories.
- Online adaptation/Kalman/RLS updates remain out of scope until Phase 5.

## Next Phase

Phase 4 should turn this working controller into evidence:

- run legacy and Koopman MPC on the same trajectory suite;
- collect comparable logs;
- compute tracking error, depth RMSE, attitude error, control energy, smoothness, fallback rate and solver latency;
- decide whether `direct_state` is sufficient or `paper_lifted_edmd` should become the primary backend;
- document the final Isaac runbook for repeated experiments.

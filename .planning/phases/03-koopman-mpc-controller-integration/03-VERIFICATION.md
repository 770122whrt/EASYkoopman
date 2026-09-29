---
phase: 03-koopman-mpc-controller-integration
status: passed
verified: 2026-07-02
verifier: codex
---

# Phase 3 Verification

## Acceptance Criteria

| Criterion | Status | Evidence |
|---|---|---|
| Manifest loader rejects unsafe models | PASS | `tests/test_koopman_runtime.py` |
| Selected model loads and predicts finite 11D state | PASS | `tests/test_koopman_runtime.py` |
| MPC returns bounded 8D PWM | PASS | `tests/test_koopman_mpc.py` |
| Cost includes tracking, energy and smoothness | PASS | `tests/test_koopman_mpc.py` |
| Quaternion sign equivalence handled in cost only | PASS | `tests/test_koopman_mpc.py` |
| Hold-previous baseline/fallback is implemented | PASS | `tests/test_koopman_mpc.py` |
| Solver diagnostics include latency/status/cost/fallback | PASS | `tests/test_koopman_mpc_controller.py` |
| Backend check compares `direct_state` and `paper_lifted_edmd` | PASS | `workflows/check_koopman_mpc_backend.py` |
| `easyuuv_env.py` has a real `koopman_mpc` branch | PASS | source-contract tests and Isaac smoke |
| `play_controller.py` can select Koopman MPC | PASS | workflow tests and server command |
| Local tests pass without Isaac | PASS | `63 passed` |
| Server Python tests pass | PASS | `63 passed` on `agentic-AUV` |
| Isaac smoke runs one env without simulation crash | PASS | server smoke completed and wrote JSONL |
| Summary reports backend/fallback/latency/limitations | PASS | JSONL solver diagnostics and `03-SUMMARY.md` |

## Local Verification

Commands run in `E:\code for project\Agentic AUV\EasyUUV`:

```powershell
python -m pytest -q
python -m compileall __init__.py easyuuv_env.py koopman workflows tests
git diff --check
```

Result:

```text
63 passed in 4.66s
compileall passed
git diff --check passed
```

## Offline Reports

Backend decision report:

```text
path = source/results/koopman_phase3/backend_check.json
backend_used = direct_state
backend_reason = direct_state kept for first Isaac smoke because it is the selected Phase 2.5 backend or safer offline
direct_state fallback_rate = 0.0
paper_lifted_edmd fallback_rate = 0.0
recommended_manifest_path = source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json
```

Offline MPC smoke:

```text
path = source/results/koopman_phase3/offline_smoke.json
backend_used = direct_state
horizon = 5
fallback_count = 0
fallback_rate = 0.0
pwm_min = 0.35
pwm_max = 0.7
average_latency_ms = 11.130049999337643
max_latency_ms = 11.533299999427982
```

## Server Verification

Commands run in `/root/EASYkoopman` on `agentic-AUV`:

```bash
/opt/conda/envs/isaaclab/bin/python -m pytest -q
/opt/conda/envs/isaaclab/bin/python -m compileall __init__.py easyuuv_env.py koopman workflows tests
```

Result:

```text
63 passed in 0.65s
compileall passed
```

## Isaac Smoke

Command run from `/root/IsaacLab`:

```bash
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

Validation:

```bash
python workflows/validate_koopman_log.py source/results/koopman_phase3/smoke_koopman_mpc.jsonl
```

Result:

```text
OK: 2 samples
state_dim=11 reference_dim=5 action_dim=4 pwm_dim=8
t_start=0.016666667 t_end=0.033333333
trajectory_types=step
controller_modes=koopman_mpc/Ssurface
```

Pulled JSONL diagnostic summary:

```text
samples = 2
backend_used = direct_state
statuses = ok, ok
fallback_count = 0
fallback_rate = 0.0
pwm_min = 0.6499999761581421
pwm_max = 1.0
latency_avg_ms = 11.857652105391026
latency_max_ms = 11.896302923560143
latency_budget_met = true, true
known_limitations_nonempty = true, true
```

Warnings observed during Isaac startup were the known environment warnings already seen in previous phases:

- Warp CUDA `cuDeviceGetUuid` driver-entry warning;
- deprecated `omni.isaac.dynamic_control`;
- Fabric point-instancer prototype warnings;
- PyTorch tensor-copy warning;
- pandas `_append` FutureWarning.

None of these stopped the rollout or invalidated the Koopman JSONL.

## Residual Risk

Phase 3 is accepted as a fallback-safe integration gate, not as a performance gate.

Remaining risk moves to Phase 4:

- short smoke does not characterize long-horizon stability;
- `direct_state` may underperform a lifted EDMD backend in closed loop;
- legacy-vs-Koopman comparison still needs matched trajectory experiments;
- solver latency should be monitored on longer runs, not just two samples.

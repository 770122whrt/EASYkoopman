# Phase 5 Verification

**Date:** 2026-07-04
**Status:** Passed for smoke evidence

## Local Verification

```powershell
python -m pytest -q
```

Result:

```text
110 passed
```

```powershell
python -m compileall __init__.py easyuuv_env.py koopman workflows tests
```

Result:

```text
passed
```

```powershell
git diff --check
```

Result:

```text
passed with CRLF warnings only
```

## Server Non-Isaac Verification

```bash
cd /root/EASYkoopman
/opt/conda/envs/isaaclab/bin/python -m pytest \
  tests/test_phase5_training_contract.py \
  tests/test_phase5_checkpoint_provenance.py \
  tests/test_ppo_koopman_logging.py \
  tests/test_koopman_offline_contract.py \
  -q
```

Result:

```text
18 passed
```

```bash
cd /root/EASYkoopman
/opt/conda/envs/isaaclab/bin/python -m pytest -q
```

Result:

```text
110 passed
```

```bash
cd /root/EASYkoopman
/opt/conda/envs/isaaclab/bin/python -m compileall __init__.py easyuuv_env.py koopman workflows tests
```

Result:

```text
passed
```

## Server Isaac Training Smoke

Training command exited with code 0 after activating conda.

Important note:

```text
Running isaaclab.sh without activating conda failed with:
python: command not found
```

This is an environment invocation issue, not a project code failure. The successful command used:

```bash
source /opt/conda/etc/profile.d/conda.sh
conda activate isaaclab
```

Training output summary:

```text
checkpoint_found: true
selected_checkpoint: /root/IsaacLab/logs/rsl_rl/easyuuv_koopman_mpc/2026-07-04_23-23-45/model_0.pt
adapter_refresh_count: 24
adapter_refresh_before_env_step: true
base_reference_goal_match_max_error: 0.0
```

## Server Provenance Verification

```bash
cd /root/EASYkoopman
/opt/conda/envs/isaaclab/bin/python workflows/validate_phase5_checkpoint_provenance.py \
  --checkpoint /root/IsaacLab/logs/rsl_rl/easyuuv_koopman_mpc/2026-07-04_23-23-45/model_0.pt \
  --source_training_summary_path /root/EASYkoopman/source/results/koopman_phase5/training_smoke_summary.json \
  --json
```

Result:

```text
checkpoint_provenance_valid: true
source_result_bucket: retrained_ppo_koopman_mpc
source_controller_path: koopman_mpc/direct_state
source_adapter_mode: heuristic_reference_delta_v0
source_koopman_backend: direct_state
source_reward_profile: legacy_easyuuv_v0
```

## Server Isaac Evaluation Smoke

Evaluation command exited with code 0.

```bash
cd /root/EASYkoopman
/opt/conda/envs/isaaclab/bin/python workflows/validate_ppo_koopman_log.py \
  source/results/koopman_phase5/retrained_ppo_koopman_step.jsonl
```

Result:

```text
OK: 2 PPO/Koopman samples
t_start=0.016666667 t_end=0.033333333
adapter_modes=heuristic_reference_delta_v0
ppo_evidence_levels=retrained_policy_smoke
policy_modes=checkpoint
backend_used=direct_state
controller_modes=koopman_mpc/Ssurface
```

Server smoke summary:

```text
sample_count: 2
checkpoint_provenance_valid: true
policy_action_clip_rate_max: 0.0
fallback_rate: 0.0
latency_ms_mean: 11.496730614453554
latency_ms_max: 11.539035476744175
pwm_min: 0.6499999761581421
pwm_max: 1.0
```

## Acceptance Criteria Check

- [x] Adapter refresh is on the RSL-RL `env.step(action_4d)` path.
- [x] Test fails if Phase 5 only sets `controller_mode=koopman_mpc`.
- [x] PPO observation remains 9D.
- [x] PPO action remains 4D.
- [x] PPO does not output 8D PWM.
- [x] First reward profile is `legacy_easyuuv_v0`.
- [x] First backend is `direct_state`.
- [x] Server one-env short training smoke completed.
- [x] Checkpoint was generated.
- [x] Checkpoint provenance validator passed.
- [x] Short evaluation loaded the retrained checkpoint.
- [x] Evaluation JSONL validates with `ppo_evidence_level=retrained_policy_smoke`.
- [x] Evaluation summary reports fallback, latency, action clipping and PWM bounds.
- [x] Summary separates allowed claims from disallowed claims.

## Residual Risk

- Training used only one iteration and one environment.
- Evaluation used only two samples.
- Training action clipping was nonzero (`policy_action_clip_rate=0.5`) because the policy is essentially untrained.
- Evaluation PWM reached `1.0`, which is bounded but saturated.
- This phase does not prove controller quality.

## Verification Conclusion

Phase 5 passes its smoke-evidence gate. It proves the retrained PPO training/evaluation chain exists under Koopman-MPC with provenance enforcement.

It does not prove convergence, superiority, deployability or final reward design.

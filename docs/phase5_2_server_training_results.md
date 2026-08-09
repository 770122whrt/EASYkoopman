# Phase 5.2 Server Training Results

Date: 2026-07-05

This document records the first Phase 5.2 server-side PPO ablation run on `agentic-AUV`.

## Server Execution Summary

All runs used:

- Isaac Lab: `/root/IsaacLab`
- Project: `/root/EASYkoopman`
- Koopman manifest: `/root/EASYkoopman/source/results/koopman_phase2_5/selected_model_manifest.json`
- PPO evidence level: `phase5_2_health_candidate`
- Matched eval evidence level: `phase5_2_matched_eval`
- Training length: `200` iterations
- Save interval: `50`
- Eval trajectories: `step`, `sine`, `irregular`
- Eval length: `350` samples per trajectory

The generated server results were copied locally to:

```text
source/results/koopman_phase5_2_server/
```

The aggregate result file is:

```text
source/results/koopman_phase5_2_server/phase5_2_experiment_summary.json
```

All 12 PPO/Koopman JSONL eval logs passed `workflows/validate_ppo_koopman_log.py`.

## PPO Parameters

The PPO training configuration was the current `agents/rsl_rl_ppo_cfg.py` contract:

| Parameter | Value |
| --- | --- |
| `num_steps_per_env` | `24` |
| `max_iterations` | `200` |
| `save_interval` | `50` |
| `learning_rate` | `5e-4` |
| `num_learning_epochs` | `5` |
| `num_mini_batches` | `4` |
| `clip_param` | `0.2` |
| `gamma` | `0.99` |
| `lam` | `0.95` |
| `desired_kl` | `0.01` |
| `entropy_coef` | `0.0` |
| `max_grad_norm` | `1.0` |

## Tested Profiles

| Profile | Reward | Adapter | MPC |
| --- | --- | --- | --- |
| `baseline_rerun` | `legacy_easyuuv_v0` | default | default |
| `reward_v1_only` | `koopman_mpc_stability_v1` | default | default |
| `adapter_soft_v1_only` | legacy | `rpy_delta_scale=0.30`, `depth_delta_scale=0.40` | default |
| `mpc_health_v1_only` | legacy | default | `control_weight=0.03`, `smoothness_weight=0.10`, `delta_pwm_limit=0.35` |

## Matched Eval Averages

Average over `step`, `sine`, `irregular`:

| Profile | Fallback | PWM Sat | Clip | Latency Mean ms | Depth RMSE | Attitude RMSE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline_rerun` | `0.2333` | `0.2293` | `0.0517` | `11.8990` | `0.8564` | `0.8135` |
| `reward_v1_only` | `0.1248` | `0.3379` | `0.1393` | `11.7225` | `0.9360` | `0.7434` |
| `adapter_soft_v1_only` | `0.1114` | `0.3963` | `0.1088` | `11.7759` | `1.0074` | `0.7449` |
| `mpc_health_v1_only` | `0.1524` | `0.3731` | `0.4952` | `11.7458` | `2.0573` | `0.7004` |

## Gate Results

Hard evidence gates passed for all four candidates:

- Checkpoint generated and selected.
- Training summary contains Phase 5.2 profile/provenance metadata.
- Matched eval logs generated for `step`, `sine`, `irregular`.
- JSONL validator passed for all eval logs.
- Mean latency stayed below `20 ms`.
- No non-finite observation/action/reward evidence was reported in summaries.

Promotion gates versus `baseline_rerun`:

| Profile | Fallback Gate | Depth Guard | PWM Sat Guard | Clip Guard | Result |
| --- | --- | --- | --- | --- | --- |
| `reward_v1_only` | pass | pass | fail | pass | best balanced candidate, not full promotion |
| `adapter_soft_v1_only` | pass | pass | fail | pass | best fallback, worse saturation/depth than reward v1 |
| `mpc_health_v1_only` | pass | fail | fail | fail | reject |

The current best candidate is:

```text
reward_v1_only
```

Remote checkpoint:

```text
/root/IsaacLab/logs/rsl_rl/phase52_reward_v1_only/2026-07-05_10-24-46_reward_v1_only_200/model_199.pt
```

Parameter set:

```text
reward_profile = koopman_mpc_stability_v1
w_fallback = 0.30
w_pwm_sat = 0.20
w_latency = 0.05
latency_ref_ms = 20.0
adapter_profile = heuristic_reference_delta_v0_default
rpy_delta_scale = 0.35
depth_delta_scale = 0.50
mpc_profile = mpc_default_v0
mpc_delta_pwm_limit = 0.35
mpc_control_weight = 0.01
mpc_smoothness_weight = 0.05
```

## Interpretation

`reward_v1_only` is the best balanced Phase 5.2 candidate because it reduces average fallback from `0.2333` to `0.1248`, a relative improvement of about `46.5%`, while keeping depth regression below the `20%` guard and clip regression below the `0.10` absolute guard.

It must not be promoted as final controller evidence yet, because PWM saturation worsened from `0.2293` to `0.3379`, and it does not beat the older Phase 5.1 selected checkpoint across fallback/depth. This is a useful next candidate for reward/adapter refinement, not a superiority claim.

## Next Gate Recommendation

Use `reward_v1_only` as the next candidate baseline, then run a second ablation focused only on PWM saturation:

1. Keep `reward_profile=koopman_mpc_stability_v1`.
2. Keep adapter default initially.
3. Add a stronger but bounded PWM saturation penalty or reason-aware fallback penalty.
4. Do not change MPC delta limit yet.
5. Promote only if fallback remains improved and PWM saturation no longer regresses.

# Phase 5.3 Cross-Combination Server Results

Date: 2026-07-05
Server: `agentic-AUV` / `/root/EASYkoopman`
Isaac: Isaac Sim 5.0 + Isaac Lab 2.2.1
Koopman manifest: `/root/EASYkoopman/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json`

## What Was Run

Phase 5.3 screened cross-combinations of Phase 5.2 reward, adapter and MPC profiles.

Completed:

- `cross_reward_v1_adapter_soft`: 50-iteration sentinel, 200-iteration candidate, matched `step/sine/irregular`.
- `cross_reward_v1_mpc_health`: 50-iteration sentinel, 200-iteration candidate, matched `step/sine/irregular`.
- `cross_adapter_soft_mpc_health`: 50-iteration sentinel, 200-iteration candidate, matched `step/sine/irregular`.
- `cross_reward_v1_adapter_soft_mpc_health`: 50-iteration sentinel only.

The triple cross was not promoted to 200 iterations because the pairwise MPC crosses did not pass the promotion gate.

## Comparison Baselines

Phase 5.2 `reward_v1_only` is the comparison baseline:

| Metric | Value |
|---|---:|
| fallback rate | 0.1248 |
| PWM saturation rate | 0.3379 |
| policy action clip rate | 0.1393 |
| depth RMSE | 0.9360 |
| attitude RMSE | 0.7434 |
| latency mean ms | 11.7225 |

Phase 5.2 `baseline_rerun` is the health floor:

| Metric | Value |
|---|---:|
| fallback rate | 0.2333 |
| PWM saturation rate | 0.2293 |
| policy action clip rate | 0.0517 |
| depth RMSE | 0.8564 |
| attitude RMSE | 0.8135 |
| latency mean ms | 11.8990 |

## Candidate Metrics

Mean over matched `step/sine/irregular` logs:

| Profile | Fallback | PWM sat | Clip | Depth RMSE | Attitude RMSE | Latency ms | Health score | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `cross_reward_v1_adapter_soft` | 0.1514 | 0.3748 | 0.0000 | 1.7543 | 0.7512 | 11.7670 | -0.0513 | fail |
| `cross_reward_v1_mpc_health` | 0.3105 | 0.1192 | 0.0400 | 0.7173 | 0.7354 | 11.8692 | 0.1846 | fail |
| `cross_adapter_soft_mpc_health` | 0.2724 | 0.2094 | 0.4683 | 0.5022 | 0.7769 | 11.9155 | -0.1977 | fail |

Selector output:

```text
selection_status = no_selection
selected_profile_id = null
best_non_promoted_profile_id = cross_reward_v1_mpc_health
```

## Interpretation

`cross_reward_v1_adapter_soft` directly tested the user hypothesis that reward v1 and the softer adapter may combine well. It did not. It removed policy action clipping, but PWM saturation, fallback and depth RMSE all regressed versus `reward_v1_only`.

`cross_reward_v1_mpc_health` is the best non-promoted signal. It improved PWM saturation, action clip, depth RMSE and attitude RMSE versus `reward_v1_only`, but fallback rose from 0.1248 to 0.3105. This violates the Phase 5.3 fallback regression guard.

`cross_adapter_soft_mpc_health` lowered depth RMSE and PWM saturation, but action clipping was very high and fallback exceeded both `reward_v1_only` and `baseline_rerun`.

## Conclusion

No Phase 5.3 cross-combination should be promoted as the next stable PPO+Koopman-MPC profile.

The useful signal is narrower:

```text
MPC health weights help PWM saturation and depth,
but they cause fallback pressure to become the dominant failure.
```

Recommended next step:

```text
Phase 5.4 should not add LLM yet.
Phase 5.4 should diagnose and reduce MPC fallback while preserving the PWM/depth gains from cross_reward_v1_mpc_health.
```

Concrete next probes:

- Reason-aware fallback penalty: separate `timeout` from `no_cost_improvement`.
- MPC timeout/latency budget probe: increase timeout modestly or add fallback-reason reporting by trajectory.
- MPC smoothness/control sweep around `mpc_health_v1`, with fallback guard first.
- Keep `cross_reward_v1_mpc_health` as the best non-promoted reference, not as a selected controller.

## Server Artifacts

Main selection:

```text
/root/EASYkoopman/source/results/koopman_phase5_3/phase5_3_cross_selection.json
```

Matched metrics:

```text
/root/EASYkoopman/source/results/koopman_phase5_3/cross_reward_v1_adapter_soft_matched_metrics.json
/root/EASYkoopman/source/results/koopman_phase5_3/cross_reward_v1_mpc_health_matched_metrics.json
/root/EASYkoopman/source/results/koopman_phase5_3/cross_adapter_soft_mpc_health_matched_metrics.json
```

Candidate summaries:

```text
/root/EASYkoopman/source/results/koopman_phase5_3/cross_reward_v1_adapter_soft_candidate_summary.json
/root/EASYkoopman/source/results/koopman_phase5_3/cross_reward_v1_mpc_health_candidate_summary.json
/root/EASYkoopman/source/results/koopman_phase5_3/cross_adapter_soft_mpc_health_candidate_summary.json
```

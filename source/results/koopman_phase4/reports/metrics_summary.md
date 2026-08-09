# Phase 4 Controller Evaluation Metrics

Run count: 9

| Trajectory | Controller | Backend | Samples | Depth RMSE | Attitude RMSE | Fallback | Max Latency ms | PWM Bounded |
|---|---|---|---:|---:|---:|---:|---:|---|
| irregular | koopman_mpc/Ssurface | direct_state | 1400 | 0.551377 | 1.36248 | 0.387 | 16.1554 | yes |
| sine | koopman_mpc/Ssurface | direct_state | 1400 | 0.898539 | 2.2372 | 0.106 | 13.6569 | yes |
| step | koopman_mpc/Ssurface | direct_state | 1400 | 1.03723 | 2.04434 | 0.118 | 13.957 | yes |
| irregular | legacy/Ssurface | legacy | 1400 | 0.3742 | 1.05559 | 0.000 | 0 | yes |
| sine | legacy/Ssurface | legacy | 1400 | 0.398036 | 0.783965 | 0.000 | 0 | yes |
| step | legacy/Ssurface | legacy | 1400 | 0.398826 | 0.954227 | 0.000 | 0 | yes |
| irregular | koopman_mpc/Ssurface | paper_lifted_edmd | 1400 | 14.2464 | 1.08308 | 0.199 | 12.9008 | yes |
| sine | koopman_mpc/Ssurface | paper_lifted_edmd | 1400 | 13.4571 | 0.905854 | 0.171 | 12.868 | yes |
| step | koopman_mpc/Ssurface | paper_lifted_edmd | 1400 | 14.2359 | 1.09904 | 0.166 | 13.3848 | yes |

## Phase 4.5 Baseline

Eligible for Phase 4.5 baseline: yes

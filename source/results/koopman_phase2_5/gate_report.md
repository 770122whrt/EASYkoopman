# Phase 2.5 Koopman Model Gate Report

Gate Status: pass

## Selected Model

- Candidate: direct_state_selected_quadratic_ridge_0p0001_norm_off
- Model class: direct_state
- Model path: source/results/koopman_phase2_5/sweep/models/direct_state_selected_quadratic_ridge_0p0001_norm_off.json
- Normalizer path: none
- Ridge: 0.0001
- dt: 0.016666666666666607

## Data Split

- Train logs: 1
- Validation logs: 1
- Test logs: 1

## Candidate Summary

| Candidate | Class | Status | RMSE@20 | RMSE@60 |
|---|---|---:|---:|---:|
| direct_state_selected_quadratic_ridge_0p0001_norm_off | direct_state | pass | 0.00485868 | 0.381052 |
| direct_state_selected_quadratic_ridge_0p01_norm_off | direct_state | pass | 0.00662777 | 0.400135 |
| paper_lifted_edmd_selected_quadratic_ridge_0p01_norm_off | paper_lifted_edmd | pass | 0.00775289 | 0.404717 |
| paper_lifted_edmd_linear_ridge_0p01_norm_off | paper_lifted_edmd | pass | 0.00902106 | 0.402068 |
| direct_state_linear_ridge_0p01_norm_off | direct_state | pass | 0.00902354 | 0.400137 |
| direct_state_linear_ridge_0p01_norm_standard | direct_state | pass | 0.010951 | 0.400827 |
| paper_lifted_edmd_linear_ridge_0p01_norm_standard | paper_lifted_edmd | pass | 0.0109511 | 0.400843 |
| direct_state_linear_ridge_0p0001_norm_off | direct_state | pass | 0.0130739 | 0.304275 |
| paper_lifted_edmd_linear_ridge_0p0001_norm_off | paper_lifted_edmd | pass | 0.0132447 | 0.399393 |
| direct_state_linear_ridge_0p0001_norm_standard | direct_state | pass | 0.0446206 | 4.34984 |
| paper_lifted_edmd_linear_ridge_0p0001_norm_standard | paper_lifted_edmd | pass | 0.0446289 | 4.31864 |
| paper_lifted_edmd_selected_quadratic_ridge_0p0001_norm_off | paper_lifted_edmd | fail | 0.00488915 | 2.01039e+77 |
| direct_state_selected_quadratic_ridge_1em06_norm_off | direct_state | fail | 0.00686709 | inf |
| paper_lifted_edmd_selected_quadratic_ridge_1em06_norm_off | paper_lifted_edmd | fail | 0.00750173 | inf |
| paper_lifted_edmd_linear_ridge_1em06_norm_off | paper_lifted_edmd | fail | 0.584723 | 23037.4 |
| direct_state_linear_ridge_1em06_norm_off | direct_state | fail | 0.650196 | 40329.9 |
| paper_lifted_edmd_linear_ridge_1em06_norm_standard | paper_lifted_edmd | fail | 2.53284 | 4.02365e+06 |
| direct_state_linear_ridge_1em06_norm_standard | direct_state | fail | 2.57908 | 4.52001e+06 |
| paper_lifted_edmd_linear_ridge_1em08_norm_off | paper_lifted_edmd | fail | 3.47568 | 1.56961e+07 |
| direct_state_linear_ridge_1em08_norm_off | direct_state | fail | 3.91936 | 2.58187e+07 |
| paper_lifted_edmd_linear_ridge_1em08_norm_standard | paper_lifted_edmd | fail | 903.288 | 4.53888e+16 |
| direct_state_linear_ridge_1em08_norm_standard | direct_state | fail | 22379 | 8.24656e+20 |
| direct_state_selected_quadratic_ridge_1em08_norm_off | direct_state | fail | inf | inf |
| paper_lifted_edmd_selected_quadratic_ridge_1em08_norm_off | paper_lifted_edmd | fail | inf | inf |
| direct_state_selected_quadratic_ridge_1em08_norm_standard | direct_state | fail | inf | inf |
| paper_lifted_edmd_selected_quadratic_ridge_1em08_norm_standard | paper_lifted_edmd | fail | inf | inf |
| direct_state_selected_quadratic_ridge_1em06_norm_standard | direct_state | fail | inf | inf |
| paper_lifted_edmd_selected_quadratic_ridge_1em06_norm_standard | paper_lifted_edmd | fail | inf | inf |
| direct_state_selected_quadratic_ridge_0p0001_norm_standard | direct_state | fail | inf | inf |
| paper_lifted_edmd_selected_quadratic_ridge_0p0001_norm_standard | paper_lifted_edmd | fail | inf | inf |
| direct_state_selected_quadratic_ridge_0p01_norm_standard | direct_state | fail | inf | inf |
| paper_lifted_edmd_selected_quadratic_ridge_0p01_norm_standard | paper_lifted_edmd | fail | inf | inf |

## Baseline Comparison

| Baseline | Status | RMSE@20 |
|---|---:|---:|
| persistence | fail | 0.113645 |
| simple_linear | fail | 0.577989 |

## Held-Out Metrics

- Validation one-step RMSE: 1.15477
- Validation multi-step RMSE@20: 0.00485868
- Validation divergence_rate@20: 0
- Test one-step RMSE: 1.45399
- Test multi-step RMSE@20: 0.524326
- Test divergence_rate@20: 0

## Known Limitations

- none

## Recommendation For Phase 3

Proceed to MPC integration with the selected manifest.

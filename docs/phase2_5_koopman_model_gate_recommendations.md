# Phase 2.5 Koopman Model Gate Recommendations

**Audience:** the agent implementing the next Koopman phase  
**Purpose:** make Phase 2.5 precise enough to protect Phase 3 MPC integration from using an unqualified dynamics model  
**Document type:** explanation plus execution reference  
**Date:** 2026-07-01

## Summary

Phase 2.5 should be treated as an **Offline Koopman Model Qualification Gate**, not as a loose tuning pass.

Its central question is:

> Is the selected Koopman model stable, generalizable, reproducible, and theoretically close enough to Koopman-Sim2Real to be used as the Phase 3 MPC prediction model?

The current EasyUUV implementation already has JSONL logging, dataset loading, lifting, EDMD fitting, model serialization, and offline evaluation. Phase 2.5 should build on that foundation by adding disciplined data splits, model sweeps, held-out multi-step evaluation, divergence checks, and a selected-model manifest.

## Current Algorithmic Gap

The current implementation is closer to a direct next-state predictor:

```text
x[k+1] = A * lift(x[k], r[k]) + B * u[k]
```

This means the model uses lifted features of the current state and reference, plus control input, to directly regress the next raw state.

The Koopman-Sim2Real paper is closer to lifted-space evolution:

```text
f[k+1] = Theta^T * f[k]
```

Here `f[k]` is the observable vector itself, including state, tracking error, control input terms, and selected nonlinear terms. The raw state is only part of the lifted observable vector.

This distinction matters because:

- Direct-state prediction is useful as an engineering baseline, but it is weaker as a Koopman replication claim.
- Lifted-space EDMD is closer to the paper and easier to defend in a methods section.
- MPC should consume a model whose multi-step behavior is stable, not only one-step accurate.

Phase 2.5 should therefore compare the current direct-state model against at least one paper-style lifted-space EDMD model.

## Recommended Scope

Phase 2.5 should include:

- Train / validation / test split at the log level.
- Multi-log training and evaluation.
- Ridge and lifting-configuration sweep.
- Held-out one-step and multi-step prediction evaluation.
- Rollout divergence checks.
- Baseline comparisons.
- Selected model artifact and manifest.
- A gate report that states pass/fail and known limitations.

Phase 2.5 should not include:

- MPC controller implementation.
- `easyuuv_env.py` closed-loop controller changes.
- PPO retraining.
- LLM tuning.
- Kalman online update, unless it is explicitly isolated as a non-blocking prototype.

## Inputs

Expected input artifacts:

```text
EasyUUV/source/results/**/*.jsonl
EasyUUV/koopman_data.py
EasyUUV/koopman/dataset.py
EasyUUV/koopman/lifting.py
EasyUUV/koopman/edmd.py
EasyUUV/koopman/model.py
EasyUUV/workflows/train_koopman.py
EasyUUV/workflows/evaluate_koopman.py
```

Current sample schema:

```text
t
state          # 11D: [z, quat_wxyz, body_linear_velocity_xyz, body_angular_velocity_xyz]
reference      # 5D: [depth_ref, quat_ref_wxyz]
action_4d      # legacy/direct controller command
pwm_8d         # PWM before dead zone and thrust polynomial
next_state     # 11D
trajectory_type
controller_mode
```

## Outputs

Phase 2.5 should produce:

```text
split_manifest.json
sweep_results.json
selected_model.json
selected_model_manifest.json
gate_report.md
```

The selected model manifest is the formal handoff to Phase 3. Phase 3 should read this manifest rather than hard-coding model assumptions.

## Data Split Rules

Do not randomly split rows. Adjacent rows in a trajectory are highly correlated, so row-level random split leaks future information into training.

Use log-level or trajectory-level splitting:

```text
train       # fit EDMD / model coefficients
validation  # choose ridge, lifting variant, normalization, model class
test        # final held-out report only
```

The split manifest should record:

```json
{
  "train_logs": [],
  "validation_logs": [],
  "test_logs": [],
  "split_rule": "log_level",
  "seed": 0,
  "notes": "No continuous trajectory appears in more than one split."
}
```

If there are too few logs for a clean split, Phase 2.5 should fail with a data-insufficient status instead of pretending that row-level split is valid.

## Candidate Models

Sweep at least these model classes.

### Candidate A: Current Direct-State Predictor

```text
x[k+1] = W * [lift(x[k], r[k]), u[k]]
```

Use this as an engineering baseline. It is already close to the current implementation.

### Candidate B: Paper-Style Lifted EDMD

```text
f[k]     = observable(x[k], r[k], u[k])
f[k+1]   = observable(x[k+1], r[k+1], u[k+1])
Theta    = argmin ||f[k+1] - Theta^T f[k]||^2
x_pred   = select_state(f_pred)
```

This is the most important addition for theoretical alignment with Koopman-Sim2Real.

For EasyUUV, a first paper-style observable can be:

```text
f[k] = [
  state,
  reference_error,
  body_angular_velocity^2,
  vertical_velocity^2,
  pwm_8d,
  pwm_8d^2
]
```

Keep the feature set small and interpretable. The Koopman-Sim2Real paper explicitly avoids generic high-dimensional RBF or large monomial dictionaries.

### Candidate C: Controlled Koopman Form

```text
z[k]   = lift(x[k], r[k])
z[k+1] = A * z[k] + B * u[k]
x[k+1] = C * z[k+1]
```

This is not the exact form used in the paper, but it is standard and often convenient for MPC. It can be evaluated if it remains simple and does not delay the paper-style lifted EDMD model.

## Sweep Space

Keep the sweep small enough to be interpretable:

```text
ridge in [1e-8, 1e-6, 1e-4, 1e-2]

lifting variants:
  linear
  linear + selected squared velocity/rate/control terms
  current full quadratic, only as a stress test
```

Add normalization if possible. Mixed units make ridge behavior unstable because `z`, quaternion components, velocities, angular rates, and PWM live on different scales.

The sweep result for every candidate should include:

```json
{
  "candidate_id": "paper_lifted_edmd_ridge_1e-4_selected_quadratic",
  "model_class": "paper_lifted_edmd",
  "ridge": 0.0001,
  "lifting_config": {},
  "normalizer": {},
  "train_metrics": {},
  "validation_metrics": {},
  "status": "complete"
}
```

## Required Metrics

Report at least:

```text
one_step_rmse
depth_rmse
attitude_angle_rmse
velocity_rmse
multi_step_rmse@5
multi_step_rmse@20
multi_step_rmse@60
max_error
nonfinite_count
divergence_rate@20
divergence_rate@60
```

Ranking should prioritize held-out validation multi-step behavior, not training loss.

Recommended ranking order:

1. No NaN / Inf / physical-envelope divergence.
2. Best validation `multi_step_rmse@20` and `multi_step_rmse@60`.
3. Better than persistence and simple linear baselines.
4. Smaller validation-test gap.
5. Simpler lifting if metrics are comparable.

## Baselines

Use at least two baselines:

```text
persistence baseline:
  x[k+1] = x[k]

simple linear baseline:
  x[k+1] = W * [x[k], u[k], r[k]]
```

The selected Koopman model should beat these baselines on validation and test. If it does not, it is not ready for MPC.

## Divergence Checks

A model should fail the gate if any of the following happen on validation or test rollouts:

```text
NaN or Inf appears
quaternion norm becomes physically unreasonable before optional renormalization
depth or velocity leaves a configured physical envelope
multi_step_rmse@60 > 3 * one_step_rmse
divergence_rate@20 > 0
```

The exact physical envelope should be recorded in the manifest. A reasonable first envelope can be derived from EasyUUV boundary and velocity settings, then tightened after more data is available.

## Gate Criteria

A model can pass Phase 2.5 only if:

- All input logs pass schema validation.
- Train / validation / test split is log-level or trajectory-level.
- The selected model is evaluated once on held-out test logs.
- Validation and test metrics beat persistence and simple linear baselines.
- No divergence is observed at the configured required horizon.
- The model artifact, lifting config, normalization config, and metrics are captured in `selected_model_manifest.json`.
- The gate report explicitly states whether the chosen model is direct-state, lifted-space, or controlled-Koopman.

If these conditions are not met, Phase 3 should not consume the model.

## Selected Model Manifest

Phase 3 should consume one manifest with all required assumptions:

```json
{
  "gate_status": "pass",
  "model_class": "paper_lifted_edmd",
  "model_path": "source/results/koopman_models/selected_model.json",
  "state_dim": 11,
  "reference_dim": 5,
  "control_dim": 8,
  "dt": 0.0166666667,
  "lifting_config": {},
  "normalizer_path": "source/results/koopman_models/selected_normalizer.json",
  "ridge": 0.0001,
  "train_logs": [],
  "validation_logs": [],
  "test_logs": [],
  "metrics": {
    "one_step_rmse": 0.0,
    "multi_step_rmse@20": 0.0,
    "multi_step_rmse@60": 0.0,
    "divergence_rate@20": 0.0
  },
  "baselines": {},
  "known_limitations": []
}
```

Do not let Phase 3 infer `dt`, feature dimensions, control dimension, or normalization behavior from code defaults.

## Advice To The Implementing Agent

1. Preserve the current direct-state model as a baseline.
2. Add a paper-style lifted-space EDMD candidate before integrating MPC.
3. Keep the observable dictionary small and task-specific.
4. Avoid row-level random splits.
5. Make the selected manifest the only Phase 3 contract.
6. Treat multi-step divergence as a blocking issue even if one-step RMSE looks good.
7. Be explicit in docs and reports: this project adapts Koopman-Sim2Real from a 3-DOF turtle robot to an 11D EasyUUV state and 8D PWM control interface.

## Suggested Phase 2.5 Task List

| Task | Output | Done when |
| --- | --- | --- |
| Validate logs | validation summary | every log passes schema, time, finite-value, and PWM checks |
| Split logs | `split_manifest.json` | no trajectory leakage across splits |
| Add model candidates | candidate implementations | direct-state and paper-style lifted EDMD both train |
| Run sweep | `sweep_results.json` | all ridge/lifting variants report validation metrics |
| Evaluate held-out test | test metrics | selected candidate evaluated once on test |
| Check divergence | divergence summary | required horizons pass with no nonfinite rollout |
| Write manifest | `selected_model_manifest.json` | Phase 3 can load all model assumptions from one file |
| Write report | `gate_report.md` | pass/fail, metrics, limitations, and recommendation are clear |

## Bottom Line

Phase 2.5 should make the Koopman model scientifically defensible and operationally safe enough for MPC. The current model is a useful baseline, but the next step should add true lifted-space EDMD so the project can honestly claim alignment with the Koopman-Sim2Real direction.

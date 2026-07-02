---
phase: 04-evaluation-documentation-and-isaac-sim-runbook
status: completed
created: 2026-07-02
---

# Phase 4 Research

## Question

What does Phase 4 need in order to fairly evaluate EasyUUV legacy control against Koopman+MPC backends before PPO is reintroduced?

## Findings

### 1. Use The Controller-Only Entrypoint

`workflows/play_controller.py` is the correct execution surface for Phase 4.

It supports:

```text
--controller_mode legacy
--controller_mode koopman_mpc
--trajectory_type step|sine|irregular
--koopman_manifest_path
--mpc_horizon
--mpc_timeout_ms
--mpc_delta_pwm_limit
--mpc_*_weight
--koopman_log_path
```

This is better than `play_eval*.py` for Phase 4 because the `play_eval*.py` scripts are PPO inference paths and require `OnPolicyRunner` plus checkpoint handling.

### 2. JSONL Is The Common Evaluation Substrate

Every relevant path can produce Koopman JSONL:

```json
{
  "t": 0.016666666666666666,
  "state": [...],
  "reference": [...],
  "action_4d": [...],
  "pwm_8d": [...],
  "next_state": [...],
  "trajectory_type": "step",
  "controller_mode": "koopman_mpc/Ssurface",
  "solver_diagnostics": {...}
}
```

The same JSONL format lets local analysis compare legacy and Koopman+MPC without importing Isaac.

### 3. Metrics Must Separate Tracking, Effort And Solver Health

Tracking error alone is not enough for this project. A controller can track better while saturating thrusters or falling back constantly.

Phase 4 metrics should include:

```text
tracking:
  depth_rmse
  attitude_angle_rmse
  combined_tracking_cost

control effort:
  mean_pwm_l2
  mean_pwm_abs
  pwm_saturation_rate

smoothness:
  mean_delta_pwm_l2
  max_delta_pwm_l2

solver health:
  fallback_rate
  status_counts
  mean_latency_ms
  max_latency_ms
  latency_budget_violation_rate

data quality:
  sample_count
  nonfinite_count
  pwm_bounded
```

### 4. Quaternion Error Needs Sign Equivalence

The MPC code already accounts for quaternion sign equivalence in tracking cost. Phase 4 metrics must do the same:

```text
angle_error = 2 * acos(abs(dot(q_current, q_reference)))
```

with dot product clipping into `[-1, 1]`.

### 5. Phase 4 Should Preserve Experiment Provenance

The report should capture:

```text
controller_label
trajectory_type
backend_used
manifest_path
mpc_horizon
mpc_timeout_ms
steps_per_action
max_goals
trajectory_cycles
log_path
sample_count
```

This is important because Phase 4.5 will compare PPO-driven references against the Phase 4 scripted-reference baseline.

## Recommended Evaluation Matrix

Minimum complete matrix:

| Controller | Backend | Trajectories |
|---|---|---|
| legacy | Ssurface | step, sine, irregular |
| Koopman+MPC | direct_state | step, sine, irregular |
| Koopman+MPC | paper_lifted_edmd | step, sine, irregular if eligible |

Recommended default run settings:

```text
num_envs = 1
headless = true
steps_per_action = 100
trajectory_cycles = 2
max_goals = unset for full short matrix, or 2 for smoke
mpc_horizon = 5
mpc_timeout_ms = 12
mpc_delta_pwm_limit = 0.35
```

If server time is limited, run the minimum smoke matrix first:

```text
all controllers x step
then sine
then irregular
```

## Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Paper-lifted has high fallback on longer runs | Report it, do not hide it; keep direct-state baseline. |
| Solver latency occasionally exceeds 12 ms | Report violation rate and max latency; avoid claiming real-time readiness if violated. |
| Legacy and Koopman use different generated references | Use `play_controller.py` with identical `trajectory_type`, `steps_per_action` and `trajectory_cycles`. |
| Local analysis accidentally imports Isaac | Keep metrics in a pure Python workflow with unit tests using fixture JSONL. |
| Result files are large | Commit code/docs only; keep `source/results` as experiment artifacts unless explicitly requested. |

## Research Conclusion

Phase 4 should not add PPO yet and should not change the controller. It should add a small but rigorous evaluation layer:

```text
server: generate matched JSONL logs
local: validate logs and aggregate metrics
docs: runbook + summary + Phase 4.5 baseline handoff
```

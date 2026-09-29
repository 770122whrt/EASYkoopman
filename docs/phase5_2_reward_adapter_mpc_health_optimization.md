# Phase 5.2 Reward, Adapter, and MPC Health Optimization Review Guide

**Date:** 2026-07-05
**Status:** Review incorporated before implementation
**Phase docs:**

- `.planning/phases/05.2-reward-adapter-mpc-health-optimization/05.2-SPEC.md`
- `.planning/phases/05.2-reward-adapter-mpc-health-optimization/05.2-PLAN.md`

## 1. Why Phase 5.2 Exists

Phase 5.1 proved the first reliable Koopman-MPC-conditioned PPO candidate:

```text
PPO -> heuristic_reference_delta_v0 -> direct_state Koopman+MPC -> PWM
```

That candidate is reliable enough to continue, but not good enough to claim superiority. Its matched evaluation showed:

```text
step fallback_rate = 0.1343
sine fallback_rate = 0.0314
irregular fallback_rate = 0.0971

step pwm_saturation_rate = 0.2757
sine pwm_saturation_rate = 0.4664
irregular pwm_saturation_rate = 0.3746
```

So Phase 5.2 should improve health metrics before longer training or broader performance claims.

## 2. What Phase 5.2 Is Allowed To Change

Allowed:

```text
reward_profile
adapter_profile
mpc_profile
profile_id metadata
candidate-selection validators
matched-evaluation analysis
```

Not allowed:

```text
rewrite PPO
change PPO observation from 9D
change PPO action from 4D
let PPO output 8D PWM
make paper_lifted_edmd default
add LLM to the real-time loop
claim deployment or superiority
```

## 3. Proposed Reward Formula

The first new reward profile is:

```text
koopman_mpc_stability_v1
```

Formula:

```text
r_v1 = r_legacy
       - w_fallback(reason) * I[fallback_used]
       - w_pwm_sat * mean(max(0, abs(pwm_i) - pwm_soft_limit) / (1 - pwm_soft_limit))
       - w_latency * min(max(0, latency_ms - latency_ref_ms) / latency_ref_ms, latency_clip)
       - w_action * ||action_4d||_2^2
       - w_delta_action * ||action_4d - previous_action_4d||_2^2
```

Proposed values:

```text
pwm_soft_limit = 0.90
latency_ref_ms = 20.0
latency_clip = 3.0
w_fallback = 0.30
w_pwm_sat = 0.20
w_latency = 0.05 thresholded above latency_ref_ms
w_action = 0.01
w_delta_action = 0.02
```

Optional reason-aware fallback penalty:

```text
nonfinite_input / exception: 0.50
no_cost_improvement: 0.30
timeout: 0.15
```

Required diagnostics:

```text
r_legacy
fallback_penalty
pwm_saturation_penalty
latency_penalty
action_penalty
delta_action_penalty
r_total
```

## 4. Proposed Adapter Profile

Current default:

```text
rpy_delta_scale = 0.35
depth_delta_scale = 0.50
policy_action_limit = 1.0
```

Proposed `adapter_scale_soft_v1`:

```text
rpy_delta_scale = 0.30
depth_delta_scale = 0.40
policy_action_limit = 1.0
depth_bounds = [-3.0, 3.0]
```

Reserved stronger backup:

```text
adapter_scale_soft_v2:
  rpy_delta_scale = 0.25
  depth_delta_scale = 0.30
```

Required diagnostics:

```text
reference_delta_norm_mean
reference_delta_norm_max
depth_reference_delta_mean
attitude_reference_delta_mean
depth_rmse
attitude_rmse
```

## 5. Proposed MPC Profile

Current default:

```text
mpc_delta_pwm_limit = 0.35
mpc_control_weight = 0.01
mpc_smoothness_weight = 0.05
```

Proposed `mpc_health_v1`:

```text
mpc_delta_pwm_limit = 0.35
mpc_control_weight = 0.03
mpc_smoothness_weight = 0.10
mpc_horizon = 5
mpc_timeout_ms = 12.0
```

Optional later probe:

```text
mpc_delta_limit_probe_v1:
  mpc_delta_pwm_limit = 0.25
  mpc_control_weight = 0.03
  mpc_smoothness_weight = 0.10
```

## 6. Proposed Server Matrix

First matrix:

| Profile | Reward | Adapter | MPC | Changed axis |
|---|---|---|---|---|
| baseline_rerun | legacy_easyuuv_v0 | default | default | none |
| reward_v1_only | koopman_mpc_stability_v1 | default | default | reward |
| adapter_soft_v1_only | legacy_easyuuv_v0 | adapter_scale_soft_v1 | default | adapter |
| mpc_health_v1_only | legacy_easyuuv_v0 | default | mpc_health_v1 | mpc |
| mpc_delta_limit_probe_v1 | legacy_easyuuv_v0 | default | mpc_delta_limit_probe_v1 | mpc_delta_probe |

`baseline_rerun` is mandatory. `mpc_delta_limit_probe_v1` is optional and not part of the initial matrix. Combined profile is deferred to Phase 5.2b or Phase 5.3.

## 7. Candidate Promotion Rule

Draft rule:

```text
Pass all hard gates
and improve the primary health metric mean across trajectories by at least 20 percent
and meet the minimum absolute improvement for that metric.
```

Minimum absolute improvements:

```text
pwm_saturation_rate: >= 0.05 absolute
fallback_rate: >= 0.015 absolute if baseline >= 0.05
policy_action_clip_rate_mean: >= 0.03 absolute
```

Regression guards:

```text
fallback_rate:
  no trajectory may have both absolute increase > 0.02 and relative increase > 25%

depth_rmse:
  mean depth RMSE may not worsen by more than 10%

attitude_rmse / quaternion_error:
  mean attitude RMSE may not worsen by more than 10%
```

Hard gates:

```text
checkpoint exists
checkpoint provenance valid
no NaN/Inf
PWM stays inside [-1, 1]
adapter refresh happened before env.step
matched step/sine/irregular eval validates
```

## 8. Review Decisions Incorporated

The review document changed the executable defaults:

1. `w_fallback` is now `0.30`, not `0.50`.
2. `adapter_scale_soft_v1` is now `0.30 / 0.40`, with `0.25 / 0.30` reserved as v2.
3. `mpc_health_v1` keeps `mpc_delta_pwm_limit = 0.35`.
4. `mpc_delta_pwm_limit = 0.25` is an optional later probe.
5. Fresh `baseline_rerun` is mandatory.
6. Candidate promotion uses relative and absolute improvement plus regression guards.
7. Combined profile is deferred.

## 9. Recommended Default

My recommended default is:

```text
Approve the one-factor matrix.
Require a fresh baseline re-run.
Use reward_v1 with w_fallback=0.30.
Use adapter_soft_v1 with 0.30 / 0.40.
Use mpc_health_v1 weights-only, keeping delta_pwm_limit=0.35.
Keep 0.25 delta limit as optional probe only.
Require 20 percent plus absolute improvement for promotion.
Defer combined profile until Phase 5.2b or Phase 5.3.
```

This keeps the next step ambitious enough to learn something, but still bounded enough that a failure tells us which subsystem caused it.

# Phase 4.5 PPO-to-Koopman Adapter Review And Guidance

**Date:** 2026-07-03
**Audience:** project owner and the agent implementing Phase 4.5
**Document type:** explanation plus execution guidance
**Scope:** Phase 4.5 PPO/RL reference adapter integration, with source alignment to EasyUUV and Koopman-Sim2Real

## 1. Executive Conclusion

Phase 4.5 is directionally correct.

The current plan preserves the most important control boundary:

```text
PPO/RSL-RL policy
  -> high-level 4D action or correction
  -> adapter
  -> 5D Koopman reference
  -> Koopman+MPC low-level controller
  -> bounded 8D PWM
  -> thruster and physics pipeline
```

This is consistent with the project goal: combine the EasyUUV high-level RL architecture with the Koopman-Sim2Real model-based control direction, while replacing the low-level controller path rather than letting PPO directly command thrusters.

However, Phase 4.5 should not claim that the existing PPO action semantics have been fully preserved merely because the workflow runs. The original EasyUUV policy action is consumed by the A-S-Surface/PID low-level controller. In Phase 4.5, that same 4D action is reinterpreted as a bounded reference correction for Koopman+MPC. That is a reasonable engineering bridge, but it is an adapter assumption, not a theorem from either paper.

The plan should therefore add several explicit gates:

1. `action_semantics_disclaimer`
2. `base_reference_matches_observation_goal`
3. `reference_refreshed_before_env_step`
4. `ppo_evidence_level`
5. `quaternion_composition_convention`
6. `controller_swap_distribution_shift`

Without these gates, the phase may become misleading: it may prove plumbing, but not prove that PPO, the adapter and Koopman-MPC are algorithmically aligned.

## 2. Source Ground Truth

This section separates paper facts, original repository facts and current project facts. Later recommendations should be read as derived from this source map.

### 2.1 EasyUUV Paper Facts

Source:

- Local PDF: `E:/code for project/Agentic AUV/Research/agentic-auv/Sources/Papers/EasyUUV-TIE.pdf`
- Public paper page: `https://arxiv.org/abs/2510.22126`

Relevant facts:

1. EasyUUV is a hybrid RL plus low-level controller architecture for UUV attitude control.
2. The learned policy is not described as a direct actuator policy. It outputs high-level attitude corrections, and these corrections are executed by an adaptive S-Surface controller.
3. The RL implementation uses RSL-RL with Proximal Policy Optimization, abbreviated as PPO.
4. The paper describes a 9D observation vector containing current attitude quaternion, desired attitude quaternion and depth error. In the local code, the concrete observation order is `[goal_quat(4), current_depth_z(1), current_quat(4)]`.
5. The policy outputs a 4D action vector representing roll, pitch, yaw and depth deviations or corrections.
6. The low-level A-S-Surface controller computes a nonlinear control output using tracking error and error derivative:

```text
u_t = 2 / (1 + exp(-zeta_1 e(t) - zeta_2 e_dot(t))) - 1 + Delta u(t)
Delta u(t+1) = Delta u(t) + alpha e(t) sign(u_t)
```

7. The LLM component is a low-frequency tuning or supervisory component. It should not be placed in the real-time actuator path in Phase 4.5.

Interpretation for Phase 4.5:

- PPO is a high-level policy layer.
- A-S-Surface/PID is the original low-level controller.
- Replacing the low-level controller with Koopman+MPC is consistent with the project goal.
- Direct PPO-to-8D-PWM is not consistent with the EasyUUV architecture.

### 2.2 Original EasyUUV Repository Facts

Source:

- Original repository file: `https://github.com/360ZMEM/EasyUUV-Isaac-Simulation/blob/main/easyuuv_env.py`
- Current local adaptation: `EasyUUV/easyuuv_env.py`

Relevant local code facts:

1. `EasyUUVEnvCfg` exposes a 4D action space and 9D observation space:

```text
easyuuv_env.py:82-86
action_space = 4
observation_space = 9
num_actions = 4
num_observations = 9
```

2. `_get_observations()` returns:

```text
easyuuv_env.py:304-315
obs = [self._goal, root_pos_w[:, 2], root_quat_w]
```

This means the PPO policy sees the desired attitude quaternion through `_goal`, the current depth coordinate and the current attitude quaternion.

3. `_pid_control()` maps the 4D action to 8D motor values using S-Surface or PID logic:

```text
easyuuv_env.py:441-462
4D action -> PID_value -> motorValue[:, 0:8] -> clipped PWM-like command
```

4. Existing PPO eval scripts force the legacy controller path:

```text
workflows/play_eval.py:108
env_cfg.controller_mode = 'legacy'

workflows/play_eval.py:230-233
actions = policy(obs)
obs, _, _, _ = env.step(actions)
```

Interpretation for Phase 4.5:

- In the original path, `policy(obs)` produces the 4D input consumed by the legacy low-level controller.
- The current PPO checkpoint, if one exists, was trained under the legacy low-level controller dynamics.
- Switching the low-level controller to Koopman+MPC changes the closed-loop transition distribution seen by the same policy.

### 2.3 Koopman-Sim2Real Paper Facts

Source:

- Local PDF: `E:/code for project/Agentic AUV/Research/agentic-auv/Sources/Papers/Koopman-Sim2Real.pdf`

Relevant facts:

1. The paper uses Extended Dynamic Mode Decomposition, abbreviated as EDMD, to construct a finite-dimensional approximation of a Koopman model.
2. The core learned evolution is expressed in lifted observable space:

```text
f[k+1] = Theta^T f[k]
```

Here `f[k]` is an observables vector, and `Theta` is the coefficient matrix identified from data.

3. The observables may include system states, inputs and associated functions. The exact Koopman model depends on the selected observables.
4. The paper uses the model for prediction and model-based control, including MPC.
5. The paper also proposes online model parameter updates using Kalman filtering. This is an online adaptation layer and should remain outside Phase 4.5.

Interpretation for Phase 4.5:

- Koopman-Sim2Real contributes the model-based low-level control direction: data-driven Koopman identification plus MPC.
- Its core algorithm is closer to lifted-space evolution than direct raw-state regression.
- Phase 4.5 should not use the current direct-state backend as proof of exact Koopman-Sim2Real replication.

### 2.4 Current Local Koopman Implementation Facts

Source:

- `EasyUUV/koopman/edmd.py`
- `EasyUUV/koopman/lifted_edmd.py`
- `EasyUUV/koopman/mpc_controller.py`
- `EasyUUV/easyuuv_env.py`

Relevant facts:

1. `direct_state` EDMD is implemented as a direct raw next-state predictor:

```text
koopman/edmd.py:25-27
phi = lift_state_reference(dataset.X, dataset.R, config)
design = concatenate([phi, dataset.U])
target = dataset.Y
```

This corresponds to:

```text
x[k+1] = W * [phi(x[k], r[k]), u[k]]
```

2. `paper_lifted_edmd` is closer to the Koopman-Sim2Real lifted-space formulation:

```text
koopman/lifted_edmd.py:107-108
current = build_observables(dataset.X, dataset.R, dataset.U, config)
target = build_observables(dataset.Y, dataset.R, dataset.U, config)

koopman/lifted_edmd.py:120-135
transition = solve(...)
return LiftedEDMDModel(transition_matrix=transition, ...)
```

3. The current Koopman-MPC controller is fallback-safe:

```text
koopman/mpc_controller.py:32-68
command(state, reference, previous_pwm, legacy_pwm)
```

It returns bounded PWM and diagnostics, and can fall back to legacy PWM when inputs or solver behavior are invalid.

4. In `koopman_mpc` mode, the environment uses the current state and a 5D reference:

```text
easyuuv_env.py:255-269
state = [depth, quat, lin_vel_b, ang_vel_b]
reference = _koopman_reference_5d if set, else [0, _goal]
```

5. In `_compute_dynamics()`, legacy PWM is still computed before Koopman-MPC so it can be used as fallback:

```text
easyuuv_env.py:481-500
legacy_pwm = _pid_control(actions, ...)
output = _koopman_mpc_controller.command(..., legacy_pwm=legacy_pwm)
```

Interpretation for Phase 4.5:

- Passing `policy_output_4d` to `env.step()` is still useful because it defines legacy fallback behavior.
- The actual Koopman-MPC target must come from `_koopman_reference_5d`, not from the raw 4D PPO action.
- The adapter must set `_koopman_reference_5d` before each `env.step()`.

## 3. Terminology Contract

The following terms should be used consistently in code, logs and summaries.

| Term | Meaning | Dimension | Source |
| --- | --- | ---: | --- |
| `policy_observation` | PPO input observation. In local code: `[goal_quat, current_depth_z, current_quat]`. | 9 | EasyUUV code |
| `policy_output_4d` | PPO output consumed by legacy S-Surface/PID. It is a high-level correction/control input, not a PWM vector. | 4 | EasyUUV paper and code |
| `base_reference_5d` | Nominal Koopman-MPC reference before PPO correction. Should be `[depth_ref, quat_ref]`. | 5 | Current Koopman-MPC interface |
| `adapted_reference_5d` | Adapter output consumed by Koopman-MPC. | 5 | Phase 4.5 adapter |
| `state_11d` | Koopman-MPC measured state: `[depth, quat, linear_velocity_b, angular_velocity_b]`. | 11 | Current local code |
| `pwm_8d` | Bounded motor command before thrust polynomial and hydrodynamics. | 8 | EasyUUV actuator pipeline |
| `legacy_pwm` | PWM generated by S-Surface/PID from `policy_output_4d`, used as fallback in Koopman-MPC mode. | 8 | Current local code |
| `fallback_used` | Whether Koopman-MPC used a safe fallback rather than solver output. | boolean | Current local controller |
| `backend_used` | Koopman backend used at runtime, such as `direct_state` or `paper_lifted_edmd`. | string | Current local runtime |
| `ppo_evidence_level` | Evidence class for a run: `stub_only`, `checkpoint_smoke`, `training_entrypoint_only`, or `retrained_policy_smoke`. | string | Recommended Phase 4.5 gate |

Critical terminology rule:

`policy_output_4d` must not be called `reference_5d`. The adapter converts or interprets it into a reference correction, but the original object remains a policy action.

## 4. Why An Adapter Is Required

The original EasyUUV architecture is:

```text
policy_observation_9d
  -> PPO policy
  -> policy_output_4d
  -> A-S-Surface/PID
  -> pwm_8d
  -> thruster and hydrodynamics
```

The intended Phase 4.5 architecture is:

```text
policy_observation_9d
  -> PPO or stub policy
  -> policy_output_4d
  -> policy_adapter
  -> adapted_reference_5d
  -> Koopman+MPC
  -> pwm_8d
  -> thruster and hydrodynamics
```

The adapter is required because:

1. PPO outputs 4D.
2. Koopman-MPC consumes a 5D reference plus 11D measured state.
3. The 4D action was trained under a different low-level controller.
4. A direct `play_eval.py` controller-mode flip would let PPO affect fallback semantics but would not provide a valid MPC reference unless `_koopman_reference_5d` is explicitly set.

Therefore the correct Phase 4.5 claim is:

> Phase 4.5 reconnects the PPO/RL layer to Koopman-MPC through a bounded reference adapter.

The incorrect claim is:

> Phase 4.5 proves the original PPO controller works unchanged with Koopman-MPC.

## 5. Review Of Current Phase 4.5 SPEC And PLAN

### 5.1 What Is Correct

The current SPEC and PLAN already make several strong choices:

1. They explicitly reject direct PPO-to-8D-PWM.
2. They state that PPO 4D output is not the same object as the 5D Koopman reference.
3. They require a local adapter that can be tested without Isaac, Omniverse or RSL-RL.
4. They require a stub-policy smoke path before trusting any real PPO checkpoint.
5. They require checkpoint discovery and clear behavior when checkpoints are absent.
6. They keep `direct_state` as the default backend and keep `paper_lifted_edmd` research-only for Phase 4.5.
7. They require logging of policy output, adapted reference, solver diagnostics, fallback, latency and bounded PWM.

These decisions are aligned with the paper-code boundary.

### 5.2 Required Correction 1: Action Semantics Disclaimer

Current PLAN text:

```text
adapter_mode = "bounded_4d_correction"
policy_output_4d = [roll_delta, pitch_delta, yaw_delta, depth_delta]
adapted_depth = base_depth + depth_scale * clipped_depth_delta
adapted_quat = normalize(base_quat * quat_from_scaled_rpy_delta)
```

Issue:

This makes the PPO action look like a native reference delta. In the original EasyUUV path, the action is a control input passed to A-S-Surface/PID, not a formally defined desired reference.

Required change:

Rename the first adapter mode to something that makes the assumption explicit:

```text
adapter_mode = "heuristic_reference_delta_v0"
```

Add this statement to SPEC and PLAN:

```text
The adapter interprets PPO's 4D legacy controller input as a bounded reference
delta for Koopman-MPC. This is an explicit engineering adapter assumption.
It is not equivalent to proving that the original PPO action semantics are
unchanged under the new low-level controller.
```

Acceptance gate:

- Phase 4.5 summary must include `action_semantics = heuristic_reference_delta_v0`.
- Any checkpoint result must be labeled as guarded inference under an adapter assumption.

### 5.3 Required Correction 2: Base Reference Must Match PPO Observation Goal

Issue:

PPO sees `_goal` inside its observation. If the workflow uses an independent scripted base reference for Koopman-MPC, PPO and MPC may optimize against different targets.

Required invariant:

```text
base_reference_5d.quat == env.unwrapped._goal for the same step
```

Depth also needs a defined source:

```text
base_reference_5d.depth_ref must come from the same trajectory generator
used by the log record and must be written before adapter execution.
```

Acceptance gate:

- Add a validator check that `base_reference[1:5]` matches the goal quaternion used in `policy_observation`.
- Add `goal_quat_from_obs` and `base_reference` to PPO-Koopman logs.
- Fail validation if the angular difference exceeds a small tolerance, while respecting `q` and `-q` quaternion equivalence in metrics.

### 5.4 Required Correction 3: Refresh `_koopman_reference_5d` Before Every Step

Current PLAN correctly says:

```text
set env._koopman_reference_5d -> env.step(policy_output_4d)
```

Issue:

This must be enforced every step, including after reset. If `_koopman_reference_5d` is stale, Koopman-MPC may track an old target while PPO observes a new `_goal`.

Required implementation rule:

```text
for each control step:
    update env._goal from trajectory
    build policy_observation
    policy_output_4d = policy(obs)
    base_reference_5d = [depth_ref, env._goal]
    adapted_reference_5d = adapter(policy_output_4d, base_reference_5d)
    env.unwrapped._koopman_reference_5d[:] = adapted_reference_5d
    env.step(policy_output_4d)
```

Acceptance gate:

- Source-contract test checks that `env._koopman_reference_5d` is assigned before `env.step`.
- Log records include `reference_set_step_index`.
- Reset code clears or refreshes `_koopman_reference_5d`.

### 5.5 Required Correction 4: Evidence Levels For PPO Claims

Issue:

A stub policy proves the adapter and Koopman-MPC pipeline, not PPO inference. A training smoke proves the training entrypoint, not a trained policy. A checkpoint smoke proves only short guarded inference under the adapter assumption.

Required status field:

```text
ppo_evidence_level =
  "stub_only" |
  "checkpoint_smoke" |
  "training_entrypoint_only" |
  "retrained_policy_smoke"
```

Recommended meanings:

| Level | What it proves | What it does not prove |
| --- | --- | --- |
| `stub_only` | Adapter, logging and Koopman-MPC can run. | PPO correctness or policy performance. |
| `checkpoint_smoke` | A discovered PPO checkpoint can execute through the adapter. | Stability, optimality or semantic equivalence. |
| `training_entrypoint_only` | PPO training script still starts under current environment. | Learned policy quality. |
| `retrained_policy_smoke` | A policy trained with the new low-level controller can run. | Full convergence or sim-to-real success. |

Acceptance gate:

- Phase 4.5 summary must print `ppo_evidence_level`.
- A missing checkpoint cannot be summarized as successful PPO inference.

### 5.6 Required Correction 5: Quaternion Composition Convention

Issue:

The expression:

```text
adapted_quat = normalize(base_quat * quat_from_scaled_rpy_delta)
```

does not state whether the delta is applied in the body frame, world frame or reference frame. It also depends on the quaternion multiplication convention used by Isaac math utilities.

Required decision:

Choose one and document it:

```text
adapter_quat_convention = "reference_frame_right_multiply"
```

or:

```text
adapter_quat_convention = "world_frame_left_multiply"
```

Recommended for first implementation:

Use one convention consistently, write it in the adapter docstring and log it as `adapter_quat_convention`. Do not silently change signs except in metrics where `q` and `-q` equivalence is expected.

Acceptance tests:

1. Zero action returns the base quaternion.
2. Roll-only delta produces the expected quaternion under the chosen convention.
3. Pitch-only delta produces the expected quaternion.
4. Yaw-only delta produces the expected quaternion.
5. Output quaternion norm is near 1.
6. `q` and `-q` are handled as equivalent in error metrics, not by arbitrary mutation of training data conventions.

### 5.7 Required Correction 6: Controller-Swap Distribution Shift

Issue:

Existing PPO checkpoints, if found, were trained with legacy S-Surface/PID dynamics. Koopman-MPC changes the closed-loop transition distribution. Even if the same observation and action shapes are preserved, the policy is now off-distribution relative to its training environment.

Required PLAN note:

```text
Checkpoint inference in Phase 4.5 is off-policy with respect to the low-level
controller swap. Poor tracking may indicate adapter mismatch or controller-swap
distribution shift, not only PPO failure.
```

Acceptance gate:

- Compare checkpoint smoke against stub smoke and Phase 4 controller-only results.
- Log policy action statistics: mean, standard deviation, min, max and clipping rate.
- If checkpoint actions saturate frequently, mark the run as `adapter_or_distribution_shift_risk`.

### 5.8 Required Correction 7: Requirements Status Drift

Issue:

`REQUIREMENTS.md` currently includes Phase 4.5 requirements, but older requirements still show `Pending` even though roadmap and state documents describe earlier phases as completed.

This is lower priority than the algorithmic gates, but it can confuse future agents.

Required change:

Either update requirement statuses to match the roadmap, or add a note:

```text
The requirement table records coverage targets. Completion status is authoritative
only when cross-checked with ROADMAP.md and STATE.md.
```

## 6. Recommended Adapter Contract

### 6.1 Adapter Name

Use:

```text
heuristic_reference_delta_v0
```

Avoid:

```text
ppo_reference_direct
```

Reason:

The first adapter is not a learned or paper-derived semantic mapping. It is a deterministic, bounded, testable bridge from legacy PPO action space to Koopman-MPC reference space.

### 6.2 Inputs

```text
policy_output_4d: shape (N, 4)
base_reference_5d: shape (N, 5)
current_state_11d: optional, shape (N, 11)
config:
    action_clip: [roll, pitch, yaw, depth]
    rpy_scale: [roll_scale, pitch_scale, yaw_scale]
    depth_scale: scalar
    depth_bounds: [min_depth_ref, max_depth_ref]
    quaternion_convention: string
```

### 6.3 Outputs

```text
adapted_reference_5d: shape (N, 5)
policy_output_4d_clipped: shape (N, 4)
adapter_mode: "heuristic_reference_delta_v0"
adapter_quat_convention: string
adapter_status: "ok" | "rejected_nonfinite" | "clipped" | "depth_bounded"
adapter_diagnostics:
    clipping_applied: boolean
    depth_bounding_applied: boolean
    quat_norm_before_normalize: float
    quat_norm_after_normalize: float
```

### 6.4 Reference Formula

The first implementation can use:

```text
a = clip(policy_output_4d, -action_clip, action_clip)
delta_rpy = rpy_scale * a[0:3]
delta_depth = depth_scale * a[3]

adapted_depth = clip(base_depth + delta_depth, depth_min, depth_max)
delta_quat = quat_from_euler_xyz(delta_rpy)
adapted_quat = normalize(quat_compose(base_quat, delta_quat, convention))

adapted_reference_5d = [adapted_depth, adapted_quat]
```

This formula must be documented as an engineering adapter. It should not be described as a PPO policy retraining objective or as the Koopman-Sim2Real model itself.

### 6.5 Failure Behavior

The adapter must never pass unsafe data into Koopman-MPC.

Required behavior:

| Condition | Behavior |
| --- | --- |
| NaN or Inf in `policy_output_4d` | reject record or return safe base reference with `adapter_status = rejected_nonfinite` |
| Extreme finite action | clip to configured action limit |
| Invalid quaternion norm | reject or normalize with diagnostic |
| Depth outside bounds | clip and record `depth_bounding_applied = true` |
| Missing base reference | fail early with clear error |

Recommended conservative default:

If non-finite policy output is detected, do not silently convert it to zero. Fail the local validator or mark the step as rejected, because silent zeroing hides policy instability.

## 7. Workflow Guidance For The Implementing Agent

### 7.1 Local First

Implement and test these without Isaac:

1. `koopman/policy_adapter.py`
2. `tests/test_policy_adapter.py`
3. `workflows/validate_ppo_koopman_log.py`
4. `tests/test_ppo_koopman_logging.py`
5. `tests/test_phase45_source_contract.py`

Local tests must not import Isaac, Omniverse, CUDA-only modules or RSL-RL.

### 7.2 Source-Contract Tests

Add tests that check the workflow source text or a thin wrapper contract:

1. Workflow supports `--policy_mode stub`.
2. Workflow supports `--policy_mode checkpoint`.
3. Workflow requires `--koopman_manifest_path`.
4. Workflow sets `env_cfg.controller_mode = "koopman_mpc"`.
5. Workflow assigns `_koopman_reference_5d` before `env.step(...)`.
6. Workflow passes `policy_output_4d` to `env.step(...)` only as policy action and fallback context.
7. Workflow logs `policy_output`, `base_reference`, `adapted_reference`, `adapter_mode`, `ppo_evidence_level` and solver diagnostics.

### 7.3 Stub Smoke

The first server smoke should be:

```text
scripted base reference
  -> deterministic stub policy output
  -> heuristic_reference_delta_v0 adapter
  -> _koopman_reference_5d
  -> env.step(policy_output_4d)
  -> direct_state Koopman+MPC
  -> bounded pwm_8d
```

What this proves:

- The adapter runs in the Isaac workflow.
- Koopman-MPC consumes adapted references.
- Logging is complete.
- Fallback and latency diagnostics are visible.

What this does not prove:

- A PPO checkpoint is available.
- PPO policy is stable.
- PPO is better than legacy.

### 7.4 Checkpoint Discovery

Checkpoint discovery should output JSON:

```json
{
  "checkpoint_found": true,
  "count": 1,
  "paths": ["..."],
  "selected_checkpoint": "...",
  "policy_mode": "checkpoint"
}
```

If no checkpoint exists:

```json
{
  "checkpoint_found": false,
  "count": 0,
  "policy_mode": "stub",
  "ppo_evidence_level": "stub_only"
}
```

Do not allow a missing checkpoint to look like successful PPO inference.

### 7.5 Guarded Checkpoint Smoke

If a checkpoint exists, run a short one-env smoke with conservative adapter scales.

Required extra metrics:

```text
policy_action_mean
policy_action_std
policy_action_min
policy_action_max
policy_action_clip_rate
adapter_depth_clip_rate
quat_norm_error_max
fallback_rate
latency_budget_met_rate
```

Interpretation:

- High action clipping may indicate adapter scaling mismatch.
- High fallback may indicate MPC solver/model issues.
- Good bounded PWM with poor tracking may indicate reference mapping mismatch.
- Instability after controller swap may indicate off-distribution PPO behavior.

### 7.6 Training Smoke

If no checkpoint exists, a short training smoke is allowed only as an entrypoint check.

Allowed claim:

```text
RSL-RL PPO training entrypoint starts under the current environment.
```

Disallowed claim:

```text
PPO learned a valid Koopman-MPC policy.
```

For any trained-policy claim, a later phase must train the policy with `controller_mode = koopman_mpc` or with an environment wrapper that faithfully represents the adapter and low-level controller.

### 7.7 Comparison Against Phase 4

Phase 4.5 should compare against Phase 4 controller-only logs:

1. `legacy/Ssurface`
2. `direct_state` Koopman+MPC
3. `paper_lifted_edmd` Koopman+MPC, research-only

Comparison should separate failure sources:

| Symptom | Likely source |
| --- | --- |
| Stub policy works, checkpoint fails | PPO checkpoint or adapter distribution shift |
| Both stub and checkpoint fail | Adapter, Koopman-MPC, model or workflow issue |
| High fallback with valid references | MPC solver/model issue |
| Good MPC diagnostics but bad tracking | reference mapping or policy issue |
| Good controller-only Phase 4 but bad PPO Phase 4.5 | policy-adapter integration issue |

## 8. Acceptance Gate Checklist

### P0 Gates

These must pass before any checkpoint inference result is trusted.

- [ ] `policy_output_4d` is never sent directly to 8D PWM.
- [ ] Adapter output shape is exactly 5D: `[depth_ref, quat_ref]`.
- [ ] `_koopman_reference_5d` is set before every `env.step(...)` in the PPO-Koopman workflow.
- [ ] `base_reference_5d.quat` matches the goal quaternion used in the PPO observation for the same step.
- [ ] NaN and Inf policy outputs are rejected or clearly marked unsafe.
- [ ] Logs include `ppo_evidence_level`.
- [ ] Default backend is `direct_state`, not `paper_lifted_edmd`.

### P1 Gates

These should pass before Phase 4.5 is considered complete.

- [ ] Unit tests cover clipping, non-finite input, quaternion normalization and depth bounds.
- [ ] Quaternion composition convention is documented and tested.
- [ ] Stub-policy server smoke produces valid JSONL with policy, adapter, MPC and PWM fields.
- [ ] Checkpoint discovery reports `checkpoint_found=true/false`.
- [ ] Missing checkpoint cannot be summarized as PPO inference.
- [ ] Checkpoint smoke, if run, reports action distribution and clipping rate.
- [ ] Summary compares against Phase 4 controller-only baselines.

### P2 Gates

These are useful but can be deferred if the phase needs to stay small.

- [ ] Add a second adapter mode based on current-state feedback, not only base-reference delta.
- [ ] Add a replay validator that replays logged adapted references through the MPC solver offline.
- [ ] Add a follow-up phase for PPO retraining under Koopman-MPC.
- [ ] Add a follow-up phase for paper-lifted backend diagnosis before promoting it.

## 9. Allowed And Disallowed Claims

### Allowed Claims After Phase 4.5

Use these only if the corresponding gates pass:

1. Phase 4.5 added a bounded adapter from PPO 4D action space to Koopman-MPC 5D reference space.
2. PPO or a stub policy can be routed through the adapter without bypassing Koopman-MPC.
3. Koopman-MPC remains the only component producing 8D PWM in the new path.
4. Stub smoke proves the adapter, logging and controller plumbing.
5. Checkpoint smoke, if available, proves guarded inference through the adapter.
6. `direct_state` remains the default engineering backend because Phase 4 showed `paper_lifted_edmd` is not yet suitable as the default low-level controller.

### Disallowed Claims After Phase 4.5

Do not write these unless a later phase adds stronger evidence:

1. PPO performance improves over legacy.
2. Existing PPO checkpoint is semantically unchanged under Koopman-MPC.
3. Phase 4.5 fully reproduces Koopman-Sim2Real.
4. `direct_state` is equivalent to the paper's lifted-space Koopman formulation.
5. Stub-policy smoke is PPO inference.
6. Short training smoke is trained policy validation.
7. LLM is part of real-time actuator control.

## 10. Concrete Modifications To Planning Docs

### 10.1 `04.5-SPEC.md`

Add to Requirements:

```text
The first adapter mode must be labeled as an engineering interpretation of
the legacy 4D policy action, not as a proven semantic equivalence.
```

Add to Acceptance:

```text
Logs and summaries include ppo_evidence_level and adapter_mode.
```

Add to Out Of Scope:

```text
Proving existing PPO checkpoint semantic equivalence after replacing
A-S-Surface/PID with Koopman-MPC.
```

### 10.2 `04.5-PLAN.md`

Change:

```text
adapter_mode = "bounded_4d_correction"
```

to:

```text
adapter_mode = "heuristic_reference_delta_v0"
```

Add a source invariant:

```text
base_reference.quat must be the same goal quaternion used in the current
PPO observation.
```

Add source-contract test:

```text
workflow sets env._koopman_reference_5d before every env.step(...)
```

Add summary fields:

```text
ppo_evidence_level
action_semantics
adapter_quat_convention
policy_action_clip_rate
base_reference_goal_match_max_error
```

### 10.3 `REQUIREMENTS.md`

Refine `RL-02`:

```text
RL-02: A locally testable adapter must convert PPO's current 4D legacy
controller input into a bounded 5D Koopman-MPC reference under an explicit
adapter_mode. The requirement does not imply semantic equivalence to the
original A-S-Surface input.
```

Add:

```text
RL-04: Phase 4.5 summaries must report ppo_evidence_level so stub, checkpoint
and training-smoke evidence cannot be confused.
```

### 10.4 `ROADMAP.md`

Add to Phase 4.5 Boundary:

```text
Checkpoint inference is guarded smoke under an adapter assumption. A later
phase is required for PPO retraining or performance claims under Koopman-MPC.
```

### 10.5 `STATE.md`

Add to Current next action:

```text
Implement the adapter with explicit action semantics, reference-goal matching,
per-step reference refresh and ppo_evidence_level logging before server
checkpoint inference.
```

## 11. Recommended Minimum Implementation Order

Use this order to reduce ambiguity:

1. Update SPEC/PLAN wording with the six gates.
2. Implement `koopman/policy_adapter.py`.
3. Add local adapter unit tests.
4. Add PPO-Koopman log schema and validator.
5. Add source-contract tests for the workflow.
6. Implement stub-policy workflow.
7. Run local tests and compile checks.
8. Run server stub smoke.
9. Discover checkpoints.
10. Run guarded checkpoint smoke only if a checkpoint exists.
11. Write Phase 4.5 summary using `ppo_evidence_level`.

Do not start with checkpoint inference. Checkpoints should be the last thing touched after adapter semantics and logging are nailed down.

## 12. Final Guidance To The Implementing Agent

Treat Phase 4.5 as a control-interface phase, not as a training or performance phase.

The implementation should answer four questions:

1. Can the existing 9D PPO observation and 4D policy output path still execute?
2. Can the 4D output be converted into a bounded 5D Koopman reference without bypassing the controller?
3. Does Koopman-MPC remain the sole producer of 8D PWM in the new path?
4. Do the logs let us distinguish policy failure, adapter failure, MPC fallback, latency issues and model/backend limitations?

If the answer to these four questions is yes, Phase 4.5 is successful even if tracking performance is not yet better than legacy.

If the answer to any of these questions is hidden or ambiguous, the phase should not be marked complete.

## 13. Source Map

### Papers

- `EasyUUV-TIE.pdf`: source for EasyUUV hybrid RL plus A-S-Surface architecture, PPO/RSL-RL use, 9D observation, 4D action and A-S-Surface equations.
- `Koopman-Sim2Real.pdf`: source for EDMD, observables, lifted evolution `f[k+1] = Theta^T f[k]`, MPC use and Kalman-based online update.
- Public EasyUUV paper page: `https://arxiv.org/abs/2510.22126`

### Original Code

- `https://github.com/360ZMEM/EasyUUV-Isaac-Simulation/blob/main/easyuuv_env.py`: source for original EasyUUV environment shape and low-level controller structure.

### Local Project Code

- `EasyUUV/easyuuv_env.py`: current action/observation contract, Koopman-MPC state/reference path, legacy fallback PWM path.
- `EasyUUV/workflows/play_eval.py`: current PPO eval path using legacy controller.
- `EasyUUV/koopman/edmd.py`: current `direct_state` EDMD training form.
- `EasyUUV/koopman/lifted_edmd.py`: current `paper_lifted_edmd` lifted observable backend.
- `EasyUUV/koopman/mpc_controller.py`: current fallback-safe Koopman-MPC controller wrapper.

### Planning Docs

- `EasyUUV/.planning/phases/04.5-ppo-rl-reference-adapter-integration/04.5-SPEC.md`
- `EasyUUV/.planning/phases/04.5-ppo-rl-reference-adapter-integration/04.5-PLAN.md`
- `EasyUUV/.planning/REQUIREMENTS.md`
- `EasyUUV/.planning/ROADMAP.md`
- `EasyUUV/.planning/STATE.md`
- `EasyUUV/docs/phase3_algorithm_alignment_review.md`
- `EasyUUV/docs/phase4_controller_evaluation_runbook.md`

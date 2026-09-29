# Phase 3: Koopman MPC Controller Integration - Research

**Question:** What do we need to know to plan Koopman+MPC integration well?

## 1. Article-Derived Constraints

### EasyUUV paper

The EasyUUV architecture should be read as a layered controller:

```text
high-level policy/reference -> A-S-Surface/PID low-level controller -> PWM/thruster dynamics
```

The LLM component is a low-frequency parameter tuner and analysis layer. It is not a real-time actuator controller. Phase 3 should preserve this safety separation: Koopman+MPC replaces the low-level controller branch, but it should not introduce an LLM or high-level stochastic policy into the real-time force loop.

The current code reflects this paper structure:

```text
4D action -> _pid_control() -> 8D PWM -> _compute_dynamics() -> force/torque
```

### Koopman-Sim2Real paper

The transferable structure is:

```text
data -> EDMD / Koopman model -> MPC -> robot control -> optional online update
```

Important differences from EasyUUV:

- The paper target is a lower-dimensional 3-DOF platform.
- EasyUUV has 11D logged state and 8D PWM control.
- The paper-style lifted EDMD candidate exists in Phase 2.5, but the selected Phase 2.5 gate model is currently `direct_state`.
- Online Kalman/adaptive update is a later phase, not Phase 3.

Planning implication: Phase 3 can honestly claim Koopman-MPC structure only when described as an EDMD-trained prediction model plus first-pass receding-horizon control. It should avoid overstating theoretical equivalence to the paper. The first controller should consume the selected manifest and report known limitations.

The current selected backend is not the paper's exact lifted-space transition. The implementation should therefore separate:

```text
engineering integration layer:
  selected direct_state backend + 8D PWM MPC + fallback-safe Isaac smoke

paper-aligned algorithm layer:
  paper_lifted_edmd backend + MPC comparison + later Phase 4 evaluation
```

## 2. Current Code Seam

`easyuuv_env.py` already has the exact seam Phase 3 needs:

```python
if self.cfg.controller_mode == 'legacy':
    motorValues = self._pid_control(...)
elif self.cfg.controller_mode == 'koopman_mpc':
    raise NotImplementedError(...)
```

The correct Phase 3 integration point is the `koopman_mpc` branch. Everything after `motorValues` should remain unchanged:

- `_last_pwm_8d` cache.
- PWM dead-zone threshold.
- thrust polynomial conversion.
- thruster orientation and torque calculation.
- buoyancy, drag, viscosity.
- `set_external_force_and_torque`.

This protects the EasyUUV physics baseline and isolates failures to the controller.

## 3. Selected Model Contract

The Phase 2.5 verified manifest reports:

```text
gate_status: pass
model_class: direct_state
state_dim: 11
reference_dim: 5
control_dim: 8
dt: 0.016666666666666607
normalizer_path: null
ridge: 0.0001
```

The model path is:

```text
source/results/koopman_phase2_5_verify_20260701_231802/sweep/models/direct_state_selected_quadratic_ridge_0p0001_norm_off.json
```

The controller should not infer any of these values from defaults. A runtime loader should validate them before creating an MPC controller.

## 4. MPC Formulation

Use receding-horizon finite optimization:

```text
min_{u_0 ... u_{H-1}} sum_i [
  || controlled_state_i - reference_i ||_Q^2
  + || u_i ||_R^2
  + || u_i - u_{i-1} ||_S^2
]

subject to:
  x_{i+1} = koopman_predict(x_i, u_i, r_i)
  -1 <= u_i[j] <= 1
  |u_i[j] - u_{i-1}[j]| <= delta_pwm_limit
```

First controlled state:

```text
controlled_state = state[0:5] = [z, quat_wxyz]
reference = [depth_ref, quat_ref_wxyz]
```

Quaternion sign must be handled in cost because `q` and `-q` represent the same orientation.

The prediction wrapper should not silently change quaternion signs. The model input convention must match the training logs; sign alignment belongs only in tracking-cost calculation and diagnostics.

## 5. Solver Choice

Three implementation approaches were considered:

| Approach | Pros | Cons | Decision |
|---|---|---|---|
| Direct 8D PWM MPC | Matches selected model `control_dim = 8`; avoids hidden legacy mapping | Higher solve dimension | Use for Phase 3 |
| 4D virtual action MPC | Lower dimension; matches old controller interface | Mismatch with Phase 2.5 model trained on 8D PWM | Defer |
| External solver-first, e.g. CasADi/OSQP | More formal optimization | Adds dependency and install risk on server | Defer or optional |

Recommended first solver:

- pure NumPy;
- short horizon;
- deterministic sampling or coordinate refinement;
- bounded PWM projection;
- latency measurement;
- fallback on failure.

This is a first-pass receding-horizon optimizer. It is MPC in the practical engineering sense: it optimizes a finite-horizon cost with a predictive model and applies the first action in receding-horizon fashion. It is not a full equivalent to the paper's more formal nonlinear/CasADi-style MPC implementation.

The solver should also compare against a hold-previous-PWM predicted-cost baseline. If it cannot reduce predicted horizon cost on fixture states, it should prefer fallback and record the reason.

## 6. Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| one-step RMSE is high | Model may be imperfect even though gate passed | Keep horizon short; use fallback and server smoke only |
| validation/test gap exists | Generalization pressure remains | Log limitations; Phase 4 expands data and comparison |
| 8D optimization too slow | 60 Hz control budget may be missed | latency budget, timeout, fallback, short horizon |
| PWM search causes abrupt commands | Thruster jitter and instability | smoothness cost and delta PWM limit |
| quaternion cost is naive | q/-q ambiguity can mislead objective | align quaternion sign in cost |
| model input convention changes silently | prediction may leave the training distribution | never flip model input quaternion; only align signs in cost |
| direct_state backend is overstated | research claim becomes inaccurate | backend check and summary must name backend type |
| server Git remote is bundle | Sync may be awkward | Use zip/scp/bundle as needed; do not block planning on git pull |

## 7. Planning Recommendation

Plan Phase 3 in six waves:

1. Manifest/model runtime contract.
2. Core algorithm backend check between `direct_state` and best passing `paper_lifted_edmd`.
3. MPC cost and solver in pure Python.
4. Offline replay workflow.
5. EasyUUV environment integration with fallback.
6. Server Isaac smoke and summary.

Do not start with Isaac edits. Offline adapter and solver tests should fail fast locally before we touch the closed-loop simulation.

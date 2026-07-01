# Phase 3 Algorithm Alignment Review

**Date:** 2026-07-01  
**Audience:** the agent revising or implementing Phase 3  
**Scope:** Phase 3 planning documents, Phase 2.5 handoff artifacts, and the current Koopman model code  
**Goal:** align Phase 3 with the project objective: combine the EasyUUV RL controller architecture with the Koopman-Sim2Real model-predictive control direction while preserving the core algorithm boundary.

## Bottom Line

Phase 3 is directionally correct as a first controller-integration phase:

- It keeps the EasyUUV layered control structure.
- It consumes the Phase 2.5 selected Koopman model through a manifest.
- It optimizes 8D PWM because the selected model was trained on `pwm_8d`.
- It preserves the existing thruster and hydrodynamics pipeline.
- It treats the first Isaac run as a smoke gate, not as a final performance claim.

However, the documents need one important correction:

> The Phase 3 selected model is currently `direct_state`, not the paper-style lifted-space EDMD model. Therefore Phase 3 should be described as a fallback-safe Koopman-MPC engineering integration, not as a complete reproduction of the Koopman-Sim2Real core formulation.

The project can still proceed, but the docs must separate "first closed-loop backend" from "core paper-aligned Koopman backend."

## Sources Reviewed

Planning artifacts:

- `.planning/phases/03-koopman-mpc-controller-integration/03-SPEC.md`
- `.planning/phases/03-koopman-mpc-controller-integration/03-CONTEXT.md`
- `.planning/phases/03-koopman-mpc-controller-integration/03-RESEARCH.md`
- `.planning/phases/03-koopman-mpc-controller-integration/03-PLAN.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`

Phase 2.5 handoff:

- `docs/phase2_5_consolidation_report.md`
- `source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json`
- `source/results/koopman_phase2_5_verify_20260701_231802/gate_report.md`

Code contracts:

- `koopman/edmd.py`
- `koopman/model.py`
- `koopman/lifted_edmd.py`
- `koopman/selection.py`
- `easyuuv_env.py`
- `workflows/play_controller.py`

## Intended Paper Combination

### EasyUUV Paper Role

EasyUUV should provide the control-layer architecture:

```text
high-level policy or direct reference
  -> low-level controller
  -> 8D PWM
  -> thruster and hydrodynamics pipeline
```

For this project, Phase 3 should replace the low-level A-S-Surface/PID branch with Koopman+MPC. It should not move LLM or PPO logic into the real-time actuator loop.

### Koopman-Sim2Real Paper Role

Koopman-Sim2Real should provide the model-based control direction:

```text
data
  -> EDMD / Koopman model
  -> MPC finite-horizon optimization
  -> robot control
  -> optional online Kalman update later
```

The exact paper system is 3-DOF and cannot be copied directly into EasyUUV's 11D state and 8D PWM interface. The valid transfer is the structure and modeling principle, not the original state/control dimensions.

## Current Algorithmic Reality

The selected Phase 2.5 model is:

```text
model_class = direct_state
control_dim = 8
```

Its prediction form is:

```text
x[k+1] = W * [phi(x[k], r[k]), u[k]]
```

where:

- `x[k]` is the 11D EasyUUV state.
- `r[k]` is the 5D reference.
- `u[k]` is 8D PWM.
- `phi(x[k], r[k])` includes state, reference, tracking error and quadratic terms.

This is useful for MPC integration, but it differs from the Koopman-Sim2Real lifted-space formulation:

```text
f[k+1] = Theta^T * f[k]
```

The codebase already contains a closer paper-style backend in `koopman/lifted_edmd.py`, but Phase 2.5 selected `direct_state` because it passed the gate with the best validation ranking.

## Healthy Contract Points

The following parts of Phase 3 are well aligned and should be kept:

- **Manifest-first runtime:** Phase 3 must load `selected_model_manifest.json` and reject non-pass or stale artifacts.
- **8D PWM optimization:** This matches `control_dim = 8` and avoids a hidden mismatch through legacy `_pid_control()`.
- **Physics preservation:** `_compute_dynamics()` after PWM generation should remain unchanged.
- **Fallback-first safety:** previous valid PWM, then legacy controller fallback, is appropriate for a first smoke run.
- **PPO deferred:** server lacks PPO checkpoint, so `workflows/play_controller.py` remains the right first entrypoint.
- **No final performance claim:** Phase 3 should only prove closed-loop execution and diagnostics.

## Must-Fix Recommendations

### 1. Add An Explicit Algorithm Contract To `03-SPEC.md`

Add a section after `Paper Alignment`:

```text
## Algorithm Contract

Phase 3 uses the Phase 2.5 selected direct_state model as the first MPC prediction backend.
This is an engineering Koopman predictor, not a full paper-style lifted EDMD controller.

The runtime interface must support both:
- direct_state
- paper_lifted_edmd

The Phase 3 summary must state which backend was used in the Isaac smoke run.
Research claims must say that Phase 3 inherits the EDMD -> Koopman model -> MPC structure, while exact lifted-space replication remains backend-dependent.
```

Rationale: this prevents future docs or papers from overstating the current implementation.

### 2. Make Phase 2.5 Limitations Non-Empty

The selected manifest currently has `known_limitations = []`, but the Phase 2.5 report shows important limitations:

- selected model is `direct_state`, not paper-style lifted EDMD;
- one-step RMSE is high;
- validation/test gap is visible;
- Phase 2.5 is an offline model gate, not closed-loop control evidence.

Update either the manifest generation logic or the consolidation report to include these limitations. The gate can still be `pass`, but the limitations must be visible before Phase 3 consumes the model.

Suggested text:

```text
known_limitations:
- selected backend is direct_state, not paper_lifted_edmd
- one-step RMSE remains high despite non-divergent multi-step rollout
- validation/test trajectory gap remains
- Phase 3 may use this model for smoke integration only; Phase 4 must perform closed-loop comparison
```

### 3. Add A Paper-Style Backend Check To `03-PLAN.md`

The plan says the runtime should load `paper_lifted_edmd` for future compatibility, but it does not require any actual check.

Add a small wave after manifest runtime loading:

```text
## Wave 1.5: Core Algorithm Backend Check

Tasks:
- Load the best passing paper_lifted_edmd candidate from Phase 2.5 sweep results.
- Run the same offline MPC replay samples with direct_state and paper_lifted_edmd.
- Report prediction metrics, horizon cost and command boundedness for both backends.
- Keep direct_state for the first Isaac smoke only if it is clearly safer.
- Record the backend decision in the Phase 3 summary.
```

Rationale: this keeps the implementation connected to the Koopman-Sim2Real core formulation without blocking the first smoke on a worse backend.

## Should-Fix Recommendations

### 4. Rephrase The First Solver

The current plan uses a pure NumPy solver. That is acceptable for Phase 3, but it should be described as:

```text
first-pass receding-horizon optimizer
```

not as a full equivalent to the paper's CasADi MPC.

Add this acceptance criterion:

```text
For fixture states, the solver must produce lower predicted horizon cost than hold-previous-PWM. If it cannot, fallback should be preferred and recorded.
```

### 5. Preserve The Future RL Interface

Phase 3 does not require PPO, but the final project goal is still RL + Koopman-MPC. Add this constraint:

```text
The MPC adapter input must remain state/reference based so future PPO-generated 4D attitude/depth corrections can be converted into the same reference interface.
```

This preserves the EasyUUV paper structure even while Phase 3 uses direct-controller smoke.

### 6. Separate Quaternion Cost Handling From Model Input Handling

The MPC cost should handle `q` and `-q` equivalence. But the prediction wrapper should not silently change quaternion signs unless the training pipeline does the same.

Add requirements:

- cost function may align quaternion sign for error computation;
- model input quaternion convention must match training logs;
- diagnostics should record predicted quaternion norm.

## Suggested Exact Document Edits

### `03-SPEC.md`

Add:

- `Algorithm Contract` section.
- Acceptance criterion: Phase 3 summary states selected backend type and whether it is paper-style lifted EDMD.
- Acceptance criterion: solver beats hold-previous-PWM predicted cost or explicitly falls back.
- Boundary statement: Phase 3 smoke with `direct_state` is not a final Koopman-Sim2Real replication claim.

### `03-PLAN.md`

Add:

- `Wave 1.5: Core Algorithm Backend Check`.
- Offline comparison between `direct_state` and best passing `paper_lifted_edmd`.
- Final summary field: `backend_used`, `backend_reason`, `fallback_rate`, `latency_budget_met`.

### `03-RESEARCH.md`

Strengthen:

- "Phase 3 can honestly claim Koopman-MPC structure" should be qualified with "when described as EDMD-trained prediction model plus receding-horizon control."
- Add warning that current selected backend is not the paper's exact lifted-space transition.

### `docs/phase2_5_consolidation_report.md`

Change the "Known limitations" section from implicit prose into a concrete list. The current report already says the cautious points, but they should be promoted to the model handoff contract.

### `selected_model_manifest.json`

If this artifact is regenerated, include non-empty `known_limitations`. If it is treated as immutable server output, keep it as-is but make Phase 3 runtime summary copy limitations from the consolidation report.

## Recommended Phase 3 Success Statement

Use this wording at the end of Phase 3:

```text
Phase 3 completed the first fallback-safe Koopman-MPC controller integration.
The smoke run used the Phase 2.5 selected direct_state prediction backend.
This validates the controller seam, bounded 8D PWM output, manifest loading, solver diagnostics and Isaac closed-loop execution.
It does not yet prove final performance superiority or full paper-style lifted EDMD control.
Those claims are deferred to backend comparison and Phase 4 experiments.
```

## Decision

Phase 3 can proceed, but only after the docs distinguish these two layers:

1. **Engineering integration layer:** selected `direct_state` model + 8D PWM MPC + fallback-safe Isaac smoke.
2. **Core paper-aligned algorithm layer:** lifted-space EDMD backend + MPC comparison, ideally evaluated before or during Phase 3 and emphasized in Phase 4.

This keeps the project honest: the first closed-loop controller can be practical and safe, while the research claim remains anchored to the Koopman-Sim2Real formulation and the EasyUUV layered control architecture.

# Requirements: EASYkoopman v2.0

**Defined:** 2026-08-09
**Milestone:** v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control
**Core Value:** Build control experiments whose model, checkpoint, controller path and evaluation evidence are explicit enough to reproduce, compare and reject safely.

## v2.0 Requirements

### EasyUUV 2.0 Intake and Qualification

- [x] **QUAL-01**: A researcher can identify the exact received `easyuuv_v2-main/` simulator snapshot separately from all later integration changes in Git history.
- [x] **QUAL-02**: A researcher can enumerate exactly `base`, `long_body`, `heavy_moderate`, `asymmetric`, `uuv6`, `uuv6_angled`, `uuv4` and `uuv4_angled` through one supported configuration catalog.
- [x] **QUAL-03**: A server operator can install and import the simulator through one documented `easyuuv_nc` package, entry-point and asset-resolution contract.
- [x] **QUAL-04**: A qualification report records each supported configuration's expected thruster count, TAM rank and controllable-degree-of-freedom mask, including explicit yaw underactuation for `uuv4*`.
- [x] **QUAL-05**: A server operator can run a minimum Isaac rollout for `base` and a defined smoke test for each of the other seven supported configurations.
- [x] **QUAL-06**: Qualification rejects any rollout that produces a non-finite value or a PWM/virtual-control command outside its declared bound.
- [x] **QUAL-07**: A researcher can run the existing Isaac-free v1 regression suite after intake without modifying the `v1.0` tag or archived v1.0 planning records.
- [x] **QUAL-08**: Phase 6 produces a server runbook, machine-readable qualification artifact, SUMMARY and VERIFICATION before Phase 7 begins.

### Cross-Configuration Data and Control Contract

- [x] **CONT-01**: A versioned schema v2 records `state_11`, `reference_5`, `raw_action_4`, `virtual_control_4`, `motor_pwm_padded_8`, `thruster_mask_8`, `applied_wrench_6`, platform/environment context, `next_state_11`, configuration identity and episode provenance.
- [x] **CONT-02**: Koopman and MPC consumers use `virtual_control_4 = [roll, pitch, yaw, depth]` as the topology-independent control meaning before TAM allocation.
- [x] **CONT-03**: Padded PWM is available for diagnostic, saturation and energy analysis but cannot silently become the default cross-configuration learned-control input.
- [x] **CONT-04**: Dataset records distinguish oracle environment context from estimated deployable environment context.
- [x] **CONT-05**: Existing v1 logs remain readable through an explicit compatibility path without being relabelled as schema v2 or multi-configuration evidence.

### Multi-Configuration Koopman Identification

- [x] **KID-01**: Training, validation and test data are split by configuration and episode rather than by randomly sampled rows.
- [x] **KID-02**: The identification workflow compares persistence, linear, per-configuration Koopman, pooled Koopman, conditional Koopman and per-configuration expert upper-bound models under the same split manifest.
- [x] **KID-03**: Held-out-configuration reports include one-step, multi-step and rollout prediction metrics with configuration-level aggregation.
- [x] **KID-04**: Orientation prediction error uses an SO(3) geodesic metric and is not labelled from raw quaternion-component RMSE.
- [x] **KID-05**: Model selection writes a provenance-checked manifest and permits `no_selection` when no candidate passes every required gate.

### Phase 8.1 Local Simulator and Identification Repair

- [x] **KIDR-01**: Thruster first-order dynamics use physics-substep end times so the first substep after reset receives one full `physics_dt` and D substeps match the analytic first-order response.
- [x] **KIDR-02**: Additive schema v2.1 records a causal `actuator_memory_4` and exposes an exact 19D primary view without modifying schema v2 bytes or defaults.
- [x] **KIDR-03**: The v2.1 Bridge/collector records and validates `physics_dt_s`, integer `decimation` and `control_dt_s=physics_dt_s*decimation`, with zero warm-up and episode-local memory reset.
- [x] **KIDR-04**: The Phase 8.1 backend predicts body-right SO(3) increments through deterministic Log/Exp semantics rather than arbitrary quaternion-component recursion and projection.
- [x] **KIDR-05**: Frozen 22/56D observables and 66/100D PCA2 structured conditional designs pass exact ordering, source-only PCA and numerical admission contracts.
- [x] **KIDR-06**: Multi-step rollout uses only the window-start memory and causal recurrence, never future memory truth, and reports identity/simple-linear estimator equivalence honestly.
- [x] **KIDR-07**: Every fold can seal a complete source candidate ledger, isolate held-out descriptor diagnostics, independently select a non-promoting expert and report all source-per-configuration models without cross-unit ranking.
- [x] **KIDR-08**: Positive selection can execute a test-free all-eight fit/validation final refit and atomic publication through an interface that accepts only the selected family.
- [x] **KIDR-09**: Phase 8.1 role/analysis protocols remain pending D-23, while a separate approval-record validator fails closed without creating or authenticating a real human approval.
- [x] **KIDR-10**: Targeted and related local regressions verify v2/v2.1 isolation and claim boundaries without bundle, SSH, server collection, formal LOCO or Phase 9 execution.

### Phase 8.2 Fresh Server Evaluation and Closeout

- [ ] **KIDO-01**: A versioned Phase 8.2 operational shell validates canonical D-23, targeted/relevant local tests and a clean committed HEAD, then creates an offline-verified and cloneable Git bundle before any SSH request.
- [ ] **KIDO-02**: The unchanged server collects a fresh exact-eight v2.1 dataset in isolated checkout/result roots with exactly 96 protocol episodes and fail-closed native, tee, schema and partial-file gates.
- [ ] **KIDO-03**: Server inventory/split and staged local pullback validate source commit, protocol/approval hashes, exact file set, every v2.1 episode and exact-eight split before atomic canonical promotion.
- [ ] **KIDO-04**: Formal eight-fold LOCO preserves source-only selection and pre-test freeze in every fold, then publishes the frozen outer `SELECTION` or pathless `NO_SELECTION` without post-test tuning.
- [ ] **KIDO-05**: Independent closeout verifies all canonical envelopes and limits the conclusion to fresh-episode transfer within the fixed exact-eight catalog before any Phase 9 handoff.

### Configuration-Aware Koopman-MPC

- [ ] **MPC2-01**: MPC optimizes bounded 4D virtual control and uses the active configuration's TAM allocator to produce physical thruster commands.
- [ ] **MPC2-02**: Controllable-degree-of-freedom masks prevent infeasible objectives, including yaw tracking on `uuv4*`, from entering optimization or scoring as achievable targets.
- [ ] **MPC2-03**: Timeout, infeasibility, non-finite output and saturation trigger deterministic bounded fallback with reason-coded diagnostics.
- [ ] **MPC2-04**: Each configuration is compared with the legacy/S-Surface baseline under matched scenario, seed, horizon and disturbance inputs.

### Environment Awareness and Online Adaptation

- [ ] **ADAPT-01**: Oracle environment context establishes an upper-bound result before any claim is made for estimated context.
- [ ] **ADAPT-02**: A deployable estimator derives environment context only from signals available to the runtime controller and reports estimation error separately from control error.
- [ ] **ADAPT-03**: RLS/KF online Koopman updates enforce parameter bounds, non-finite rejection, a frozen prior, rollback and a documented disable path.
- [ ] **ADAPT-04**: Adaptation evaluation reports pre-shift degradation, post-shift recovery curve, rollback events and matched frozen-model baselines.
- [ ] **ADAPT-05**: Online adaptation is promoted only when it improves the declared aggregate gate without violating per-configuration safety or stability sentinels.

### Low-Frequency Agent Supervisor

- [ ] **AGENT-01**: The Agent Supervisor can choose only from allow-listed model selection, online-update enablement, bounded reference/MPC configuration and safety-fallback decisions.
- [ ] **AGENT-02**: The Agent Supervisor cannot issue PWM, produce a PPO action or participate in the real-time `env.step()` loop.
- [ ] **AGENT-03**: Every Agent decision records inputs, selected action, rationale/provenance, gate result and fallback outcome; invalid or unavailable decisions fail closed.
- [ ] **AGENT-04**: Agent effectiveness is evaluated against both no-supervisor and deterministic rule-supervisor baselines under the same matched experiment manifest.

### Final Evaluation and Research Evidence

- [ ] **EVAL-01**: The final matrix covers nominal, held-out-configuration, environment-shift and combined-shift scenarios with declared seeds and episode counts.
- [ ] **EVAL-02**: Every result is labelled as local contract evidence, server smoke, stable run, matched evaluation or promotion evidence and passes a machine-readable artifact validator.
- [ ] **EVAL-03**: Reports include per-configuration results, aggregate results, safety/stability sentinels, controller fallback rates and uncertainty or repeated-seed summaries.
- [ ] **EVAL-04**: Final promotion requires every mandatory gate and explicitly supports a negative `no_selection` conclusion.
- [ ] **EVAL-05**: The milestone closes with reproducible server commands, artifact provenance, limitations and a research-summary boundary that does not claim Sim2Real or hardware validation.

## Future Requirements

### Deployment

- **DEPLOY-01**: Validate the selected architecture on physical UUV hardware with calibrated sensor, actuator and timing models.
- **DEPLOY-02**: Establish a Sim2Real transfer protocol with hardware safety supervision and reproducible field-trial evidence.

### Rich Embodiment Assets

- **ASSET-01**: Provide distinct geometry, collision and sensor assets when research questions require visually or physically different hulls rather than parameter/topology variants.

## Out of Scope

| Feature | Reason |
|---|---|
| Hardware or Sim2Real success claims | No physical platform evidence is part of v2.0. |
| Eight distinct CAD/visual robots | The received configurations share one USD appearance; v2.0 studies parameter and actuator-topology transfer. |
| Direct Agent/LLM/PPO PWM control | Violates the bounded layered-control architecture and makes safety attribution ambiguous. |
| End-to-end unrestricted autonomous agent | v2.0 evaluates a low-frequency allow-listed supervisor only. |
| PPO training during Phase 6 | Simulator qualification and interface truth must precede learning. |
| Row-level random OOD split | It leaks temporal/configuration information and cannot support transfer claims. |
| Forced winner selection | A negative result is required when no candidate passes every promotion gate. |

## Traceability

| Requirement | Phase | Status |
|---|---|---|
| QUAL-01 | Phase 6 | Complete |
| QUAL-02 | Phase 6 | Complete |
| QUAL-03 | Phase 6 | Complete |
| QUAL-04 | Phase 6 | Complete |
| QUAL-05 | Phase 6 | Complete |
| QUAL-06 | Phase 6 | Complete |
| QUAL-07 | Phase 6 | Complete |
| QUAL-08 | Phase 6 | Complete |
| CONT-01 | Phase 7 | Complete |
| CONT-02 | Phase 7 | Complete |
| CONT-03 | Phase 7 | Complete |
| CONT-04 | Phase 7 | Complete |
| CONT-05 | Phase 7 | Complete |
| KID-01 | Phase 8 | Complete |
| KID-02 | Phase 8 | Complete |
| KID-03 | Phase 8 | Complete |
| KID-04 | Phase 8 | Complete |
| KID-05 | Phase 8 | Complete |
| KIDR-01 | Phase 8.1 | Complete |
| KIDR-02 | Phase 8.1 | Complete |
| KIDR-03 | Phase 8.1 | Complete |
| KIDR-04 | Phase 8.1 | Complete |
| KIDR-05 | Phase 8.1 | Complete |
| KIDR-06 | Phase 8.1 | Complete |
| KIDR-07 | Phase 8.1 | Complete |
| KIDR-08 | Phase 8.1 | Complete |
| KIDR-09 | Phase 8.1 | Complete |
| KIDR-10 | Phase 8.1 | Complete |
| KIDO-01 | Phase 8.2 | Pending |
| KIDO-02 | Phase 8.2 | Pending |
| KIDO-03 | Phase 8.2 | Pending |
| KIDO-04 | Phase 8.2 | Pending |
| KIDO-05 | Phase 8.2 | Pending |
| MPC2-01 | Phase 9 | Pending |
| MPC2-02 | Phase 9 | Pending |
| MPC2-03 | Phase 9 | Pending |
| MPC2-04 | Phase 9 | Pending |
| ADAPT-01 | Phase 10 | Pending |
| ADAPT-02 | Phase 10 | Pending |
| ADAPT-03 | Phase 10 | Pending |
| ADAPT-04 | Phase 10 | Pending |
| ADAPT-05 | Phase 10 | Pending |
| AGENT-01 | Phase 11 | Pending |
| AGENT-02 | Phase 11 | Pending |
| AGENT-03 | Phase 11 | Pending |
| AGENT-04 | Phase 11 | Pending |
| EVAL-01 | Phase 12 | Pending |
| EVAL-02 | Phase 12 | Pending |
| EVAL-03 | Phase 12 | Pending |
| EVAL-04 | Phase 12 | Pending |
| EVAL-05 | Phase 12 | Pending |

**Coverage:**

- v2.0 requirements: 51 total
- Mapped to phases: 51
- Unmapped: 0 ✓

---

*Requirements defined: 2026-08-09*
*Last updated: 2026-08-30 for Phase 8.2 operational isolation*

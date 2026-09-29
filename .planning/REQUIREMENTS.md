# Requirements: EASYkoopman v2.0

**2026-09-29最终确认：** 下一步仅做“加扰动”和“物理与Koopman结合”。物理基线事前冻结，不学习新增扰动数据、不重新校准；Koopman可离线学习，测试参数冻结，完整提升状态自行传播。旧的同数据重校准要求与覆盖优先研究顺序不再作为当前条件。执行细节以 `.planning/STATE.md` 及其交接为准。

**Defined:** 2026-08-09
**Milestone:** v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control
**Core Value:** Build control experiments whose model, checkpoint, controller path and evaluation evidence are explicit enough to reproduce, compare and reject safely.

**Phase9历史结果（2026-09-24，v76首组报告）：** 首组四构型×三臂12案例均已尝试：8完整验收、4失败。base投影MPC相对反馈改善3.05%，uuv4变差5.79%；long_body/uuv6未形成完整MPC配对。连续优化及恢复分支已实现；已定位进程CPU计时干扰、初值敏感性和目标/评分差异。当前投影模型与同参数物理等价，独特Koopman收益未证明。 服务器48项定向检查、本地15通过/4跳过（服务器有覆盖）。不勾选整体控制有效性或泛化需求。[当前报告](../docs/phase9_continuous_v76_report.md)。

**当前v78：** v78四构型统一设置2秒验证已交付。8个MPC单元中8个完整验收；投影分支1/4个构型的综合误差低于反馈，名义物理分支1/4个。模型冻结、零训练；本轮只作短任务描述性比较，Phase9保持开放。 仍不勾选整体控制、泛化或实时性需求。[完整表](../docs/phase9_common_profile_v78_report.md)。

**历史v77：** v77有界求解与控制实验已交付。r4首组四构型×两模型8例均完整验收；原repair设置仅base改善0.67%，其他三个构型仍负收益。uuv4提高深度权重并延长时域后，相对反馈改善12.15%，是短任务局部收益，不是统一跨构型或独特Koopman收益证明。模型冻结、零训练，Phase9保持开放。 不勾选整体控制有效性或泛化需求。[当前报告](../docs/phase9_reliable_control_v77_report.md)。

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

- [x] **KIDO-01**: A versioned Phase 8.2 operational shell validates canonical D-23, targeted/relevant local tests and a clean committed HEAD, then creates an offline-verified and cloneable Git bundle before any SSH request.
- [x] **KIDO-02**: The unchanged server collects a fresh exact-eight v2.1 dataset in isolated checkout/result roots with exactly 96 protocol episodes and fail-closed native, tee, schema and partial-file gates.
- [x] **KIDO-03**: Server inventory/split and staged local pullback validate source commit, protocol/approval hashes, exact file set, every v2.1 episode and exact-eight split before atomic canonical promotion.
- [x] **KIDO-04**: Formal eight-fold LOCO preserves source-only selection and pre-test freeze in every fold, then publishes the frozen outer `SELECTION` or pathless `NO_SELECTION` without post-test tuning.
- [x] **KIDO-05**: Independent closeout verifies all canonical envelopes and limits the conclusion to fresh-episode transfer within the fixed exact-eight catalog before any Phase 9 handoff.

Completion labels synchronized on2026-09-12 from [08.2-VERIFICATION.md](phases/08.2-phase-8-1-fresh-server-evaluation-and-closeout/08.2-VERIFICATION.md) and canonical closeout (`VERIFIED`, `NO_SELECTION`, no model handoff). No experiment was rerun or promoted for this documentation correction.

### Phase 8.3 Control and Identification Forensics

- [x] **CFR-01**: Effective configuration, actual loaded source and Isaac substep trace establish the control/physics/token timing; default raw-action excitation is distinguished from true state-feedback modes.
- [x] **CFR-02**: One fixed source-only historical candidate is diagnosed at its earliest failing horizon/step with reason and provenance, without test tuning or rerunning formal LOCO.
- [x] **CFR-03**: Behavior-preserving bounded traces across base/uuv6/uuv4 quantify substep controls and cold/warm reset effects, including propagation beyond the first row and explicit terminal/reset boundaries.
- [x] **CFR-04**: Input, actuator-state and platform-context representations are compared with causal/deployable observability, same-trajectory controls and explicit oracle/sample-coverage limitations.
- [x] **CFR-05**: An evidence-backed interface recommendation and GO/NO_GO/INCONCLUSIVE investment decision separate contract correctness from model benefit; missing runtime evidence cannot be marked complete.
- [x] **CFR-06**: Diagnostic runs preserve frozen results, source-role isolation, bounded budgets and server-start gates; no implicit recollection or Phase9 promotion occurs.

### Phase 8.4 Conditional Contract and Identification Experiment

- [x] **NID-01**: After an accepted8.3 GO, one versioned causal/deployable control/state contract is implemented and evaluated by a fresh bounded pilot before formal recollection is considered.
- [x] **NID-02**: Formal work starts only after pilot GO and a new approved D-23 with a new experiment ID/result root, declared schema semantics and whole-episode role isolation; old test results cannot tune the new protocol.
- [x] **NID-03**: A new selection/no-selection and independent closeout honestly delimit model/control handoff; alternative linear/per-config evidence cannot inherit pooled-Koopman or zero-shot claims.

- [x] **NID-04**: After the frozen formal NO_SELECTION, establish free-water/contact/clearance and force-balance admission, then audit state-dynamics structure/coverage, prepare one constrained Koopman candidate and a separately frozen fresh-evidence gate; old validation improvements cannot qualify the new model. Necessary offline screens do not certify absence of contact.
- [x] **NID-05**: After projected pilot GO, reconcile controlled lifted input timing, observable recurrence and the implemented predictor; separate physical-parameter identification from a learned Koopman contribution and freeze fresh evidence before model handoff.

### Configuration-Aware Koopman-MPC

Latest user priority (2026-09-20): evaluate existing Koopman implementations on the supported configurations before expanding adaptation, persistent learning or Agent work. Preserve variant-specific results; verify useful control and actual cost first, and propose a direction change when fair bounded evaluation fails. Unique Koopman representation advantage is a separate claim, not a prerequisite for testing practical control. See [effectiveness-first criteria](../docs/phase9_shared_policy_generalization_scope.md#0-最新优先级先验证现有-koopman-是否有效).

- [ ] **MPC2-01**: MPC jointly optimizes a continuous multi-step, multi-axis sequence of bounded 4D pre-TAM virtual control (the old fixed 7/9-candidate search alone is insufficient), validates the optimization predictor against the admitted exact rollout, and uses a qualifying model whose input, deployable state and hold/substep timing match actual execution through the active configuration's mask, limiter and TAM; MPC output is not reinterpreted by S-surface/PID.
- [ ] **MPC2-02**: Controllable-degree-of-freedom masks prevent infeasible objectives, including yaw tracking on `uuv4*`, from entering optimization or scoring as achievable targets.
- [ ] **MPC2-03**: Timeout, infeasibility, non-finite output, out-of-support states/commands, stale plans and saturation enter reason-coded bounded fallback/limiter arbitration with explicit controller/actuator-estimator handover. A feasible recovery may be admitted when the internal baseline is infeasible; normal improvement and restoration have distinct semantics. Failure to find a solution, timeout and numerical failure are distinguished from proven infeasibility. The solver cannot block low-level command deadlines; late plans never become issued history.
- [ ] **MPC2-04**: Each configuration is compared with Legacy/S-Surface under matched scenarios, seeds, horizons, information access and disturbances. A same-optimizer, same-compute-budget comparison of nominal physics, identified-parameter physics and the admitted projected model separates control, identification and representation benefits; algebraically equivalent models cannot support a unique Koopman advantage claim. Include a feedback-only fallback comparator and actual MPC activation/fallback, failures, constraint violations and complete-cycle cost for every episode. Define practical equivalence margins and uncertainty before running; do not require exact trajectory equality or interpret short interface checks as control benefit.

Shared-policy interpretation (2026-09-20): freeze the learned parameters, controller settings and configuration-to-constraint rules across evaluated configurations; expose declared mechanical descriptors/TAM/masks as inputs, not target-specific tuning. Separate known-configuration shared control from unseen-configuration transfer. The current fit-domain loader intentionally excludes heldout configurations; target trajectory data cannot silently provide their admission domain. See [code-grounded scope](../docs/phase9_shared_policy_generalization_scope.md).

Progress interpretation and sequencing (user accepted 2026-09-20): the subjective 40–50/100 research estimate is not an acceptance metric; the 94% plan count does not complete MPC/ADAPT/AGENT/EVAL. Establish useful matched closed-loop behavior before expanding adaptation or Agent work; negative evidence can close an evaluation without qualifying its successor. This turn updates documents and stops before server access.

### Environment Awareness and Online Adaptation

- [ ] **ADAPT-01**: Oracle environment context establishes an upper-bound result before any claim is made for estimated context.
- [ ] **ADAPT-02**: A deployable estimator derives environment context only from signals available to the runtime controller and reports estimation error separately from control error.
- [ ] **ADAPT-03**: Before RLS/KF updates, specify the admitted update target (environment context, physical parameters or lifted operator) and identifiability. Enforce bounds, non-finite rejection, a frozen prior, rollback and a disable path; parameter adaptation is not full-operator learning.
- [ ] **ADAPT-04**: Adaptation evaluation reports pre-shift degradation, post-shift recovery curve, rollback events and matched frozen-model baselines.

For cross-task improvement claims under ADAPT-04, additionally compare retained experience with per-task reset and continuous updating without a model library; evaluate fresh repeated-condition trajectories, sample efficiency and old-task retention under matched data/compute/memory budgets. This is a planned extension, not a completed requirement or a new experiment authorization.
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
| KIDO-01 | Phase 8.2 | Complete |
| KIDO-02 | Phase 8.2 | Complete |
| KIDO-03 | Phase 8.2 | Complete |
| KIDO-04 | Phase 8.2 | Complete |
| KIDO-05 | Phase 8.2 | Complete |
| CFR-01 | Phase 8.3 | Complete — actual default-mode clock/source/substeps |
| CFR-02 | Phase 8.3 | Complete — one source-only candidate; no family-wide causality |
| CFR-03 | Phase 8.3 | Complete — revised repaired static coverage; unexecuted legacy cases retained |
| CFR-04 | Phase 8.3 | Complete —12 fixed exploratory causal comparisons; performance remains inadequate |
| CFR-05 | Phase 8.3 | Complete — GO to bounded direct-interface pilot only |
| CFR-06 | Phase 8.3 | Complete — isolated source/results, bounded budgets and real pullback gates |
| NID-01 | Phase 8.4 | Complete;02 NO_GO frozen,03 independent structured pilot GO, no formal handoff |
| NID-02 | Phase 8.4 | Complete; approved formal56episodes accepted and fixed68fit validation; test uncollected after NO_GO |
| NID-03 | Phase 8.4 | Complete; independently checked NO_SELECTION, no model handoff |
| NID-04 | Phase 8.4 | Complete; causal free-water data, coverage,34 frozen models,new16validation and independent projected pilot GO; no full-operator handoff |
| NID-05 | Phase 8.4 | Complete within scope; frozen v38 validation/test independently GO; corrected command handoff v2; model/parameter equivalence explicit, no extra Koopman advantage proven |
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

- v2.0 requirements: 62 total
- Mapped to phases: 62
- Unmapped: 0 ✓

---

*Requirements defined: 2026-08-09*
*Last updated: 2026-09-12 for8.2 completion synchronization,8.3 forensic planning, conditional8.4 and Phase9 interface constraints. CFR-02 completed by the fixed local source-only replay; other CFR requirements remain open. Future planning is not evidence of execution.*

Current8.3 closure: see `phases/08.3-control-identification-forensics/08.3-VERIFICATION.md`. Six forensic requirements complete; NID/MPC/ADAPT/AGENT/EVAL remain unproven.

Current2026-09-20: NID-01..05 completed within their scoped requirements; see [08.4 verification](phases/08.4-conditional-identification-experiment/08.4-VERIFICATION.md). MPC/ADAPT/AGENT/EVAL remain open; qualified prediction handoff does not imply full-operator closure, control benefit or scientific-goal completion.

2026-09-20路线审核：MPC2-03/04及ADAPT-03细化截止时间、支持域和收益归因；没有新增requirement或关闭MPC/ADAPT/AGENT/EVAL。参见[审核](../docs/phase9_roadmap_review.md)。


2026-09-20 v57推进：v57本地采集与离线执行/仲裁重放通过325项相关测试；不构成真实Isaac、实时性或闭环效果验收，MPC2-01..04保持未完成。 [结果](../docs/phase9_runtime_collector_v57_results.md)。


2026-09-20 v58推进：v58独立执行包通过347项相关回归，1项真实Linux进程测试等待现场探针。实际Isaac、完整周期实时性和匹配闭环收益均未验证，MPC2-01..04保持未完成。 [结果](../docs/phase9_runtime_release_v58_results.md)。

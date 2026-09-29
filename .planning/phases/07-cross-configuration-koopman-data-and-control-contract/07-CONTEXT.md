# Phase 7: Cross-Configuration Koopman Data and Control Contract — Context

**Gathered:** 2026-08-11  
**Status:** Ready for planning  
**Source:** PRD Express Path (`07-SPEC.md`, Phase 6 verified evidence, canonical v2.0 roadmap/requirements)

<domain>
## Phase Boundary

Phase 7 establishes the versioned transition schema v2 and Koopman Bridge that align EasyUUV 2.0 state, reference, 4D topology-independent control, N-thruster execution, actual actuator wrench, platform/environment context and episode provenance. It adds an explicit v2 dataset view and an explicit read-only v1 compatibility adapter.

It does not train or select a multi-configuration Koopman model, evaluate held-out-configuration prediction, migrate MPC, implement an environment estimator/online adaptation, or add an Agent runtime. Those capabilities remain in Phase 8–11.

</domain>

<decisions>
## Implementation Decisions

### Additive versioning and v1 isolation

- **D-01:** schema v2 is implemented through additive modules and explicit entry points. Existing v1 logger/loader, `KoopmanDataset`, `koopman/model.py`, `koopman/mpc.py` and `koopman/mpc_controller.py` keep their current default semantics during Phase 7.
- **D-02:** v1 logs are accepted only by a named read-only compatibility adapter. The adapter records `source_schema=v1`, unavailable fields and `eligible_for_v2_cross_configuration_training=false`; it never fabricates virtual control, applied wrench, context or configuration identity.
- **D-03:** strict schema v2 validation rejects both raw v1 records and adapter views. Compatibility is not relabelling, upgrading or promotion evidence.

### Control and actuator semantics

- **D-04:** the only default v2 model-facing control is `virtual_control_4` in fixed `[roll,pitch,yaw,depth]` order, measured after low-level control/mask handling and before TAM allocation.
- **D-05:** `raw_action_4` records the high-level action supplied to the environment and remains distinct from `virtual_control_4`. For `uuv4*`, nonzero raw yaw is allowed as an input record but virtual yaw must be zero before TAM.
- **D-06:** `motor_pwm_padded_8` uses canonical thruster order, records clipped actual N-channel PWM, right-pads with exact zeros and is interpreted only together with `thruster_mask_8`. The default v2 training tuple cannot return PWM as `U`.
- **D-07:** `applied_wrench_6` is the thruster-only body-frame wrench actually produced after PWM conversion, thruster dynamics and runtime efficiency/fault/ventilation scaling. Desired TAM wrench and total wrench including hydrodynamic/boundary forces are different quantities and cannot satisfy this field.

### Context and provenance

- **D-08:** `platform_context` is derived from the active catalog/runtime configuration, not an independently copied configuration table. It includes configuration identity, topology/control facts and the platform dynamics fields enumerated by `07-SPEC.md`.
- **D-09:** `environment_context_oracle` and `environment_context_estimated` are separate typed objects with independent availability, method/source, unit/frame and value provenance. Phase 7 may emit estimated context as unavailable; it does not implement an estimator.
- **D-10:** schema v2 uses one exact version identifier and rejects unknown/ambiguous versions, missing/extra required fields, non-finite values, shape/range violations, context provenance violations, topology contradictions and episode continuity drift with stable reason codes.
- **D-11:** a transition binds pre-step state/reference/action to post-controller control/execution telemetry and post-step `next_state_11` atomically. Episode identity and invariant provenance cannot change silently between rows; step/time are monotonic.

### Evidence and completion

- **D-12:** local evidence covers the exact eight-config catalog, schema fixtures, negative validator cases, Bridge/dataset contracts, v1 compatibility and full Isaac-free regression. It is labelled `local_contract` only.
- **D-13:** real server evidence covers one representative of each actuator topology: `base` (8), `uuv6` (6), and `uuv4` (4, yaw-underactuated), with at least eight contiguous v2 transitions per configuration after create/reset.
- **D-14:** server evidence is fail closed and binds the tested source commit, Isaac Sim 5.0, Isaac Lab 2.2.1, task/configuration, native command status, logs and artifact SHA-256. Missing/partial/stale/mock evidence keeps Phase 7 incomplete.
- **D-15:** Phase 7 completes only after a runbook, strict machine-readable server artifact, pullback validation, SUMMARY and VERIFICATION map every `CONT-01`..`CONT-05` requirement to concrete PASS/FAIL evidence.
- **D-16:** planning, implementation and pulled-back `source/results` evidence remain independently auditable commit/push boundaries; successful server artifacts are not pre-created by local tests.

### The agent's discretion

- Exact Python package/module names for v2 schema, Bridge, dataset view, adapter and validator, provided public imports are unambiguous and v1 defaults remain unchanged.
- Exact serialization container (for example JSONL plus a manifest), provided transitions remain streamable, deterministic, strictly validated and atomically written.
- Exact schema identifier string, provided it is a single documented constant and validators require exact equality.
- Internal dataclass/TypedDict/Pydantic-free implementation choice, provided the local environment does not gain avoidable runtime dependencies and type/shape checks remain strict.
- Exact context subfield grouping and optional-value encoding, provided the minimum semantics in `07-SPEC.md` are present and oracle/estimated separation is enforceable.
- Exact test file grouping and helper decomposition.
- Whether the three server topology smokes run in one process or three isolated invocations, provided failure/provenance remains configuration-specific and one failure blocks merge/promotion.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked Phase Contract

- `.planning/phases/07-cross-configuration-koopman-data-and-control-contract/07-SPEC.md` — authoritative Phase 7 semantics, boundaries and falsifiable acceptance criteria.
- `.planning/REQUIREMENTS.md` — canonical `CONT-01`..`CONT-05` wording and milestone traceability.
- `.planning/ROADMAP.md` — Phase 7 goal, dependency and phase-to-phase responsibility split.
- `.planning/PROJECT.md` — milestone architectural constraints and evidence philosophy.
- `docs/Agentic_AUV_v2_milestone_design.md` — user-approved v2 schema/control architecture.
- `.planning/phases/06-easyuuv-2-0-intake-and-multi-configuration-qualification/06-VERIFICATION.md` — verified upstream eight-configuration and server evidence boundary.

### Current v1 Data and Koopman Baseline

- `koopman_data.py` — v1 transition logger/loader and fixed `pwm_8d` schema.
- `koopman/dataset.py` — v1 model-facing `U=PWM_8` dataset semantics that must remain unchanged.
- `koopman/model.py` — v1 Koopman model dimension contract; not migrated in Phase 7.
- `koopman/mpc.py` — v1 bounded PWM MPC contract; not migrated in Phase 7.
- `koopman/mpc_controller.py` — v1 controller integration; not migrated in Phase 7.
- `workflows/koopman_logging.py` — current v1 environment logging seam.

### EasyUUV 2.0 Runtime Truth

- `easyuuv_nc/embodiments.py` — canonical public catalog and platform/topology metadata.
- `easyuuv_nc/thrust_allocation.py` — canonical channel order, TAM construction, control-to-wrench mapping and allocation behavior.
- `easyuuv_nc/env/easyuuv_env.py` — `EasyUUVEnvCfg`、active configuration application、state/reference/action、motor telemetry、actuator dynamics、fluid/context 与实际 force/torque 的当前定义位置；Phase 7 不为整理路径而顺手拆分该文件。
- `.planning/phases/06-easyuuv-2-0-intake-and-multi-configuration-qualification/06-QUALIFICATION-RUNBOOK.md` — proven offline server transfer/execution/pullback pattern to reuse without weakening provenance.
- `scripts/phase6_prepare_bundle.ps1`, `scripts/phase6_server_bootstrap.sh`, `scripts/phase6_server_qualification.sh`, `scripts/phase6_pullback.ps1` — fail-closed evidence-chain patterns, not files to copy blindly.

</canonical_refs>

<specifics>
## Specific Ideas

- Prefer a small, pure-Python schema core that can validate serialized records without importing Isaac, Gym or Torch; keep runtime extraction in the Bridge layer.
- Cache actual thruster-only force and torque at the point where the environment already sums per-thruster forces/torques, so `applied_wrench_6` is measured rather than reconstructed from clipped PWM.
- Make the model-facing v2 dataset return a named object or explicit fields instead of a positional tuple that could confuse virtual control with PWM diagnostics.
- Reuse the Phase 6 catalog rather than hard-code the supported eight configurations or masks in schema code.
- Treat episode-level manifest validation separately from per-row validation so row validity cannot hide duplicated, missing or discontinuous transitions.
- Include negative fixtures for semantic swaps (raw action used as virtual control, desired wrench used as applied wrench, oracle copied to estimated) in addition to type/shape failures.

</specifics>

<deferred>
## Deferred Ideas

- Multi-configuration data collection matrix, episode/configuration splits, model training, model comparison, held-out OOD gates and prediction metrics — Phase 8.
- Making Koopman/MPC runtime consumers optimize/use 4D virtual control and active TAM/masks — Phase 9.
- Environment estimator, oracle upper-bound experiments, RLS/KF online updates, rollback and adaptation promotion — Phase 10.
- Low-frequency Agent Supervisor — Phase 11.
- Final matched multi-shift evaluation and research claims — Phase 12.
- Hardware, Sim2Real and distinct CAD/USD assets — future milestones.

</deferred>

---

*Phase: 07-cross-configuration-koopman-data-and-control-contract*  
*Context gathered: 2026-08-11 via PRD Express Path*

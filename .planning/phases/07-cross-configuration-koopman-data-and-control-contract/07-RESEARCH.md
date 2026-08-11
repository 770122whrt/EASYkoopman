# Phase 7: Cross-Configuration Koopman Data and Control Contract - Research

**Researched:** 2026-08-11  
**Domain:** versioned transition schema、Isaac runtime telemetry seam、4D Koopman data contract、evidence chain  
**Confidence:** HIGH（主要结论均由锁定 SPEC/CONTEXT、当前源码和 Phase 6 已验证证据直接支持）

<user_constraints>
## User Constraints (from CONTEXT.md)

> 以下内容逐字复制自 `07-CONTEXT.md` 的锁定决定、代理裁量和延期项；它们是计划与实现的硬约束。[VERIFIED: `.planning/phases/07-cross-configuration-koopman-data-and-control-contract/07-CONTEXT.md:17-116`]

### Locked Decisions

#### Additive versioning and v1 isolation

- **D-01:** schema v2 is implemented through additive modules and explicit entry points. Existing v1 logger/loader, `KoopmanDataset`, `koopman/model.py`, `koopman/mpc.py` and `koopman/mpc_controller.py` keep their current default semantics during Phase 7.
- **D-02:** v1 logs are accepted only by a named read-only compatibility adapter. The adapter records `source_schema=v1`, unavailable fields and `eligible_for_v2_cross_configuration_training=false`; it never fabricates virtual control, applied wrench, context or configuration identity.
- **D-03:** strict schema v2 validation rejects both raw v1 records and adapter views. Compatibility is not relabelling, upgrading or promotion evidence.

#### Control and actuator semantics

- **D-04:** the only default v2 model-facing control is `virtual_control_4` in fixed `[roll,pitch,yaw,depth]` order, measured after low-level control/mask handling and before TAM allocation.
- **D-05:** `raw_action_4` records the high-level action supplied to the environment and remains distinct from `virtual_control_4`. For `uuv4*`, nonzero raw yaw is allowed as an input record but virtual yaw must be zero before TAM.
- **D-06:** `motor_pwm_padded_8` uses canonical thruster order, records clipped actual N-channel PWM, right-pads with exact zeros and is interpreted only together with `thruster_mask_8`. The default v2 training tuple cannot return PWM as `U`.
- **D-07:** `applied_wrench_6` is the thruster-only body-frame wrench actually produced after PWM conversion, thruster dynamics and runtime efficiency/fault/ventilation scaling. Desired TAM wrench and total wrench including hydrodynamic/boundary forces are different quantities and cannot satisfy this field.

#### Context and provenance

- **D-08:** `platform_context` is derived from the active catalog/runtime configuration, not an independently copied configuration table. It includes configuration identity, topology/control facts and the platform dynamics fields enumerated by `07-SPEC.md`.
- **D-09:** `environment_context_oracle` and `environment_context_estimated` are separate typed objects with independent availability, method/source, unit/frame and value provenance. Phase 7 may emit estimated context as unavailable; it does not implement an estimator.
- **D-10:** schema v2 uses one exact version identifier and rejects unknown/ambiguous versions, missing/extra required fields, non-finite values, shape/range violations, context provenance violations, topology contradictions and episode continuity drift with stable reason codes.
- **D-11:** a transition binds pre-step state/reference/action to post-controller control/execution telemetry and post-step `next_state_11` atomically. Episode identity and invariant provenance cannot change silently between rows; step/time are monotonic.

#### Evidence and completion

- **D-12:** local evidence covers the exact eight-config catalog, schema fixtures, negative validator cases, Bridge/dataset contracts, v1 compatibility and full Isaac-free regression. It is labelled `local_contract` only.
- **D-13:** real server evidence covers one representative of each actuator topology: `base` (8), `uuv6` (6), and `uuv4` (4, yaw-underactuated), with at least eight contiguous v2 transitions per configuration after create/reset.
- **D-14:** server evidence is fail closed and binds the tested source commit, Isaac Sim 5.0, Isaac Lab 2.2.1, task/configuration, native command status, logs and artifact SHA-256. Missing/partial/stale/mock evidence keeps Phase 7 incomplete.
- **D-15:** Phase 7 completes only after a runbook, strict machine-readable server artifact, pullback validation, SUMMARY and VERIFICATION map every `CONT-01`..`CONT-05` requirement to concrete PASS/FAIL evidence.
- **D-16:** planning, implementation and pulled-back `source/results` evidence remain independently auditable commit/push boundaries; successful server artifacts are not pre-created by local tests.

### the agent's Discretion

- Exact Python package/module names for v2 schema, Bridge, dataset view, adapter and validator, provided public imports are unambiguous and v1 defaults remain unchanged.
- Exact serialization container (for example JSONL plus a manifest), provided transitions remain streamable, deterministic, strictly validated and atomically written.
- Exact schema identifier string, provided it is a single documented constant and validators require exact equality.
- Internal dataclass/TypedDict/Pydantic-free implementation choice, provided the local environment does not gain avoidable runtime dependencies and type/shape checks remain strict.
- Exact context subfield grouping and optional-value encoding, provided the minimum semantics in `07-SPEC.md` are present and oracle/estimated separation is enforceable.
- Exact test file grouping and helper decomposition.
- Whether the three server topology smokes run in one process or three isolated invocations, provided failure/provenance remains configuration-specific and one failure blocks merge/promotion.

### Deferred Ideas (OUT OF SCOPE)

- Multi-configuration data collection matrix, episode/configuration splits, model training, model comparison, held-out OOD gates and prediction metrics — Phase 8.
- Making Koopman/MPC runtime consumers optimize/use 4D virtual control and active TAM/masks — Phase 9.
- Environment estimator, oracle upper-bound experiments, RLS/KF online updates, rollback and adaptation promotion — Phase 10.
- Low-frequency Agent Supervisor — Phase 11.
- Final matched multi-shift evaluation and research claims — Phase 12.
- Hardware, Sim2Real and distinct CAD/USD assets — future milestones.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|---|---|---|
| CONT-01 | schema v2 记录完整 transition、context、configuration 与 episode provenance | 严格 record/episode/manifest 三层验证、原子 JSONL+manifest 写入和稳定 reason code 设计。[VERIFIED: `.planning/REQUIREMENTS.md:29`; `07-SPEC.md:43-49`] |
| CONT-02 | 默认 learned control 为 TAM 前固定 4D virtual control | 定位 `_pid_control` 中低层控制输出、mask 与 TAM 的精确边界，并要求新增 `_last_virtual_control_4`。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:2019-2174`] |
| CONT-03 | padded PWM 仅为 diagnostics | 新 `KoopmanDatasetV2` 以命名字段存储 4D control，`.U` 只能返回 4D；PWM 仅由 diagnostics 对象访问。[VERIFIED: `koopman/dataset.py:13-49,82-112`; `07-SPEC.md:59-65`] |
| CONT-04 | oracle 与 estimated context 分离 | 定义两个独立 typed envelope；Phase 7 的 estimated 默认 unavailable，不复制 oracle。[VERIFIED: `07-SPEC.md:67-73`; `07-CONTEXT.md:35`] |
| CONT-05 | v1 显式兼容但不重标 | 只读 `V1CompatibilityView` 包装现有严格 v1 loader，不生成 v2 record、不提供 promotion API。[VERIFIED: `koopman_data.py:14-24,158-186`; `07-CONTEXT.md:21-23`] |
</phase_requirements>

## Summary

Phase 7 应采用“纯 Python schema core + Isaac-adjacent Bridge + 独立 v2 dataset + 显式 v1 view + Phase 6 风格 server evidence chain”的分层实现。当前 v1 从 `koopman_data.py` 到 `KoopmanDataset`、model、MPC 全部把控制含义固定为 8D PWM；这些文件必须保持原默认行为，新能力通过带 `v2` 名称的模块和类型添加。[VERIFIED: `koopman_data.py:9-24,172-186`; `koopman/dataset.py:39-42,82-112`; `koopman/model.py:20-30`; `koopman/mpc.py:9-15,90-113`]

最重要的源码发现是：现有 `_last_pid_value` 不能直接声明为 `virtual_control_4`。它在 `PID_value` 被送入 TAM 前缓存，但 `uuv4*` 的不可控 yaw 当前是由 WLS 的零权重在 allocator 内忽略，`PID_value[:,2]` 本身没有显式归零；因此必须从 catalog 生成 4D control mask，在 TAM 前形成并缓存新的 `_last_virtual_control_4`，并让 TAM 消费同一被 mask 的值。对于 `uuv4*`，这与现有 WLS 物理输出数学等价，但能把语义从“allocator 隐式忽略”升级为“Bridge 可验证的 post-mask/pre-TAM truth”。[VERIFIED: `easyuuv_nc/embodiments.py:157-189`; `easyuuv_nc/thrust_allocation.py:113-144`; `easyuuv_nc/env/easyuuv_env.py:2149-2174`]

`applied_wrench_6` 也不能由 desired TAM wrench、clipped PWM 或 `_thrust/_moment` 反推。可靠点是 `_compute_dynamics` 在 PWM conversion、first-order dynamics、fault/mismatch/ventilation efficiency 后，将逐推进器 force/torque 求和的瞬间；紧接着 hydrodynamic、buoyancy、boundary 和 pulse 才被加进总力。应在该点缓存 thruster-only body wrench，并在同一次 dynamics 调用中缓存实际 fluid velocity 与 efficiency，避免 Bridge 在 step 后重新计算一个时间点可能不同的 wave velocity。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:2263-2338,2360-2385`]

**Primary recommendation:** 先用 TDD 完成纯 schema/manifest/validator，再增加三处只读运行时遥测和原子 Bridge，随后交付 `U=4` dataset 与 v1 adapter，最后复用 Phase 6 的 bundle/bootstrap/isolated server/pullback 模式对 `base/uuv6/uuv4` 各采集至少 8 条连续 transition。[VERIFIED: `07-CONTEXT.md:41-45`; `docs/phase6_easyuuv_v2_qualification_runbook.md:8-18,53-76,181-198`]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| record/episode/manifest schema 与 validator | Pure Python data-contract tier | CLI/workflow | 必须在无 Isaac、Gym、Torch 的本地环境中验证文件和 provenance。[VERIFIED: `07-CONTEXT.md:47-55`; `.planning/PROJECT.md:134-144`] |
| raw/virtual/PWM/applied-wrench telemetry | EasyUUV runtime tier | Bridge extraction tier | 只有运行时知道控制链中的真实时序和 post-actuator force。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:1424-1491,2019-2385`] |
| atomic transition alignment | Bridge/workflow tier | runtime telemetry tier | Bridge 负责把 pre-step 与 post-step 事实绑定，runtime 只暴露本步只读缓存。[VERIFIED: `07-CONTEXT.md:37,94-101`] |
| v2 model-facing arrays | Koopman data-access tier | schema loader | `.U` 语义必须是 4D，且 diagnostics 不得通过位置 tuple 混入。[VERIFIED: `07-SPEC.md:53-65,91`] |
| v1 compatibility | compatibility tier | existing v1 loader | 复用 v1 自身验证，但结果不能成为 v2 record 或训练资格。[VERIFIED: `koopman_data.py:158-186`; `07-CONTEXT.md:21-23`] |
| server smoke/evidence | server workflow tier | local strict validator/pullback | Isaac 进程产生事实，本地 sidecar/hash/validator 只做独立复核。[VERIFIED: `06-VERIFICATION.md:57-63`; `07-CONTEXT.md:42-45`] |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard Here |
|---|---:|---|---|
| Python standard library | local Python 3.12.4；server 3.11.13 | dataclass、JSONL、hashlib、pathlib、tempfile、atomic replace | schema core 无需新增依赖，且项目要求本地纯 Python validation。[VERIFIED: local environment probe 2026-08-11; `06-SERVER-EVIDENCE.md:48`] |
| NumPy | 1.26.4 | v2 dataset 的 `(n,11)/(n,4)/(n,5)` 数组与 finite/shape assertions | 当前 dataset 已使用 NumPy，版本已固定在 `requirements-dev.txt`。[VERIFIED: `requirements-dev.txt:5`; `koopman/dataset.py:6-49`; local environment probe 2026-08-11] |
| Torch | 2.8.0+cpu local；server 由 Isaac runtime 提供 | TAM/mask 等价测试与 EasyUUV runtime tensors | allocation/runtime 已使用 Torch；schema core 不得导入 Torch。[VERIFIED: `requirements-dev.txt:4`; `easyuuv_nc/thrust_allocation.py:9-144`; local environment probe 2026-08-11] |
| pytest | 8.4.2 local | RED→GREEN mutation、contract、regression tests | workflow 已启用 TDD，现有 qualification 使用参数化 mutation tests。[VERIFIED: `.planning/config.json`; `tests/test_easyuuv_v2_qualification.py:1-260`; local environment probe 2026-08-11] |
| Isaac Sim / Isaac Lab | 5.0 / 2.2.1 server | 三拓扑真实 Bridge smoke | Phase 6 已在同一目标服务器证明该组合，但 Phase 7 执行时仍须重新做版本 preflight。[VERIFIED: `06-VERIFICATION.md:46-52`; `06-SERVER-EVIDENCE.md:39-49`] |

### Supporting

| Component | Purpose | When to Use |
|---|---|---|
| existing `qualification_record()` | configuration、thruster count、mask、rank、allocation mode 的唯一 catalog source | schema topology validation 与 platform context build；不得复制八构型表。[VERIFIED: `easyuuv_nc/embodiments.py:157-189`] |
| existing `state_vector_from_env()` / `reference_vector()` | 保持 v1 的 11D state 与 5D reference 顺序 | Bridge 可复用或做逐值 parity test，避免 Phase 7 私自重定义 state/reference。[VERIFIED: `workflows/koopman_logging.py:24-36`] |
| `json.dumps(..., allow_nan=False, sort_keys=True)` + `os.replace` | deterministic finite serialization 与 atomic promotion | final JSON/manifest；保留 `.part` 作为失败证据。[VERIFIED: `workflows/qualify_easyuuv_v2.py:350-374`] |
| Git bundle + source sidecar + SHA-256 pullback | 无 GitHub 代理服务器的离线源码与证据绑定 | server handoff，沿用 Phase 6 经验证模式而非手工复制源码。[VERIFIED: `scripts/phase6_prepare_bundle.ps1:31-74`; `scripts/phase6_pullback.ps1:82-179`] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| standard-library schema | Pydantic/JSON Schema package | 可减少部分类型代码，但会引入当前项目没有的运行依赖，且仍需手写 topology、episode continuity 和 oracle provenance 语义；本阶段不采用。[VERIFIED: `pyproject.toml:1-15`; `requirements-dev.txt:1-5`; `07-CONTEXT.md:49-54`] |
| JSONL + episode manifest | 单个巨型 JSON artifact | 单 JSON 易做整体验证但不利流式写入和中断保留；transition JSONL 加 manifest 同时满足 streamability 与整体 hash/连续性。[VERIFIED: `07-CONTEXT.md:49`; `07-SPEC.md:46-49`] |
| 新 `_last_virtual_control_4` | 将 `_last_pid_value` 重命名/重解释 | 后者会改变 v1/Phase 6 telemetry 语义并隐藏 `uuv4` yaw 未显式 mask 的事实；禁止。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:2149-2174`; `07-CONTEXT.md:21,27-30`] |

**Installation:** 不新增 package。使用现有 `requirements-dev.txt`；Isaac 继续由服务器独立提供。[VERIFIED: `requirements-dev.txt:1-5`; `.planning/PROJECT.md:134-144`]

## Prescriptive Schema and API Design

### Exact identifiers

- transition constant：`KOOPMAN_TRANSITION_SCHEMA_V2 = "easyuuv-koopman-transition-v2"`；只接受完全相等，不接受整数 `2`、前缀或未来版本。[VERIFIED: locked discretion and D-10 in `07-CONTEXT.md:36,49-52`]
- episode manifest constant：`KOOPMAN_EPISODE_MANIFEST_V1 = "easyuuv-koopman-episode-manifest-v1"`；manifest 明确引用 transition identifier。[VERIFIED: D-10/D-11 in `07-CONTEXT.md:36-37`]
- evidence level 只允许 `local_contract` 或 `server_isaac_smoke`；本地 builder 的默认值只能是前者。[VERIFIED: `07-CONTEXT.md:41-45`; Phase 6 precedent `workflows/easyuuv_v2_qualification_artifact.py:13-16`]

### Transition exact top-level fields

每行只允许以下 13 个 top-level key：`schema_version`, `state_11`, `reference_5`, `raw_action_4`, `virtual_control_4`, `motor_pwm_padded_8`, `thruster_mask_8`, `applied_wrench_6`, `platform_context`, `environment_context_oracle`, `environment_context_estimated`, `next_state_11`, `episode_provenance`。[VERIFIED: `07-SPEC.md:23-39`; exact grouping is agent discretion in `07-CONTEXT.md:47-55`]

`episode_provenance` 应精确包含：`configuration`, `scenario`, `episode_id`, `step_index`, `seed`, `simulation_time_s`, `control_dt_s`, `task_id`, `controller_mode`, `source_commit`, `evidence_level`。`configuration/scenario/episode_id/task/controller/source/evidence` 为非空字符串；commit 为 40 个小写 hex；step/seed 为非 bool 整数；time 有限且 `control_dt_s>0`。[VERIFIED: `07-SPEC.md:39,46-49,112-115`]

`platform_context` 应精确包含：`configuration`, `thruster_count`, `control_channels`, `control_mask`, `allocation_mode`, `declared_control_rank`, `mass_kg`, `inertia_diagonal_kg_m2`, `com_to_cob_offset_m`, `volume_m3`, `drag_multiplier`, `thruster_dynamics_time_constant_s`。identity/topology 来自 `qualification_record()`；数值动力学字段从 reset 后当前 env-index 的 live tensors 读取，因为 mass、inertia、COM/COB、volume、drag 和 time constant 都可能按 episode randomize。[VERIFIED: `easyuuv_nc/embodiments.py:157-189`; `easyuuv_nc/env/easyuuv_env.py:1845-1927`]

两个 environment context 使用相同 envelope shape 但必须独立构造：`available`, `method`, `method_version`, `source_kind`, `source_signals`, `values`, `units`, `frames`, `value_provenance`。oracle 的 `source_kind="simulator_ground_truth"`；estimated 的 `source_kind="deployable_observation"`。Phase 7 默认 estimated 为 `available=false`、空 `source_signals`、空 `values/units/frames/value_provenance`，不得把 oracle 对象浅拷贝后换标签。[VERIFIED: `07-SPEC.md:36-37,67-73`; `07-CONTEXT.md:35`]

oracle `values` 最少包含 `fluid_velocity_world_3`, `water_density_kg_m3`, `dynamic_viscosity_pa_s`, `drag_multiplier`, `thruster_efficiency_n`；velocity frame 为 `world`，其余为 scalar/per-thruster dimensionless 或明确 SI unit。fluid velocity 必须使用 dynamics 当步缓存值，而不是 step 后再次调用函数。[VERIFIED: `07-SPEC.md:36`; `easyuuv_nc/env/easyuuv_env.py:1231-1267,2265-2338`]

### Record validator

validator 必须不修改输入，先检查 exact key set，再做严格类型、shape、finite、range、topology 和 provenance checks；Python `bool` 不得作为整数通过。所有 failure 抛出/返回稳定 reason code，CLI 在任何 warning-like 语义冲突时退出非零。[VERIFIED: D-10 in `07-CONTEXT.md:36`; strict negative criteria in `07-SPEC.md:46-49`]

必须覆盖的 reason-code 族：`schema_version_mismatch`, `field_set_mismatch`, `type_invalid`, `shape_invalid`, `nonfinite_value`, `control_out_of_bounds`, `pwm_out_of_bounds`, `configuration_unknown`, `topology_mismatch`, `padding_nonzero`, `mask_mismatch`, `underactuated_yaw_nonzero`, `context_unavailable_invalid`, `context_provenance_invalid`, `oracle_as_estimate`, `source_commit_invalid`, `episode_invariant_drift`, `step_discontinuity`, `time_discontinuity`, `state_transition_discontinuity`, `manifest_hash_mismatch`, `evidence_level_invalid`。[VERIFIED: `07-SPEC.md:46-49,70-73,78-81`]

shape 固定为 11/5/4/4/8/8/6/11；action、virtual control、PWM 均在 `[-1,1]`，容差 `1e-6`；mask 仅接受整数 0/1，且必须为 `[1]*N+[0]*(8-N)`；padding 位 PWM 必须数值等于 0；`uuv4*` virtual yaw 必须等于 0。[VERIFIED: `07-SPEC.md:23-39,110-116`; `easyuuv_nc/embodiments.py:157-189`]

### Episode and manifest validator

一份 JSONL 只容纳一个 episode。row `i+1.step_index == i.step_index+1`，time 差与 invariant `control_dt_s` 在声明 tolerance 内相等，且 `row[i].next_state_11 == row[i+1].state_11`；Bridge 应把前一 `next_state` 直接作为下一 pre-state，避免二次采样造成伪差异。[VERIFIED: D-11 in `07-CONTEXT.md:37`; acceptance in `07-SPEC.md:46-49`]

manifest 应精确记录：manifest/schema versions、transition file basename、SHA-256、record count、first/last step/time、episode invariants、platform-context digest、runtime provenance、evidence level。server manifest 还必须含 actual Isaac versions、source commit、task/configuration、runner/log status 与 log hashes；本地 manifest 禁止自称 server evidence。[VERIFIED: `07-CONTEXT.md:41-45`; Phase 6 precedent `06-VERIFICATION.md:57-63`]

logger 不支持 append 或跨 episode reuse；逐行先验证再写 `.part`，flush，finalize 时做 episode validation、计算 hash、写临时 manifest，再用 `os.replace` 提升。中断的 `.part` 保留为失败证据，不得被 loader 当成 canonical episode。[VERIFIED: atomic precedent `workflows/qualify_easyuuv_v2.py:350-374`; failure preservation `docs/phase6_easyuuv_v2_qualification_runbook.md:200-211`]

### `KoopmanDatasetV2` safe API

推荐 dataclass 字段为 `X`, `virtual_control_4`, `R`, `Y`, `diagnostics`, `platform_contexts`, `oracle_contexts`, `estimated_contexts`, `episode_provenance`，只读 property `.U` 返回 `virtual_control_4` 且强制 `(n,4)`。`ActuatorDiagnostics` 单独包含 `(n,8)` PWM、mask、wrench、饱和率和能耗代理；不得提供把 diagnostics 位置参数传给 `.U` 的构造器或别名 `action/control/u`。[VERIFIED: `07-SPEC.md:53-65,91`; v1 contrast `koopman/dataset.py:13-49,82-112`]

Phase 7 不让 v1 `KoopmanModel`、lifted EDMD 或 MPC 消费该 dataset；这些类的默认 `control_dim=PWM_DIM` 和 PWM solver 保持不变，Phase 8/9 再引入相应 model/controller version。[VERIFIED: `koopman/model.py:20-39`; `koopman/lifted_edmd.py:21-40`; `koopman/mpc.py:90-113`; `07-SPEC.md:96-104`]

### Explicit v1 adapter

推荐公开入口 `load_v1_compatibility(path) -> V1CompatibilityView`。view 固定包含 `source_schema="v1"`, `eligible_for_v2_cross_configuration_training=False`, `unavailable_fields=(virtual_control_4, thruster_mask_8, applied_wrench_6, platform_context, environment_context_oracle, environment_context_estimated, configuration_identity, episode_provenance)` 和经过现有 v1 loader 验证的原记录；不实现 `to_v2()`、不继承 v2 record、不能传给 v2 dataset loader。[VERIFIED: `koopman_data.py:158-186`; `07-CONTEXT.md:21-23`]

## Runtime Capture Points

| Required fact | Exact capture recommendation | Why this point is reliable |
|---|---|---|
| `raw_action_4` | `_pre_physics_step()` 覆盖/clip `_actions` 前，缓存 `actions[:, :4].detach().clone()` 为 `_last_raw_action_4` | 当前 line 1439 后原始值被覆盖，line 1440 再 clip；更晚读取只能得到执行输入而不是提交输入。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:1424-1442`] |
| `virtual_control_4` | `_pid_control()` 完成 priority/deadband 等处理后，乘 catalog-derived `_control_mask_4`，缓存 `_last_virtual_control_4`，再由同一值进入 sign/TAM | `_last_pid_value` line 2172 是 unmasked PID；uuv4 yaw 目前只在 WLS weight 内被忽略，不能满足 post-mask 语义。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:2101-2174`; `easyuuv_nc/thrust_allocation.py:113-144`] |
| actual N PWM | 继续读取 `_last_motor_values_clipped` | 它在 allocation 后、clip 后按当前 `_num_thrusters` 缓存，正是需要 padding 的命令域。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:2153-2176`] |
| `applied_wrench_6` | line 2329-2330 求和后立即 `cat(force_b, torque_b)` 缓存 `_last_applied_wrench_6` | 已经过 PWM conversion、lag、efficiency/fault/ventilation；尚未混入 buoyancy/drag/boundary/pulse。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:2263-2338,2360-2380`] |
| fluid velocity oracle | line 2336 同一次 dynamics 调用缓存 `_last_fluid_velocity_w` | sine/JONSWAP 依赖 episode time，step 后重算可能不是施力所用的同一时刻。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:1231-1265,2336-2338`] |
| efficiency oracle | force magnitude相乘后缓存当前 N-vector | 该值已经组合 fault、mismatch、ventilation，且实际参与 line 2311 的 thrust。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:2267-2318`] |
| state/reference | Bridge 在 step 前用现有 11D state extraction 和 `[depth,quat]` reference extraction，step 后读 next-state | 维持 v1 state/reference 顺序而不改变 v1 logger。[VERIFIED: `workflows/koopman_logging.py:24-36`] |

新增 telemetry buffers 应在 `__init__` 和 `_reset_idx` 明确归零/标记 unavailable；Bridge 必须拒绝 reset 后尚未 step 的 stale/default telemetry，并通过递增的 runtime step token 证明所有 post-step 字段来自同一 physics step。[VERIFIED: 当前 reset 已清多类 telemetry `easyuuv_nc/env/easyuuv_env.py:1642-1724`; D-11 `07-CONTEXT.md:37`]

## Architecture Patterns

### System Architecture Diagram

```text
caller action_4
    |
    v
Bridge begin-step ---- pre state_11/reference_5/provenance snapshot
    |
    v
env._pre_physics_step -- cache raw_action_4 before clipping
    |
    v
low-level PID/S-surface -- priority + topology mask
    |                         |
    |                         +--> cache virtual_control_4
    v
TAM allocator --> clipped N PWM --> actuator dynamics/efficiency/ventilation
                                      |
                                      +--> cache padded-PWM source
                                      +--> cache thruster-only applied_wrench_6
                                      +--> cache oracle context for same step
    |
    v
Isaac physics --> Bridge end-step --> next_state_11
    |
    v
strict row validator --> episode JSONL.part --> episode validator
    |
    v
SHA-256 manifest + atomic promotion --> DatasetV2(U=4) / diagnostics
                                      \--> explicit V1CompatibilityView (separate path)
```

该流程把 entry point、时序边界、TAM 分支、runtime/service boundary 和最终消费者完整连起来。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:1424-1491,2019-2385`; D-11 `07-CONTEXT.md:37`]

### Recommended Project Structure

```text
koopman/
├── schema_v2.py              # pure record/episode/manifest types + validators
├── dataset_v2.py             # named U=4 dataset and diagnostics
└── v1_compatibility.py       # read-only explicit v1 view
workflows/
├── koopman_bridge_v2.py      # env telemetry extraction and atomic step alignment
├── validate_koopman_v2.py    # deterministic reason-coded CLI
└── collect_koopman_v2_smoke.py
scripts/
├── phase7_prepare_bundle.ps1
├── phase7_server_bootstrap.sh
├── phase7_server_smoke.sh
└── phase7_pullback.ps1
tests/
├── test_koopman_schema_v2.py
├── test_koopman_bridge_v2.py
├── test_koopman_dataset_v2.py
├── test_koopman_v1_compatibility.py
└── test_phase7_server_evidence_contract.py
```

模块命名属于 agent discretion；核心要求是 pure schema 不导入 Isaac/Torch，Bridge 不改变 v1 APIs，dataset/adapter 公共名称显式带 v2/compatibility。[VERIFIED: `07-CONTEXT.md:47-55,90-101`]

### Pattern 1: Runtime truth, not reconstruction

Bridge 只读取 runtime 同步缓存；不以 PWM×TAM 重构 applied wrench，不在 step 后重新求 fluid velocity，不以 desired wrench 代替 actual wrench。[VERIFIED: `07-SPEC.md:34`; `easyuuv_nc/env/easyuuv_env.py:2153-2157,2263-2380`]

### Pattern 2: One episode, one immutable artifact

JSONL 行可流式生成，但只有 episode validator、hash 和 manifest 同时成功后才成为 canonical artifact；失败 `.part` 与 log 被保留且不会被 dataset loader 自动发现。[VERIFIED: Phase 6 fail-closed precedent `docs/phase6_easyuuv_v2_qualification_runbook.md:181-211`]

### Pattern 3: Named semantic types

`TransitionV2`, `EpisodeManifestV1`, `KoopmanDatasetV2`, `ActuatorDiagnostics`, `V1CompatibilityView` 为不同类型；禁止一个宽泛 dict/tuple 同时代表 v1、v2、training 和 diagnostics。[VERIFIED: D-01..D-06 `07-CONTEXT.md:21-30`]

### Anti-Patterns to Avoid

- **把 `_last_pid_value` 直接重命名为 virtual control：** 会让 `uuv4` yaw 语义错误且改写已有 telemetry 合同。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:2149-2174`]
- **从 clipped PWM 重构 actual wrench：** 会丢失 first-order lag、conversion、fault、mismatch、ventilation 的执行后效果。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:2263-2318`]
- **读取 `_thrust/_moment` 作为 applied wrench：** 它们含 buoyancy、drag、boundary 和 runtime pulse，不是 thruster-only。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:1490-1491,2332-2385`]
- **复制八构型/mask 表到 schema：** 会产生 catalog drift；必须调用 `qualification_record()`。[VERIFIED: `tests/test_easyuuv_v2_catalog.py:88-139`]
- **允许 JSON extra fields/duplicate keys/NaN：** 容易隐藏拼写、schema 混用和非标准数值；loader 必须限大小、拒绝 duplicate key 和 JSON constants。[VERIFIED: Phase 6 precedent `workflows/easyuuv_v2_qualification_artifact.py:33,86-107,133-165`]
- **把 v1 record 补 null 后叫 v2：** 缺失事实无法补造，且会污染 Phase 8 training eligibility。[VERIFIED: D-02/D-03 `07-CONTEXT.md:22-23`]
- **本地 fixture 自称 server pass：** JSON 自述不能认证进程来源；需要 source bundle、native/tee/semantic gates、log 与 pullback hash。[VERIFIED: `06-VERIFICATION.md:57-63`; `07-CONTEXT.md:41-45`]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| configuration topology truth | 新的 Phase 7 构型表 | `SUPPORTED_EMBODIMENTS` + `qualification_record()` | Phase 6 已证明 exact-eight、mask、rank，并有 snapshot drift tests。[VERIFIED: `easyuuv_nc/embodiments.py:11-31,157-189`; `tests/test_easyuuv_v2_catalog.py:88-139`] |
| state/reference semantic order | 新 11D/5D 定义 | 现有 extraction helper 或 parity fixture | v1/Phase 7 只迁移 control meaning，不应顺手改 state/reference。[VERIFIED: `workflows/koopman_logging.py:24-36`; `07-SPEC.md:23-30`] |
| applied wrench estimate | PWM/TAM 反算器 | runtime force/torque sum cache | 只有该点包含实际 actuator dynamics 且排除环境力。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:2263-2380`] |
| server transport | GitHub pull 或手工文件拷贝 | 已验证 Git bundle/bootstrap/pullback pattern | 服务器无代理可能难以访问 GitHub，Phase 6 已建立离线且 commit-bound 流程。[VERIFIED: `docs/phase6_easyuuv_v2_qualification_runbook.md:53-76`] |
| hash function | 自定义 checksum | `hashlib.sha256` / `sha256sum` / `Get-FileHash` | 跨 Windows/Linux 已在 Phase 6 得到相同结果。[VERIFIED: `scripts/phase6_server_qualification.sh:160-161`; `scripts/phase6_pullback.ps1:109-117`] |

**Key insight:** 本阶段复杂度不在 JSON serialization，而在控制链时序、数据资格和 provenance；标准库足够，语义 checks 必须由项目 contract 明确实现。[VERIFIED: `07-SPEC.md:43-81`; current runtime seams above]

## Runtime State Inventory

| Category | Items Found | Action Required |
|---|---|---|
| Stored data | canonical v1 JSONL/fixtures 与 `source/results` 继续存在；扫描到 336 个 JSON/JSONL artifact 文件 | 不做数据 migration；v1 只经 explicit adapter 读取，新 v2 写到新的 Phase 7 evidence root。[VERIFIED: repository file inventory 2026-08-11; D-02/D-16 `07-CONTEXT.md:22,45`] |
| Live service config | Phase 6 已验证 `/root/IsaacLab` 与隔离 `/root/EASYkoopman-phase6-v2`；没有 repo 外 UI 配置需要迁移 | Phase 7 使用新的隔离 server path，重新验证固定 Isaac state，不修改历史 path。[VERIFIED: `06-VERIFICATION.md:38-40`; `06-SERVER-EVIDENCE.md:39-49`] |
| OS-registered state | 本阶段不重命名/注册 Windows service、scheduled task、systemd unit | 无迁移任务；server 通过一次性 shell entrypoint 执行。[VERIFIED: Phase 7 scope `07-SPEC.md:85-104`] |
| Secrets/env vars | repo 扫描未发现 Phase 7 所需 secret；现有 W&B vars 与本阶段无关 | 不新增 secret；SSH alias/authorization 继续由 operator 环境提供，不写进 artifact。[VERIFIED: repository grep 2026-08-11; `workflows/play_controller.py:198-201`] |
| Build artifacts / installed packages | 本地 `.venv` 有 editable package；server 使用独立 Isaac Python | implementation 后本地 `pip install -e .`/`pip check`，server bundle clone 后离线 editable install；不复用旧 evidence checkout。[VERIFIED: `requirements-dev.txt`; Phase 6 runbook `docs/phase6_easyuuv_v2_qualification_runbook.md:20-31,78-110`] |

## Common Pitfalls

### Pitfall 1: post-mask control 捕获在错误位置

**What goes wrong:** `uuv4` 的 nonzero yaw 被写进 `virtual_control_4`，但 motor output 因 WLS 看似正常。  
**Why:** 当前 mask 是 allocator weight，不是 `_last_pid_value` 的显式 channel mask。[VERIFIED: `easyuuv_nc/thrust_allocation.py:113-144`; `easyuuv_nc/env/easyuuv_env.py:2149-2174`]  
**Avoid:** 新增 catalog-derived mask，cache 与 TAM 共用同一 masked tensor；测试 nonzero raw yaw、zero virtual yaw、allocation output 与旧 WLS 等价。  
**Warning sign:** `uuv4` record 的 `virtual_control_4[2] != 0` 或 Bridge 对 `_last_pid_value` 直接 rename。

### Pitfall 2: step 时序 off-by-one

**What goes wrong:** state/action 属于 step k，motor/wrench 或 next_state 属于 k±1。  
**Why:** 多个 mutable `_last_*` buffer 在 physics hook 中更新。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:1424-1491,2172-2176,2256-2258`]  
**Avoid:** Bridge 维护 pending token 和 runtime step token，单一 `step_and_record` 入口；连续性 validator 复核 next→next pre-state。  
**Warning sign:** JSONL 时间单调但 `next_state_11 != next row state_11`。

### Pitfall 3: live platform context 被静态 catalog 覆盖

**What goes wrong:** configuration name 正确，但 episode 的 mass/inertia/volume/drag/tau 与 domain randomization 实际值不同。  
**Why:** catalog 是 baseline，reset 可按 env 改写多项 runtime tensor。[VERIFIED: `easyuuv_nc/env/easyuuv_env.py:1845-1927`]  
**Avoid:** topology 从 catalog，连续值从当前 env-index live buffer；manifest 将 platform context digest 设为 episode invariant。

### Pitfall 4: oracle 泄漏进 estimated

**What goes wrong:** 未来 Phase 10 用了部署不可见的 ground truth，结果被误称为 deployable。  
**Avoid:** Phase 7 默认 estimated unavailable；available 时必须 `source_kind=deployable_observation` 且 sources 不得引用 ground-truth runtime symbols；oracle 与 estimate 采用独立对象和 provenance。[VERIFIED: `07-SPEC.md:67-73`; D-09 `07-CONTEXT.md:35`]

### Pitfall 5: PWM 通过 API 别名重新成为 U

**What goes wrong:** `.U`、`action` 或 positional tuple 指向 `(n,8)` padded PWM，CONT-03 表面通过字段命名却实质失败。  
**Avoid:** v2 class constructor 只接受命名 `virtual_control_4`，`.U.shape[1]` 固定 4；PWM 只在 `diagnostics` namespace。[VERIFIED: `07-SPEC.md:59-65`; current v1 contrast `koopman/dataset.py:39-42,95`]

### Pitfall 6: manifest 自证 server origin

**What goes wrong:** 手工 JSON 带上 `server_isaac_smoke` 就通过。  
**Avoid:** 复用 Phase 6 source sidecar、clean checkout、native/tee/semantic gate、server/local hash equality；validator 的 JSON checks 是必要但非充分证据。[VERIFIED: `06-VERIFICATION.md:57-63`; `scripts/phase6_server_qualification.sh:91-161`]

## Code Examples

以下是基于当前源码 seam 的 implementation sketch，不是已存在生产代码。

### Explicit masked virtual control and measured wrench

```python
# Source seam: easyuuv_nc/env/easyuuv_env.py:2149-2174, 2328-2338
virtual_control = PID_value * self._control_mask_4
self._last_virtual_control_4 = virtual_control.detach().clone()

cmd = virtual_control * self._alloc_channel_sign
wrench_cmd = control_channels_to_wrench(cmd)
motor_value = allocate(self._alloc_B, wrench_cmd, mode=self._alloc_mode, weight=self._alloc_weight)

# after conversion, lag, efficiency and per-thruster summation; before hydrodynamics
self._last_applied_wrench_6 = torch.cat(
    [thruster_forces, thruster_torques], dim=-1
).detach().clone()
```

### Named dataset control

```python
# Contract source: 07-SPEC.md:53-65
@dataclass(frozen=True)
class KoopmanDatasetV2:
    X: np.ndarray
    virtual_control_4: np.ndarray
    R: np.ndarray
    Y: np.ndarray
    diagnostics: ActuatorDiagnostics

    @property
    def U(self) -> np.ndarray:
        return self.virtual_control_4
```

### Compatibility is a view, not promotion

```python
# Contract source: 07-CONTEXT.md:21-23
@dataclass(frozen=True)
class V1CompatibilityView:
    source_schema: Literal["v1"] = "v1"
    eligible_for_v2_cross_configuration_training: bool = False
    unavailable_fields: tuple[str, ...] = V2_UNAVAILABLE_FROM_V1
    records: tuple[Mapping[str, object], ...] = ()
```

## State of the Art in This Repository

| Old/Current Approach | Phase 7 Approach | Impact |
|---|---|---|
| v1 row has `action_4d` + fixed `pwm_8d` | additive v2 row separates raw action、masked virtual control、diagnostic PWM、actual wrench | topology meaning becomes comparable without rewriting v1。[VERIFIED: `koopman_data.py:14-24`; `07-SPEC.md:23-39`] |
| v1 dataset `.U=(n,8)` | `KoopmanDatasetV2.U=(n,4)` and PWM under diagnostics | enables Phase 8 identification contract while Phase 9 MPC migration remains deferred。[VERIFIED: `koopman/dataset.py:39-42,95`; `07-SPEC.md:91,96-104`] |
| Phase 6 server rows summarize extrema | Phase 7 server stores contiguous per-step transitions plus episode manifest/hash | proves real Bridge alignment, not only environment qualification。[VERIFIED: `06-SERVER-EVIDENCE.md:56-67`; `07-SPEC.md:115,130`] |
| estimated context absent | typed `available=false` estimated object | prevents future oracle leakage while leaving estimator implementation to Phase 10。[VERIFIED: `07-SPEC.md:67-73,100-102`] |

**Deprecated/outdated for v2-only consumers:** generic `action_4d/pwm_8d` tuple reconstruction is v1 compatibility behavior only；它不得被复制进 v2 loader。[VERIFIED: `koopman_data.py:172-186`; D-01/D-03 `07-CONTEXT.md:21-23`]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| local Python | schema/dataset/tests | ✓ | 3.12.4 | — [VERIFIED: local probe 2026-08-11] |
| local NumPy/Torch/pytest | dataset/TAM/TDD | ✓ | 1.26.4 / 2.8.0+cpu / 8.4.2 | — [VERIFIED: local probe 2026-08-11] |
| local Isaac/Omni | real runtime Bridge | ✗ | modules not found | local mocks只能产出 `local_contract`。[VERIFIED: local import probe 2026-08-11; `07-SPEC.md:113`] |
| target Isaac server | three topology smokes | 已在 Phase 6 可用；Phase 7 需重新 preflight | Isaac 5.0 / Lab 2.2.1 / Python 3.11.13 | 无 server fallback；缺失则 phase 保持 incomplete。[VERIFIED: `06-VERIFICATION.md:46-52`; `07-CONTEXT.md:42-45`] |
| GitHub access on server | source transfer | 不依赖 | — | Git bundle + SCP。[VERIFIED: `docs/phase6_easyuuv_v2_qualification_runbook.md:53-76`] |

**Missing dependencies with no fallback:** Phase 7 completion需要真实 server 重新产生 `base/uuv6/uuv4` artifacts；本地环境不能替代。[VERIFIED: `07-SPEC.md:115,130-131`]

**Missing dependencies with fallback:** server GitHub connectivity 不需要，已有 offline bundle 流程。[VERIFIED: Phase 6 runbook above]

## Security Domain

### Applicable ASVS Categories

本阶段不是网络应用；ASVS 用于检查适用边界，而不是宣称完整 ASVS compliance。[ASSUMED]

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | no | 无用户身份/网络入口。[VERIFIED: Phase 7 scope `07-SPEC.md:85-104`] |
| V3 Session Management | no | 无 session。[VERIFIED: Phase 7 scope `07-SPEC.md:85-104`] |
| V4 Access Control | limited | evidence promotion 由 explicit local/server level、isolated path 和 commit sidecar 控制，而非用户 ACL。[VERIFIED: `07-CONTEXT.md:41-45`] |
| V5 Input Validation | yes | exact keys/types/shapes、duplicate-key/NaN/Inf/oversize/path checks、stable reason code、nonzero CLI exit。[VERIFIED: `07-SPEC.md:46-49`] |
| V6 Cryptography | limited | SHA-256 只用于完整性与 sidecar equality，不宣称来源认证；不手写 crypto。[VERIFIED: `06-VERIFICATION.md:57-63`] |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| malicious/malformed JSON 造成 memory/semantic bypass | Tampering/DoS | max bytes、duplicate-key rejection、`parse_constant` rejection、exact field set。[VERIFIED: Phase 6 precedent `workflows/easyuuv_v2_qualification_artifact.py:33,86-107`] |
| output path escape / evidence overwrite | Tampering | resolve-and-confine paths、canonical dir must not exist、temp+atomic replace。[VERIFIED: `workflows/qualify_easyuuv_v2.py:91-127,350-374`; `scripts/phase6_pullback.ps1:82-179`] |
| local/mock relabelled server | Spoofing | clean source bundle、runtime versions、process/log/semantic statuses、hash pullback。[VERIFIED: `06-VERIFICATION.md:57-63`] |
| source commit does not match executed tree | Repudiation/Tampering | clean worktree、branch tip=bundle ref=sidecar=server HEAD；record same commit in manifest。[VERIFIED: `scripts/phase6_prepare_bundle.ps1:25-63`; `scripts/phase6_server_bootstrap.sh:32-41`] |
| oracle leakage labelled estimate | Information-flow integrity | disjoint source_kind/provenance namespaces，Phase 7 estimated defaults unavailable。[VERIFIED: D-09 `07-CONTEXT.md:35`] |
| silent PWM-as-U alias | Tampering | type-level namespace separation and `(n,4)` invariant tests。[VERIFIED: CONT-03 `07-SPEC.md:59-65`] |

## Recommended Plan Decomposition

### Wave 1 — `07-01`: Pure schema v2, episode manifest, logger/loader and validator (TDD)

先写 `tests/test_koopman_schema_v2.py` 与 CLI mutation tests，再实现 pure `koopman/schema_v2.py` 和 `workflows/validate_koopman_v2.py`。覆盖 exact fields、reason codes、finite/bounds、catalog topology、contexts、episode invariants、JSON size/duplicate keys、atomic logger/manifest/hash。此计划覆盖 CONT-01、CONT-04 的结构部分，并建立后续唯一数据入口。[VERIFIED: D-10/D-11 `07-CONTEXT.md:36-37`; `07-SPEC.md:43-49,67-73`]

### Wave 2A — `07-02`: Runtime telemetry and atomic Koopman Bridge (TDD; depends on 07-01)

先写 pure TAM/mask equivalence、mock env step-token、semantic swap negative tests；再为 env 添加 `_last_raw_action_4`, `_last_virtual_control_4`, `_last_applied_wrench_6`, `_last_fluid_velocity_w` 和 reset validity token，最后实现 Bridge 的 begin/step/end atomic record builder 与 live platform/oracle extraction。exact-eight 本地 tests 验证 mask/PWM dimension/rank，`uuv4` 非零 raw yaw→零 virtual yaw。覆盖 CONT-01、CONT-02、CONT-04。[VERIFIED: runtime seams and `07-SPEC.md:51-57,85-90`]

### Wave 2B — `07-03`: DatasetV2, diagnostics and explicit v1 compatibility (TDD; depends on 07-01, may run parallel with 07-02)

先写 `(n,4)` `.U`、PWM alias rejection、diagnostics shape/mask、v1 fixture adapter、strict-v2 rejection 和 v1 regression tests；再实现 `dataset_v2.py` 与 `v1_compatibility.py`。明确不修改 `KoopmanDataset`、model、MPC。覆盖 CONT-02、CONT-03、CONT-05。[VERIFIED: `koopman/dataset.py:13-49,82-112`; D-01..D-06 `07-CONTEXT.md:21-30`]

### Wave 3 — `07-04`: Fail-closed base/uuv6/uuv4 server smoke and phase evidence (depends on 07-02/03)

新增 Phase 7 runner、artifact merger/validator wrapper、bundle/bootstrap/server/pullback scripts 和 runbook。使用三个独立 Isaac process 最易保留 configuration-specific failure；每个 create/reset 后采至少 8 条 contiguous v2 row，分别验证，再在 aggregate evidence 中绑定 source/runtime/log/hash。先跑全量 local regression；checkpoint 后才连接 server。回传后 fresh validation、SUMMARY、VERIFICATION 对 CONT-01..05 逐项 PASS/FAIL。任何一拓扑失败、缺 log/hash、source drift 或 local artifact 冒充都阻断完成。[VERIFIED: D-12..D-16 `07-CONTEXT.md:41-45`; `07-SPEC.md:115,130-131`]

### Dependency graph

```text
07-01 schema/validator
   ├──> 07-02 runtime telemetry + Bridge ──┐
   └──> 07-03 dataset + v1 adapter ───────┤
                                           v
                          07-04 server evidence + verification
```

该拆分把 pure contract、runtime mutation、consumer compatibility 和 external checkpoint 隔离成可审计 commits；不会提前进入 Phase 8 training 或 Phase 9 MPC migration。[VERIFIED: `07-SPEC.md:96-104`; D-16 `07-CONTEXT.md:45`]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | ASVS 分类术语可用于本地 artifact threat review，但不构成 compliance 声明 | Security Domain | LOW；不影响实现，只影响审查措辞。 |

除 A1 外，implementation recommendation 均由锁定文档、当前源码或 Phase 6 artifacts 支持；没有需要用户在计划前补充的产品决定。[VERIFIED: sources throughout]

## Open Questions (RESOLVED)

1. **`easyuuv_nc/env/easyuuv_env_cfg.py` canonical ref 不存在**  
   - What we know: `EasyUUVEnvCfg` 实际定义在 `easyuuv_nc/env/easyuuv_env.py:95`。[VERIFIED: repository lookup 2026-08-11]  
   - What's unclear: CONTEXT 的该文件引用是预期未来拆分还是陈旧路径。  
   - **Resolution adopted:** planner/implementation 以当前真实 `easyuuv_nc/env/easyuuv_env.py` 为准，不为 Phase 7 顺手拆 cfg 文件；`07-CONTEXT.md` 的 canonical ref 已修正。

2. **estimated available=true 的未来字段 allowlist**  
   - What we know: Phase 7 不实现 estimator，默认 `available=false` 足够验收。[VERIFIED: `07-SPEC.md:67-73,100-102`]  
   - What's unclear: Phase 10 最终估计器 method/version/source signals。  
   - **Resolution adopted:** schema 保留 typed envelope，不在 Phase 7 发明 estimator method；Phase 7 默认写 `available=false`，validator 对 unavailable 路径严格，对未来 available 路径只验证 provenance 结构并禁止 simulator-ground-truth source。

## Sources

### Primary (HIGH confidence)

- `.planning/phases/07-*/07-SPEC.md` — authoritative field semantics、scope、acceptance。  
- `.planning/phases/07-*/07-CONTEXT.md` — D-01..D-16 locked decisions。  
- `koopman_data.py`, `koopman/dataset.py`, `koopman/model.py`, `koopman/lifted_edmd.py`, `koopman/mpc.py`, `koopman/mpc_controller.py` — current v1 PWM8 contract。  
- `easyuuv_nc/embodiments.py`, `easyuuv_nc/thrust_allocation.py`, `easyuuv_nc/env/easyuuv_env.py` — catalog、TAM、runtime telemetry/physics truth。  
- `06-VERIFICATION.md`, `06-SERVER-EVIDENCE.md`, Phase 6 runbook/scripts — verified server/evidence boundary。

### Secondary (MEDIUM confidence)

- None；本研究无需外部库/API 决策，未使用 web secondary sources。

### Tertiary (LOW confidence)

- ASVS applicability mapping only，已在 Assumptions Log 标注。

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — no new dependency; versions由 lock files、本地 probe 和已验证 server artifact 支持。  
- Architecture: HIGH — capture points由当前控制/physics call graph 直接确定。  
- Pitfalls: HIGH — 每项均对应当前源码的可观察 semantic gap 或 Phase 6 已修复的 evidence failure class。  
- Server availability: MEDIUM for future execution — Phase 6 已验证，但 Phase 7 运行前必须重新 preflight，不能沿用历史成功。

**Research date:** 2026-08-11  
**Valid until:** 当前 Phase 7 实现开始前；若 `easyuuv_nc/env/easyuuv_env.py` 的 control/dynamics hooks 发生变化，应立即重做 capture-point audit。

# Roadmap: EASYkoopman

## Milestones

- [x] **v1.0 Koopman-UUV Single-Configuration Control** — Phase 1 through Phase 5.4, closed 2026-08-09. Canonical history: [v1.0 roadmap](milestones/v1.0-ROADMAP.md), [summary](reports/MILESTONE_SUMMARY-v1.0.md), [audit](milestones/v1.0-MILESTONE-AUDIT.md).
- [ ] **v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control** — Phase 6 through Phase 12, active.

v1.0 的阶段名称、结论和证据已冻结，不在本活动 roadmap 中重新解释。`.planning/phases/` 中保留的 v1.0 目录是历史工作材料；v2.0 只以 Phase 6–12 为活动范围。

## Milestone Goal

验证同一套 configuration-aware Koopman 控制架构能否跨八种 EasyUUV 2.0 构型迁移，在环境变化下安全更新，并通过受限的低频 Agent Supervisor 获得可审计收益。

## Phase Overview

| Phase | Name | Requirements | Depends on | Status |
|---|---|---|---|---|
| 6 | EasyUUV 2.0 Intake and Multi-Configuration Qualification | QUAL-01..08 | v1.0 frozen baseline | Complete — 4/4 plans verified |
| 7 | Cross-Configuration Koopman Data and Control Contract | CONT-01..05 | Phase 6 | Complete — 4/4 plans verified |
| 8 | Multi-Configuration Koopman Identification and OOD Gate | KID-01..05 | Phase 7 | Ready for planning |
| 9 | Configuration-Aware Koopman-MPC Integration | MPC2-01..04 | Phase 8 | Pending |
| 10 | Environment Awareness and Online Koopman Update | ADAPT-01..05 | Phase 9 | Pending |
| 11 | Low-Frequency Agent Supervisor | AGENT-01..04 | Phase 10 | Pending |
| 12 | Final Matched Evaluation and Research Evidence | EVAL-01..05 | Phase 11 | Pending |

## Active Phases

### Phase 6: EasyUUV 2.0 Intake and Multi-Configuration Qualification

**Goal:** 在不改写 v1.0 证据的前提下，建立新版 `easyuuv_nc` 的唯一安装/运行合同，并证明八种支持构型的身份、推进器拓扑、可控自由度和基础运行行为可被可靠枚举与验证。

**Depends on:** Frozen v1.0 baseline and `docs/Agentic_AUV_v2_milestone_design.md`

**Requirements**: QUAL-01, QUAL-02, QUAL-03, QUAL-04, QUAL-05, QUAL-06, QUAL-07, QUAL-08

**Success Criteria**:
1. Git 历史能区分收到的 `easyuuv_v2-main/` 快照与所有后续集成修改，且 v1.0 tag/归档未改变。
2. 一个机器可读 catalog 精确列出八种 CLI 构型、预期推进器数量、TAM rank 和可控自由度，`uuv4*` yaw 欠驱动被显式记录。
3. 服务器按照唯一 `easyuuv_nc` 安装与资产路径合同完成 `base` 最小 Isaac rollout 和其余七种分级 smoke。
4. 所有资格测试拒绝非有限输出或越界 PWM/virtual control，并保留原因可审计的结果文件。
5. 现有 Isaac-free v1 回归继续通过，Phase 6 同时交付 runbook、SUMMARY 和 VERIFICATION。

**Plans:** 4 plans

Plans:

**Wave 1**

- [x] 06-01-PLAN.md — verified the isolated snapshot and established canonical `easyuuv_nc` packaging, asset and v1-isolation contracts (`f2e660e`, `8b8c7e0`, `d916a12`).

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 06-02-PLAN.md — established the canonical eight-configuration catalog, pure TAM report, control masks/ranks and snapshot-backed zero-drift proof (`9237e3c`, `fcd804a`, `0dc2dc1`, `06dcd5e`).
- [x] 06-03-PLAN.md — established the strict versioned qualification artifact schema, validator and deterministic Isaac-free CLI, then closed provenance/type/range bypasses found by independent audit (`2c3cf47`, `985f630`, `0779cda`, `b85fbbc`, `ffa2e26`).

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 06-04-PLAN.md — connected the catalog/validator to a fail-closed Isaac runner and offline server evidence chain; real eight-configuration smoke, strict pullback validation and artifact hash all passed (`e24f76a`, evidence `7670f66`).

**Cross-cutting constraints:**

- The received simulator snapshot, v1.0 `source/results` evidence and v2.0 planning/integration remain independently auditable commit and push boundaries.
- Local tests may establish only `local_contract` evidence; only actual Isaac server runs may establish `server_isaac_smoke` evidence.
- Phase 6 does not change the v1 Koopman `state=11`, `reference=5`, `control=PWM_8` semantics and does not claim Phase 7+ transfer behavior.
- Missing, partial, non-finite, out-of-bounds or topology-inconsistent server evidence keeps Phase 6 open; no mock artifact may satisfy the checkpoint.

### Phase 7: Cross-Configuration Koopman Data and Control Contract

**Goal:** 建立 schema v2 与 Koopman Bridge，使 4、6、8 推进器平台共享固定 4D virtual control，同时保留拓扑、平台与环境上下文以及 v1 兼容读取边界。

**Depends on:** Phase 6

**Requirements**: CONT-01, CONT-02, CONT-03, CONT-04, CONT-05

**Success Criteria**:
1. schema v2 对 REQUIREMENTS 中列出的状态、控制、PWM、mask、wrench、context 和 provenance 字段进行版本化验证。
2. Koopman/MPC 的默认控制输入固定为 `[roll, pitch, yaw, depth]`，各构型仅在 TAM 分配后产生实际推进器命令。
3. Padded PWM 只能用于诊断、饱和与能耗分析，无法被静默当作跨构型模型输入。
4. oracle 与 estimated environment context 在数据与 API 中保持分离，v1 日志仅通过显式 compatibility adapter 读取。

**Plans:** 4/4 plans verified

Plans:

**Wave 1**

- [x] 07-01-PLAN.md — establish the pure schema v2 transition/episode/manifest contract, strict validator CLI and local mutation gates.

**Wave 2** *(blocked on Wave 1 completion; plans may run in parallel)*

- [x] 07-02-PLAN.md — add physically correct EasyUUV runtime telemetry and the atomic schema-v2 Koopman Bridge, including explicit `uuv4*` yaw masking before TAM.
- [x] 07-03-PLAN.md — add immutable `U=virtual_control_4` DatasetV2/diagnostics and an explicit non-promoting v1 compatibility view.

**Wave 3** *(blocked on both Wave 2 plans)*

- [x] 07-04-PLAN.md — passed the complete local preflight and produced independently pulled, exact-inventory-verified real-server schema/Bridge evidence for `base`, `uuv6` and `uuv4` (`a36689a`, evidence `1c0a6ca`).

**Cross-cutting constraints:**

- Existing v1 logger/dataset/model/MPC defaults remain `U=PWM_8`; Phase 7 adds versioned v2 interfaces and does not perform the Phase 8/9 model/controller migration.
- `raw_action_4`, post-mask/pre-TAM `virtual_control_4`, padded diagnostic PWM and post-actuator thruster-only `applied_wrench_6` remain distinct fields with distinct capture points.
- Local fixtures and mocked Bridge tests are `local_contract` only. Phase completion requires actual Isaac Sim 5.0 / Isaac Lab 2.2.1 evidence for one 8-, 6- and 4-thruster representative.
- Planning/implementation and pulled-back `source/results/koopman_phase7` evidence remain separate commits; no planning test may pre-create a canonical success artifact.
- Completing Phase 7 proves the data/control contract is connected to the simulator; it does not prove cross-configuration Koopman prediction or control effectiveness.

### Phase 8: Multi-Configuration Koopman Identification and OOD Gate

**Goal:** 在按 configuration/episode 隔离的数据上比较单构型、共享与条件化 Koopman，并用 held-out configuration 预测门决定是否存在可用的跨构型模型。

**Depends on:** Phase 7

**Requirements**: KID-01, KID-02, KID-03, KID-04, KID-05

**Success Criteria**:
1. 所有 train/validation/test manifest 按 configuration 和 episode 分组，验证器拒绝 row-level leakage。
2. persistence、linear、per-configuration、pooled、conditional 和 expert upper-bound 模型使用同一 split manifest 比较。
3. 报告包含 one-step、multi-step、rollout 与 SO(3) geodesic 姿态指标，并给出逐构型和聚合结果。
4. 选择 manifest 记录数据/模型 provenance，并在无人通过全部门时输出 `no_selection`。

**Plans:** 0 plans

Plans:

- [ ] TBD — plan after schema v2 is verified.

### Phase 9: Configuration-Aware Koopman-MPC Integration

**Goal:** 让 Koopman-MPC 在统一 4D virtual-control 空间优化，并通过当前构型 TAM、可控自由度 mask 与确定性 fallback 实现可比较的多构型闭环控制。

**Depends on:** Phase 8

**Requirements**: MPC2-01, MPC2-02, MPC2-03, MPC2-04

**Success Criteria**:
1. MPC 输出有界 4D virtual control，且每个构型使用自身 TAM 产生正确数量的推进器命令。
2. `uuv4*` yaw 目标在优化和评分入口被 mask，不能作为可实现跟踪目标进入结果。
3. timeout、infeasible、non-finite 与 saturation 均触发 reason-coded bounded fallback。
4. 每个构型在相同 scenario、seed、horizon 和 disturbance 下与 Legacy/S-Surface 完成 matched comparison。

**Plans:** 0 plans

Plans:

- [ ] TBD — plan after a Koopman model passes the Phase 8 gate.

### Phase 10: Environment Awareness and Online Koopman Update

**Goal:** 分离环境估计误差与控制误差，先建立 oracle-context 上界，再验证带限幅、冻结先验和回滚的 RLS/KF 在线 Koopman 更新能否缩短环境变化后的恢复过程。

**Depends on:** Phase 9

**Requirements**: ADAPT-01, ADAPT-02, ADAPT-03, ADAPT-04, ADAPT-05

**Success Criteria**:
1. oracle-context 结果先于 estimated-context 声明生成，并作为可达到上界单独报告。
2. deployable estimator 只使用运行时可用信号，并将 context estimation error 与 control error 分开记录。
3. RLS/KF 更新具备参数 bounds、non-finite rejection、frozen prior、rollback 和 disable path 的自动测试。
4. matched evaluation 报告 shift 前退化、恢复曲线、rollback 事件和 frozen-model baseline。
5. 只有聚合收益门与所有逐构型安全/稳定 sentinel 同时通过时才允许 promotion。

**Plans:** 0 plans

Plans:

- [ ] TBD — plan after multi-configuration closed-loop control is qualified.

### Phase 11: Low-Frequency Agent Supervisor

**Goal:** 构建只做 allow-listed、低频、可回退决策的 Agent Supervisor，并证明其无法绕过确定性低层控制器或直接发送 PWM。

**Depends on:** Phase 10

**Requirements**: AGENT-01, AGENT-02, AGENT-03, AGENT-04

**Success Criteria**:
1. Agent API 只暴露已准入模型选择、online-update enablement、有界 reference/MPC 配置和 safety fallback。
2. 合同测试证明 Agent 不产生 PWM/PPO action，也不参与实时 `env.step()` 循环。
3. 每个决策记录输入、选项、rationale/provenance、gate 和 fallback；无效决定 fail closed。
4. no-supervisor、rule-supervisor、agent-supervisor 在相同 manifest 下完成三方消融。

**Plans:** 0 plans

Plans:

- [ ] TBD — plan after environment adaptation gates are stable.

### Phase 12: Final Matched Evaluation and Research Evidence

**Goal:** 在统一的 nominal、held-out configuration、environment shift 与 combined shift 矩阵中完成最终匹配评测，并形成可复现、可拒绝且不过度外推的研究结论。

**Depends on:** Phase 11

**Requirements**: EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05

**Success Criteria**:
1. 最终 manifest 固定 scenario、configuration、shift、seed 与 episode count，覆盖四类目标条件。
2. 每项结果都有 evidence level 和 artifact validator 结果，不混淆本地合同、server smoke、stable run、matched evaluation 与 promotion。
3. 报告同时给出逐构型/聚合指标、安全稳定 sentinel、fallback rate 和重复 seed/不确定性摘要。
4. promotion 必须通过所有 mandatory gates；否则明确输出 `no_selection` 并保留负结果。
5. 里程碑以服务器命令、artifact provenance、限制与研究结论边界关闭，不声称 Sim2Real 或硬件有效性。

**Plans:** 0 plans

Plans:

- [ ] TBD — plan after Agent Supervisor implementation and ablation contract are verified.

## Requirement Coverage

| Phase | Requirement IDs | Count |
|---|---|---:|
| 6 | QUAL-01..08 | 8 |
| 7 | CONT-01..05 | 5 |
| 8 | KID-01..05 | 5 |
| 9 | MPC2-01..04 | 4 |
| 10 | ADAPT-01..05 | 5 |
| 11 | AGENT-01..04 | 4 |
| 12 | EVAL-01..05 | 5 |
| **Total** | **All v2.0 requirements** | **36** |

Coverage: 36 mapped, 0 unmapped, 0 multiply mapped.

---

*Roadmap created: 2026-08-09 for milestone v2.0*

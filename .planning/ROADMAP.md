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
| 8 | Multi-Configuration Koopman Identification and OOD Gate | KID-01..05 | Phase 7 | Complete — 5/5 plans verified; valid `NO_SELECTION` |
| 8.1 | Local Simulator and Koopman Identification Repair | KIDR-01..10 | Phase 8 | Complete — 4/4 local plans verified; D-23 approved |
| 8.2 | Phase 8.1 Fresh Server Evaluation and Closeout | KIDO-01..05 | Phase 8.1 D-23 approval | Complete — 4/4 plans verified; terminal `NO_SELECTION` with `VERIFIED` closeout |
| 9 | Configuration-Aware Koopman-MPC Integration | MPC2-01..04 | Phase 8.2 terminal selection | Blocked — no Phase 8.2 handoff model; awaiting user decision on negative-result carry-forward |
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

**Goal:** 在按 configuration/episode 隔离的数据上，以同一 controlled-EDMD v2 backend 比较 persistence/simple-linear baselines、per-configuration/pooled/conditional regimes 和 non-promoting expert，并用 exact-eight held-out-configuration 预测门决定是否存在可进入 Phase 9 的 pooled/conditional 模型。

**Depends on:** Phase 7

**Requirements**: KID-01, KID-02, KID-03, KID-04, KID-05

**Success Criteria**:
1. Pilot 只判断 exact-eight 采集链/schema/runtime/safety/coverage 是否健康，不参与模型、feature、horizon、threshold 或主实验预算选择。
2. 所有 fit/validation/test manifest 按 configuration 和完整 episode 分组；exact-eight LOCO 每折只用七个 source configurations 做模型相关决策，验证器拒绝 row-level 或 held-out trajectory leakage。
3. persistence、simple-linear、per-configuration、pooled、conditional 和 expert 角色使用同一 split/analysis policy；只有 pooled/conditional 允许进入 selector。
4. 报告包含 one-step、5/20/60-step、full rollout 与 SO(3) geodesic 姿态指标，并给出逐构型、equal-config macro 和 worst-configuration 结果。
5. 选择 envelope 绑定数据/模型/protocol/runtime provenance；通过时 final refit 只用八构型 fit+validation 重新选择设置并拟合，失败时输出无 model path 的 `no_selection`。

**Plans:** 5 plans

Plans:

**Wave 1**

- [x] 08-01-PLAN.md — establish the external Phase 8 evidence envelope, pre-collection protocol schemas and exact-eight collection-health-only pilot through a locally gated server chain.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 08-02-PLAN.md — implement exact main inventory, configuration/episode role views, LOCO split manifests, opened-file leakage audits and fold-local physical platform descriptors.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 08-03-PLAN.md — implement one controlled-EDMD v2 backend, true baselines, six evaluation roles, episode-safe rollout and quaternion-correct/configuration-balanced metrics through TDD.

**Wave 4** *(blocked on Wave 3 completion; includes D-23 user decision and server checkpoint)*

- [x] 08-04-PLAN.md — froze the approved D-23 hashes and independently pulled back the real exact-eight 96-episode/49,152-transition server dataset with exact inventory, LOCO split and external evidence gates (`a7e8198`, evidence `98dbd76`).

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 08-05-PLAN.md — completed all eight frozen LOCO folds, atomically published a pathless `no_selection`, and passed independent goal-backward verification (`PASS_VALID_FROZEN_NO_SELECTION`).

**Cross-cutting constraints:**

- Pilot is collection-health-only; model-affecting choices are pre-registered or selected inside each outer fold from seven source configurations only.
- Phase 8 transition rows keep the frozen Phase 7 `evidence_level`; new pilot/dataset/evaluation/selection names live only in a validated external `qualification_level` envelope.
- Main selection inputs are `state_11 + virtual_control_4`, with optional fold-fitted physical platform context. Reference, PWM, measured wrench and environment oracle remain diagnostic/non-promoting.
- Planning, local implementation, pilot evidence, main server dataset, offline evaluation, terminal selection/no-selection and closeout remain separate commits and immutable roots.
- Phase 8 proves or rejects held-out-configuration prediction transfer only; MPC/closed-loop, environment adaptation, Agentic and hardware claims remain Phase 9+.
- Phase 8 closed with a valid negative result: neither eligible Koopman family passed the frozen gate, so Phase 9 has no model handoff and must not begin execution from this artifact.

### Phase 08.1: Local Simulator and Koopman Identification Repair (INSERTED)

**Goal:** 在完全保留旧 Phase 8 frozen `NO_SELECTION` 的前提下，本地修复推进器一阶动态时钟，建立 additive schema/model/evaluation v2.1 与 pending-D-23 协议提案，使新实验可以在用户另行批准后重新采集，而不使用旧 held-out test 调参。

**Depends on:** Phase 8 frozen negative result and approved Phase 8.1 design

**Requirements**: KIDR-01, KIDR-02, KIDR-03, KIDR-04, KIDR-05, KIDR-06, KIDR-07, KIDR-08, KIDR-09, KIDR-10

**Success Criteria**:
1. reset 后第一个 physics substep 获得完整 `physics_dt`，D-substep response 与 control-interval closed form 等价。
2. schema v2.1 以 19D `[state_11, actuator_memory_4, virtual_control_4]` primary view 接通 Bridge/dataset/rollout，并保持旧 v2 bytes/API 不变。
3. SO(3) Log/Exp、22/56D observables、PCA2 structured conditional 66/100D 和 rank/condition admission 均由 targeted tests 精确验证。
4. source ledger、held-out diagnostic、expert、pre-test freeze 和 positive final-refit/publication 状态机在 synthetic local tests 中 fail closed。
5. 新 role/analysis protocols 的 bytes 保持 `pending_d23/proposal_only`，独立 canonical approval record 精确绑定用户批准的 hashes、experiment ID 与 `approved` decision；server dataset 与正式 LOCO 仍不存在。

**Plans:** 4 plans

Plans:

**Wave 1**

- [x] 08.1-01-PLAN.md — repaired the first-substep actuator clock and established strict causal actuator-memory/schema/dataset/Bridge v2.1 contracts.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 08.1-02-PLAN.md — implemented deterministic SO(3), exact observables, source-only PCA2 structured conditional and causal rollout.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 08.1-03-PLAN.md — sealed complete source ledgers, isolated held-out diagnostics/experts and implemented test-free family-only final refit/publication.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 08.1-04-PLAN.md — froze pending-D-23 proposals, guarded formal entrypoints, passed relevant local regression and stopped at hash-review readiness.

**Post-fix D-23:** User approval binds role hash `083d5eae...9417`, analysis hash `7a790b43...e18c` and experiment `phase8.1-main-identification-v1`. The canonical approval record validates this binding only (`identity_assurance=none`). All server/formal work is isolated in Phase 8.2.

### Phase 08.2: Phase 8.1 Fresh Server Evaluation and Closeout

**Goal:** 从 clean committed HEAD 构建并验证离线 bundle；在用户启动现有服务器后重新采集 fresh v2.1 exact-eight dataset，经 staged pullback/inventory/split validation 后执行冻结的正式 8-fold LOCO、outer `SELECTION/NO_SELECTION` 和独立 closeout。

**Depends on:** Phase 8.1 local repair and exact D-23 protocol-hash approval

**Requirements**: KIDO-01, KIDO-02, KIDO-03, KIDO-04, KIDO-05

**Success Criteria**:
1. canonical approval、targeted/relevant tests、clean HEAD、versioned operational scripts 与 verified offline bundle 全部在请求启动服务器前完成。
2. fresh server result root 精确完成 8×12 v2.1 episodes，任一 native/tee/schema/inventory gate 失败都不能产生 canonical success evidence。
3. pullback 只在 source/protocol/approval/file/schema/inventory/split 全部验证后从随机 staging 原子提升。
4. formal evaluator 对每折严格执行 source-only selection、pre-test freeze 和 guarded held-out test，八折后输出冻结的 `SELECTION` 或 `NO_SELECTION`。
5. independent closeout 只支持 fixed exact-eight catalog 的 fresh-episode prediction-transfer 结论，并在进入 Phase 9 前明确是否存在有效模型 handoff。

**Plans:** 4 plans

Plans:

**Wave 1**

- [x] 08.2-01-PLAN.md — implemented the complete operational shell, passed canonical D-23 plus 32 targeted/200 relevant tests, and verified an offline-cloneable bundle; stopped before SSH.

**Wave 2** *(blocked on Wave 1 and explicit server-start checkpoint)*

- [x] 08.2-02-PLAN.md — collected the fresh v2.1 server dataset (96 episodes, zero `.part`, 49,152 transitions) in isolated `v2` roots, validated the staged pullback and atomically promoted `dataset/` + `collection_status/`; the failed `v1` bootstrap attempt is preserved.

**Wave 3** *(blocked on Wave 2)*

- [x] 08.2-03-PLAN.md — ran the frozen formal eight-fold LOCO as eight independent processes with per-fold pre-test freeze and atomic publication, assembled canonical `evaluation/` and published the terminal `NO_SELECTION` envelope.

**Wave 4** *(blocked on Wave 3)*

- [x] 08.2-04-PLAN.md — independently verified the exact evidence/claim boundary with verdict `VERIFIED` and closed Phase 8.2.

**Cross-cutting constraints:**

- Experiment ID and D-23 protocol bytes remain Phase 8.1-owned and immutable; Phase 8.2 only operates them.
- No server/formal artifact is appended to Phase 8.1 or to the frozen pre-fix Phase 8 experiment.
- No Phase 9, Koopman-MPC, PPO, Agent, environment transfer or Sim2Real work begins in Phase 8.2.

### Phase 9: Configuration-Aware Koopman-MPC Integration

**Goal:** 让 Koopman-MPC 在统一 4D virtual-control 空间优化，并通过当前构型 TAM、可控自由度 mask 与确定性 fallback 实现可比较的多构型闭环控制。

**Depends on:** Phase 8.2 terminal `koopman_selection`; planning may inspect a valid `NO_SELECTION`, execution remains blocked without a model handoff

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
| 8.1 | KIDR-01..10 | 10 |
| 8.2 | KIDO-01..05 | 5 |
| 9 | MPC2-01..04 | 4 |
| 10 | ADAPT-01..05 | 5 |
| 11 | AGENT-01..04 | 4 |
| 12 | EVAL-01..05 | 5 |
| **Total** | **All v2.0 requirements** | **46** |

Coverage: 46 mapped, 0 unmapped, 0 multiply mapped.

---

*Roadmap created: 2026-08-09 for milestone v2.0*

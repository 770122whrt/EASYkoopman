# Roadmap: EASYkoopman

**2026-09-29最终确认：** 下一步仅做“加扰动”和“物理与Koopman结合”。物理基线事前冻结，不学习新增扰动数据、不重新校准；Koopman可离线学习，测试参数冻结，完整提升状态自行传播。旧的同数据重校准要求与覆盖优先研究顺序不再作为当前条件。执行细节以 `.planning/STATE.md` 及其交接为准。

**2026-09-29当前讨论入口：** 请先读[STATE](STATE.md)中的完整提升传播交接。Phase9/09-04保持开放；不新增或关闭阶段，不按下方旧日期的下一动作重启实验。

**当前入口（结果截至2026-09-27，2026-09-28补充中文解释）：** 已完成五种模型的预测比较与单构型诊断。数据校准的物理模型整体最好；限制自由度的学习残差接近物理预测；两种“非线性特征＋矩阵传播”模型尚未合格。同一基础构型换成未参与训练的扫频输入也失败，因此不能只归因于跨构型。六次连续控制优化中一次达到可接受精度、五次超时，新两秒闭环尚未运行。模型中文名称、正则参数λ、论文关系及完整数字见[统一报告与八构型表](../docs/phase9_model_comparison_v84_report.md)。本轮先解释与修正文档，没有新实验；下方旧日期内容为历史证据。

**已完成v82报告（2026-09-26，历史Goal结果）：** 已完成10条2秒真实闭环、18个非等价学习模型及八折留构型预测。uuv4两学习候选相对同MPC辨识物理的综合误差降低11.7%/9.8%；base高3.0%/17.9%，仅部分完整目标改善。已观察局部控制收益，未证明普遍模型优势或未见构型闭环泛化。10条原Linux验收通过，9条本地完整复核，uuv4学习0.001在Windows因果预演未复现、另经原运行时严格重验通过；失败保留。下一步先修求解质量和预演平台分支敏感性，再冻结新任务验证。服务器无本任务遗留进程，可关闭。 [最终报告](../docs/phase9_koopman_mpc_v82_report.md)；[执行范围](../docs/phase9_goal_v80_plan.md)。下方旧日期的运行状态仅为历史。

**2026-09-26架构补充审核：** 当前是物理条件的投影EDMD速度残差＋NMPC，不是完整线性提升＋QP。53维有物理来源但存在精确冗余和自由交叉项外推风险；复算首起点计划再次确认求解质量混杂。下一步在共同求解回归之外，增加精简残差与经典线性提升的离线小对照，原执行链和物理基线保留；新模型通过预测准入后再比较控制架构。不预先认定任一路线胜出。[检查与建议](../docs/phase9_architecture_v83_review.md)。本轮无新拟合、求解或服务器运行。

**当前方法审核（2026-09-26）：** 2026-09-26已完成两篇论文与控制/模型/验证三端交叉审核：主线合理；修复短计划广播验收漏洞，新增因果参考独立复核和preview开关。本地/服务器各109项通过。服务器4次真实离线求解均返回可行且通过单决策审核，base/uuv4预演开启预测成本下降57.84%/63.95%，开启臂均达迭代上限且更慢；不是闭环收益。CPU/GPU PWM差异已复现，uuv6旧实际门失败保留。零新物理/拟合；任务已退出、证据回传。先补完整新版采集/轨迹验收及数值余量，再2秒配对；之后另测非等价学习模型。 [审核与实测报告](../docs/phase9_methodology_crosscheck_2026-09-26.md)。以下日期较早段落为历史证据。

**2026-09-25当前v79：** 用户要求优先控制debug及物理/Koopman分离，服务器未启动、先做本地。因果反馈预演、备选代价重算和实际PWM余量检查已实现；36项离线预演可行，不能算闭环收益。旧投影与辨识物理等价，旧完整提升算子不得重新包装为新模型；下一模型优先保留运动学、学习超出D/Q的速度动力学。先服务器核对PWM边界并做2秒单因素控制回归，再单独做非等价学习模型对照。[v79报告](../docs/phase9_control_model_separation_v79.md)。Phase9仍开放，v78成绩不变。

**当前v78已交付：** v78四构型统一设置2秒验证已交付。8个MPC单元中8个完整验收；投影分支1/4个构型的综合误差低于反馈，名义物理分支1/4个。模型冻结、零训练；本轮只作短任务描述性比较，Phase9保持开放。 [v78报告](../docs/phase9_common_profile_v78_report.md)。

**历史v77交付状态（2026-09-24）：** v77有界求解与控制实验已交付。r4首组四构型×两模型8例均完整验收；原repair设置仅base改善0.67%，其他三个构型仍负收益。uuv4提高深度权重并延长时域后，相对反馈改善12.15%，是短任务局部收益，不是统一跨构型或独特Koopman收益证明。模型冻结、零训练，Phase9保持开放。 [v77报告](../docs/phase9_reliable_control_v77_report.md)。

**当前范围（2026-09-24）：** 用户明确授权连续优化、离线归因与小范围匹配闭环；同一MPC换模型，另设反馈对照。控制频率性能后置，模型冻结、零训练。首组base/uuv4/long_body/uuv6，后续四构型与Agent仍条件开放；旧v73不重启、不改写。

## Milestones

- [x] **v1.0 Koopman-UUV Single-Configuration Control** — Phase 1 through Phase 5.4, closed 2026-08-09. Canonical history: [v1.0 roadmap](milestones/v1.0-ROADMAP.md), [summary](reports/MILESTONE_SUMMARY-v1.0.md), [audit](milestones/v1.0-MILESTONE-AUDIT.md).
- [ ] **v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control** — Phase 6 through Phase 12, active.

v1.0 的阶段名称、结论和证据已冻结，不在本活动 roadmap 中重新解释。`.planning/phases/` 中保留的 v1.0 目录是历史工作材料；v2.0 只以 Phase 6–12 为活动范围。



**历史算法效率审核（2026-09-20；A/B已由v64完成）：** 已完成本地冻结模型同一fit原点6次剖析，未连接服务器或修改求解器。预测时域循环是主要候选热点；下一步先验证整段循环编译、同请求共享8步承诺前缀，再按profile处理重复固定检查。有限候选搜索/计划热启动/承诺窗口与QP分别作为算法层改进，不混入等价加速；原16.667ms/100ms门保持。详见[算法改进审核](../docs/phase9_algorithm_efficiency_review_v63.md)。

## Milestone Goal

验证同一套 configuration-aware Koopman 控制架构能否跨八种 EasyUUV 2.0 构型迁移，在环境变化下安全更新，并通过受限的低频 Agent Supervisor 获得可审计收益。

**最新优先级（用户2026-09-20进一步澄清）：** 先回答“已有Koopman接入不同构型是否有效”。已有预测结果不重复重跑，优先补实际闭环与成本证据；自适应、自进化和Agent暂列条件后续，不因路线图存在就自动实施。公平验证无效或成本不可接受时停止扩展并重新讨论方向；既不把当前投影模型成功归给旧模型，也不要求先证明独特表示优势才能测试控制。[效果证据与停止条件](../docs/phase9_shared_policy_generalization_scope.md#0-最新优先级先验证现有-koopman-是否有效)。

**同一策略边界（2026-09-20）：** 固定学习参数、优化设置及统一约束规则，构型机械信息作为显式输入。优先做已知八构型统一控制的效果验证；未见构型须补源数据/机械依据的运行范围，不借目标fit/test轨迹设门；基础效果成立后才推进在线适应、跨任务保留和Agent决策。见[当前代码取证与后续实验](../docs/phase9_shared_policy_generalization_scope.md)。v58与v59均保留NO_GO；v59已越过参数合同，但首周期超时、MPC未提交；退出问题已有修复；本轮有界效果goal已形成结论，反馈尾延迟和实时门仍开放。

**用户确认的主线（2026-09-12）：** 学长建议与代码/实验判断共同主导，细节由本任务自主处理。目标是Koopman-UUV／Agentic-AUV有效性证据；persistence、普通线性、分构型方案是诊断与对照，不自动替代研究目标。完整表述见[PROJECT](PROJECT.md#target-research-direction-user-confirmed-2026-09-12)。阶段8.3/8.4服务Koopman输入/状态与新数据验证，9验证控制，10–12再分别检验适应与Agent增益。

**当前推进（v78已交付）：** 先用已记录状态验证因果反馈预演：在模型预测的未来状态逐步计算反馈，作为同一个连续优化器的初值和可行参照；核对因果性、执行器记忆与精确约束，再保持本轮权重/时域做2秒单因素闭环对照及已有正例回归。若仍无改善，再拆分末端条件与局部优化原因。解决后才做较长任务、新初态验证。暂不扩大第二组、不训练或进入Agent。

## Phase Overview

| Phase | Name | Requirements | Depends on | Status |
|---|---|---|---|---|
| 6 | EasyUUV 2.0 Intake and Multi-Configuration Qualification | QUAL-01..08 | v1.0 frozen baseline | Complete — 4/4 plans verified |
| 7 | Cross-Configuration Koopman Data and Control Contract | CONT-01..05 | Phase 6 | Complete — 4/4 plans verified |
| 8 | Multi-Configuration Koopman Identification and OOD Gate | KID-01..05 | Phase 7 | Complete — 5/5 plans verified; valid `NO_SELECTION` |
| 8.1 | Local Simulator and Koopman Identification Repair | KIDR-01..10 | Phase 8 | Complete — 4/4 local plans verified; D-23 approved |
| 8.2 | Phase 8.1 Fresh Server Evaluation and Closeout | KIDO-01..05 | Phase 8.1 D-23 approval | Complete — 4/4 plans verified; terminal `NO_SELECTION` with `VERIFIED` closeout |
| 8.3 | Control and Identification Forensics | CFR-01..06 | Phase 8.2 closeout and senior-advice review | Complete for forensics —6/6 requirements; GO to one fresh pilot, no modelhandoff |
| 8.4 | Conditional Control Contract and Identification Experiment | NID-01..05 | Phase 8.3 GO and accepted interface decision | Complete — 8/8 scoped plans; v38 validation/test independent GO; qualified prediction handoff only |
| 9 | Configuration-Aware Koopman-MPC Integration | MPC2-01..04 | v38 corrected prediction/control handoff v2 | In progress — v78 common-profile 2s comparison delivered; longer tasks and independent representation evidence remain open |
| 10 | Environment Awareness and Online Koopman Update | ADAPT-01..05 | Phase 9 | Conditional — only after useful matched closed-loop evidence |
| 11 | Low-Frequency Agent Supervisor | AGENT-01..04 | Phase 10 | Conditional — adaptation and meaningful supervisor choices first |
| 12 | Final Matched Evaluation and Research Evidence | EVAL-01..05 | Phase 11 | Pending |

## Active Phases

**Historical v32/v37 continuation (superseded by current status above):** v37的4D因果命令预测接口已实现，八构型64个对照物理子步的状态/PWM/转速/作用输入/时钟差均0，分支隔离及独立核验通过；46相关测试通过。修正了名义质量与PhysX倒数往返读回的准入差异，预测始终保留实际质量。07按模型形式/负证据/接口合同范围完成；08/NID-05准备新的正式协议与本地运行包，D-23尚未请求或批准。保留v30速度观测量回归加已知运动学，不声称完整Koopman闭合或超越参数模型；v34/v35 NO_GO、旧正式NO_SELECTION及24test未采保持，goal active，无Phase9 handoff。 [当前接口与证据入口](../docs/phase8_4_command_prediction_v37_results.md)。

**Completed r16 calibration 2026-09-13:** r16八构型全部通过4.27秒冷启动配平及5.33秒脉冲，原始归档和本地独立重算通过。380 root/clone；物理参数、零转速初态和原误差门不变。新fit/validation、受约束Koopman候选及NID-04仍未完成，Phase9无model handoff。 [修复结果与下一步](../docs/phase8_4_state_feedback_results.md)。

**Historical 2026-09-12 direction (current authorization/status above and STATE take priority):** [学长建议解析](../docs/phase8_3_senior_advice_analysis.md) and [independent review](../docs/phase8_3_independent_critical_review.md) motivate a bounded investigation, not an assumed control-defect explanation for NO_SELECTION. First locate source-candidate failure and measure unchanged substep/reset behavior; then choose one interface. A is closest to the existing Phase9 goal; B remains an alternative and C is a temporal representation, not necessarily a third controller. Planning authorization does not start implementation, SSH, recollection or promotion. Existing Phase6–8.2 completion records retain their historical validation scope.

**Historical Phase8.3 evidence:** [表征比较](../docs/phase8_3_representation_results.md)：新增8例256区间、49文件拉回通过，累计34进程1312区间。12个固定拟合中，有序输入部分改善角速度，N状态未带来一致收益；同构型不同seed也明显落后persistence。125相关测试通过。[8.3验收](phases/08.3-control-identification-forensics/08.3-VERIFICATION.md)已关闭6项取证要求，[决定](phases/08.3-control-identification-forensics/08.3-DECISION.md)仅GO到一个直接pre-TAM fresh pilot。用户已启用持续goal并授权本路线内实现/服务器工作。Phase9仍无handoff。

**Causal state:** 已知零初始化下，12条修复轨迹的完整子步命令/执行器转速可从预设输入和自身历史重建；误差不超过1.184e-4。该事实不代表模型收益，未知初始转速、DR、在线换构型仍待独立验证。

**Controller/interval evidence:** [Control-seam assay](../docs/phase8_3_control_seam_findings.md) identifies topology-dependent PWM/deadzone effects and missing first-substep information. Earlier7.56 ratio is a single CPU depth probe; the real mixed-axis PRBS impulse discrepancy was9.55% for one measured axis. Neither quantifies formal prediction-error causality. Runtime is now available; use repaired matched traces for the next representation comparison.

**Previous evidence-led direction:** The user authorized one further bounded local assay, now [completed](../docs/phase8_3_direction_assay.md). Known kinematics improves one-step pose; per-config dynamics improves on PRBS but fails on unseen excitation and long recursion (3/21 full survivors; adding kinematics0/21). Prioritize measured interval inputs and deployable actuator state, then kinematics plus identified dynamics. Per-config remains diagnostic, not the accepted final branch. No more old-validation tuning; actual trace and a fresh pilot are needed before any performance claim orPhase9 entry.

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

### Phase 08.3: Control and Identification Forensics

**Goal:** 区分transition记录、reset历史、执行器状态、平台条件和模型递推失败；通过有界证据选择一个控制/辨识接口及继续或停止的方向，不预设修复后Koopman会改善。

**Depends on:** Phase8.2 frozen closeout and 2026-09-12 independent/advice review.

**Requirements:** CFR-01, CFR-02, CFR-03, CFR-04, CFR-05, CFR-06.

**Success Criteria:**
1. 真实加载源码/config与trace共同验证调用/token/dt；默认预设raw-action路径和真正状态反馈路径分开解释。
2. 一个固定source-only候选定位最早失败horizon/step/reason，不能将总括rollout failure当作根因。
3. base/uuv6/uuv4的有界trace先通过日志行为不变对照，再量化两子步、cold/warm reset及后续影响。
4. 同轨迹比较可部署输入/状态/context的增量信息，明确oracle、未来输入和样本覆盖限制。
5. 输出一种接口的建议及GO/NO_GO/INCONCLUSIVE；合同正确性和继续投入门分开。缺runtime证据保留未完成状态。
6. 不改写Phase8.2、不调用formal LOCO、不自动重采；满足预算和具体服务器启动条件。

**Latest repair result:** [local repair assay](../docs/phase8_3_repair_results.md) removed20/21 full-rollout divergence failures but all6 macro errors remained worse than persistence. The candidate is rejected for use; prioritize the control/input/state evidence route, not repeated validation tuning.

**Completed direction assay:** Eight fixed local fits, four diagnostic variants plus persistence;176 focused tests pass. [Results](../docs/phase8_3_direction_assay.md) support a known-kinematics backbone but reject simple per-config substitution and a stable-only success criterion. The rank20/22 in uuv4 includes two structurally masked zero columns; do not call this purely data shortage. This additional local work does not close runtime or causal representation requirements.

**Plans:** 3/3 closed within the bounded forensic scope;CFR-01..06 complete. Final decision GO_TO_BOUNDED_PILOT selected directpre-TAM with causal substepactuation; no modelpromotion. Historical intermediate findings above remain evidence, not current open tasks. The [control-chain gap register](../docs/phase8_3_control_chain_findings.md) separates local repairs, runtime evidence and future architecture work.

- [x] [08.3-01-PLAN.md](phases/08.3-control-identification-forensics/08.3-01-PLAN.md) — 完成固定源候选失败定位、隔离修复和真实运行准备；历史局部状态见SUMMARY，最终以08.3-VERIFICATION为准。
- [x] [08.3-02-PLAN.md](phases/08.3-control-identification-forensics/08.3-02-PLAN.md) — 完成修复后的有界覆盖替换、子步/reset/初始化取证；46个弃用旧plant病例明确未执行。
- [x] [08.3-03-PLAN.md](phases/08.3-control-identification-forensics/08.3-03-PLAN.md) — 完成12个固定因果表征拟合及A/B/C决策；GO到单个fresh pilot，无模型晋级。

**Contract:** [08.3-CONTEXT.md](phases/08.3-control-identification-forensics/08.3-CONTEXT.md) owns diagnostic candidate, matrix, resource cap, measurement fields and stop conditions. Trace alone cannot establish full-horizon model or closed-loop performance.

### Phase 08.4: Conditional Control Contract and Identification Experiment

**Goal:** 只在8.3支持继续且接口方向被接受后，实施一种版本化合同并通过fresh bounded pilot决定是否值得新正式辨识实验。

**Depends on:** Phase8.3 evidence-backed GO within the user-confirmed Koopman-UUV/Agentic-AUV line. Routine interface/implementation decisions are delegated; a changed research objective requires a separate user decision. NO_GO/INCONCLUSIVE does not auto-start8.4.

**Pilot initialization prerequisite:** Use the versioned static authored mechanical initialization, declared inertia sync and episode-local controller reset; include measured first-step response and raw backend readback, not setter/getter alone. The existing32-step traces are diagnostic; a fresh longer pilot needs frozen episode roles. Dynamic mechanical switching/DR requires separate qualification.

**Pilot design priority from current evidence:** Known pose kinematics plus a simple identified dynamics head; fit-only scaling and topology-defined active features; episode/seed-separated excitation coverage; one-step and all-sliding20/60-step errors plus failure/worst-config reports. Treat per-config as a reference before shared/conditioned complexity. These are planning priorities, not a selected model or permission to recollect.

**Requirements:** NID-01, NID-02, NID-03, NID-04, NID-05.

**Success Criteria:**
1. 选定合同的模型输入、可部署状态、dt/hold/子步、mask/TAM/限幅和fallback一致；先通过独立fresh pilot。
2. 只有pilot GO及新D-23后才进入新ID/结果根的formal collection/evaluation；不预先承诺96episodes。
3. 正式selection/no-selection和closeout保留实际证据等级；handoff匹配执行接口，不能把旧simple-linear自动晋级。

**Plans:** 8/8 completed within scope; [verification](phases/08.4-conditional-identification-experiment/08.4-VERIFICATION.md).

- [x] [08.4-01-PLAN.md](phases/08.4-conditional-identification-experiment/08.4-01-PLAN.md) — direct bounded control/causal actuator contract and real GPU seam equivalence.
- [x] [08.4-02-PLAN.md](phases/08.4-conditional-identification-experiment/08.4-02-PLAN.md) — one frozen fresh prediction pilot; prepare new formal D-23 only after pilot GO.

- [x] [08.4-03-PLAN.md](phases/08.4-conditional-identification-experiment/08.4-03-PLAN.md) — 已知输入结构及独立新种子pilot GO；保留02负结果。
- [x] [08.4-04-PLAN.md](phases/08.4-conditional-identification-experiment/08.4-04-PLAN.md) — 正式协议、源码包、运行入口和具体D-23提案准备完成；2026-09-13用户已确认。
- [x] [08.4-05-PLAN.md](phases/08.4-conditional-identification-experiment/08.4-05-PLAN.md) — 8预检+48fit/validation、68模型、2280评分及独立NO_SELECTION closeout完成；test未采，无handoff。
- [x] [08.4-06-PLAN.md](phases/08.4-conditional-identification-experiment/08.4-06-PLAN.md) — 自由水域/反馈/因果数据、覆盖、34候选及独立新16验证完成；投影pilot GO，完整算子未通过。
- [x] [08.4-07-PLAN.md](phases/08.4-conditional-identification-experiment/08.4-07-PLAN.md) — 完成时序/流形/运动学缺项否决、参数模型等价边界与4D因果接口核查；无handoff。
- [x] [08.4-08-PLAN.md](phases/08.4-conditional-identification-experiment/08.4-08-PLAN.md) — 新正式协议、批准范围内validation/test及独立审核全部GO，交接v2就绪；额外Koopman/MPC/Agentic收益未证明。

**Current evidence:** [v38正式结果](../docs/phase8_4_v38_formal_results.md)支持固定八构型的新episode投影预测及[handoff v2](../docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json)。NID-01..05按范围完成；完整算子失败、同D/Q参数模型等价及旧NO_SELECTION保持。

### Phase 9: Configuration-Aware Koopman-MPC Integration

**Goal:** 让 Koopman-MPC 在统一 4D virtual-control 空间优化，并通过当前构型 TAM、可控自由度 mask 与确定性 fallback 实现可比较的多构型闭环控制。

**Depends on:** [v38交接v2](../docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json)已满足限定预测接口前置条件；Phase8.2 `NO_SELECTION`保持且不提供交接。当前模型为六速度读出加已知位姿积分的非线性投影，不是合格固定A/B线性系统。先本地接口/成本验证，后闭环控制；不改变Koopman-UUV/Agentic-AUV研究目标。

**Requirements**: MPC2-01, MPC2-02, MPC2-03, MPC2-04

**Success Criteria**:
1. MPC以未来多步、多轴有界4D virtual control为优化变量，完成预测表达/梯度检查与精确执行链复核；固定7/9候选不足以完成此要求。每个构型使用自身TAM及mask；不把当前混合非线性模型直接当作固定A/B线性QP。
2. `uuv4*` yaw 目标在优化和评分入口被 mask，不能作为可实现跟踪目标进入结果。
3. timeout、infeasible、non-finite、越支持域、过期计划与 saturation 均进入 reason-coded bounded fallback/限幅仲裁；求解器不得阻塞低层发令，晚结果不能提交执行历史。
4. 每个构型在相同 scenario、seed、horizon、信息权限和 disturbance 下与 Legacy/S-Surface 完成 matched comparison；另在相同优化器/计算预算下比较名义物理先验、辨识参数物理模型与当前投影模型，分别评价控制、学习与表示增量。
5. 模型的输入/状态估计和hold或子步时间语义与实际执行完全匹配；MPC输出不再经S-surface/PID重新解释。Legacy通过并联仲裁及明确状态接管保留。
6. 匹配实验包含仅反馈回退对照，报告全部episode的误差、失败、约束违反、MPC实际激活/回退和周期成本。事前定义改善及效果相近的容差/不确定性判据；不以精确相等或少量短预检替代控制效果证据。负结果允许关闭本次评价，但不自动准入Phase10–11。

同一策略与泛化按[当前代码边界](../docs/phase9_shared_policy_generalization_scope.md)执行：先固定同一pooled模型与控制设置测已知构型的新任务，另以源构型训练的冻结策略测留出构型。现有`load_fit_domains`仅准入训练构型，未见构型需要新的已验证支持域来源；不得移除原保护或读取目标测试轨迹补域。先用统一外部参考比较下层，再审阅旧PPO动作语义和迁移/重训练问题。

**当前计划（2026-09-22）：** 连续控制优化优先于扩大固定候选覆盖。在线30Hz仍需独立验收；离线能力验证不能冒充实时资格。

- [x] [09-01](phases/09-configuration-aware-koopman-mpc/09-01-PLAN.md) — 已完成的因果预测/分支接口证据。
- [ ] [09-02](phases/09-configuration-aware-koopman-mpc/09-02-PLAN.md) — 保留成本/调度工作；新优化器能力验证后再测30Hz完整周期，旧60Hz记录为历史。
- [ ] [09-03](phases/09-configuration-aware-koopman-mpc/09-03-PLAN.md) — 有限候选、执行接口与v73覆盖历史；不再作为算法主线，不因已有工程验收称效果通过。
- [ ] [09-04](phases/09-configuration-aware-koopman-mpc/09-04-PLAN.md) — 当前主线：模型/执行器求解表达 → 连续多步多轴优化 → 离线失败归因 → base/uuv4起步及4+4闭环 → 同MPC模型对照。

新环境：[算力云核验与迁移](../docs/phase9_suanliyun_v75_environment.md)。已有base部署smoke可复用作接口准备证据，但不是旧实验重现、MPC收益或30Hz资格。当前不启动旧v73队列或新训练。成功反馈未来指令仅供事后诊断，不泄露给在线控制器。

### Phase 10: Environment Awareness and Online Koopman Update

**Goal:** 分离环境估计误差与控制误差，先建立 oracle-context 上界，再验证带限幅、冻结先验和回滚的 RLS/KF 在线 Koopman 更新能否缩短环境变化后的恢复过程。

**Depends on:** Phase 9

**启动条件补充（2026-09-20）：** 先完成现有Koopman-MPC的基础效果判断；当前不开展在线更新或跨任务记忆实现。若Phase9公平验证无效，先提出修改思路，不自动进入本阶段。

**Requirements**: ADAPT-01, ADAPT-02, ADAPT-03, ADAPT-04, ADAPT-05

**Success Criteria**:
1. oracle-context 结果先于 estimated-context 声明生成，并作为可达到上界单独报告。
2. deployable estimator 只使用运行时可用信号，并将 context estimation error 与 control error 分开记录。
3. 先明确RLS/KF更新对象是环境context、D/Q物理参数还是已准入提升算子，并检验激励/可辨识性；更新具备bounds、non-finite rejection、frozen prior、rollback和disable path。参数适应不改称完整Koopman算子学习。
4. matched evaluation 报告 shift 前退化、恢复曲线、rollback 事件和 frozen-model baseline。
5. 只有聚合收益门与所有逐构型安全/稳定 sentinel 同时通过时才允许 promotion。

用户提出的持续进化目标在单次适应成立后细化：跨任务保留已验证模型/经验，比较每任务重置、连续更新和带记忆更新，在重复工况及新组合上报告样本效率与遗忘。此扩展尚无具体实验规模，不视为在线参数更新已完成或Agent已带来收益；边界见[同一策略实验说明](../docs/phase9_shared_policy_generalization_scope.md)。

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
4. 先证明监督器有运行时可观测的决策条件及效果不同的准入选项，再将no-supervisor、rule-supervisor、agent-supervisor在相同manifest/信息权限下三方消融；无增量允许NO_GO。

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
| 8.3 | CFR-01..06 | 6 |
| 8.4 | NID-01..05 | 5 |
| 9 | MPC2-01..04 | 4 |
| 10 | ADAPT-01..05 | 5 |
| 11 | AGENT-01..04 | 4 |
| 12 | EVAL-01..05 | 5 |
| **Total** | **All v2.0 requirements** | **62** |

Coverage: 62 mapped, 0 unmapped, 0 multiply mapped. Counts include conditional future requirements; they do not imply those phases are authorized or completed.

---

*Roadmap created: 2026-08-09 for milestone v2.0*

*Updated: 2026-09-12 — senior-advice analysis, bounded8.3 planning, conditional8.4 and Phase9 entry correction. Prior coverage total46 was stale; pre-addition requirement rows totalled51.*

Historical r16 update2026-09-13:r16八构型全部通过4.27秒冷启动配平及5.33秒脉冲，原始归档和本地独立重算通过。380 root/clone；物理参数、零转速初态和原误差门不变。新fit/validation、受约束Koopman候选及NID-04仍未完成，Phase9无model handoff。先冻结独立的新fit/validation角色、种子、时长和外部激励；适配实际已发命令、两子步因果执行器历史及真实物理参数，审查输入/状态覆盖与共线性，再实现受物理结构约束的Koopman候选。校准轨迹不改名训练，旧NO_SELECTION/24test未采保持冻结。

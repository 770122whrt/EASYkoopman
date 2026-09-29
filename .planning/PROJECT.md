# EASYkoopman

**2026-09-29最终确认：** 下一步仅做“加扰动”和“物理与Koopman结合”。物理基线事前冻结，不学习新增扰动数据、不重新校准；Koopman可离线学习，测试参数冻结，完整提升状态自行传播。旧的同数据重校准要求与覆盖优先研究顺序不再作为当前条件。执行细节以 `.planning/STATE.md` 及其交接为准。

**2026-09-29当前讨论入口：** 请先读[STATE](STATE.md)中的完整提升传播交接；以下旧日期结论保留为历史证据，两步方向已确认，服务器实验尚未执行。

**当前入口（结果截至2026-09-27，2026-09-28补充中文解释）：** 已完成五种模型的预测比较与单构型诊断。数据校准的物理模型整体最好；限制自由度的学习残差接近物理预测；两种“非线性特征＋矩阵传播”模型尚未合格。同一基础构型换成未参与训练的扫频输入也失败，因此不能只归因于跨构型。六次连续控制优化中一次达到可接受精度、五次超时，新两秒闭环尚未运行。模型中文名称、正则参数λ、论文关系及完整数字见[统一报告与八构型表](../docs/phase9_model_comparison_v84_report.md)。本轮先解释与修正文档，没有新实验；下方旧日期内容为历史证据。

**已完成v82报告（2026-09-26，历史Goal结果）：** 已完成10条2秒真实闭环、18个非等价学习模型及八折留构型预测。uuv4两学习候选相对同MPC辨识物理的综合误差降低11.7%/9.8%；base高3.0%/17.9%，仅部分完整目标改善。已观察局部控制收益，未证明普遍模型优势或未见构型闭环泛化。10条原Linux验收通过，9条本地完整复核，uuv4学习0.001在Windows因果预演未复现、另经原运行时严格重验通过；失败保留。下一步先修求解质量和预演平台分支敏感性，再冻结新任务验证。服务器无本任务遗留进程，可关闭。 [最终报告](../docs/phase9_koopman_mpc_v82_report.md)；[执行范围](../docs/phase9_goal_v80_plan.md)。下方旧日期的运行状态仅为历史。

**当前2026-09-26：** 2026-09-26已完成两篇论文与控制/模型/验证三端交叉审核：主线合理；修复短计划广播验收漏洞，新增因果参考独立复核和preview开关。本地/服务器各109项通过。服务器4次真实离线求解均返回可行且通过单决策审核，base/uuv4预演开启预测成本下降57.84%/63.95%，开启臂均达迭代上限且更慢；不是闭环收益。CPU/GPU PWM差异已复现，uuv6旧实际门失败保留。零新物理/拟合；任务已退出、证据回传。先补完整新版采集/轨迹验收及数值余量，再2秒配对；之后另测非等价学习模型。 [方法审核](../docs/phase9_methodology_crosscheck_2026-09-26.md)。

**当前v78已交付：** v78四构型统一设置2秒验证已交付。8个MPC单元中8个完整验收；投影分支1/4个构型的综合误差低于反馈，名义物理分支1/4个。模型冻结、零训练；本轮只作短任务描述性比较，Phase9保持开放。 [v78报告](../docs/phase9_common_profile_v78_report.md)。

**历史v77交付状态（2026-09-24）：** v77有界求解与控制实验已交付。r4首组四构型×两模型8例均完整验收；原repair设置仅base改善0.67%，其他三个构型仍负收益。uuv4提高深度权重并延长时域后，相对反馈改善12.15%，是短任务局部收益，不是统一跨构型或独特Koopman收益证明。模型冻结、零训练，Phase9保持开放。 [v77报告](../docs/phase9_reliable_control_v77_report.md)。

**当前范围（2026-09-24）：** 用户明确授权连续优化、离线归因与小范围匹配闭环；同一MPC换模型，另设反馈对照。控制频率性能后置，模型冻结、零训练。首组base/uuv4/long_body/uuv6，后续四构型与Agent仍条件开放；旧v73不重启、不改写。

## What This Is

EASYkoopman is an EasyUUV/Isaac research project for learning and controlling underwater-vehicle dynamics with Koopman models, model-predictive control and bounded higher-level supervisors.

Milestone v1.0 established the system on one EasyUUV configuration. Milestone v2.0 extends that evidence chain to multiple vehicle parameterizations and 4/6/8-thruster topologies, then adds environment-context estimation, guarded online Koopman updates and an auditable low-frequency Agent Supervisor.

## Core Value

Build control experiments whose model, checkpoint, controller path and evaluation evidence are explicit enough to reproduce, compare and reject safely.

## Current Milestone: v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control

**Historical route (2026-09-24, v78; superseded by v84 planning above):** 先用已记录状态验证因果反馈预演：在模型预测的未来状态逐步计算反馈，作为同一个连续优化器的初值和可行参照；核对因果性、执行器记忆与精确约束，再保持本轮权重/时域做2秒单因素闭环对照及已有正例回归。若仍无改善，再拆分末端条件与局部优化原因。解决后才做较长任务、新初态验证。暂不扩大第二组、不训练或进入Agent。

**最新用户优先级（2026-09-20）：** 首先把不同构型接入已有Koopman方法，检验实际预测/控制效果与计算成本；公平验证无效时允许提出路线调整。现有v38预测证据足以继续有界控制验证，不先追求新字典、独特表示优势或完整提升闭合。自适应、经验库和Agent仅在基础效果成立后推进；分清旧模型失败与当前投影分支的限定成功。执行与停止条件见[效果验证优先](../docs/phase9_shared_policy_generalization_scope.md#0-最新优先级先验证现有-koopman-是否有效)。

**用户细化（2026-09-20）：** 以“同一冻结控制策略跨构型运行”为核心实验，允许已知机械描述符及按统一规则生成的TAM/mask/配平作为输入；不按目标构型重训或手调。先检验已知八构型的统一控制，再补未见构型运行范围以检验冻结迁移；随后分别验证在线适应、跨任务经验保留与Agent增量。当前pooled/fit域预检不构成未见构型闭环证据。详见[代码边界与实验顺序](../docs/phase9_shared_policy_generalization_scope.md)。

**Goal:** Demonstrate whether one configuration-aware Koopman control architecture can transfer across the eight supported EasyUUV 2.0 configurations, adapt safely to environmental change and expose bounded decisions to an Agent Supervisor.

**Target features:**

- Qualified EasyUUV 2.0 configuration catalog with explicit thruster topology and controllable-degree-of-freedom metadata.
- Versioned cross-configuration data and control contract using fixed 4D virtual control before TAM allocation.
- Per-configuration, pooled and physically conditioned regimes of one v2 controlled-EDMD backend, compared with explicit baselines and held-out-configuration gates.
- Configuration-aware Koopman-MPC with masks, fallback and matched closed-loop evaluation.
- Environment-context estimation and rollback-protected RLS/KF online updates.
- Low-frequency Agent Supervisor that cannot directly command PWM or bypass safety gates.

## Target research direction (user confirmed 2026-09-12)

以学长建议与本任务基于代码、控制链和实验的判断共同决定前进方向；实现、调试、实验准备及其他代码细节由本任务自主处理。主线是建立Koopman-UUV或Agentic-AUV形式的可复现有效性证据。persistence、普通线性、分构型模型用于诊断、消融、基线及必要的控制fallback，不因它们局部表现更好而自动替换研究目标。若需要改变这一研究主线，应明确提出依据并由用户决定。

分别验证：Koopman模型的状态/观测量、输入与时间合同及预测/闭环作用；Agentic上层相对无Agent和规则Supervisor的任务收益。身份lift与普通线性等价时明确标注，不仅凭Koopman命名宣称方法收益。整体系统收益与组件贡献分开报告，保留失败实验与现有NO_SELECTION。上层Agent的调度不能替代底层模型/控制验证。

## Requirements

### Validated

- ✓ A reproducible single-configuration JSONL → Koopman model → selected manifest → bounded MPC chain exists — v1.0.
- ✓ Legacy/S-Surface remains available as a matched baseline and fallback — v1.0.
- ✓ PPO integration, checkpoint provenance and evidence-level separation exist — v1.0.
- ✓ The eight CLI-supported EasyUUV 2.0 configurations have a provenance-bound package/catalog/topology contract and real Isaac server smoke evidence — Phase 6.

### Active

- [x] Import and qualify the eight CLI-supported EasyUUV 2.0 configurations without rewriting v1.0 evidence.
- [x] Establish a topology-independent Koopman/data/control contract for 4, 6 and 8 thrusters — Phase 7.
- [ ] Measure held-out-configuration Koopman prediction and closed-loop transfer against explicit baselines.
- [ ] Estimate environment context and allow only bounded, reversible online model updates.
- [ ] Evaluate a low-frequency Agent Supervisor against no-supervisor and rule-supervisor baselines.
- [ ] Produce server-verifiable evidence with clear smoke, training, matched-evaluation and promotion levels.

### Out of Scope

- Sim2Real or hardware-success claims — v2.0 remains simulation research unless a later milestone adds hardware evidence.
- Eight distinct vehicle appearance/CAD assets — current configurations share one USD appearance and differ in dynamics or thruster topology.
- Direct PWM generation by PPO, Agent or LLM — all high-level decisions remain above bounded low-level control.
- End-to-end LLM control or an unrestricted autonomous agent — Phase 11 exposes only allow-listed low-frequency decisions.
- Immediate PPO retraining during Phase 6 intake — qualification precedes learning and controller integration.

## Current State

**Historical r16 checkpoint (2026-09-13):** r16八构型全部通过4.27秒冷启动配平及5.33秒脉冲，原始归档和本地独立重算通过。380 root/clone；物理参数、零转速初态和原误差门不变。新fit/validation、受约束Koopman候选及NID-04仍未完成，Phase9无model handoff。 [当前结果](../docs/phase8_4_state_feedback_results.md)。

**Repair follow-up:** One fixed-context stability-constrained diagnostic now survives21/21 source full rollouts, but all6 macro prediction errors are worse than persistence; no usable model is selected. See [repair results](../docs/phase8_3_repair_results.md). The stable prior is exploratory, not a new approved system architecture.

**Historical initialization runtime finding (superseded current position above):** 固定构型初始化修复已通过真实GPU验收：原资产22.8kg造成冷启动首步响应异常，authored_static_v1在PhysX创建前写入质量/惯量；base/uuv4 seed8201及uuv6 seed8201/8202共四组冷/热对照，64个observed物理子步state11逐分量差0。新增576区间/13进程，累计1056区间/26进程；210本地及210独立克隆测试通过，105文件拉回核验通过。完成修复后覆盖审查，再用匹配轨迹比较有序子步输入与因果N维执行器状态；8.4 fresh pilot在接口决定后冻结。剩余46个旧plant病例保持未完成且不自动恢复。动态换构型/DR尚未验证，32步trace不支持60/512步性能结论。Phase8.3仍partial，8.4conditional，Phase9无handoff。

**Control-seam evidence:** [Controller/interval investigation](../docs/phase8_3_control_seam_findings.md) found actual control-kernel allocation/PWM/ordering interactions. Command-only actuator estimation and backend readback are now exercised in real traces. Their information value for prediction remains to be compared after the repaired initialization gate.

**Previous direction assay:** [Eight fixed fits and kinematics probes](../docs/phase8_3_direction_assay.md) found one-step pose benefits and excitation-dependent dynamics errors; per-config full survival3/21, per-config with kinematics0/21. No model handoff. Continue toward measured control intervals and command-driven actuator state, then known kinematics plus identified dynamics; retain the cross-configuration research question and use per-config as a diagnostic.176 focused local tests pass. Actual Isaac trace remains unexecuted.

The following implemented chain describes the frozen v1.0 baseline, not a successful current multi-configuration handoff.

**Shipped research milestone:** `v1.0 Koopman-UUV Single-Configuration Control`

The implemented chain is:

```text
observation_9d
  -> RSL-RL PPO
  -> action_4d
  -> heuristic_reference_delta_v0
  -> reference_5d
  -> direct_state Koopman + bounded MPC
  -> PWM_8d
  -> EasyUUV Isaac physics
```

Validated in v1.0:

- Isaac Sim 5.0 + Isaac Lab 2.2.1 direct and PPO-integrated workflows;
- step/sine/irregular JSONL data collection;
- offline direct-state and paper-style lifted EDMD model tooling;
- selected-model manifest and prediction-quality gate;
- bounded 8D PWM Koopman-MPC with timeout/fallback diagnostics;
- controller-only matched evaluation;
- PPO adapter, retraining path and checkpoint provenance;
- stability, one-factor, cross-combination and 11-profile Pareto experiments;
- 175 local tests passing at milestone close.

The final Phase 5.4 selector returned `no_selection`. v1.0 therefore remains a reproducible research baseline rather than a performance-superiority or deployment release.

## Known Limitations

- Legacy/S-Surface remains the strongest nominal controller baseline.
- `heuristic_reference_delta_v0` is an explicit engineering assumption, not a lossless action-semantics migration.
- `no_cost_improvement` fallback needs cost-margin and prediction-error diagnosis.
- `paper_lifted_edmd` has large depth error and is research-only.
- Koopman models are trained offline and remain fixed online.
- Koopman performance evidence still covers the v1.0 single configuration; Phase 6 qualified eight simulator configurations and Phase 7 connected the 4D data/control contract on representative 8/6/4-thruster servers, but neither proves Koopman prediction transfer.
- No LLM runtime, Sim2Real, hardware deployment or broad 6-DOF claim exists.
- Several historical phases lack standard GSD verification artifacts; see the milestone audit.

## Milestone Transition

v1.0 is frozen at tag `v1.0`. v2.0 continues phase numbering at Phase 6 and treats the received `easyuuv_v2-main/` tree as a provenance-preserving simulator snapshot. Integration changes, archived server evidence and planning documents remain separate commits and push boundaries.

## Constraints That Remain Valid

- Isaac-dependent validation runs on the server; local development must retain Isaac-free tests where possible.
- PWM commands must stay in `[-1, 1]` and pass through the existing thruster/hydrodynamic plant.
- Legacy control must remain available as a matched baseline and fallback.
- PPO or a future LLM cannot silently bypass the low-level controller to command PWM.
- Model and checkpoint selection must be provenance-checked and fail closed.
- Claims must distinguish smoke, stable training, matched evaluation and performance promotion.
- Cross-configuration control uses `virtual_control_4 = [roll, pitch, yaw, depth]`; padded PWM is diagnostic data, not the default learned-control meaning.
- `uuv4*` yaw underactuation must be represented explicitly and cannot be scored as a feasible yaw-tracking target.
- Online model updates require bounded parameters, non-finite rejection, a frozen prior and rollback.
- Local work owns Isaac-free contracts and tests; server work owns Isaac physics rollout and matched evaluation.

## Key Decisions

| Decision | Rationale | Outcome |
|---|---|---|
| Preserve Isaac Lab `DirectRLEnv` and EasyUUV physics | Limit simultaneous migration and algorithm risk | Good |
| Build the data seam before EDMD/MPC | Identification needs reproducible transitions | Good |
| Split datasets by log, not row | Avoid temporal leakage | Good |
| Use selected manifests at runtime | Prevent stale or unsupported models entering control | Good |
| Keep direct-state engineering and paper-lifted comparison distinct | Avoid overstating paper alignment | Good |
| Optimize model-consistent 8D PWM in the first MPC | Match the identified control input | Good |
| Put PPO above Koopman-MPC through a versioned adapter | Preserve layered control architecture | Revisit adapter semantics |
| Reuse RSL-RL PPO | Focus effort on MDP and controller integration | Good |
| Add checkpoint provenance/evidence levels | Prevent relabeling and unsupported claims | Good |
| Close Phase 5.4 with `no_selection` | Preserve a valid negative result | Good |
| Defer online adaptation and LLM | Finish the core control evidence first | Still valid |
| Continue v2.0 at Phase 6 | Preserve the v1.0 historical phase identity | Good — Phase 6 verified |
| Use fixed 4D virtual control before TAM allocation | Give 4/6/8-thruster platforms one controller-facing meaning | Good — Phase 7 schema/Bridge/server evidence verified |
| Treat `uuv4*` yaw as explicitly unavailable | Avoid impossible tracking claims on underactuated configurations | Good — rank/mask and server smoke verified |
| Restrict Agent to an allow-listed low-frequency supervisor | Preserve deterministic low-level control and fail-closed behavior | Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**

1. Move verified active requirements to Validated with the phase reference.
2. Move invalidated requirements to Out of Scope with the reason.
3. Record new requirements and decisions without rewriting frozen v1.0 conclusions.
4. Re-check that the project description and core value still match the evidence.

**After each milestone:**

1. Audit every requirement against implementation and verification artifacts.
2. Re-check the core value and all explicit exclusions.
3. Update context, constraints and decision outcomes from measured results.

## Canonical Records

- `.planning/reports/MILESTONE_SUMMARY-v1.0.md`
- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- `docs/Agentic_AUV_project_handover.md`
- `docs/project_parameters_and_work_summary_2026_07_05.md`

---

*Last updated: 2026-08-13 after Phase 8 planning and independent contract review*

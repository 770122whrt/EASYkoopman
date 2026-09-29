# v87整理前的入口文档原文

2026-09-29。以下四份文档按整理前内容逐字保存，供核对历史决策和当时状态。代码块内的“当前”“下一步”和相对链接属于原文件语境，不能作为当前执行指令；相对路径以标注的原文件目录解析。当前入口见[研究索引](../phase9_research_index.md)。冻结报告与原始实验材料未移动、删除或改写。

## README.md

原文件字节 SHA256：`24fb9578f2e608238d26e47e266c3122e258b03970e15a3c4e62fac87bbae1bf`。原文如下（代码块分隔符之外的换行不属于原文件）：

````text
# EasyUUV-Isaac-Simulation

[![WebSite](https://img.shields.io/badge/Github_Page-PDF-77DDFF.svg)](https://360zmem.github.io/easyuuv/) [![WebSite](https://img.shields.io/github/last-commit/360ZMEM/EasyUUV-Isaac-Simulation?color=green)](https://github.com/360ZMEM/EasyUUV-Isaac-Simulation)

This repository contains code implementation for simulator of the paper "EasyUUV: An LLM-Enhanced Universal and Lightweight Sim-to-Real Reinforcement Learning Framework for UUV Attitude Control".

> **EASYkoopman migration status:** This branch extends the upstream EasyUUV simulator with offline Koopman identification, bounded Koopman-MPC control, a PPO-to-reference adapter, Koopman-MPC-conditioned PPO training and evidence-gated evaluation. The validated server environment is Isaac Sim 5.0 + Isaac Lab 2.2.1; the upstream Isaac Lab 1.0 instructions below are retained for historical reference. New contributors should start with [`docs/Agentic_AUV_project_handover.md`](docs/Agentic_AUV_project_handover.md) and [`.planning/ROADMAP.md`](.planning/ROADMAP.md).

The hardware deployment code repository refers to [**HERE**](https://github.com/360ZMEM/EasyUUV-UUV-Deploy)

![intro](README.assets/intro.png)

## Simulator Deployment

### Environment Setup

This project utilizes a simulator based on Isaac Sim/Lab. The code has been tested on a system with NVIDIA GeForce RTX 4060 (requiring approximately 5600MB GPU memory for 2048 parallel environments), Ubuntu 24.04 LTS, IsaacSim v4.0.0, and IsaacLab v1.0.0 (installation instructions are provided based on this configuration). Theoretically, the code should also work with other Isaac Lab V1 versions such as IsaacSim v4.2.0 + IsaacLab v1.4.1. For migration to IsaacLab V2, please refer to [this link](https://isaac-sim.github.io/IsaacLab/main/source/refs/migration.html).

First, you should [download Isaac Sim](https://docs.isaacsim.omniverse.nvidia.com/4.5.0/installation/download.html) and confirm version 4.0.0 is selected. Next, install Isaac Lab v1.0.0 using:

```bash
git clone --branch v1.0.0 https://github.com/isaac-sim/IsaacLab.git
```

To ensure compatibility with RSL-RL, modify the file `<IsaacLab_Path>/source/extensions/omni.isaac.lab_tasks/setup.py` following [these instructions](https://github.com/isaac-sim/IsaacLab/pull/1808/files/8af43cb048cdaa976c24a0f2b569ea9e45db533d) before installation. Then follow the [Isaac Lab installation guide](https://isaac-sim.github.io/IsaacLab/v1.4.1/source/setup/installation/binaries_installation.html) to complete the setup and verify functionality through tests.

### Deployment Configuration

Create a symbolic link or copy the directory to install the reinforcement learning environment:

```bash
git clone https://github.com/360ZMEM/EasyUUV-Isaac-Simulation.git
ln -s EasyUUV-Isaac-Simulation <IsaacLab_Path>/source/extensions/omni.isaac.lab_tasks/omni/isaac/lab_tasks/direct/EasyUUV-Isaac-Simulation
```

### Training

Train using the following command (ensure correct Python environment activation and execution from IsaacLab root directory; `--headless` flag is recommended for improved performance):

```bash
./isaaclab.sh -p source/standalone/workflows/rsl_rl/train.py --task EasyUUV-Direct-v1 --num_envs 1024 --headless
```

Note that when visualization is enabled, loading USD files consumes significant memory. Therefore, if the `--headless` option is not specified, you should reduce the `--num_envs` parameter (e.g., to 512); otherwise, it may lead to excessive resource usage or crashes.

Monitor training with Tensorboard:

```bash
tensorboard --logdir <IsaacLab_Path>/logs/rsl_rl/EasyUUV-Isaac-Simulation/
```

Generated policy checkpoints can be exported to Torch JIT/ONNX formats using:

```bash
./isaaclab.sh -p <IsaacLab_Path>/source/extensions/omni.isaac.lab_tasks/omni/isaac/lab_tasks/direct/EasyUUV-Isaac-Simulation/workflows/gen_policy.py
```

Exported files will be saved at `<IsaacLab_Path>/logs/rsl_rl/EasyUUV-Isaac-Simulation/<latest_date>/exported/policy.pt` (contains both Torch JIT and ONNX formats). Load Torch JIT models with `torch.jit.load()`. Note that RSL-RL creates date-stamped folders for each training session, where `<latest_date>` represents the most recent timestamp folder.

### Evaluation

The `workflows` directory contains trajectory tracking implementations. For example:

```bash
./isaaclab.sh -p <IsaacLab_Path>/source/extensions/omni.isaac.lab_tasks/omni/isaac/lab_tasks/direct/EasyUUV-Isaac-Simulation/workflows/play_eval_task1.py
```

- `play_eval.py`: Tracks sinusoidal signals.
- `play_eval_task2.py`: Tracks irregular dynamic signals.
- `play_eval_step.py`: Tracks step signals.
- `play_controller.py`: Direct controller implementation (w/o RL).

Note: Requires prior configuration of `wandb` for real-time visualization. Also, we provide offline file for tracking result: `<IsaacLab_Path>/source/results/rsl_rl/EasyUUV-Isaac-Simulation/.*/model_.*_play/logs.csv`.

## Acknowledgement

This repository is modified based on [this codebase](https://github.com/warplab/isaac-auv-env).

# Cite

If you find it useful for your work please cite:

```bibtex
@article{xie2025easyuuv,
      title={EasyUUV: An LLM-Enhanced Universal and Lightweight Sim-to-Real Reinforcement Learning Framework for UUV Attitude Control},
      author={Xie, Guanwen and Xu, Jingzehua and Tang, Jiwei and Huang, Yubo and Zhang, Shuai and Li, Xiaofan},
      journal={arXiv preprint arXiv:2510.22126},
      year={2025}
    }
```

````

## .planning/PROJECT.md

原文件字节 SHA256：`cf89a4ac07df85bdb78147bc049e6bee56f0ccb353687b96171f1491cd1a1731`。原文如下（代码块分隔符之外的换行不属于原文件）：

````text
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

````

## .planning/STATE.md

原文件字节 SHA256：`c7a712cb038accc9a2aff354bb06ca1f1164a0de8640dfc1c0ec69a8208f376c`。原文如下（代码块分隔符之外的换行不属于原文件）：

````text
---

gsd_state_version: 1.0
milestone: v2.0
milestone_name: Multi-Configuration Koopman Transfer and Environment-Aware Control
status: in_progress
last_updated: "2026-09-29"
last_activity: 2026-09-29 -- v86 eight Isaac disturbance traces accepted; frozen fit and solver checks complete; Koopman and hybrid fail chirp prediction; closed loop held for discussion
progress:
  total_phases: 11
  completed_phases: 7
  total_plans: 36
  completed_plans: 33
  percent: 92
---

**2026-09-29当前入口（v86真实扰动结果）：** 已完成20%额外二次阻力、完整提升独立传播与冻结物理结合；本地238项定向回归和服务器153项子集通过。8条真实Isaac轨迹全部采集并在服务器/本地验收，模型只训练一次。三臂均通过同类新种子验证；独立扫频测试物理6/6、Koopman3/6、结合5/6窗口通过，学习两臂预测门失败。六次离线求解保留可行新候选，其中两次CPU超时候选修复有效；共同启动初态重复，不宣称多工况覆盖。按预定规则停在2秒闭环前，等待讨论，不重训调到获胜。114个证据文件回传哈希核对通过，无服务器任务遗留进程。Phase9/09-04与no-selection保持。见[v86结果](../docs/phase9_disturbance_v86_report.md)、[执行证据](../docs/evidence/phase9/disturbance-v86-20260929/README.md)。旧负结果及原始材料保留，下方旧日期段落仅作历史。

**当前入口（结果截至2026-09-27，2026-09-28补充中文解释）：** 已完成五种模型的预测比较与单构型诊断。数据校准的物理模型整体最好；限制自由度的学习残差接近物理预测；两种“非线性特征＋矩阵传播”模型尚未合格。同一基础构型换成未参与训练的扫频输入也失败，因此不能只归因于跨构型。六次连续控制优化中一次达到可接受精度、五次超时，新两秒闭环尚未运行。模型中文名称、正则参数λ、论文关系及完整数字见[统一报告与八构型表](../docs/phase9_model_comparison_v84_report.md)。本轮先解释与修正文档，没有新实验；下方旧日期内容为历史证据。

**已完成v82报告（2026-09-26，历史Goal结果）：** 已完成10条2秒真实闭环、18个非等价学习模型及八折留构型预测。uuv4两学习候选相对同MPC辨识物理的综合误差降低11.7%/9.8%；base高3.0%/17.9%，仅部分完整目标改善。已观察局部控制收益，未证明普遍模型优势或未见构型闭环泛化。10条原Linux验收通过，9条本地完整复核，uuv4学习0.001在Windows因果预演未复现、另经原运行时严格重验通过；失败保留。下一步先修求解质量和预演平台分支敏感性，再冻结新任务验证。服务器无本任务遗留进程，可关闭。 [最终报告](../docs/phase9_koopman_mpc_v82_report.md)；[执行范围](../docs/phase9_goal_v80_plan.md)。下方旧日期的运行状态仅为历史。

**当前（2026-09-26）：** 2026-09-26已完成两篇论文与控制/模型/验证三端交叉审核：主线合理；修复短计划广播验收漏洞，新增因果参考独立复核和preview开关。本地/服务器各109项通过。服务器4次真实离线求解均返回可行且通过单决策审核，base/uuv4预演开启预测成本下降57.84%/63.95%，开启臂均达迭代上限且更慢；不是闭环收益。CPU/GPU PWM差异已复现，uuv6旧实际门失败保留。零新物理/拟合；任务已退出、证据回传。先补完整新版采集/轨迹验收及数值余量，再2秒配对；之后另测非等价学习模型。 [报告](../docs/phase9_methodology_crosscheck_2026-09-26.md)。

**以下为此前阶段记录，当前执行入口以上段为准。**

**2026-09-25当前v79本地阶段：** 因果反馈预演、完整备选代价重算、模型身份分离及实际PWM余量检查已实现。36项预演可行，零新NLP/物理/拟合；旧投影与辨识物理等价。新完整提升探针不准入。uuv6实际PWM门存在小幅偏差，服务器恢复后先复核并补新验收，再做2秒控制单因素对照；学习动力学模型另行实现，不混合归因。[v79报告](../docs/phase9_control_model_separation_v79.md)。用户要求先本地，不连接关闭的服务器。

**当前v78已交付：** v78四构型统一设置2秒验证已交付。8个MPC单元中8个完整验收；投影分支1/4个构型的综合误差低于反馈，名义物理分支1/4个。模型冻结、零训练；本轮只作短任务描述性比较，Phase9保持开放。 [v78报告](../docs/phase9_common_profile_v78_report.md)。

**历史v77交付状态（2026-09-24）：** v77有界求解与控制实验已交付。r4首组四构型×两模型8例均完整验收；原repair设置仅base改善0.67%，其他三个构型仍负收益。uuv4提高深度权重并延长时域后，相对反馈改善12.15%，是短任务局部收益，不是统一跨构型或独特Koopman收益证明。模型冻结、零训练，Phase9保持开放。 [v77报告](../docs/phase9_reliable_control_v77_report.md)。

**当前范围（2026-09-24）：** 用户明确授权连续优化、离线归因与小范围匹配闭环；同一MPC换模型，另设反馈对照。控制频率性能后置，模型冻结、零训练。首组base/uuv4/long_body/uuv6，后续四构型与Agent仍条件开放；旧v73不重启、不改写。

# Project State: EASYkoopman

**Updated:** 2026-09-29
**Current focus:** v86扰动预测出现负结果，停在两秒闭环之前讨论。结合较单独Koopman明显改善，但扫频深度劣于冻结物理；未证明可靠轨迹泛化或控制收益。完整数据、冻结模型、超时候选与本地复核已保存；本轮改动尚未提交或推送。
**Active milestone:** `v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control`
**Branch:** `no-selection` (verified at this planning update; recheck before execution)

**Research direction:** User confirmed Koopman-UUV / Agentic-AUV as the main objective; senior advice plus evidence-led agent judgment guide the route. Routine details are delegated. Linear/per-config/persistence remain comparators, not automatic replacement goals.

## Project Reference

See `.planning/PROJECT.md`.

**Core value:** Build control experiments whose model, checkpoint, controller path and evaluation evidence are explicit enough to reproduce, compare and reject safely.

## Current Position

v82旧闭环结果与v84/v85负结果保留，详见[统一报告](../docs/phase9_model_comparison_v84_report.md)。当前讨论与下一项工作以[2026-09-29交接](checkpoints/phase9-lifted-generalization-handoff-2026-09-29.md)为准，未新增2秒闭环。

## Milestone Goal

Qualify the eight supported EasyUUV 2.0 configurations, establish a topology-independent Koopman control/data contract, then evaluate cross-configuration transfer, guarded environment adaptation and a bounded Agent Supervisor.

## Inherited v1.0 Baseline

v1.0 remains frozen at tag `v1.0`, covering Phase 1 through Phase 5.4. Its accepted closeout records are:

- `.planning/reports/MILESTONE_SUMMARY-v1.0.md`
- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- `.planning/MILESTONES.md`
- `.planning/RETROSPECTIVE.md`

Verified at v1.0 close:

```text
python -m pytest -q --basetemp .pytest-milestone-v1
175 passed

python -m compileall __init__.py easyuuv_env.py koopman workflows tests
passed
```

Server evidence accumulated during v1.0 includes:

- Isaac Sim 5.0 + Isaac Lab 2.2.1 direct-controller rollout;
- validated step/sine/irregular Koopman logs;
- Phase 2.5 direct-state model gate pass;
- Phase 3 bounded Koopman-MPC smoke;
- controller-only three-backend matched evaluation;
- Koopman-MPC-conditioned PPO checkpoint smoke;
- Phase 5.1 stable-training candidate;
- Phase 5.2 one-factor, Phase 5.3 cross-combination and Phase 5.4 Pareto experiments.

Frozen conclusions carried into v2.0:

- The single-configuration end-to-end control/retraining/evaluation chain runs.
- `direct_state` is the engineering Koopman backend for v1.0.
- `paper_lifted_edmd` is a research comparison and is not the default controller.
- Legacy/S-Surface remains the strongest nominal baseline.
- Phase 5.4 completed 11/11 sentinels and 11/11 matched candidates but selected no profile.
- Latency was not the primary Phase 5.4 bottleneck.
- Adapter/reference semantics and `no_cost_improvement` fallback are stronger hypotheses than further broad reward/MPC micro-tuning.
- No online Koopman learning or LLM runtime is present.

## Locked v2.0 Decisions

| Decision | State |
|---|---|
| Phase numbering | Continue at Phase 6; do not restore Phase 5.5/5.6. |
| New simulator source | Import `easyuuv_v2-main/` as an isolated received snapshot before integration changes. |
| Supported configurations | `base`, `long_body`, `heavy_moderate`, `asymmetric`, `uuv6`, `uuv6_angled`, `uuv4`, `uuv4_angled`. |
| Cross-configuration control | `virtual_control_4 = [roll, pitch, yaw, depth]` before TAM allocation. |
| Underactuation | `uuv4*` yaw is explicitly unavailable and excluded from feasible yaw tracking. |
| Online adaptation | RLS/KF only behind bounds, non-finite rejection, frozen prior and rollback. |
| Agent boundary | Low-frequency allow-listed supervisor; no direct PWM or real-time `env.step()` loop. |
| Evidence | Local contract tests and server Isaac evidence remain separate and level-labelled. |
| Promotion | `no_selection` is a valid outcome when no candidate passes every gate. |
| Phase 8.1 D-23 | Approved only for role `083d5eae...9417`, analysis `7a790b43...e18c` and experiment `phase8.1-main-identification-v1`; identity assurance remains none. |
| Phase 8.2 isolation | Server collection, pullback, formal LOCO and closeout live only in `source/results/koopman_phase8_2`, never in frozen Phase 8/8.1 result roots. |
| Phase 8.2 terminal | `NO_SELECTION` with `VERIFIED` closeout; fresh-root isolation and freeze semantics enforced; evidence roots immutable. |

## Git Delivery Boundaries

1. New EasyUUV 2.0 simulator snapshot.
2. v1.0 server experiment evidence plus an explicit manifest.
3. v2.0 PROJECT, REQUIREMENTS, ROADMAP, STATE, Phase 6 SPEC/PLAN and supporting design documents.

All three boundaries are visible on `origin/v2.0-multi-configuration`: simulator snapshot `7ba2499`, v1 evidence `7147379`, and planning head `c8b9c70`. Phase execution commits remain later local commits; no remote force-push was used.

## Planning Result

Historical planning setup (superseded by Current focus): [advice analysis](../docs/phase8_3_senior_advice_analysis.md), [8.3 context](phases/08.3-control-identification-forensics/08.3-CONTEXT.md) and three serial plans are ready for future execution; [8.4 context](phases/08.4-conditional-identification-experiment/08.4-CONTEXT.md) is conditional. No new evidence or scientific requirement has been marked complete. KIDO-02..05 labels were corrected from existing8.2 verification. The following bullets are a chronological historical record; older pending/absent-artifact statements describe their time of writing, not current status.

- Phase 6 SPEC ambiguity gate passed at `0.08` with QUAL-01..08 locked.
- Research and pattern mapping are complete.
- Four execution plans cover 8/8 QUAL requirements and 14/14 locked D-ID decisions.
- Wave 1 establishes package/provenance; Wave 2 runs catalog and validator TDD in parallel; Wave 3 blocks on actual eight-configuration Isaac evidence.
- Plan 06-01 completed with canonical `easyuuv_nc` packaging, package-confined USD lookup, a local `.venv` workflow and 21 passing package/v1 source-contract tests.
- Plan 06-02 completed with one exact eight-name catalog, an Isaac-free 8/6/4-thruster TAM report, explicit `uuv4*` yaw underactuation and snapshot-backed zero-drift proof.
- Plan 06-03 completed with a strict versioned artifact schema, exact-set/topology/safety/evidence gates and a deterministic CLI; independent audit added fixed-baseline, strict-mask-type and ordered-extrema gates, bringing the mutation suite to 55 passes.
- Plan 06-04 completed the deterministic Isaac runner, exact-eight merger, offline bundle/bootstrap, semantic process/log/row gates, strict provenance validator and staged pullback chain.
- The tested source commit `e24f76a` ran on the isolated server path `/root/EASYkoopman-phase6-v2`; `base` completed 64 steps and the other seven public configurations completed 8 steps each.
- The actual Isaac Sim 5.0 / Isaac Lab 2.2.1 artifact passed as `server_isaac_smoke` with 8/8 configurations, zero non-finite values, zero dimension mismatches and SHA-256 `6cb83fcb63fc7bd33ffcfa678d09f3e128fcf6f6380ee3b948541814421a1a92`.
- The 64-file server evidence package is isolated in commit `7670f66`; Phase 6 SUMMARY, SERVER-EVIDENCE and VERIFICATION provide the planning handoff.
- Phase 6 qualifies simulator/configuration behavior only. Koopman transfer, MPC integration, environment adaptation and Agent effectiveness remain Phase 7–12 work.
- Phase 7 SPEC ambiguity is `0.14`; it locks schema v2 field semantics, additive v1 isolation, actual post-actuator wrench, oracle/estimated context separation and a three-topology server completion gate.
- Phase 7 research and pattern mapping identify the exact control/dynamics capture points: explicit catalog-derived yaw mask before TAM, actual thruster wrench before environmental forces, and same-step fluid/efficiency caches.
- Four plans cover CONT-01..05 and D-01..16 with dependency graph `07-01 -> {07-02,07-03} -> 07-04`.
- Independent plan checking converged from five blocking findings to zero remaining issues. It corrected the per-episode fixture boundary, real Phase 6 script path, aggregate validator, executable full local preflight and resolved research questions.
- Phase 7 planning does not mark any CONT requirement complete and does not create or claim server evidence. Existing v1 `U=PWM_8` model/MPC defaults remain frozen.
- Plan 07-01 completed strict schema v2 transition/context validation, contiguous episode JSONL/manifest/hash and a pure-Python validator CLI through two explicit RED→GREEN cycles (`aba86e6`→`0bb631c`, `788f451`→`89491fa`).
- Independent Wave 1 rerun passed 179 tests with `.pytest-tmp/phase7-wave1-root`; the first unisolated rerun exposed only a Windows `%TEMP%` permission error before project code, which the planned repository-local basetemp resolved.
- Plan 07-02 added catalog-masked post-PID/pre-TAM virtual control, post-actuator thruster-only wrench, same-call fluid/efficiency telemetry and a one-step/one-token strict Bridge; independent serial rerun passed 208 tests and both mandatory key links.
- Plan 07-03 added immutable `U=virtual_control_4` DatasetV2 plus named diagnostics and a non-promoting v1 compatibility view; independent rerun passed 123 tests while frozen v1 model/MPC defaults remained 8D.
- Plan 07-04 added the exact-three collector/merger/validator, full local preflight, offline bundle/bootstrap and staged pullback chain; final pre-transfer gates passed 222 Phase 7 tests and 559 full-suite tests with one Windows-only symlink skip.
- Tested source `a36689a` ran on the unchanged Isaac server in isolated `/root/EASYkoopman-phase7-v2`; `base`, `uuv6` and `uuv4` each produced 8 contiguous strict schema-v2 transitions.
- All three native/tee/semantic gates passed. `uuv4` recorded two nonzero raw-yaw probes and zero virtual-yaw leaks, confirming the catalog mask before TAM in the real runtime chain.
- The aggregate passed server and pullback validators with `warnings=[]`, source/runtime provenance matched, SHA-256 `2f07a6835f0b32fe0277fd819394580f261b6028dc3d07520e70b124e0758463`, and all 44 server-authored files passed the self-excluding relative-path inventory validator on server and pullback.
- Server evidence is isolated in commit `1c0a6ca`; `07-SERVER-EVIDENCE.md`, `07-04-SUMMARY.md` and `07-VERIFICATION.md` close CONT-01..05 without claiming Koopman prediction, OOD transfer or MPC effectiveness.
- Phase 8 SPEC now distinguishes persistence/simple-linear baselines, per-configuration/pooled/conditional regimes and the non-promoting expert role; its ambiguity score is `0.10`.
- An independent contract audit corrected transductive pilot leakage: pilot is collection-health-only, while every model-affecting decision is pre-registered or fold-local over exactly seven source configurations.
- Five plans cover KID-01..05 and D-01..23 in dependency order `08-01 -> 08-02 -> 08-03 -> 08-04 -> 08-05`, with one explicit D-23 user protocol approval before main-server collection.
- Phase 8 evidence uses external `qualification_level` envelopes without extending or relabelling the frozen Phase 7 transition `evidence_level` enum.
- Evaluation and terminal selection/no-selection use separate immutable roots; a selected final refit reruns the registered inner algorithm on all eight fit+validation roles only, while refit failure atomically yields `no_selection` with no model path.
- The approved plan set initially marked no KID requirement complete and created no success artifact. Phase 8 will close only after an independent goal-backward `08-VERIFICATION.md` passes KID-01..05.
- Plan 08-01 completed the additive Phase 8 evidence/protocol layer and fail-closed local/server/pullback chain without changing the frozen Phase 7 transition evidence enum.
- Real Isaac Sim 5.0 / Isaac Lab 2.2.1 pilot evidence contains exactly eight configurations, two episodes per configuration and 128 transitions per episode: 16 episodes, 16 manifests, 16 logs and 2048 strict rows.
- The pulled envelope passed both operational-policy and external-evidence validators with `warnings=[]`; resumed closeout passed 53 Phase 8 server-contract tests and the full suite as `638 passed, 1 skipped`.
- This is collection-health evidence only. KID-01..05, model quality, LOCO OOD transfer, selection and Koopman-MPC effectiveness remain unproven.
- Plan 08-02 added a local-contract-only immutable multi-episode inventory, exactly eight seven-source LOCO fold manifests, distinct non-promoting expert views and dynamic opened-byte leakage audits.
- Physical conditioning is identity-free and fold-local: each normalizer binds the exact seven source configurations, source episode hashes and feature schema hash; no global or held-out statistics are accepted.
- Independent closeout passed 55 focused tests, 210 Phase 8/schema/pilot tests and the full repository suite as `675 passed, 1 skipped`; both declared key links and protected paths passed.
- The 8x12 main role protocol remains `pending_d23`. No real main dataset or fitted model exists, so KID-01..05 remain incomplete.
- Plan 08-03 added one additive `ControlledEDMDV2` backend, state_11/control_4 persistence and simple-linear baselines, exact identity/kinematic observable schemas and fold-fitted platform-affine Kronecker conditioning.
- Recursive evaluation is episode-local at one-step/5/20/60/full horizons; official attitude is sign-invariant normalized SO(3) geodesic radians, with per-configuration, equal-macro and worst-configuration aggregates.
- Every synthetic fold decision evaluates the frozen 108-candidate local grid from exactly seven source configurations, records every opened episode/statistic and seals before held-out test access; only pooled/conditional result types are eligible.
- Independent closeout passed 396 broad tests plus one existing skip and the final full suite as `733 passed, 1 skipped`; compileall, standalone diff-check, key links, protected paths and forbidden-root absence passed.
- Plan 08-03 is `local_contract` only. Its policy fixture is not D-23 approval, no real main/evaluation/selection root exists and KID-01..05 remain incomplete.
- Plan 08-04 froze the explicitly approved D-23 role/action and analysis-policy hashes, then ran the exact protocol from tested source `a7e8198` in isolated `/root/EASYkoopman-phase8-main-v2` on the unchanged Isaac server.
- The successful server chain completed 8/8 native, tee and semantic gates and produced exactly 96 episode JSONL, 96 manifests, 96 logs, zero `.part` files and 49,152 transitions: each configuration has six fit, three validation and three test episodes of 512 transitions.
- The post-collection inventory, exact-eight LOCO split and external envelope were built only after the exact set completed. Server and local validators returned `phase8_external_evidence_valid`, 293 referenced files and `warnings=[]`; envelope SHA-256 is `46d02531457123f2a1dfda3b16159b359a6caff2d90b14283094a349647a1b04`.
- Random-staging pullback validated all 294 canonical files, exact protocol/source/runtime hashes and all process statuses before atomic promotion. Evidence is isolated in commit `98dbd76`, and Git text conversion is disabled only for that immutable dataset subtree.
- Three failed server attempts were preserved and never promoted or appended: missing non-interactive Conda activation, native 178-step timeout, and postprocessing hash contamination. The successful attempt used a fresh bundle/checkout/result root and completed with `bootstrap.exit=0`.
- Plan 08-04 proves exact-eight dataset and LOCO-split readiness only. No model has been fitted or selected and no held-out prediction, OOD transfer, MPC, environment-adaptation or Agentic claim is supported. KID-01 data and KID-02/03/05 prerequisites are ready, but formal KID completion remains pending 08-05 and independent verification.
- Plan 08-05 completed all eight source-only LOCO folds. Every primary candidate/model was frozen before held-out access with zero test opens at freeze and zero post-test mutations; the evaluation envelope validates 106 referenced files with `warnings=[]`.
- Pooled Koopman was identical to simple linear and failed the frozen improvement/bootstrap gates. Conditional Koopman was ineligible after reason-coded quaternion-projection failures on `heavy_moderate`, `uuv4` and `uuv4_angled`.
- The atomic terminal envelope is a pathless `no_selection`; it validates with `warnings=[]`. Independent verification reran the canonical envelopes, structural audit and 64 relevant tests, then passed KID-01..05 as `PASS_VALID_FROZEN_NO_SELECTION`.
- Phase 8 is scientifically complete but no Phase 9 handoff model exists. This result supports held-out prediction evaluation and rejection only, not Koopman-MPC, environment transfer, Agentic, Sim2Real or hardware claims.
- Phase 8.1 completed its four local-only repair plans: corrected first-substep thruster dynamics, added isolated schema/model/evaluation v2.1, implemented fail-closed formal entrypoints and produced two pending-D-23 protocol proposals. The historical pre-approval review remains preserved.
- Phase 8.1 local validation passed 214 targeted tests and 435 relevant simulator/embodiment/runtime/v2 compatibility regressions. A later scoped semantic fix passed 5 targeted tests and 201 relevant regressions at source commit `5fd7a995e2fc1abfcc85b8921ab98096dafc3ee7`.
- The user approved the exact Phase 8.1 role hash `083d5eae3729e9939287345ab258dbfe4b4c8ca71ab769c2fd8616431a649417` and analysis hash `7a790b43d0f1581b8995ccdcbd9b6d259cb09bc8fe2268201400243d05f1e18c`. `protocols/phase8_1/d23_approval.json` machine-validates this decision binding and explicitly provides no human identity authentication.
- Phase 8.2 now owns a separate four-plan chain: local preflight/bundle, fresh server collection/pullback, formal eight-fold LOCO/outer decision and independent closeout. Its new operational contract tests pass locally, but no server or formal evidence has been created.
- Plan 08.2-01 completed the versioned preflight, bundle/bootstrap/collection/pullback/formal/closeout scripts and runbook. The checked-in preflight passed canonical approval, 32 targeted tests, 200 relevant regressions, compileall, script parsing, protected-history, clean-tree and absent-root gates; bundle verify plus isolated offline clone passed before any SSH.
- The first Plan 08.2-02 `v1` server bootstrap cloned the verified source but stopped before collection because the bootstrap reassigned its own readonly `RESULT_ROOT` variable. No episode, model, held-out test or formal result was created. The failed `/root/EASYkoopman-phase8-2-v1` attempt is preserved; the scoped repair uses fresh `v2` checkout/result roots and has 15 passing operational contract tests.
- Plan 08.2-02 collected the fresh v2.1 exact-eight dataset on the unchanged Isaac server from tested source `4f3b4cb` in isolated `/root/EASYkoopman-phase8-2-v2` (checkout) and `/root/EASYkoopman-phase8-2-results-v2` (results): 8 configurations x 12 episodes, 96 JSONL/manifest/log triplets, zero `.part`, 49,152 strict transitions. The operational `v1` failure (readonly variable reassignment before collection) is preserved and never promoted. Staged pullback validated all gates before atomic promotion of `dataset/` and `collection_status/`.
- Plan 08.2-03 executed the frozen formal eight-fold LOCO as eight independent Python processes with per-fold pre-test freeze and atomic publication, then assembled canonical `evaluation/` and published the terminal `NO_SELECTION` envelope through the checked-in formal chain; all eight folds succeeded. Pooled Koopman remained numerically identical to simple linear (24/24 evaluations) and both comprehensively lost to the persistence baseline; conditional Koopman failed closed 8/8 with reason `source_candidate_unavailable`. The terminal artifact is pathless; final refit was not invoked. Evaluation and selection evidence is isolated in commit `ce622c0`.
- Plan 08.2-04 independently revalidated canonical D-23, the dataset/evaluation/selection envelopes, the exact eight-fold set, zero leakage/freeze evidence and the exact evidence/claim boundary, producing `source/results/koopman_phase8_2/closeout/` with status `VERIFIED`, `terminal_decision=NO_SELECTION`, `model_handoff=false` and `fold_count=8`. Closeout gate alignment is isolated in commit `384caf1` and closeout evidence in `ab3c867`.

## Next Action

Read [v38本地就绪报告](../docs/phase8_4_v38_tolerance_repair.md) and [正式运行手册](../docs/phase8_4_projected_formal_v38_runbook.md). 本地任务1已完成；提请一次绑定freeze85fda36f…e9b6d7的新D-23。批准且服务器开启后，只运行新v38 preflight→validation→独立复核/GO→test；不重跑已冻结实验，不复用旧test，不重新拟合。当前无新正式批准、数据或Phase9 handoff。

````

## docs/phase9_control_chain_contract.md

原文件字节 SHA256：`cbce9bb1ad1940713a87a0cde9702ec42c18c5083d12db09e382e19538014615`。原文如下（代码块分隔符之外的换行不属于原文件）：

````text
# 当前控制链路、参考量与控制效果

**2026-09-29当前路线：** 下一步仅做加扰动、物理与Koopman结合。物理基线冻结，不学习新增扰动数据、不重新校准。以下数值和既有协议保留为历史证据；与此冲突的旧下一步建议已被替代。当前执行入口见[STATE](../.planning/STATE.md)。

**2026-09-27规划补充：** [线性/非线性多模型比较计划](phase9_model_comparison_v84_plan.md)区分非线性plant、提升空间线性传播和MPC优化形式。下一步拟保留共同执行器，先比较主体预测，再比较控制架构；尚未实施，以下v80/v82仍是当前实际接口。

## 当前接口：v80/v82（2026-09-26）

当前结果入口是 [Koopman-MPC有效性与泛化报告](phase9_koopman_mpc_v82_report.md)，已完成同设置2秒配对。下方v78记录保留为历史，不代表新模型仍与物理等价。

**区别在MPC内部的预测模型；实际受控机器人、观测、推进器和验证规则保持一致。** 共用深度/姿态目标、当前11维状态（高度、四元数、机体线速度和角速度）、从历史实际指令重建的转速与时钟、机械参数。当前状态由仿真器提供，Koopman是预测器，不是感知器。

| 当前控制臂 | 预测或决策 | 接入点 |
|---|---|---|
| `feedback` | PD误差反馈＋已知物理补偿＋受限静态推力逆解 | 四维TAM前指令 |
| `identified_physics` / `matched_physics` | 同数据辨识D/Q物理动力学 → 连续序列MPC | 同上 |
| `learned_velocity` | 53特征的自由六维速度读出＋共同解析位置/姿态投影 → 相同MPC | 同上 |

三者随后都经过原TAM分配、PWM、死区、转速滞后和Isaac刚体。控制每1/30秒更新，物理步长1/120秒；MPC预测20个控制区间，只执行首个指令并保持4个物理子步。当前是同步非实时实验，不是30Hz实时运行。首个控制区间仍为共同反馈启动，随后59次才进行MPC决策。

参考是直接给定高度5.5m和俯仰0.04rad的任务，未读取真实未来状态。因果反馈预演在各自预测的未来状态上递推反馈，作为连续优化的初值及可行参照。旧的固定方向搜索已不作为当前算法主线。

新学习矩阵由对应fit数据训练，在父进程精确检查器和CasADi优化进程中独立加载同一文件身份；不同于旧D/Q等价模型。两固定正则候选都保留，效果依据实际轨迹、模型配对和独立验收，不能只凭预测代价或求解成功认定收益。

架构边界与53维字典复核见[补充审核](phase9_architecture_v83_review.md)：当前逐步重提升＋非线性姿态更新，不是完整自主线性提升传播。

## 历史接口：v77/v78

2026-09-24。本文解释已经执行的 v77/v78 控制端。实验结果以[四构型2秒报告](phase9_common_profile_v78_report.md)及其原始证据为准；本文不改变冻结控制代码、模型或实验数据。

**目前比较的是：物理补偿反馈、投影模型 MPC、名义物理模型 MPC。三者共用实际推进器与仿真物理；后两者共用连续序列优化器。当前投影模型的控制读出与同辨识参数的物理模型等价，尚不能证明独特 Koopman 表示收益。**

## 1. 三条链路分别怎么控制

共同入口：任务目标 r + 当前状态 x + 已确认执行的上一控制量；MPC 另外使用因果执行器记忆与构型参数。

| 方法 | 控制量生成过程 | 向机器人发什么 |
|---|---|---|
| 反馈基线 `feedback` | 当前高度/姿态误差 → PD 期望加速度 → 重力、浮力、恢复力矩补偿 → 静态推进映射求逆 → 指令变化率与支持域限制 | 当前一个四维 pre-TAM 命令 |
| 投影模型 MPC `projected_koopman` | 当前状态 → 投影模型预演未来状态 → 同一个连续优化器联合优化未来各步控制 → 精确可行性复核与计划选择 | 选中序列的第一个四维命令 |
| 名义物理 MPC `nominal_physics` | 当前状态 → 名义物理方程预演未来状态 → 同一个连续优化器联合优化未来各步控制 → 同样的复核与选择 | 选中序列的第一个四维命令 |

后两条都用反馈生成启动命令与内部参照。第一控制区间由共同启动反馈发出，其后 59 次决策才调用 MPC；不能把 60 次全部写成优化器输出。

共同下游链路：

```text
四维命令 [roll, pitch, yaw, heave]
 → 构型可控轴掩码
 → 构型推进器分配 / 原 base 混控
 → 每个推进器的归一化 PWM
 → PWM 死区及转速映射
 → 有记忆的推进器动态
 → 推力 / 力矩 + 水动力、浮力、重力
 → Isaac 刚体运动
 → 读取新状态，进入下一控制区间
```

四维命令是归一化虚拟控制通道，**不是四个角度、也不是直接带 N/N·m 单位的四维力矩**；物理作用通过分配、推进器曲线和动态产生。PD 中间计算的六维 `target_wrench` 才是物理力/力矩目标。

接入点是 `direct_pre_tam_v24`：在推进器分配之前接入。虽然环境仍经过名为 `_pid_control` 的函数，这个模式会立即转入 `direct_pwm`，不再运行原级联 PID 控制律。三臂保留下游同一 plant；当前任务目标由实验直接给定，没有 PPO/Agent 参与在线决策。

执行时每个命令保持 4 个 120Hz 物理子步，模拟时间控制频率为 30Hz。MPC 求解期间仿真暂停，当前不是实时 30Hz 系统。

## 2. Koopman 怎么“感知”

**模型不负责感知；它接收状态，再预测给定控制会造成的运动。** 当前状态直接读自 Isaac 机器人数据，不是由 Koopman 从图像估计，也没有验证真实传感器或状态估计器。

| 输入 | 当前来源与意义 |
|---|---|
| 11维状态 x | 世界坐标 z、四元数 wxyz、机体坐标线速度3维、角速度3维 |
| 目标 r | 实验给定的 z 目标与目标四元数，共5维 |
| 构型信息 | 已知且与运行时核对的质量、惯量、浮心、排水体积、水动力参数，以及构型分配与可控轴 |
| 执行器记忆 | 从已验证的零转速初始化出发，仅用确认实际发出的命令递推；预测分支各自复制记忆 |

推进器真实转速在 trace 中另行记录，用于初始化和执行核验；控制预测的记忆不是每步用未来真实转速覆盖。未执行的预测命令不能写回实际历史。

这里通常称“深度”的第一个状态实际是 `root_pos_w[...,2]`（世界 z）。目标 5.5m 是该坐标值，不能直接解释成“水面下5.5m”。水平位置没有进入11维跟踪状态，但有独立水平位移安全检查。

将来上实机需要用深度/姿态/速度测量与状态估计填充同一接口，并处理噪声、延迟、坐标变换和未知执行器初态；这些尚未由当前仿真证明。

## 3. 模型预测什么，MPC 优化什么

MPC 的决策是未来20个控制区间的连续控制序列 U，时域约0.667秒；每一步联合优化全部可控轴。uuv4 不优化不可控偏航。它不是从预先猜好的几个方向中选一个，也不是 Koopman 直接输出动作。

预演每一步依次计算：命令分配 → 推进器状态 → 六维驱动加速度 → 模型预测新速度/姿态/z。连续优化使用 CasADi/IPOPT；最终序列还经过原 float32 分配、执行器递推及状态预测链复核。支持域、输入范围、变化率、PWM 余量/死区距离、速度和姿态等约束仍生效。没有找到可行解不能等价为“系统没有解”；当前局部求解不保证全局最优。

优化代价包含高度、姿态、垂直速度、角速度、控制力度、控制变化与末端误差。本轮深度权重4、姿态权重1；控制代价以零命令为参照，没有单独的 `||u-u_ref||²` 反馈模仿项。反馈序列是初值/可行参照，不是必须模仿的标签。每次只执行选中计划的第一步，再读取新状态重新求解。

投影分支的具体实现不能省略：

1. 从状态和已知物理量构造提升特征，包括旋转、速度、阻力、浮力、恢复力矩与陀螺项。
2. 用冻结矩阵的速度列 `matrix[:,10:16]` 预测速度，再通过几何积分更新姿态和 z；每个物理步从预测状态重新计算特征。
3. 拟合文件保留了完整提升矩阵，但上述速度列被限定为带辨识 D/Q 参数的物理结构。当前控制路径并不使用其余自由拟合列独立传播完整提升状态。
4. 因而该读出与同 D/Q 参数的 `identified_physics` 方程等价；实际对照臂 `nominal_physics` 使用 D=0、Q=1，其余已知构型信息保持一致。

因此当前准确名称是“结构化投影模型 MPC”。要归因于 Koopman 表示，须审清真正学习的提升动力学如何参与预测，并与使用同样数据辨识的物理模型比较；不能仅凭代码里的 `projected_koopman` 名字下结论。

## 4. 有哪些参考量，是不是物理算出来的

| 名称 | 从哪里来 | 起什么作用 |
|---|---|---|
| 目标状态 r | 实验人为设定；本轮保持 z=5.5，俯仰目标0.04rad（约2.29°） | 定义任务，不由物理模型生成 |
| 物理力/力矩目标 | 当前误差 → PD → 已知质量/惯量/浮力/浮心补偿 | 指明此时希望产生的物理作用 |
| 反馈命令 u_fb | 用静态分配与推进器模型求逆，再按支持域和变化率限制 | 反馈臂实际动作；MPC 启动、内部参照的来源 |
| 静态目标命令 `static_command` | 上述物理逆映射，尚未做当前步变化率限制 | 必要时生成跨出 PWM 死区的连续爬升初值；仍需精确验收 |
| MPC 内部参照 U_hold | 把当前 u_fb 重复20步；反馈特定搜索失败时可改为保持上一实际命令 | 初值和经过检查的可行参照，不是未来反馈闭环轨迹 |
| MPC 输出 U* | 连续优化，再与精确可行的保持序列/因果平移旧计划比较预测代价 | 执行首步；可能保留参照而没有优化收益 |

反馈的高度环为 `a_z = clip(1*(z_ref-z) - 2*v_world_z, ±1)`。姿态环用四元数误差（uuv4 使用可控倾角误差），比例增益9、角速度阻尼增益6，角加速度限幅16。再用重力/浮力与浮心恢复力矩补偿形成目标 wrench；没有积分项，也不声称消除所有阻力/陀螺效应。求逆残差未达到目标但命令满足执行约束时会明确记录 `tracking_limited`。

所以“有物理算出来的参考控制量”是对的；“目标姿态由物理算出来”或“MPC直接照抄物理控制量”都不准确。没有事先已知的最优动作真值。真实反馈轨迹只是独立运行后的比较基线，不作为本轮 MPC 未来动作答案输入。

**当前已确认的比较缺口：真实反馈每一步会随新状态重新算命令，内部 U_hold 却保持当前命令。优于 U_hold 的预测代价，不保证优于真实反馈的完整闭环。** 后续因果反馈预演应在模型预测的未来状态上重新计算反馈，不能偷用真实未来轨迹；这是待实施验证项，不是 v78 已具备能力。

## 5. 控制效果目前能说什么

四构型共同设置、每例2秒。以下为相对同构型反馈的综合跟踪误差降低比例，正值改善、负值变差。

| 构型 | 投影模型 MPC | 名义物理 MPC |
|---|---:|---:|
| base | -12.17% | -8.14% |
| uuv4 | +12.15% | +10.61% |
| long_body | -2.94% | -3.54% |
| uuv6 | -3.24% | -2.16% |

指标是240个实际物理子步的 `mean[(z误差/0.02m)^2 + (姿态误差/0.04rad)^2]`。uuv4 使用可控倾角，其他构型使用完整四元数角度；只作同构型配对比较。首步共同反馈也计入实际任务。当前 uuv4 的投影分支比名义物理 MPC 再低约1.72%，但这不能区分参数辨识与独特表示收益。

8/8 MPC 单元完整验收代表链路、约束和执行检查通过；只有 uuv4 在此共同设置下优于反馈。其余负结果保留，不能以“已通过”替代效果结论。求解中位数约7.6–21.8秒，当前仅证明非实时仿真的短任务结果。尚无长时稳定、统计显著收益、未知构型泛化、自适应或 Agent 收益结论。

## 6. 代码对应与下一步

| 内容 | 实现入口 |
|---|---|
| 三臂构建、任务目标与时钟 | [collect_reliable_v77.py](../workflows/collect_reliable_v77.py)、[v78采集入口](../workflows/collect_reliable_v78.py)、[protocol_v77.py](../workflows/protocol_v77.py) |
| 状态来源、物理执行桥 | [koopman_logging.py](../workflows/koopman_logging.py)、[isaac_execution_v67.py](../workflows/isaac_execution_v67.py) |
| PD和物理目标、受限逆映射 | [bounded_feedback_v46.py](../koopman/bounded_feedback_v46.py)、[inexact_tracking_v66.py](../koopman/inexact_tracking_v66.py) |
| 内部保持参照、首步执行 | [reliable_runtime_v77.py](../koopman/reliable_runtime_v77.py) |
| 连续优化、计划选择和独立复核 | [continuous_mpc_v76.py](../koopman/continuous_mpc_v76.py)、[reliable_mpc_v77.py](../koopman/reliable_mpc_v77.py) |
| 两种预测器与结构化拟合 | [prepared_projected_v40.py](../koopman/prepared_projected_v40.py)、[physical_control_v76.py](../koopman/physical_control_v76.py)、[identify_sparse_world_v30.py](../workflows/identify_sparse_world_v30.py) |
| 因果执行器记忆、30Hz命令保持、TAM前接入 | [command_state_v39.py](../koopman/command_state_v39.py)、[rate30_v67.py](../koopman/rate30_v67.py)、[control_v67.py](../easyuuv_nc/control_v67.py) |

顺序：先据此固定三臂接口和比较口径；保持现有模型、权重、时域，验证因果反馈预演初值与参照是否改善2秒闭环，并保住 uuv4 正例；随后再做学习提升动力学与同数据辨识物理模型的归因对照。控制收益与 Koopman 表示收益分别验收，再扩展构型和时长。

````

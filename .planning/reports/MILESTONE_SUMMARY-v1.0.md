# Milestone v1.0 - Koopman-UUV Single-Configuration Control

**状态：** 已关闭，作为单构型研究基线保留
**周期：** 2026-06-10 至 2026-08-09
**生成日期：** 2026-08-09
**用途：** 项目回顾、团队交接和后续多构型 AUV 工作的事实基线

---

## 1. 项目概览

v1.0 的目标是在不重写 EasyUUV 推进器、水动力和 Isaac Lab 环境的前提下，把原有单构型 UUV 扩展成一条可采集数据、可训练模型、可闭环控制、可训练 PPO、可做匹配评估的 Koopman-UUV 研究链路。

最终形成的主链路为：

```text
Isaac trajectory / goal
  -> observation_9d
  -> RSL-RL PPO policy
  -> action_4d
  -> heuristic_reference_delta_v0
  -> reference_5d
  -> direct_state Koopman model + bounded MPC
  -> PWM_8d
  -> EasyUUV thruster and hydrodynamics
  -> next simulation state
```

这个里程碑完成的是“单构型 UUV 上可运行、可追溯的 Koopman-MPC-PPO 实验系统”，不是最终控制器发布。以下声明不属于 v1.0 的成果：

- Koopman-MPC 全面优于 legacy/S-Surface；
- PPO 已达到最终收敛或可部署；
- paper-style lifted EDMD 已复现论文性能；
- Koopman 已实现在线更新；
- LLM 已进入控制闭环；
- 系统已经适用于多个 AUV 构型或真实硬件。

## 2. 架构与技术决策

### 2.1 保留 EasyUUV 物理层

- **决策：** 保留原有 8 推进器布局、PWM 到推力映射、浮力、阻力和刚体动力学。
- **原因：** v1.0 只替换控制决策层，避免同时改变仿真承载层与控制算法，保留 legacy 回归基线。
- **结果：** legacy 与 Koopman-MPC 可以在同一 `EasyUUVEnv` 内切换，并共享物理后处理。

### 2.2 使用数据合同分离在线仿真与离线学习

- **决策：** 用 JSONL 记录 `state_11d`、`reference_5d`、`action_4d`、`pwm_8d` 和 `next_state_11d`。
- **原因：** Isaac 只负责产生真实仿真转移，Koopman 辨识、模型 sweep 和指标分析可以在不安装 Isaac 的机器上完成。
- **结果：** step、sine、irregular 日志可以被同一数据集、训练和验证工具消费。

### 2.3 用 manifest-first gate 管理 Koopman 模型

- **决策：** MPC 不直接读取任意模型路径，而是读取包含模型类别、维度、采样周期、数据拆分、指标和 gate 状态的 selected manifest。
- **原因：** 防止只在训练日志上表现良好或维度不匹配的模型被直接放入闭环。
- **结果：** `direct_state` 模型通过 Phase 2.5 gate，测试集 `multi_step_rmse@20 = 0.5243264020`，成为工程默认 backend。

### 2.4 保留论文风格 backend 作为对照

- **决策：** 单独实现并评估 `paper_lifted_edmd`，不覆盖工程默认 manifest。
- **原因：** 区分“可运行的工程集成”和“与论文 lifted-space 形式更接近的算法对照”。
- **结果：** paper-style backend 完成离线和 Isaac 对照，但 controller-only depth RMSE 约为 13 至 14，因此没有晋级为默认低层控制器。

### 2.5 MPC 直接优化 8D PWM

- **决策：** 第一版 MPC 使用 Koopman 模型预测状态，并在短 horizon 内直接优化有界 `pwm_8d`。
- **原因：** Phase 2.5 选中模型的控制输入就是 `pwm_8d`，这样避免再引入未经辨识的 4D 到 8D 控制映射。
- **结果：** 形成带 PWM 上下界、增量限制、控制能量、平滑代价、timeout 和 fallback 的 receding-horizon 控制器。

### 2.6 PPO 不直接控制推进器

- **决策：** PPO 保持 `observation_9d -> action_4d`，通过 `heuristic_reference_delta_v0` 把动作解释为姿态/深度参考修正，再交给 Koopman-MPC。
- **原因：** 保持高层策略与低层实时控制边界，同时复用 EasyUUV 的 RSL-RL PPO 实现。
- **结果：** 新 PPO checkpoint 在真实 `env.step(action_4d)` 路径内经过 adapter 和 Koopman-MPC 训练，旧 checkpoint 只作为受限基线。

### 2.7 证据等级和 checkpoint provenance

- **决策：** smoke、稳定训练、matched evaluation 和各阶段候选使用不同 evidence/provenance 标签。
- **原因：** 防止旧 checkpoint、短 smoke 或缺少来源的权重被误写成经过 Koopman-MPC 重训练的性能证据。
- **结果：** 训练摘要、选中 checkpoint、评估日志和参数 profile 可以相互校验。

## 3. 已交付阶段

| 阶段 | 名称 | 功能状态 | 一句话结果 |
|---|---|---|---|
| 1 | Baseline Data and Controller Boundary | 完成 | 建立 legacy 控制边界、PWM cache 和 Koopman JSONL 数据接口。 |
| 1.5 | Isaac Lab 2.x Compatibility | 完成 | 在 Isaac Sim 5.0 + Isaac Lab 2.2.1 上跑通 direct-controller smoke。 |
| 2 | Offline Koopman Identification | 完成 | 实现数据集、lifting、ridge EDMD、模型保存加载与预测评估。 |
| 2.5 | Koopman Model Qualification | 完成 | 完成 log-level split、baseline、模型 sweep、divergence gate 和 selected manifest。 |
| 3 | Koopman-MPC Integration | 完成 | `direct_state + bounded 8D PWM MPC + fallback` 在 Isaac 闭环跑通。 |
| 3.5 | Paper-Style Lifted EDMD | 完成但未晋级 | 建立论文风格 backend 对照，确认其当前深度预测/控制误差不适合作为默认。 |
| 4 | Controller-Only Evaluation | 完成 | legacy、direct-state MPC、paper-lifted MPC 完成 step/sine/irregular 匹配评估。 |
| 4.5 | PPO Reference Adapter | 完成 | 建立 4D PPO action 到 5D Koopman reference 的显式 heuristic adapter。 |
| 4.6 | PPO Checkpoint Evidence Gate | 完成 | 建立 checkpoint 发现、加载、证据等级和 baseline sidecar。 |
| 5 | Koopman-MPC PPO Retraining Smoke | 完成 | 证明 PPO 在 Koopman-MPC transition dynamics 内训练并产生可验证 checkpoint。 |
| 5.1 | PPO Stability Training | 完成 | 完成 50-iteration sentinel、200-iteration candidate 和三轨迹 matched eval。 |
| 5.2 | One-Factor Health Ablation | 完成 | 比较 reward、adapter、MPC 单因素，`reward_v1_only` 为最佳平衡信号但未完全晋级。 |
| 5.3 | Cross-Combination Screening | 完成 | 评估三组 pairwise 交叉和一组 sentinel，最终 `no_selection`。 |
| 5.4 | Dual-Track Pareto Sweep | 完成 | 11/11 sentinel、11/11 candidate 和全 matched eval 完成，最终 `no_selection`。 |

### 3.1 关键实验结果

Phase 2.5 选中工程模型：

```text
model_class = direct_state
control_dim = 8
dt = 0.0166666667 s
test multi_step_rmse@20 = 0.5243264020
gate_status = pass
```

Phase 3 首次闭环 smoke：

```text
backend_used = direct_state
fallback_rate = 0.0
latency_budget_met = true
PWM bounds = respected
```

Phase 5.2 匹配评估均值：

| Profile | Fallback | PWM saturation | Clip | Depth RMSE | Attitude RMSE |
|---|---:|---:|---:|---:|---:|
| `baseline_rerun` | 0.2333 | 0.2293 | 0.0517 | 0.8564 | 0.8135 |
| `reward_v1_only` | 0.1248 | 0.3379 | 0.1393 | 0.9360 | 0.7434 |
| `adapter_soft_v1_only` | 0.1114 | 0.3963 | 0.1088 | 1.0074 | 0.7449 |
| `mpc_health_v1_only` | 0.1524 | 0.3731 | 0.4952 | 2.0573 | 0.7004 |

Phase 5.3 最强但未晋级的交叉信号：

```text
cross_reward_v1_mpc_health:
  fallback = 0.3105
  PWM saturation = 0.1192
  clip = 0.0400
  depth RMSE = 0.7173
  attitude RMSE = 0.7354
```

Phase 5.4 最终结论：

```text
selection_status = no_selection
selected_profile_id = null
sentinels = 11/11
candidates = 11/11
matched trajectories = step + sine + irregular for every candidate
latency mean gate = passed for all formal candidates
latency max gate = passed for all formal candidates
```

这说明当前主要瓶颈不是计算延迟，也不是某一个 reward/MPC 小权重，而更可能是 PPO action 到 reference 的语义桥接以及 `no_cost_improvement` fallback 的形成机制。

## 4. 需求覆盖与审计结论

原 v1 需求共有 40 项，功能层面均有实现或实验结果支撑，并在归档 requirements 中记录最终 outcome。但旧规划没有为所有阶段补齐标准 `VERIFICATION.md` 和 `requirements-completed` frontmatter，因此形式化三源审计不能给出 40/40 全绿。

审计结论为：**带已知缺口关闭（gaps accepted at close）**。

- **功能链路：** 已完成并通过本地测试与多次服务器 Isaac 实验。
- **本地回归：** `175 passed`，`compileall` 通过。
- **正式 phase verification：** 5/14 个阶段目录具有 `VERIFICATION.md`。
- **完整性能晋级：** 未达到；Phase 5.4 明确为 `no_selection`。
- **多构型适用性：** 未验证；v1.0 只覆盖当前 EasyUUV 单构型。

详细审计见 `.planning/milestones/v1.0-MILESTONE-AUDIT.md`。

## 5. 关键决策日志

| ID | 决策 | 结果 |
|---|---|---|
| D-01 | 保留 Isaac Lab `DirectRLEnv`，不改写为 standalone app | 正确，迁移风险被限制在兼容层。 |
| D-02 | 先建立数据 seam，再训练 Koopman 和接入 MPC | 正确，模型与闭环证据可追溯。 |
| D-03 | 用 log-level split，而不是时序样本随机拆分 | 正确，降低同轨迹泄漏。 |
| D-04 | `direct_state` 作为工程 backend，paper-lifted 作为论文对照 | 正确，避免把形式相似误当成控制性能。 |
| D-05 | MPC 优化与模型一致的 8D PWM | 正确，闭环集成得以快速建立。 |
| D-06 | PPO 通过 adapter 输出 reference correction | 可运行但需要后续重审语义，不是无损迁移。 |
| D-07 | PPO 复用 RSL-RL，不重写 PPO 算法 | 正确，把实验重点放在 MDP、reward 和控制链。 |
| D-08 | 每个训练阶段使用 checkpoint provenance gate | 正确，避免旧权重和短 smoke 被错误晋级。 |
| D-09 | Phase 5.4 禁止初始 adapter 混调 | 正确，得到 reward/MPC 小参数不足的可解释结论。 |
| D-10 | LLM 后置且不进入实时 PWM 环 | 继续有效，v1.0 未接入 LLM。 |

## 6. 技术债与延期项

### 6.1 控制与学习

- `heuristic_reference_delta_v0` 是有边界的工程桥，不证明 PPO 原动作语义与 reference delta 等价。
- `no_cost_improvement` fallback 需要记录候选 cost、fallback cost 和 improvement margin 才能定位。
- current `direct_state` 模型是固定离线模型，没有 KF、RLS 或在线 EDMD 更新。
- PPO 只获得稳定训练候选和有限 200-iteration 比较，不构成最终收敛证明。
- legacy/S-Surface 仍是当前最可靠的 nominal controller baseline。

### 6.2 模型与数据

- 训练和评估来自单一 AUV 构型，尚无构型 ID、几何参数、质量/惯量、推力矩阵等条件变量。
- paper-style lifted EDMD 的深度误差很大，原因尚未完成独立辨析。
- raw server artifacts 约 104 MB，保留在本地 `source/results/`，未纳入 v1.0 Git 标签；长期证据仓库需要单独的数据版本策略。

### 6.3 GSD 文档债

- Phase 1、1.5、2、2.5、3.5、5.1、5.2、5.3、5.4 缺少部分标准验证或 summary frontmatter。
- 旧 `REQUIREMENTS.md` 的 checkbox 长期没有随实际执行更新；归档版根据代码、summary、服务器结果补写 outcome，但保留审计警告。
- v1.0 关闭时不创建 v2.0；多构型范围、需求和阶段编号由后续 milestone 单独确认。

## 7. 新成员上手

### 7.1 推荐阅读顺序

1. `docs/Agentic_AUV_project_handover.md`
2. `docs/project_parameters_and_work_summary_2026_07_05.md`
3. `.planning/reports/MILESTONE_SUMMARY-v1.0.md`
4. `.planning/milestones/v1.0-ROADMAP.md`
5. `.planning/milestones/v1.0-REQUIREMENTS.md`
6. `.planning/phases/03-koopman-mpc-controller-integration/03-SUMMARY.md`
7. `.planning/phases/05.4-dual-track-reward-mpc-pareto-optimization/05.4-SUMMARY.md`

### 7.2 关键代码入口

| 路径 | 作用 |
|---|---|
| `easyuuv_env.py` | Isaac 环境、controller switch、reward 和 PPO/MPC 交界。 |
| `koopman/dataset.py` | JSONL 到 Koopman 训练矩阵。 |
| `koopman/model.py`、`koopman/lifted_edmd.py` | 两类 Koopman backend。 |
| `koopman/runtime.py` | manifest-first 模型加载。 |
| `koopman/mpc.py`、`koopman/controller.py` | 有界 MPC 和 fallback 控制。 |
| `koopman/policy_adapter.py` | 4D PPO action 到 5D reference。 |
| `koopman/ppo_training_adapter.py` | adapter 在 RSL-RL rollout 内的接入。 |
| `workflows/play_controller.py` | 不依赖 PPO 的 controller-only rollout。 |
| `workflows/train_ppo_koopman.py` | Koopman-MPC-conditioned PPO 训练入口。 |
| `workflows/play_ppo_koopman.py` | checkpoint/stub 评估和诊断日志。 |

### 7.3 本地验证

```powershell
python -m pytest -q --basetemp .pytest-milestone-v1
python -m compileall __init__.py easyuuv_env.py koopman workflows tests
```

Isaac 相关运行必须在已验证的服务器环境执行：

```text
Isaac Sim 5.0
Isaac Lab 2.2.1
Ubuntu 22.04
Python 3.11
```

## 统计

- **阶段：** 14 个（含 1.5、2.5、3.5、4.5、4.6、5.1 至 5.4）
- **计划：** 14 个 phase plan
- **Git 提交：** 45 个（归档提交前）
- **跟踪文件：** 212 个（归档提交前）
- **累计变更：** 40,887 行新增（归档提交前）
- **Python：** 121 个文件，约 12,741 行
- **时间：** 2026-06-10 至 2026-08-09
- **贡献者：** 770122whrt

---

v1.0 到此关闭。下一里程碑的建议方向是多构型 AUV，但本次归档不创建或预先锁定下一里程碑的需求与 roadmap。

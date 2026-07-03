# Requirements: EASYkoopman

**Defined:** 2026-06-10  
**Core Value:** 在不破坏 EasyUUV 原始仿真基线的前提下，建立一个可验证、可迭代的 Koopman+MPC 控制闭环。

## v1 Requirements

### Baseline And Controller Boundary

- [ ] **BASE-01**: `Ssurface` 和 `PID` legacy 控制路径在重构后保持行为一致。
- [ ] **BASE-02**: 环境配置可以选择 legacy controller 或 Koopman+MPC controller。
- [ ] **BASE-03**: 8D PWM 输出在进入推进器模型前可被记录和验证。
- [ ] **BASE-04**: `play_controller.py` 能作为不依赖 PPO 的控制器闭环验证入口。

### Data Collection

- [ ] **DATA-01**: 数据采集记录当前状态、目标参考、控制输入、PWM、下一步状态和时间步。
- [ ] **DATA-02**: 数据集格式可离线读取，用于 EDMD 训练和 one-step/multi-step prediction 验证。
- [ ] **DATA-03**: 数据采集覆盖 step、sine、irregular 三类轨迹，包含足够激励以辨识姿态/深度动态。

### Isaac Lab 2 Compatibility

- [ ] **COMPAT-01**: 核心环境代码优先支持 Isaac Lab 2.x 的 `isaaclab.*`、`isaaclab_tasks.*`、`isaaclab_rl.*` 命名空间，并在可行处保留 Isaac Lab 1.x `omni.isaac.lab.*` fallback。
- [ ] **COMPAT-02**: 所有需要 Kit/Omniverse 模块的 direct rollout 入口必须先启动 `AppLauncher`，再导入环境、任务注册和 Isaac Lab task utilities。
- [ ] **COMPAT-03**: `EasyUUV-Direct-v1` 的 Gym 注册不能依赖包含连字符的旧 extension module path，必须能从普通 Git clone 目录导入。
- [ ] **COMPAT-04**: 第一阶段服务器验证只要求 direct controller + legacy control + Koopman JSONL 数据链路跑通；PPO train/eval 全链路迁移延后到后续阶段。

### Koopman Identification

- [ ] **KOOP-01**: 定义 EasyUUV 姿态/深度控制的 lifting 函数，包含状态、参考误差、控制量和关键二次项。
- [ ] **KOOP-02**: 实现离线 EDMD 训练，输出可保存、可加载的 Koopman 模型参数。
- [ ] **KOOP-03**: 提供 one-step 和 multi-step 预测误差评估，避免只看闭环表现。

### Koopman Model Quality Gate

- [ ] **QUAL-01**: 训练、验证和测试日志必须可明确分离，模型选择不得只依赖训练集误差。
- [ ] **QUAL-02**: 模型训练必须支持多个 JSONL 日志联合输入，覆盖 step、sine、irregular 轨迹和可选多次初始条件运行。
- [ ] **QUAL-03**: 模型选择必须比较当前 direct-state predictor、paper-style lifted-space EDMD、persistence baseline 和 simple linear baseline。
- [ ] **QUAL-04**: 模型选择必须比较多个 ridge/lifting/normalization 配置，并输出可复现的 sweep metrics summary。
- [ ] **QUAL-05**: 进入 MPC 前必须生成 selected model manifest，记录模型路径、模型类别、训练/验证/测试数据、关键误差、normalizer、dt、维度和是否出现 rollout divergence。
- [ ] **QUAL-06**: 进入 MPC 前必须生成 gate report，明确 pass/fail、baseline 对比、held-out test 指标、divergence 检查和已知限制。

### MPC Control

- [ ] **MPC-01**: MPC 使用 Koopman 模型预测未来状态，并优化姿态/深度跟踪代价。
- [ ] **MPC-02**: MPC 输出受限控制量，最终映射到 `[-1, 1]` 的 8D PWM。
- [ ] **MPC-03**: MPC 包含控制能量和平滑项，避免推进器命令剧烈抖动。
- [ ] **MPC-04**: MPC 求解时间满足第一版 60 Hz 控制预算，若不满足必须降级或缩短预测域。

### Paper-Style Lifted EDMD Backend

- [ ] **PLED-01**: Produce a separate `paper_lifted_edmd` comparison manifest without overwriting the Phase 2.5 `direct_state` selected manifest.
- [ ] **PLED-02**: Use Isaac-generated step, sine and irregular logs, with repeated runs where feasible, to support paper-style backend qualification.
- [ ] **PLED-03**: Evaluate paper-style lifted EDMD on held-out one-step, multi-step and divergence metrics side by side with direct-state.
- [ ] **PLED-04**: Run offline MPC replay for both direct-state and paper-lifted backends with the same horizon, bounds and weights.
- [ ] **PLED-05**: Run repeated Isaac smoke tests for `paper_lifted_edmd` before allowing it into Phase 4 full evaluation.
- [ ] **PLED-06**: Produce a Phase 4 handoff that states whether paper-style lifted EDMD is eligible for three-way comparison or should remain failure analysis.

### Evaluation And Documentation

- [ ] **EVAL-01**: legacy controller 与 Koopman+MPC 在 step、sine、irregular 轨迹上有同格式日志。
- [ ] **EVAL-02**: 评估输出包含姿态误差、深度误差、控制能量、PWM 平滑性和求解耗时。
- [ ] **DOC-01**: 文档说明当前架构、目标架构、阶段计划、运行命令和已知限制。
- [ ] **DOC-02**: 文档明确哪些事实已由代码验证，哪些仍为待确认项。

### PPO/RL Reference Adapter

- [ ] **RL-01**: PPO/RSL-RL policy 必须作为高层 reference 或 correction 生成器接入，不能直接输出或绕过到 8D PWM。
- [ ] **RL-02**: 需要一个可离线测试的 `heuristic_reference_delta_v0` adapter，将当前 PPO 4D action/correction 作为有界 reference delta 转换为 Koopman+MPC 可消费的 5D reference，并明确这不是 PPO 原语义无损迁移声明。
- [ ] **RL-03**: PPO checkpoint 缺失时必须有明确的 stub-policy 或 training-smoke 路径，不能把无 checkpoint 的结果伪装成 PPO inference。
- [ ] **RL-04**: PPO/RL 接入日志必须记录 `ppo_evidence_level`（`stub_only`、`checkpoint_smoke`、`training_entrypoint_only` 或 `retrained_policy_smoke`）、`action_semantics`、`adapter_quat_convention`、`base_reference_goal_match_max_error` 和 `policy_action_clip_rate`，以区分 smoke、训练入口验证与真实性能结论。
- [ ] **MPC-05**: Koopman+MPC 在 PPO 接入后仍必须记录 solver diagnostics、fallback、latency 和 bounded PWM 状态。
- [ ] **EVAL-03**: PPO/RL 接入后的日志必须能与 Phase 4 controller-only baseline 对比，以区分 policy、adapter、MPC 和模型误差来源。

## v2 Requirements

### Online Adaptation And Sim2Real

- **ADAPT-01**: 引入 Kalman 或递推最小二乘在线更新 Koopman 参数。
- **ADAPT-02**: 支持真实传感器日志回放，用于仿真模型和真实数据的偏差分析。
- **ADAPT-03**: 扩展到 6-DOF 或 8D PWM 直接控制。
- **ADAPT-04**: 引入 LLM 低频调参接口，用于调整 MPC 权重或安全边界，而不是直接输出控制。

## Out of Scope

| Feature | Reason |
|---------|--------|
| 原生 Isaac Sim standalone 重写 | 第一阶段以控制器迁移为核心，避免同时改变仿真承载方式 |
| 真实硬件部署 | 需要仿真闭环、日志格式和 Sim2Real 数据接口稳定后再做 |
| 云端 LLM 实时控制 | 实时控制需要确定性和低延迟，LLM 只适合低频分析或调参 |
| 全量 6-DOF MPC 初版 | 维度过高会使数据、辨识和求解同时变难 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BASE-01 | Phase 1 | Pending |
| BASE-02 | Phase 1 | Pending |
| BASE-03 | Phase 1 | Pending |
| BASE-04 | Phase 1 | Pending |
| DATA-01 | Phase 1 | Pending |
| DATA-02 | Phase 1 | Pending |
| DATA-03 | Phase 1 | Pending |
| COMPAT-01 | Phase 1.5 | Pending |
| COMPAT-02 | Phase 1.5 | Pending |
| COMPAT-03 | Phase 1.5 | Pending |
| COMPAT-04 | Phase 1.5 | Pending |
| KOOP-01 | Phase 2 | Pending |
| KOOP-02 | Phase 2 | Pending |
| KOOP-03 | Phase 2 | Pending |
| QUAL-01 | Phase 2.5 | Pending |
| QUAL-02 | Phase 2.5 | Pending |
| QUAL-03 | Phase 2.5 | Pending |
| QUAL-04 | Phase 2.5 | Pending |
| QUAL-05 | Phase 2.5 | Pending |
| QUAL-06 | Phase 2.5 | Pending |
| MPC-01 | Phase 3 | Complete |
| MPC-02 | Phase 3 | Complete |
| MPC-03 | Phase 3 | Complete |
| MPC-04 | Phase 3 | Complete |
| PLED-01 | Phase 3.5 | Pending |
| PLED-02 | Phase 3.5 | Pending |
| PLED-03 | Phase 3.5 | Pending |
| PLED-04 | Phase 3.5 | Pending |
| PLED-05 | Phase 3.5 | Pending |
| PLED-06 | Phase 3.5 | Pending |
| EVAL-01 | Phase 4 | Pending |
| EVAL-02 | Phase 4 | Pending |
| DOC-01 | Phase 4 | Pending |
| DOC-02 | Phase 4 | Pending |
| RL-01 | Phase 4.5 | Pending |
| RL-02 | Phase 4.5 | Pending |
| RL-03 | Phase 4.5 | Pending |
| RL-04 | Phase 4.5 | Pending |
| MPC-05 | Phase 4.5 | Pending |
| EVAL-03 | Phase 4.5 | Pending |

**Coverage:**
- v1 requirements: 40 total
- Mapped to phases: 40
- Unmapped: 0

---
*Requirements defined: 2026-06-10*
*Last updated: 2026-07-03 after Phase 4.5 PPO/RL reference adapter planning*

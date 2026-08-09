# Agentic-AUV v2.0 里程碑设计

**状态：** 方向已批准，等待书面规格审阅

**日期：** 2026-08-09

**分支：** `v2.0-multi-configuration`

**基线：** `v1.0` / `isaaclab2-migration`

## 1. 设计结论

v2.0 将以新版 `easyuuv_v2-main` 为唯一新增仿真环境来源，把现有 EASYkoopman 的单构型研究链扩展为多构型、环境感知和可审计的低频 Agent Supervisor 研究链。

v1.0 已完成归档，Phase 1 至 Phase 5.4 的结论保持冻结。v2.0 不回写、不重新编号，也不把 v1.0 的单构型结果重新解释为多构型证据。

里程碑名称：

```text
v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control
```

## 2. 目标与边界

### 2.1 目标

1. 导入并资格验证新版 EasyUUV 的八种 CLI 支持构型。
2. 建立跨 4、6、8 推进器构型统一的 Koopman 状态、控制和数据合同。
3. 比较单构型、共享和条件化 Koopman 在 held-out 构型上的预测与闭环泛化。
4. 在离线模型基础上加入有回滚和稳定性门的 RLS/KF 在线更新。
5. 构建不直接控制 PWM 的低频 Agent Supervisor，并用无 supervisor、规则 supervisor、agent supervisor 三方消融验证效果。
6. 保持本地实现与服务器 Isaac 验证的职责隔离和证据分级。

### 2.2 非目标

1. 不在 Phase 6 立即训练 PPO、接入 LLM 或宣称 Sim2Real 成功。
2. 不把八种动力学/推进器配置描述为八套独立外观资产；当前仍共用一个 USD 外观。
3. 不使用补零 PWM 作为主要跨构型控制语义。
4. 不允许 PPO、Agent 或 LLM 绕过低层控制器直接发送 PWM。
5. 不把烟雾测试、离线预测、稳定训练或 matched evaluation 混为同一级证据。

## 3. 系统边界

新版 EasyUUV 已经包含两类构型变化：

- 参数型：`base`、`long_body`、`heavy_moderate`、`asymmetric`；
- 执行器拓扑型：`uuv6`、`uuv6_angled`、`uuv4`、`uuv4_angled`。

v2.0 的统一低层控制语义为：

```text
virtual_control_4 = [roll, pitch, yaw, depth]
```

Koopman 和 MPC 使用固定 4D 虚拟控制；新版环境的 TAM 分配器负责把它映射到 4、6 或 8 个推进器。`uuv4*` 使用显式可控自由度掩码，yaw 不作为可实现跟踪目标。

数据合同采用版本化 schema，不覆盖 v1：

```text
state_11
reference_5
raw_action_4
virtual_control_4
motor_pwm_padded_8
thruster_mask_8
applied_wrench_6
platform_context
environment_context_oracle
environment_context_estimated
next_state_11
embodiment / scenario / episode_id / step_index / seed / dt
```

`motor_pwm_padded_8` 只用于诊断、饱和和能耗分析，不作为跨构型主模型的默认控制输入。

## 4. v2.0 阶段设计

### Phase 6：EasyUUV 2.0 Intake and Multi-Configuration Qualification

导入新版环境，建立正确的 `easyuuv_nc` 包/运行合同，验证资产路径、环境注册、八种构型、推进器数量、TAM rank/可控自由度、基础 rollout 和 v1 回归隔离。

Phase 6 是首个需要完整 SPEC 和 PLAN 的活动阶段。

### Phase 7：Cross-Configuration Koopman Data and Control Contract

建立 schema v2、Koopman Bridge、统一 4D 虚拟控制、构型上下文、推进器掩码和 v1 日志兼容读取。

### Phase 8：Multi-Configuration Koopman Identification and OOD Gate

按构型和 episode 采集数据，使用 platform-level split 比较 persistence、线性模型、单构型 Koopman、pooled Koopman、conditional Koopman 和专家模型上界。

### Phase 9：Configuration-Aware Koopman-MPC Integration

让 MPC 优化固定 4D 虚拟控制，经平台 TAM 映射到实际推进器；实现构型 manifest、可控自由度 mask、fallback 和 matched closed-loop gate。

### Phase 10：Environment Awareness and Online Koopman Update

先建立 oracle-context 上界，再使用可部署信号估计环境上下文；实现 RLS/KF 更新、参数限幅、non-finite gate、frozen prior、rollback 和 recovery curve。

### Phase 11：Low-Frequency Agent Supervisor

Agent 只允许选择已准入模型、决定是否在线更新、提出有界 reference/MPC 配置以及触发安全回退。Agent 不调用实时 `env.step()`，不产生 PPO action，不发送 PWM。

### Phase 12：Final Matched Evaluation and Research Evidence

完成 nominal、held-out configuration、环境扰动、组合 shift 的统一评测，形成无 supervisor、规则 supervisor、agent supervisor 三方消融和最终可发表证据边界。

## 5. Git 与推送隔离设计

最终交付分支为：

```text
v2.0-multi-configuration
```

为满足“设计先审阅、三部分后推送”的双重要求，本设计记录先形成仅存在于本地的审阅提交，不立即推送。获得书面规格确认后，在首次远程推送前从 `v1.0` 基线组装干净的交付历史，并保留原审阅分支作为本地备份；不使用远程强制推送。

交付历史固定按“新版仿真快照 → v1.0 实验证据 → v2.0 planning”排列。每完成一个边界即执行一次远程推送，下一部分只能建立在上一部分已经可见、可审计的提交之上。因此，设计审阅提交不会作为 Push 1 或 Push 2 的祖先被意外带入远程。

远程推送分成三个可独立审计的部分：

### Push 1：新版仿真代码

```text
chore(v2.0): import EasyUUV 2.0 simulator snapshot
```

只包含 `easyuuv_v2-main/`。不包含 `source/` 和活动 planning 修改。导入提交保存收到的原始快照；包名规范化和集成修改进入后续 Phase 6 实现提交。

### Push 2：v1.0 服务器实验证据

```text
data(v1.0): archive server experiment evidence
```

包含 `source/results/` 和 `docs/v1.0_source_results_manifest.md`。manifest 记录文件数量、总大小、阶段目录、服务器来源、与 v1.0 tag 的关系、缺失 checkpoint 以及复现实验边界。

当前 `source/` 最大单文件约 2.7 MiB，不需要 Git LFS。实验结果提交不得混入 v2.0 代码或 planning 文件。

### Push 3：v2.0 planning

```text
docs(v2.0): establish multi-configuration Koopman milestone
```

包含：

- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `.planning/phases/06-*/06-SPEC.md`
- `.planning/phases/06-*/06-PLAN.md`
- `docs/Agentic_AUV_next_steps_plan.md`
- 本设计记录

本设计记录先本地原子提交用于审阅；组装交付历史时，它只进入第三段，并在正式 planning 推送时与 planning 更新处于同一远程推送序列，不会混入 Push 1 或 Push 2。

## 6. 证据与验证原则

1. 本地负责 schema、模型、数据分析、纯 Python 测试和文档一致性。
2. 服务器负责 Isaac 环境创建、USD、推进器/TAM、物理 rollout、PPO 训练和闭环评测。
3. 每个 Isaac 阶段至少包含本地合同测试、服务器 smoke、产物 validator 和 SUMMARY/VERIFICATION。
4. 数据按 configuration/episode 分组，不允许 row-level random split 冒充 OOD 泛化。
5. 姿态误差使用 SO(3) geodesic 指标，不继续把四元数分量 RMSE 标记为 angle RMSE。
6. 旧 Koopman 8D PWM 模型只作为 v1/version-shift 基线，不直接声明适用于 4/6 推平台。
7. 任一 promotion 允许得出 `no_selection`，不强制选择局部最好但整体退化的候选。

## 7. Phase 6 验收方向

Phase 6 完成必须同时满足：

1. 新版源码快照与后续集成修改可以通过 Git 历史区分。
2. `easyuuv_nc` 包名、入口和资源路径具有唯一、可复现的服务器安装合同。
3. 八种 CLI 构型均能被枚举并应用；记录预期推进器数量和可控自由度。
4. `uuv4*` 的 yaw 欠驱动被显式声明和测试，不能静默当成四自由度全可控平台。
5. base 构型完成最小 Isaac rollout，其他七种完成分级 smoke；所有 PWM/虚拟控制保持有界且无非有限值。
6. v1.0 归档文件和 tag 不被修改，现有本地非 Isaac 回归保持通过。
7. 输出 Phase 6 SUMMARY、VERIFICATION 和服务器执行 runbook 后，才允许进入 Phase 7 数据合同实现。

## 8. 已锁定决策

| 决策 | 结论 |
|---|---|
| v2.0 是否延续 v1 phase 编号 | 是，从 Phase 6 开始，不恢复 5.5/5.6。 |
| 新版 EasyUUV 是否替换 v1 源码 | 否，先以独立快照导入，Phase 6 建立适配边界。 |
| 跨构型主控制输入 | 固定 4D virtual control，不使用补零 PWM 作为主语义。 |
| v1.0 `source/results` 是否推送 | 是，单独数据提交并附 manifest。 |
| USD 是否使用 Git LFS | 当前不使用；最大文件低于 GitHub 单文件限制。 |
| Agent 是否直接控制推进器 | 禁止。Agent 仅为低频、受限、可回退 supervisor。 |
| 第一个完整 SPEC/PLAN | Phase 6。 |

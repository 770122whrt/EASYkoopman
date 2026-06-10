# EASYkoopman

## What This Is

EASYkoopman 是基于 EasyUUV Isaac Sim/Lab 仿真环境的控制器迁移项目。项目目标是在保留 EasyUUV 现有 AUV 资产、推进器模型、水动力模型和评估脚本的基础上，将底层控制器从 `Ssurface`/`PID` 逐步替换为 Koopman 模型预测控制（Koopman Model Predictive Control, Koopman+MPC）。

该项目首先服务于研究和仿真验证：在 Isaac Sim/Lab 中构建可复现的姿态与深度控制闭环，再为后续 Sim2Real 和真实 UUV 部署保留接口。

## Core Value

在不破坏 EasyUUV 原始仿真基线的前提下，建立一个可验证、可迭代的 Koopman+MPC 控制闭环。

## Requirements

### Validated

- EasyUUV 当前代码已提供 Isaac Lab `DirectRLEnv` 环境、8 推进器布局、浮力/阻力水动力计算和 RSL-RL 训练/评估脚本。
- 当前控制链路已经分层：4D action 进入 `_pid_control()`，再转为 8D PWM，最后由 `_compute_dynamics()` 转换成作用于刚体的 force/torque。

### Active

- [ ] 保留原始 `Ssurface`/`PID` 行为作为回归基线。
- [ ] 建立控制器边界，使 legacy controller 和 Koopman+MPC controller 可以在同一环境内切换。
- [ ] 建立仿真数据采集格式，记录 Koopman 辨识需要的状态、参考、控制量和下一步状态。
- [ ] 实现离线扩展动态模态分解（Extended Dynamic Mode Decomposition, EDMD）训练流程。
- [ ] 实现 Koopman+MPC 闭环控制，优先覆盖姿态和深度控制。
- [ ] 复用现有 step、sine、irregular 三类评估脚本，对比 legacy controller 与 Koopman+MPC。
- [ ] 整理 Isaac Sim/Lab 运行、验证和后续 Sim2Real 扩展文档。

### Out of Scope

- 原生 Isaac Sim app 重写 - 第一阶段保留 Isaac Lab 任务形态，避免同时迁移仿真框架和控制器。
- 真实硬件部署 - 当前先在仿真中建立闭环和数据管线。
- LLM 直接控制推进器 - EasyUUV 论文中 LLM 是低频调参器，不能替代实时控制器。
- 一开始实现完整 6-DOF 全空间 MPC - 先覆盖姿态与深度，降低模型维度和求解压力。
- 大规模重构训练框架 - PPO 训练和 RSL-RL workflow 保持可运行，后续按阶段接入。

## Context

- EasyUUV 源代码位于本目录，核心环境文件是 `easyuuv_env.py`。
- README 说明项目基于 Isaac Sim/Lab，原始测试环境为 Isaac Sim 4.0.0 和 Isaac Lab 1.0.0。目标本机 Isaac Sim/Lab 版本待确认。
- `_pid_control()` 是当前 4D action 到 8D PWM 的控制分配入口。
- `_compute_dynamics()` 包含推进器死区、多项式推力映射、推进器几何、浮力和阻力模型，应尽量保留。
- `workflows/play_controller.py` 已经提供不依赖 PPO 的直接控制入口，适合作为 Koopman+MPC 的第一版闭环验证脚本。
- `workflows/play_eval.py`、`workflows/play_eval_step.py`、`workflows/play_eval_task2.py` 已提供 sine、step、irregular 信号评估轨迹。

## Constraints

- **Workspace**: 所有规划和文档产物必须写在 `E:\code for project\Agentic AUV\EasyUUV` 下。
- **GitHub**: 远程目标为 `https://github.com/770122whrt/EASYkoopman.git`，初次发布允许覆盖 `main` 分支。
- **Compatibility**: 保留 Isaac Lab `DirectRLEnv` 环境形态，不在第一阶段改成原生 Isaac Sim standalone app。
- **Control Rate**: 当前仿真配置为 `dt=1/120`，`decimation=2`，控制闭环约 60 Hz。MPC 求解必须以该频率作为第一版预算。
- **Safety**: 控制输出最终必须限制到 8D PWM 的 `[-1, 1]`，并复用原有推进器推力模型。
- **Verification**: 每个阶段必须保留 legacy baseline，并给出可运行的回归或离线验证路径。

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 先保留 Isaac Lab 环境，不重写仿真框架 | 同时迁移仿真和控制器会放大不确定性 | Pending |
| Koopman+MPC 第一版替换控制器层，而不是替换水动力层 | `_compute_dynamics()` 已包含经过项目验证的推进器和水动力逻辑 | Pending |
| 第一版 MPC 优化 4D 虚拟控制量，后续再扩展到 8D PWM 或 6D wrench | 降低求解维度，方便复用现有 action 语义 | Pending |
| 先做数据采集和基线验证，再实现 EDMD/MPC | 没有可靠数据和 baseline 时闭环调试不可解释 | Pending |
| LLM 后续只作为调参或分析层，不进入实时控制环 | 控制闭环需要确定性和低延迟 | Pending |

---
*Last updated: 2026-06-10 after GSD project initialization*

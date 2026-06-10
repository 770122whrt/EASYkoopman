# Phase 1: Baseline Data And Controller Boundary - Specification

**Created:** 2026-06-10  
**Ambiguity score:** 0.10 (gate: <= 0.20)  
**Requirements:** 7 locked

## Goal

EasyUUV 在保留 legacy `Ssurface`/`PID` 控制行为的同时，提供可切换的控制器边界和 Koopman 辨识所需的数据采集日志。

## Background

当前 `easyuuv_env.py` 已经包含完整控制链路：`_pre_physics_step()` 接收 4D action，`_pid_control()` 将 4D action 转为 8D PWM，`_compute_dynamics()` 将 PWM 转为推进器力矩并叠加水动力，`_apply_action()` 将 force/torque 写入 Isaac 物理仿真。

当前代码没有独立 controller abstraction，没有稳定的数据采集格式，也没有将 8D PWM 和 next state 作为 Koopman 训练样本导出。Phase 1 的目标不是实现 Koopman+MPC，而是为它建立可验证入口。

## Requirements

1. **Legacy behavior preservation**: Legacy `Ssurface` 和 `PID` 控制路径必须保持可用。
   - Current: `_pid_control()` 直接根据 `cfg.control_method` 选择 `Ssurface` 或 `PID`。
   - Target: 重构或扩展后，`Ssurface`/`PID` 仍能以原配置运行。
   - Acceptance: 使用 legacy mode 时，8D PWM 输出仍被限制在 `[-1, 1]`，评估脚本仍能调用 `env.step()`。

2. **Controller mode boundary**: 环境配置必须能区分 legacy controller 和 Koopman+MPC controller。
   - Current: 只有 `control_method = 'Ssurface'` 或 `'PID'`。
   - Target: 配置层存在明确 controller mode，后续可选择 `KoopmanMPC`。
   - Acceptance: 配置项能被 workflow 设置，legacy 默认值不变。

3. **PWM visibility**: 8D PWM 在进入推进器多项式推力映射前必须可记录。
   - Current: `motorValues` 是 `_compute_dynamics()` 内部局部变量。
   - Target: 当前步 PWM 可被日志模块读取或缓存。
   - Acceptance: 单步日志包含 shape 为 `(8,)` 的 PWM 值。

4. **State schema**: 数据采集必须记录 Koopman 辨识所需的状态和目标。
   - Current: 评估日志记录姿态、位置和速度，但没有统一训练样本 schema。
   - Target: 每条样本包含 `t`, `state`, `reference`, `action_4d`, `pwm_8d`, `next_state`。
   - Acceptance: 采集文件可被离线脚本读取，并能重建 `(x_k, u_k, r_k, x_{k+1})`。

5. **Trajectory coverage**: 数据采集必须覆盖 step、sine 和 irregular 三类轨迹。
   - Current: 三类轨迹分散在 `play_eval_step.py`、`play_eval.py`、`play_eval_task2.py`。
   - Target: 三类轨迹均可生成同 schema 日志。
   - Acceptance: 每种轨迹至少产生一个日志文件，文件字段一致。

6. **Direct controller entry**: 第一版验证必须优先使用不依赖 PPO 的 direct controller 路径。
   - Current: `play_controller.py` 已经用手写姿态误差构造 4D action 并调用 `env.step(action)`。
   - Target: Phase 1 数据采集可以从 direct controller 路径开始。
   - Acceptance: 不加载 PPO checkpoint 也能生成控制数据。

7. **Documentation handoff**: Phase 1 必须留下后续 Phase 2/3 能直接使用的说明。
   - Current: README 只描述原 EasyUUV 训练/评估方式。
   - Target: 文档明确控制器边界、数据字段、验证命令和待确认事项。
   - Acceptance: `docs/koopman_mpc_migration_plan.md` 包含 Phase 1 输出和下一阶段接口。

## Boundaries

**In scope:**
- 保护 legacy `Ssurface`/`PID` 路径。
- 增加 controller mode 的规划和后续实现边界。
- 定义 Koopman 训练数据 schema。
- 设计 direct controller 数据采集入口。
- 记录 step、sine、irregular 轨迹的日志要求。
- 更新文档和 GSD 规划文件。

**Out of scope:**
- EDMD 训练实现 - Phase 2 处理。
- MPC 求解器实现 - Phase 3 处理。
- Kalman 在线更新 - v2 处理。
- 真实硬件部署 - 当前只做 Isaac Sim/Lab 仿真。
- 原生 Isaac Sim standalone app 迁移 - 当前保留 Isaac Lab `DirectRLEnv`。

## Constraints

- 所有文件必须位于 `E:\code for project\Agentic AUV\EasyUUV`。
- 默认 legacy 控制器不能改变，避免失去回归基线。
- 数据采集不得绕过现有 `_compute_dynamics()` 推进器和水动力模型。
- 控制输出最终必须进入 8D PWM 并限制在 `[-1, 1]`。
- Isaac Sim/Lab 版本待确认，Phase 1 不能假设未验证的本机版本。

## Acceptance Criteria

- [ ] Legacy `Ssurface` 和 `PID` mode 保持可配置。
- [ ] 控制器边界文档说明 legacy 和 Koopman+MPC 的接入点。
- [ ] 数据 schema 包含 `t`, `state`, `reference`, `action_4d`, `pwm_8d`, `next_state`。
- [ ] 规划中明确优先使用 `play_controller.py` 做无 PPO 验证。
- [ ] step、sine、irregular 三类轨迹均被纳入数据采集计划。
- [ ] Phase 1 不实现 EDMD、MPC 或 Kalman 在线更新。
- [ ] 所有 Phase 1 产物写在 `EasyUUV` 目录下。

## Ambiguity Report

| Dimension | Score | Min | Status | Notes |
|-----------|-------|-----|--------|-------|
| Goal Clarity | 0.92 | 0.75 | met | 输出边界和数据采集目标明确 |
| Boundary Clarity | 0.94 | 0.70 | met | 明确排除 EDMD、MPC、Kalman、硬件部署 |
| Constraint Clarity | 0.86 | 0.65 | met | 保留 legacy、路径限制、PWM 限制明确 |
| Acceptance Criteria | 0.88 | 0.70 | met | 7 个 pass/fail 条件 |
| **Ambiguity** | 0.10 | <= 0.20 | met | 可进入计划阶段 |

## Interview Log

| Round | Perspective | Question summary | Decision locked |
|-------|-------------|------------------|-----------------|
| 1 | Researcher | 当前代码中控制器在哪里接入？ | `_pid_control()` 到 `_compute_dynamics()` 是主要边界 |
| 2 | Simplifier | 最小可成功阶段是什么？ | 先做 baseline、controller boundary 和数据采集 |
| 3 | Boundary Keeper | 哪些不属于第一阶段？ | EDMD、MPC、Kalman、硬件部署均排除 |
| 4 | Failure Analyst | 什么会导致后续失败？ | 没有 legacy baseline 或统一数据 schema 会使模型和控制结果不可解释 |

---
*Phase: 01-baseline-data-controller-seam*
*Spec created: 2026-06-10*
*Next step: $gsd-plan-phase 1 - implementation planning*

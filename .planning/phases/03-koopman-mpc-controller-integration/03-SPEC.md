# Phase 3: Koopman MPC Controller Integration - Specification

**Created:** 2026-07-01  
**Ambiguity score:** 0.12 (gate: <= 0.20)  
**Requirements:** MPC-01, MPC-02, MPC-03, MPC-04  
**Primary handoff from Phase 2.5:** `source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json`

## Goal

接入一个可验证的 `koopman_mpc` 控制器模式，让 EasyUUV 在 Isaac Lab 中可以用 Phase 2.5 选出的 Koopman 模型做有限时域预测，并输出受约束的 8D PWM 控制量。

Phase 3 的目标是“第一版闭环能跑、可退回、可测量”，不是一次性完成最终性能优化。

## Background

Phase 2.5 已经证明当前离线链路可以产生一个通过 gate 的 selected model manifest。该模型的形式是：

```text
x_{k+1} = W [ phi(x_k, r_k), u_k ]
```

其中：

- `x_k` 是 11D 状态。
- `r_k` 是 5D reference。
- `u_k` 是 8D PWM。
- `phi(x_k, r_k)` 包含 state、reference、tracking error 和二次项。

这意味着 Phase 3 的第一版 MPC 应直接在 8D PWM 空间里优化控制序列。早期文档曾提出“先优化 4D virtual command”，但当前通过 gate 的模型控制输入是 8D PWM；如果仍优化 4D action，会额外引入 legacy `_pid_control()` 的非线性映射，导致 MPC 的模型输入和真实控制输入不一致。因此第一版以 8D PWM 为主，保留后续 4D adapter 作为扩展。

## Paper Alignment

EasyUUV 论文启发：

- 保持分层结构：高层 policy / direct reference 不直接输出推进器物理力。
- 实时控制安全边界在低层控制器。
- LLM 只能作为低频调参或分析层，不进入本阶段实时控制。

Koopman-Sim2Real 论文启发：

- 先用数据离线辨识 Koopman 模型。
- 再用 MPC 在预测模型上求解受约束控制。
- 在线 Kalman / adaptation 是后续阶段，不属于本阶段。
- 原论文是 3-DOF 平面系统；EasyUUV 当前是 11D state 和 8D PWM，所以只能继承“EDMD -> Koopman model -> MPC”的方法结构，不能照搬状态和控制维度。

## Algorithm Contract

Phase 3 使用 Phase 2.5 选中的 `direct_state` 模型作为第一版 MPC prediction backend。这个 backend 是工程可用的 Koopman-style next-state predictor：

```text
x[k+1] = W * [phi(x[k], r[k]), u[k]]
```

它不是 Koopman-Sim2Real 论文中完整的 lifted-space transition：

```text
f[k+1] = Theta^T * f[k]
```

因此 Phase 3 的成功声明必须写成“fallback-safe Koopman-MPC engineering integration”，不能写成“完整复现 Koopman-Sim2Real 核心算法”。本阶段继承的是 `EDMD-trained prediction model -> receding-horizon control -> bounded actuator command` 的结构。

Phase 3 runtime interface 必须支持两个 backend：

- `direct_state` - Phase 2.5 当前选中 backend，用于第一版 Isaac smoke。
- `paper_lifted_edmd` - 与 Koopman-Sim2Real 更接近的 lifted-space backend，用于 backend check 和后续 Phase 4 对比。

Phase 3 summary 必须记录：

```text
backend_used
backend_reason
backend_is_paper_style_lifted_edmd
fallback_rate
latency_budget_met
known_limitations
```

如果 `selected_model_manifest.json` 的 `known_limitations` 为空，Phase 3 summary 必须从 `docs/phase2_5_consolidation_report.md` 和 backend check 中补充 handoff limitations。

## Requirements

1. **Manifest-first runtime contract**
   - Phase 3 必须从 `selected_model_manifest.json` 加载模型路径、模型类别、维度、`dt`、normalizer 和 gate 状态。
   - 如果 `gate_status != pass`，运行时必须 fail closed，不允许继续进入闭环控制。
   - Acceptance: 本地测试覆盖 pass、fail、missing path、unsupported model class。

2. **Prediction wrapper**
   - 提供统一 `predict_next(state, pwm, reference)` 接口，支持当前 `direct_state`，并保留 `paper_lifted_edmd` loader 分支。
   - 输出维度必须是 11D。
   - 模型输入 quaternion convention 必须保持和训练日志一致；prediction wrapper 不得静默翻转输入 quaternion。
   - Acceptance: 用 Phase 2.5 selected model 和 fixture state 可以预测下一状态，维度和有限值检查通过。

3. **MPC problem definition**
   - MPC 优化变量为 horizon 内的 8D PWM 序列。
   - 代价函数至少包含姿态/深度 tracking、control energy、control smoothness。
   - Controlled state 第一版使用 `state[0:5] = [z, quat_wxyz]` 对齐 5D reference。
   - Quaternion tracking cost 必须处理 `q` 与 `-q` 等价问题，但该符号对齐只用于误差计算，不改变送入 Koopman 模型的 state。
   - Diagnostics 必须记录 predicted quaternion norm，用于发现模型 rollout 是否离开物理 envelope。
   - Acceptance: 离线测试验证代价函数对 tracking error、control energy、smoothness 单调合理。

4. **Bounded control output**
   - 输出 PWM 必须 clip 到 `[-1, 1]`。
   - 支持 `delta_pwm_limit`，限制相邻控制变化。
   - Acceptance: 任意 fixture 输入下 solver 返回 8D bounded PWM。

5. **Solver safety and fallback**
   - 第一版使用纯 NumPy first-pass receding-horizon optimizer，不引入必须安装的新优化器依赖。
   - 该 solver 不得被描述为与论文中 CasADi/非线性 MPC 完全等价。
   - solver 必须记录 latency、status、cost、iteration/candidate count。
   - 对 fixture states，solver 的 predicted horizon cost 必须低于 hold-previous-PWM baseline；如果做不到，必须优先 fallback 并记录原因。
   - 如果 solver 超时、返回非有限值或超过预算，控制器必须 fallback。
   - 第一 fallback 是上一帧有效 PWM；如果没有上一帧，则 fallback 到 legacy `_pid_control()` 结果。
   - Acceptance: 测试覆盖 solver failure、timeout flag、nonfinite output。

6. **EasyUUV controller integration**
   - `EasyUUVEnvCfg.controller_mode = "koopman_mpc"` 时，`_compute_dynamics()` 使用 Koopman MPC adapter 生成 `motorValues`。
   - 不修改 `_compute_dynamics()` 后半段推进器死区、多项式推力、水动力和 force/torque 逻辑。
   - Acceptance: local source-contract test 确认 `koopman_mpc` 不再抛 `NotImplementedError`，且 `_last_pwm_8d` 仍记录实际进入推进器映射前的 PWM。

7. **Workflow integration**
   - `workflows/play_controller.py` 支持 `--controller_mode koopman_mpc` 和 `--koopman_manifest_path`。
   - Koopman MPC 日志需要包含 solver status、latency、cost、fallback 标记。
   - MPC adapter 输入必须保持 state/reference based，使未来 PPO 生成的 4D 姿态/深度修正可以先转换为同一 reference interface，而不是绕过安全控制层直接输出 PWM。
   - Acceptance: `--help` 输出包含新参数；短 offline smoke 可以不导入 Isaac。

8. **Server Isaac gate**
   - Phase 3 的最终 gate 是服务器上运行一个单 env、短 horizon、短目标的 `koopman_mpc` rollout。
   - 必须记录 PWM bounded、solver latency、fallback rate、是否仿真崩溃。
   - Acceptance: 服务器 smoke 能完成 step trajectory 的最小目标，不要求性能优于 legacy；性能对比留给 Phase 4。

## Boundaries

**In scope:**

- Koopman selected manifest loader。
- Koopman prediction wrapper。
- 8D PWM-space receding-horizon MPC。
- Pure NumPy first solver and solver abstraction。
- Controller adapter with fallback。
- `easyuuv_env.py` controller mode integration。
- `play_controller.py` smoke workflow integration。
- Local tests and server smoke runbook.

**Out of scope:**

- PPO training or PPO checkpoint eval。
- Full Phase 4 performance comparison。
- Online Kalman / RLS adaptation。
- LLM tuning。
- Full 6-DOF wrench-space MPC。
- Replacing hydrodynamics, thruster geometry, USD assets or Isaac environment architecture。
- Claiming Sim2Real readiness.
- Claiming that a `direct_state` smoke run is a complete paper-style lifted EDMD controller.

## Acceptance Criteria

- [x] Manifest loader rejects non-pass gate and missing model artifacts.
- [x] Prediction wrapper can load selected model and produce finite 11D next-state prediction.
- [x] MPC solver returns bounded 8D PWM for fixture states.
- [x] MPC cost includes tracking, energy and smoothness terms.
- [x] MPC cost handles quaternion sign equivalence without changing model input quaternion convention.
- [x] Solver beats hold-previous-PWM predicted horizon cost on fixture states or explicitly falls back.
- [x] Solver reports latency/status/cost and handles timeout/failure through fallback.
- [x] Backend check compares selected `direct_state` with the best passing `paper_lifted_edmd` candidate offline.
- [x] `easyuuv_env.py` has a real `koopman_mpc` branch that preserves the existing force/torque pipeline.
- [x] `workflows/play_controller.py` can select `koopman_mpc` and point to a selected manifest.
- [x] Local tests pass with no Isaac runtime requirement for pure Koopman/MPC modules.
- [x] Server Isaac smoke runs `koopman_mpc` for one env without simulation crash.
- [x] Phase 3 summary states `backend_used`, `backend_reason`, fallback rate, whether the backend is paper-style lifted EDMD, and whether 60 Hz budget was met.

## Ambiguity Report

| Dimension | Score | Min | Status | Notes |
|---|---:|---:|---|---|
| Goal Clarity | 0.90 | 0.75 | met | 第一版目标是 safe smoke，不是最终性能 |
| Boundary Clarity | 0.91 | 0.70 | met | 明确不做 PPO、Phase 4 对比、online adaptation |
| Constraint Clarity | 0.86 | 0.65 | met | 8D PWM、manifest-first、fallback、server gate 都锁定 |
| Acceptance Criteria | 0.87 | 0.70 | met | 每项有本地或服务器验证方式 |
| **Ambiguity** | **0.12** | **<=0.20** | met | 可以进入 implementation planning |

## Design Decision

推荐方案：**离线 MPC adapter -> 8D PWM-space solver -> Isaac smoke**。

该方案和 Phase 2.5 selected model 的 `control_dim = 8` 对齐，不需要先训练 PPO，也不需要改动推进器/水动力层。它牺牲了一部分“求解器高级性”，换取最小闭环风险和清晰可调试的失败边界。

推荐的 Phase 3 成功声明是：

```text
Phase 3 completed the first fallback-safe Koopman-MPC controller integration.
The smoke run used the Phase 2.5 selected direct_state prediction backend.
This validates the controller seam, bounded 8D PWM output, manifest loading,
solver diagnostics and Isaac closed-loop execution.
It does not yet prove final performance superiority or full paper-style lifted
EDMD control. Those claims are deferred to backend comparison and Phase 4
experiments.
```

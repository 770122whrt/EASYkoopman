# Phase 3: Koopman MPC Controller Integration - Context

**Gathered:** 2026-07-01  
**Status:** Ready for planning  
**Source:** brainstorming + current codebase + Phase 2.5 server gate result

<domain>
## Phase Boundary

Phase 3 接入 Koopman+MPC 控制器模式。它必须从 Phase 2.5 selected model manifest 读取模型，并在 EasyUUV Isaac Lab 环境中输出 8D PWM，复用现有推进器和水动力链路。

本阶段的成功定义是：本地离线 MPC 和服务器 Isaac smoke 都能跑通，并且失败时能安全 fallback。性能对比和长轨迹评估留给 Phase 4。
</domain>

<decisions>
## Implementation Decisions

### D-01 Manifest-first
- Phase 3 只能读取 `selected_model_manifest.json`，不能硬编码模型路径、维度、dt 或 normalizer 行为。

### D-02 Fail closed
- `gate_status != pass`、模型路径不存在、模型类别不支持或预测输出非有限值时，不进入 Koopman MPC 控制。

### D-03 8D PWM control
- 第一版 MPC 直接优化 8D PWM，因为 Phase 2.5 选中模型的 `control_dim = 8`，且训练输入是 `pwm_8d`。

### D-04 Preserve physics pipeline
- 不重写 `_compute_dynamics()` 的推进器死区、推力多项式、thruster geometry、水动力和 Isaac force/torque 应用逻辑。

### D-05 Solver simplicity first
- 第一版 solver 以纯 NumPy 可测为优先，不把 SciPy、CasADi、OSQP 等新依赖作为必要条件。

### D-06 Runtime fallback
- solver 失败、超时或输出非法时先用上一帧有效 PWM；没有上一帧时 fallback 到 legacy `_pid_control()`。

### D-07 Short horizon smoke
- 第一版 horizon 保持短，例如 5-10 步，先验证闭环和日志，不追求最终性能。

### D-08 Paper alignment
- 继承 Koopman-Sim2Real 的 `EDMD -> Koopman model -> MPC` 结构，但不照搬 3-DOF turtle 状态和控制维度。
- 当前第一版 smoke 若使用 `direct_state`，只能声明为工程 Koopman predictor + MPC integration，不能声明为完整 paper-style lifted EDMD controller。

### D-09 PPO deferred
- 服务器当前没有 PPO checkpoint。Phase 3 不依赖 PPO endpoint，继续使用 `workflows/play_controller.py` direct-controller path。

### D-10 Server gate
- 真实 Isaac 闭环只在服务器验证。本地只做 pure Python tests、offline rollout 和 source-contract checks。

### D-11 Backend check
- Phase 3 必须离线比较 selected `direct_state` backend 与 Phase 2.5 sweep 中 best passing `paper_lifted_edmd` backend，并记录为何 first Isaac smoke 使用某个 backend。

### D-12 Quaternion convention
- MPC cost 可以为误差计算处理 `q` / `-q` 等价，但模型输入 quaternion 不得静默改写，必须保持训练日志 convention。

### D-13 Future PPO/RL interface
- Koopman MPC adapter 输入保持 state/reference based。未来 PPO/RL 可以输出 4D 姿态/深度修正并转换成同一 reference interface，而不是直接绕过 MPC 输出 PWM。
</decisions>

<canonical_refs>
## Canonical References

**Phase 2.5 handoff**
- `docs/phase2_5_consolidation_report.md` - 服务器复跑结果、selected model、指标、限制。
- `docs/phase3_algorithm_alignment_review.md` - Phase 3 algorithm contract review and required doc corrections.
- `source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json` - Phase 3 的默认模型入口。
- `source/results/koopman_phase2_5_verify_20260701_231802/gate_report.md` - Phase 2.5 pass/fail 报告。

**Koopman model runtime**
- `koopman/model.py` - direct-state `KoopmanModel` load/predict contract。
- `koopman/lifted_edmd.py` - paper-style `LiftedEDMDModel` load/predict contract。
- `koopman/evaluation.py` - rollout/divergence metrics，可复用到 offline MPC validation。
- `koopman/selection.py` - manifest 字段来源。

**EasyUUV controller seam**
- `easyuuv_env.py` - `EasyUUVEnvCfg.controller_mode`、`_compute_dynamics()`、`_last_pwm_8d`。
- `workflows/play_controller.py` - 不依赖 PPO 的 server smoke 入口。
- `koopman_data.py` and `workflows/koopman_logging.py` - JSONL logging schema。

**Architecture docs**
- `docs/koopman_mpc_migration_plan.md` - 原始 Koopman+MPC 迁移方案和论文映射。
- `.planning/ROADMAP.md` - Phase 3 scope and requirement mapping。
</canonical_refs>

<specifics>
## Specific Ideas

- 新增 `koopman/runtime.py` 或等价模块，用于从 manifest 加载模型和进行 contract validation。
- 新增 `koopman/mpc.py`，包含 `MPCProblem`、`MPCWeights`、`MPCResult` 和 first solver。
- 新增 backend check workflow，对比 `direct_state` 与 best passing `paper_lifted_edmd` 后端。
- 新增 `koopman/mpc_controller.py`，把 EasyUUV state/reference 和 solver 输出接起来。
- `easyuuv_env.py` 只在 `controller_mode == "koopman_mpc"` 分支调用 adapter；其余 legacy path 不变。
- `workflows/play_controller.py` 新增 `--controller_mode`、`--koopman_manifest_path`、`--mpc_horizon`、`--mpc_timeout_ms`。
</specifics>

<deferred>
## Deferred Ideas

- 4D virtual action MPC。
- Direct wrench-space or full 6-DOF MPC。
- Online Kalman/RLS update。
- PPO-based data collection and comparison。
- Full Phase 4 step/sine/irregular benchmark。
</deferred>

---

*Phase: 03-koopman-mpc-controller-integration*  
*Context gathered: 2026-07-01*

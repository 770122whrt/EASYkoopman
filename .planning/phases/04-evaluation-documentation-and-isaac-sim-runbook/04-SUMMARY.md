---
phase: 04-evaluation-documentation-and-isaac-sim-runbook
status: completed
completed: 2026-07-02
server: agentic-AUV
isaac_stack: Isaac Sim 5.0 + Isaac Lab 2.2.1
---

# Phase 4 Summary: Controller-Only Evaluation Baseline

## 1. 本阶段目的

Phase 4 的目标不是训练 PPO，也不是接入 LLM，而是在重新引入高层智能之前，先把低层控制器本身的闭环表现单独测清楚。

本阶段固定链路为：

```text
scripted trajectory/reference -> controller -> 8D PWM -> AUV
```

这样 Phase 4.5 接入 PPO 时，如果性能变差，我们能判断问题来自 policy/reference，而不是把 PPO、Koopman 模型、MPC 求解器和 legacy 控制器混在一起分析。

## 2. 实际完成的内容

本地完成：

- 增加 `koopman/evaluation_logs.py`，从 Koopman JSONL 计算 controller-only 指标。
- 增加 `workflows/summarize_phase4_evaluation.py`，生成 JSON/Markdown 指标报告。
- 增加 Phase 4 metrics 单元测试，保证工具不依赖 Isaac。
- 增加 `docs/phase4_controller_evaluation_runbook.md`，记录服务器复现实验流程。

服务器完成：

- 将本地 `isaaclab2-migration` 当前代码打包上传到 `/root/EASYkoopman`。
- 在 `/root/IsaacLab` 通过 Isaac Lab 2.2.1 跑完 9 个 controller-only rollout。
- 每个 rollout 使用 `num_envs=1`、`trajectory_cycles=2`、`steps_per_action=100`、`mpc_horizon=5`、`mpc_timeout_ms=12`、`mpc_delta_pwm_limit=0.35`。
- 每个日志均为 1400 samples，时间覆盖约 23.33 秒。
- 所有 PWM 输出都保持在 `[-1, 1]` 内。

## 3. 跑过的评估矩阵

| Controller | Backend | step | sine | irregular |
|---|---|---:|---:|---:|
| legacy | legacy `Ssurface` | pass | pass | pass |
| Koopman+MPC | `direct_state` selected manifest | pass | pass | pass |
| Koopman+MPC | `paper_lifted_edmd` comparison manifest | pass | pass | pass |

远端日志已经拉回本地：

```text
source/results/koopman_phase4/data/*.jsonl
source/results/koopman_phase4/reports/metrics_summary.json
source/results/koopman_phase4/reports/metrics_summary.md
source/results/koopman_phase4/run_logs/*.log
```

这些 `source/results` artifacts 是实验产物，默认不提交进 Git。

## 4. 核心指标结论

| Trajectory | Controller | Backend | Depth RMSE | Attitude RMSE | Fallback | Max Latency ms | PWM |
|---|---|---|---:|---:|---:|---:|---|
| step | legacy | legacy | 0.398826 | 0.954227 | 0.000 | 0.000 | bounded |
| step | Koopman+MPC | direct_state | 1.037229 | 2.044340 | 0.118 | 13.957 | bounded |
| step | Koopman+MPC | paper_lifted_edmd | 14.235875 | 1.099042 | 0.166 | 13.385 | bounded |
| sine | legacy | legacy | 0.398036 | 0.783965 | 0.000 | 0.000 | bounded |
| sine | Koopman+MPC | direct_state | 0.898539 | 2.237200 | 0.106 | 13.657 | bounded |
| sine | Koopman+MPC | paper_lifted_edmd | 13.457113 | 0.905854 | 0.171 | 12.868 | bounded |
| irregular | legacy | legacy | 0.374200 | 1.055595 | 0.000 | 0.000 | bounded |
| irregular | Koopman+MPC | direct_state | 0.551377 | 1.362476 | 0.387 | 16.155 | bounded |
| irregular | Koopman+MPC | paper_lifted_edmd | 14.246360 | 1.083079 | 0.199 | 12.901 | bounded |

解释：

- `legacy/Ssurface` 是当前最稳的 controller-only baseline，三种 trajectory 下 depth RMSE 和 attitude RMSE 都最低或接近最低，没有 fallback。
- `direct_state` Koopman+MPC 已经证明闭环可运行，PWM 有界，但 tracking 还没有超过 legacy，irregular 轨迹 fallback rate 达到 0.387，说明它还需要 solver/权重/模型质量优化。
- `paper_lifted_edmd` 已经完成论文风格 lifted EDMD 的闭环对比，但 depth RMSE 约 13-14，不能作为下一阶段默认控制器；它更适合作为研究对照和后续模型改进对象。
- Phase 4 只能说明 Isaac 仿真中的 controller-only 表现，不能直接声明真实硬件性能。

## 5. 与论文路线的关系

Phase 4 保留了两条线：

- 工程线：使用 Phase 2.5 选出的 `direct_state` 模型，把 Koopman+MPC 接入 EasyUUV 的现有 8D PWM 推进器通道。
- 论文对齐线：使用 `paper_lifted_edmd` backend 做 paper-style lifted EDMD 对比，检查它是否能在相同 MPC 接口下闭环运行。

结果说明，paper-style backend 的结构已经能接入，但当前模型/特征/训练数据还不能支撑深度控制。这一点很重要：它不是“没有做论文方法”，而是“论文风格方法已纳入对比，但当前数据下不应直接替换工程 baseline”。

## 6. Phase 4.5 决策

Phase 4.5 可以进入 PPO/RL reference adapter，但必须以 legacy 为主要 controller-only baseline，以 direct_state Koopman+MPC 为可运行的 Koopman baseline。

推荐比较顺序：

1. `scripted reference -> legacy -> PWM`，作为最稳低层基线。
2. `scripted reference -> direct_state Koopman+MPC -> PWM`，作为 Koopman 低层基线。
3. `stub policy/reference adapter -> direct_state Koopman+MPC -> PWM`，先验证 PPO adapter 不会破坏控制边界。
4. 如果服务器存在可用 checkpoint，再进入 `PPO -> reference/correction -> direct_state Koopman+MPC -> PWM`。

Phase 4.5 不应该默认使用 `paper_lifted_edmd` 做 PPO 底层控制器，除非先解决 depth RMSE 和 fallback 问题。

## 7. 完成边界

Phase 4 已完成：

```text
controller-only Isaac evaluation baseline
validated JSONL logs
metrics summary
server runbook
PPO handoff baseline
```

Phase 4 没有完成，也不声称完成：

```text
PPO inference/training
LLM planning/tuning
online Koopman adaptation
real-world hardware validation
Koopman+MPC performance superiority over legacy
```

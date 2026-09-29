# 当前控制链与比较合同

2026-09-29。本文描述 v86/v87 共用的三臂控制语义。当前范围和状态见[研究索引](phase9_research_index.md)与[STATE](../.planning/STATE.md)，精确数据和参数见[v87运行说明](phase9_diverse_v87_runbook.md)。本文不是效果报告；v86 未运行扰动闭环，v87 尚在实施验证。

## 三个预测模型与共同下游

| 控制臂 | 预测方程与训练边界 |
|---|---|
| `physics` | `x_next = F_phys(x,a)`；旧物理模型事前冻结，不用新增扰动数据校准 |
| `koopman` | `z_0 = ψ(x_observed)`，`z_next = A z + B[a,a²]`，从提升状态解码输出；A/B 用含扰动训练轨迹离线拟合 |
| `hybrid` | 同一 A/B 自主传播 z；`ξ_next = coordinates(F_phys(x,a)) + Rz`，再解码 x；R 仅用相同训练集离线拟合 |

`z` 是完整 38 维非线性提升状态；`a` 是共同执行器链预测的六维驱动加速度，不是未来观测或隐藏扰动力。混合模型的 x 与 z 分别递推，不能把物理或解码的未来 x 重新提升回灌 z。实际控制边界可重新初始化预测会话；每个分支的提升状态与执行器记忆独立。参数在验证、测试和闭环时全部冻结。

额外二次阻力只作用于仿真 plant；诊断真值可供独立数据验收使用，不进入控制器或模型输入。反馈补偿也不能读取新增扰动真值。

```text
任务高度/姿态目标 + 当前状态 + 已确认执行的命令历史
 → 因果执行器记忆 + 三臂各自预测模型
 → 同一连续序列 MPC、约束、代价和候选独立检查
 → 执行所选计划的第一个四维 pre-TAM 命令
 → 可控轴掩码 → TAM分配 → PWM → 死区与转速滞后
 → 同一含扰动 Isaac plant → 新观测 → 下一实际控制边界
```

四维命令 `[roll,pitch,yaw,heave]` 是虚拟控制通道，不是角度或直接以 N/N·m 表示的 wrench。`direct_pre_tam_v24` 接入绕过原级联 PID 控制律，仍保留相同分配及实际推进器。当前状态来自 Isaac：世界 z、wxyz 四元数、机体线速度和角速度，共 11 维；世界 z 不能直接称为水面下深度。没有感知网络、PPO 或 Agent 参与本轮在线决策。

## 时间、反馈与求解

每个命令在 30Hz 控制时钟下保持 4 个 120Hz 物理子步；预测 20 个控制区间，共 80 个物理步，约 0.667 秒。求解期间仿真暂停，这是同步非实时实验，不能声称实时 30Hz。2 秒任务共 60 个控制区间，首个区间是共同反馈启动，其余 59 次才是 MPC 决策。

反馈依据当前高度/姿态误差与已知物理补偿生成受限命令。因果反馈预演在各模型自己预测的未来状态上递推反馈，作为连续优化的初值和可行参照；它不读取真实未来状态，也不代表真实反馈闭环的最优动作标签。主链使用 CasADi/IPOPT；提升传播的线性结构不意味着整个输入、姿态解码或混合预测构成线性 QP。

三臂使用相同权重、时域、指令边界、变化率、支持域、PWM 余量/死区距离及状态安全约束。最终计划还须经过实际数值语义的独立预测检查。模型内部预测代价只用于该模型的计划选择，不能跨模型当作实际效果比较。

必须分别保留：求解器状态、最后有限原始候选、约束残差、原始候选的独立可行性、最终计划、计划来源及 fallback。超时或迭代上限不是收敛；返回候选可经检查采用，最终 fallback 可行也不能证明原始候选可行。v87 的求解验收修复围绕这一分离，具体实施和实测结果见版本报告。

## 代码职责

| 职责 | 入口 |
|---|---|
| v87三臂构建与身份绑定 | [preview_solver_v87.py](../koopman/preview_solver_v87.py) |
| 完整提升、混合残差与NumPy/CasADi实现 | [disturbance_lifted_v86.py](../koopman/disturbance_lifted_v86.py) |
| 因果记忆及每次预测会话 | [command_state_v39.py](../koopman/command_state_v39.py)、[continuous_prediction_v76.py](../koopman/continuous_prediction_v76.py) |
| 连续求解、候选与原始约束残差 | [continuous_mpc_v76.py](../koopman/continuous_mpc_v76.py) |
| 预演、父进程精确复核及计划选择 | [preview_mpc_v79.py](../koopman/preview_mpc_v79.py)、[reliable_mpc_v77.py](../koopman/reliable_mpc_v77.py) |
| 隔离求解进程 | [preview_solver_v80.py](../koopman/preview_solver_v80.py) |
| TAM前接入与真实环境 | [control_v67.py](../easyuuv_nc/control_v67.py)、[easyuuv_env.py](../easyuuv_nc/env/easyuuv_env.py) |
| 离线独立求解检查 | [solve_disturbance_v87.py](../workflows/solve_disturbance_v87.py) |

模块名中的旧版本号不自动表示已废弃；当前入口仍显式复用这些共享实现。反之，旧 collector 或报告存在也不表示它是本轮运行入口。

## 历史解释与效果边界

v77/v78 使用结构化投影，v82 的自由速度读出仍逐步重提升；它们的短任务局部收益均不是完整提升传播有效的证明。v84/v85 和 v86 的失败保留，v86 混合模型同类输入验证有改善、扫频仍有失败。[研究索引](phase9_research_index.md)按版本链接原始报告；整理前控制合同原文保存在[历史档案](history/phase9_status_before_v87_20260929.md)。旧的“物理必须用新增数据重校准”或“预演尚未实现”表述不再是当前合同。

预测合格、求解可行、真实执行合格和实际任务改善是不同结论。先预测与求解，再按准入条件做 2 秒配对；长时稳定、新构型、新扰动、在线适应、Agent、实时性与硬件效果都没有由本轮协议自动证明。

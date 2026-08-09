# Agentic-AUV 下一步路线建议与阶段记录

日期：2026-07-05
主题：EasyUUV + Koopman-MPC + PPO 的下一阶段研究路线
当前方向：跨平台通用性 + Sim2Real 泛化性
当前主链路：PPO → Adapter → Koopman-MPC → PWM → EasyUUV Isaac Physics

---

## 0. 本文定位

这份文档用于记录当前阶段之后的研究判断、问题归因和下一步建议。

核心观点是：

> 当前项目不应继续把目标设定为“在单平台 nominal setting 下，通过 PPO 微调全链路碾压 legacy / S-Surface baseline”。更合理的目标是：证明 PPO + Koopman + MPC 在平台变化、模型失配、扰动增强和 Sim2Real 迁移场景下，具备更好的通用性、泛化性和在线修正能力。

换句话说，后续工作应从“继续调参找 winner”转向“诊断链路瓶颈 + 重构 PPO/MPC 接口 + 构建跨平台评测 + 引入 online Koopman update”。

---

## 1. 当前研究方向的重新定位

### 1.1 不再追求单一平台上的全面碾压

当前 legacy / S-Surface baseline 在 EasyUUV 原始姿态跟踪任务中已经很强。尤其在单平台、固定动力学、固定任务、无明显 domain shift 的设置下，传统控制器具有天然优势：

- 控制链路短；
- 没有 Koopman 预测误差；
- 没有 MPC 求解延迟；
- 没有 fallback 机制；
- 没有 PPO action 到 MPC reference 的语义转换误差。

因此，在 nominal setting 下强行要求 PPO + Koopman-MPC 在 depth RMSE、attitude RMSE、PWM saturation、fallback、latency 等指标上全部优于 legacy，不一定是合理科研目标。

更合理的表达是：

> Legacy / S-Surface 在 nominal setting 下仍是强 baseline；但 Koopman-MPC-PPO 的价值在于面对跨平台动力学变化、扰动增强和 Sim2Real gap 时，能够通过预测模型、优化控制和在线识别机制获得更好的泛化能力。

### 1.2 项目主线应转向“跨平台 + Sim2Real 泛化”

后续主张可以从以下角度展开：

```text
EasyUUV 提供：
  - Isaac Lab 并行仿真；
  - PPO 高层策略；
  - A-S-Surface / legacy 控制基础；
  - Sim2Real 任务验证框架。

Koopman-MPC 提供：
  - 可预测的动力学模型；
  - 可约束的控制优化；
  - 跨平台动力学建模接口；
  - online update 的可扩展入口。

PPO 提供：
  - 高层 reference correction；
  - 跨环境策略选择；
  - 对不同动力学平台的经验适应能力。

Online Koopman update 提供：
  - 面向真实系统漂移的模型修正；
  - 用少量真实数据缩小 Sim2Real gap；
  - 跨平台泛化的核心证据。
```

因此，最终论文/项目主张不应是：

```text
PPO + Koopman-MPC 在所有指标上打败 legacy。
```

而应是：

```text
PPO + Koopman-KF-MPC 在 held-out platform、强扰动、动力学变化和 Sim2Real shift 下，比固定控制器和 offline model 具备更小的性能退化和更强的在线恢复能力。
```

---

## 2. 当前主要问题判断

### 2.1 PPO 微调难以继续带来全链路收益

前面已经完成了 reward、adapter、MPC profile、cross-combination、bounded Pareto sweep 等多轮实验，但没有找到可推广的全指标 winner。

这说明瓶颈很可能不再是简单 PPO 超参数问题，例如：

```text
learning_rate
clip_param
entropy_coef
hidden_dim
training iterations
reward weight
```

更可能是链路结构性问题：

```text
PPO action_4d 的语义是否适合当前 Koopman-MPC？
heuristic adapter 是否把 action 转成了合理 reference？
Koopman 预测模型是否足以支撑 MPC horizon 内优化？
MPC fallback 是否过于保守？
no_cost_improvement fallback 是保护机制还是学习阻断？
PWM / delta bound 是否让候选控制量无法体现收益？
```

### 2.2 当前 adapter 是最大不确定来源之一

当前链路中，PPO 输出 `action_4d`，但 Koopman-MPC 需要的是 `reference_5d`。二者并不是天然同构关系。

当前 `heuristic_reference_delta_v0` 的作用是：

```text
PPO action_4d
  -> depth delta + roll/pitch/yaw delta
  -> 5D reference: [depth_ref, quaternion_ref]
```

这个桥接能够让链路跑通，但不能说明：

```text
旧 PPO action 语义已经无损迁移到 Koopman-MPC reference 语义。
```

因此，后续必须诊断 adapter，而不是继续直接微调 PPO。

### 2.3 fallback 不是单一问题

当前 fallback 至少可能来自：

```text
timeout
no_cost_improvement
candidate infeasible
PWM bound active
delta limit active
prediction mismatch
```

如果只看 fallback rate，会出现误判：

- fallback rate 降低，但 no_cost_improvement 增加；
- latency 改善，但 tracking 变差；
- PWM saturation 改善，但 depth RMSE 变差；
- 单条 trajectory 好看，但 matched eval 不稳定。

因此，后续需要进入 fallback reason-level diagnostics。

---

## 3. 总体下一步路线

建议将后续工作拆成五个核心控制阶段，并把 LLM 作为其后的可选 Agentic 扩展：

```text
Phase 5.5：接口语义与 fallback 诊断
Phase 5.6：Native reference action 重构
Phase 6：跨平台 Koopman dataset 与泛化评估
Phase 7：Online Koopman-KF update
Phase 8：最终 matched evaluation 与核心控制论文主实验
Phase 9：可选 LLM 低频 supervisor
```

该编号是当前 canonical roadmap。旧版 `.planning/ROADMAP.md` 中“Phase 6 = LLM、Phase 7 = online adaptation”的排序已被替换。原因是 Phase 5.4 的服务器证据表明，当前主要风险仍位于 PPO-reference-MPC 接口、fallback 解释和模型泛化；在这些问题关闭前接入 LLM 只会增加变量，不能修复低层控制证据链。

---

# Phase 5.5：接口语义与 fallback 诊断

## 5.5.1 阶段目标

Phase 5.5 的目标不是提升最终性能，而是回答：

> 当前 Phase 5.4 为什么 no_selection？瓶颈到底来自 PPO、adapter、Koopman model、MPC cost，还是 fallback 机制？

这个阶段应当尽量少训练，甚至不训练，优先固定 checkpoint 做离线和短 rollout 诊断。

## 5.5.2 固定 PPO checkpoint

建议固定几个代表性 checkpoint：

```text
baseline_rerun
reward_v1_only
cross_reward_v1_mpc_health
```

然后对它们做相同的 adapter sweep 和 MPC diagnostics。

不要在 Phase 5.5 继续开启大规模 PPO 训练，否则很难区分“训练随机性”和“链路结构问题”。

## 5.5.3 Adapter scale sweep

建议 sweep：

```text
rpy_delta_scale:
  0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35

depth_delta_scale:
  0.05, 0.10, 0.20, 0.30, 0.40, 0.50
```

观察指标：

```text
reference_delta_norm
policy_action_clip_rate
fallback_rate
timeout_fallback_rate
no_cost_improvement_rate
PWM saturation
depth RMSE
attitude RMSE
control smoothness
actual tracking improvement
```

主要判断逻辑：

```text
如果 scale 变小后 fallback 明显下降，但 tracking 变差：
  adapter 可能过强，PPO reference 扰动过大。

如果 scale 变大后 PWM saturation 和 no_cost_improvement 明显升高：
  adapter 可能把 PPO action 放大到了 MPC 难以处理的范围。

如果不同 scale 完全没有规律：
  说明 PPO action 与 reference correction 语义可能不匹配，需要重构 action space。
```

## 5.5.4 MPC diagnostics 增强

建议在 MPC 日志中加入以下字段：

```text
fallback_pwm_cost
mpc_best_cost
cost_improvement_margin = fallback_pwm_cost - mpc_best_cost
candidate_count
feasible_candidate_count
best_candidate_pwm
best_candidate_predicted_error
fallback_predicted_error
actual_next_error
predicted_next_error
prediction_error_gap = actual_next_error - predicted_next_error
active_delta_limit_count
active_pwm_bound_count
```

这些字段可以帮助区分不同失败类型：

```text
MPC 找不到更优解：
  mpc_best_cost >= fallback_pwm_cost

MPC 预测有收益但真实无收益：
  predicted_next_error 低，但 actual_next_error 高

候选动作被约束卡死：
  active_delta_limit_count 或 active_pwm_bound_count 高

PPO reference 本身不合理：
  reference_delta_norm 大、clip 高、fallback 高、tracking 无改善
```

## 5.5.5 输出物

Phase 5.5 最终应输出一份 failure taxonomy：

```text
1. Adapter-induced failure
2. MPC no-cost-improvement failure
3. Koopman prediction-mismatch failure
4. Actuator-bound-limited failure
5. PPO reference semantic failure
6. Timeout / latency failure
```

每一种 failure 都应有证据字段，而不是只凭最终 RMSE 判断。

---

# Phase 5.6：Native reference action 重构

## 5.6.1 阶段目标

如果 Phase 5.5 证明当前 heuristic adapter 语义不稳定，那么应当重构 PPO action space。

核心思想：

> PPO 不再输出旧控制语义下的 action，而是直接输出 Koopman-MPC 原生需要的 reference correction。

## 5.6.2 新 action 定义

建议定义：

```text
action = [
  Δdepth_ref,
  Δroll_ref,
  Δpitch_ref,
  Δyaw_ref
]
```

对应 adapter：

```text
native_reference_delta_v1
```

语义：

```text
PPO 负责修改未来 reference；
Koopman-MPC 负责根据 reference 生成最优 PWM；
AUV physics 负责真实响应。
```

这比当前 `heuristic_reference_delta_v0` 更清晰。

## 5.6.3 为什么要这样改

当前链路的问题是：

```text
旧 PPO action_4d
  -> heuristic adapter
  -> Koopman reference_5d
```

中间存在语义不确定性。

新链路应为：

```text
PPO native reference action
  -> deterministic reference builder
  -> Koopman-MPC
```

这样 PPO 学到的就是“如何给 MPC 提供更好的局部参考”，而不是学习一个历史遗留 action 的再解释。

## 5.6.4 对照实验

建议比较：

```text
heuristic_reference_delta_v0 + PPO
native_reference_delta_v1 + PPO
native_reference_delta_v1 + random policy smoke
native_reference_delta_v1 + scripted policy
```

指标：

```text
training stability
policy_action_clip_rate
reference_delta_norm
fallback reason distribution
closed-loop RMSE
PWM saturation
control smoothness
```

## 5.6.5 阶段结论目标

这个阶段不是一定要显著超过 legacy，而是要证明：

```text
native reference action 的接口更稳定、更可解释，并且更适合 PPO 与 Koopman-MPC 联合训练。
```

---

# Phase 6：跨平台 Koopman dataset 与泛化评估

## 6.1 阶段目标

当前研究目标是“跨平台通用性”和“Sim2Real 泛化性”，因此必须建立 platform split，而不是继续只在一个平台上调参。

Phase 6 的核心任务是生成多平台 Koopman 数据集，并测试 Koopman model 在 held-out platform 上的预测和闭环泛化能力。

## 6.2 平台扰动维度

建议构造以下平台变化：

```text
mass shift:
  mass × 0.8, 1.0, 1.2

volume / buoyancy shift:
  volume × 0.8, 1.0, 1.2

COB-COM offset shift:
  small / medium / large offset

thruster efficiency shift:
  efficiency × 0.7, 0.85, 1.0

hydrodynamic damping shift:
  damping × 0.7, 1.0, 1.3

sensor noise / latency:
  low / medium / high

current disturbance:
  none / mild / strong
```

## 6.3 Train-test split

不要 row-level random split，而应采用 platform-level split。

示例：

```text
Train platforms:
  nominal
  mass +10%
  thruster efficiency -10%
  mild current

Held-out platforms:
  volume +15%
  COB-COM shifted
  damping +30%
  thruster efficiency -25%
  strong current
  combined shift
```

这样才能证明跨平台泛化，而不是同分布拟合。

## 6.4 Koopman model candidates

建议比较：

```text
direct_state Koopman
control-oriented lifted Koopman
conditional Koopman with platform parameters
ensemble Koopman
baseline linear model
persistence baseline
```

其中 conditional Koopman 可以加入平台参数：

```text
x_k
reference_k
u_k
platform_context
```

platform_context 可以包括：

```text
mass estimate
volume estimate
thruster scale
damping scale
current estimate
```

## 6.5 评估指标

不要只看 one-step RMSE。建议包括：

```text
one-step prediction RMSE
multi-step prediction RMSE
prediction divergence rate
closed-loop tracking RMSE
OOD performance drop
worst-case platform RMSE
PWM saturation
fallback reason distribution
energy cost
settling time
overshoot
safety violation count
```

## 6.6 阶段结论目标

Phase 6 应证明：

```text
Koopman model 在平台变化下存在明显模型失配；
跨平台训练或 conditional Koopman 可以改善 held-out platform prediction；
但仅靠 offline Koopman 仍不足以完全解决 Sim2Real shift，需要 online update。
```

这会自然引出 Phase 7。

---

# Phase 7：Online Koopman-KF update

## 7.1 阶段目标

Phase 7 是整个“跨平台 + Sim2Real 泛化”主线的关键。

目标是实现：

```text
offline Koopman prior from simulation
+ online Kalman filter update from limited real / shifted data
+ Koopman-MPC closed-loop control
```

这一步将真正把 Koopman paper 的核心思想接入当前 EasyUUV-Koopman-MPC-PPO 框架。

## 7.2 先在 Isaac 中模拟 Sim2Real shift

不建议一开始就依赖真实水池数据。可以先在 Isaac 中制造 held-out domain shift：

```text
nominal Koopman training platform:
  default mass / volume / damping / thruster

online update test platform:
  mass +10%
  volume +10%
  COB-COM offset changed
  thruster efficiency -20%
  damping +30%
  current disturbance added
```

## 7.3 对比方法

建议至少比较：

```text
Offline Koopman-MPC
Koopman-MPC + RLS
Koopman-MPC + KF
PPO + Offline Koopman-MPC
PPO + Koopman-KF-MPC
legacy / S-Surface
```

如果时间有限，最小对照可以是：

```text
legacy / S-Surface
Offline Koopman-MPC
Koopman-KF-MPC
PPO + Koopman-KF-MPC
```

## 7.4 Online update 输入

每个时间步记录：

```text
state x[k]
reference r[k]
control u[k]
next_state x[k+1]
observable f[k]
observable f[k+1]
prediction error
```

更新对象：

```text
Koopman parameter matrix Θ 或 W
```

## 7.5 KF 更新思路

可以把 Koopman 模型每个输出维度的参数视为待估计变量：

```text
θ_i[k+1] = θ_i[k]
y_i[k+1] = θ_i[k]^T f[k]
```

其中：

```text
θ_i: 第 i 个状态预测方程的参数
f[k]: 当前 observable
目标: 用实际 next_state / next_observable 修正 θ_i
```

核心日志：

```text
prediction_error_before_update
prediction_error_after_update
parameter_update_norm
KF_gain_norm
Q_value
R_value
online_steps_used
```

## 7.6 关键指标

```text
adaptation curve:
  online steps vs prediction RMSE

control recovery curve:
  online steps vs closed-loop tracking RMSE

sample efficiency:
  多少步数据后恢复到 nominal 性能的 80% / 90%

stability:
  online update 是否导致参数发散

robustness:
  combined shift 下是否仍有效
```

## 7.7 阶段结论目标

Phase 7 应证明：

```text
offline Koopman 在 held-out dynamics 下预测和控制性能下降；
KF online update 能用少量数据修正 Koopman model；
更新后的 Koopman-MPC 在扰动和平台变化下恢复控制性能；
PPO + Koopman-KF-MPC 具备更好的 Sim2Real 泛化潜力。
```

---

# Phase 8：最终 matched evaluation 与论文主实验

## 8.1 最终方法命名建议

可以暂定为：

```text
Agentic-AUV-KMPC
PPO-Koopman-KF-MPC
Koopman-Guided Sim2Real PPO
Environment-Aware Koopman-MPC-PPO
```

如果要突出 agentic，可以表述为：

```text
Agentic-AUV: Environment-Aware Koopman-Guided Sim2Real Control for Underwater Vehicles
```

但当前 LLM 尚未接入控制链路，因此论文早期版本最好谨慎使用 agentic。可以先强调：

```text
Koopman-guided cross-platform Sim2Real control
```

等后续真的接入 high-level agent / LLM supervisor 后，再强化 agentic 叙事。

## 8.2 最终对比方法

建议包含：

```text
Legacy / S-Surface
PPO + A-S-Surface
Offline Koopman-MPC
PPO + Offline Koopman-MPC
Koopman-KF-MPC
PPO + Koopman-KF-MPC
```

如果 LLM 后续接入，再增加：

```text
PPO + Koopman-KF-MPC + Agent Supervisor
```

## 8.3 最终测试场景

```text
nominal platform
mass shift
buoyancy shift
COB-COM shift
thruster degradation
hydrodynamic damping shift
sensor noise
current disturbance
combined shift
held-out platform
```

## 8.4 最终指标

```text
Depth RMSE
Attitude RMSE
Compound error
Overshoot
Settling time
Steady-state error
PWM saturation
Control smoothness
Energy cost
Fallback rate
Fallback reason distribution
Latency mean / max / violation rate
Prediction RMSE
Online adaptation speed
OOD performance drop
Worst-case platform performance
Safety violation count
```

## 8.5 预期结论表达

理想结论不是：

```text
我们的系统在所有场景下都比 legacy 更强。
```

而是：

```text
在 nominal platform 上，legacy / S-Surface 仍然是强 baseline；
但在 held-out platform、动力学漂移和强扰动条件下，固定控制器和 offline Koopman 的性能明显下降；
引入 online Koopman-KF update 后，模型预测误差和闭环控制误差能够用少量数据快速恢复；
PPO 作为 high-level reference generator 与 Koopman-KF-MPC 结合后，在跨平台 Sim2Real setting 下表现出更好的泛化性和稳定性。
```

这类结论更加可信，也更符合当前项目实际证据路径。

---

## 9. 当前不要急着做的事情

### 9.1 不要继续盲目 PPO 调参

除非 Phase 5.5 明确证明问题只来自 reward 权重或训练不足，否则不建议继续：

```text
调 learning rate
调 entropy
调 hidden dims
单纯增加 iteration
继续 sweep reward 小参数
```

这些很可能只会增加实验量，而不会改变结构性瓶颈。

### 9.2 不要过早接入 LLM

当前 LLM 尚未进入代码闭环。此时接入 LLM 容易让系统复杂度进一步上升，但不解决核心问题：

```text
PPO action 语义
MPC fallback
Koopman prediction mismatch
跨平台评估缺失
online update 缺失
```

建议 LLM / Agent 后置到 Phase 8 之后，作为 Phase 9 高层 supervisor：

```text
检测环境变化；
选择控制 profile；
触发 online update；
调整安全阈值；
解释模型失配原因。
```

### 9.3 不要直接声明 Koopman-MPC 已优于 legacy

当前证据更适合说：

```text
Koopman-MPC 链路已经跑通；
PPO-Koopman-MPC training path 已经打通；
但 controller-only 和 Phase 5.4 结果尚未证明其在 nominal setting 下优于 legacy。
```

后续应通过跨平台和 Sim2Real shift 重新定义优势场景。

---

## 10. 推荐近期执行清单

### 本周优先级 P0

```text
1. 冻结当前 Phase 5.4 结果，不再继续同类 reward/MPC sweep。
2. 增加 MPC cost diagnostics 字段。
3. 固定 checkpoint 做 adapter scale sweep。
4. 输出 fallback reason-level report。
```

### 本周优先级 P1

```text
5. 设计 native_reference_delta_v1 action space。
6. 实现 native adapter smoke test。
7. 与 heuristic_reference_delta_v0 做短 rollout 对照。
```

### 下一阶段优先级 P0

```text
8. 构建 multi-platform Isaac config。
9. 生成 platform-level train/test Koopman dataset。
10. 评估 offline Koopman 的 OOD prediction drop。
```

### 下一阶段优先级 P1

```text
11. 实现 RLS online Koopman update baseline。
12. 实现 KF online Koopman update。
13. 做 held-out platform adaptation curve。
```

---

## 11. 可以写进阶段汇报的表述

可以说：

```text
目前 PPO-Koopman-MPC 全链路已经打通，但多轮 reward、adapter 和 MPC 小参数搜索没有产生可推广的全指标 winner。我们认为主要瓶颈不再是 PPO 超参数，而是 PPO action 到 Koopman-MPC reference 的接口语义、MPC fallback 机制和 offline Koopman 在 domain shift 下的模型失配。因此下一步将从盲目调参转为结构诊断，并将研究重点转向跨平台泛化和 Sim2Real 适应能力。
```

也可以说：

```text
后续工作将不再以 nominal setting 下全面超过 legacy/S-Surface 为唯一目标，而是建立 platform-level split 和 held-out dynamics evaluation，重点验证 Koopman-KF online update 在平台变化和环境扰动下对模型预测与闭环控制性能的恢复能力。
```

---

## 12. 最终路线一句话总结

> 停止盲调 PPO；先诊断 PPO-reference-MPC 接口和 fallback 机制；再重构 native reference action；随后建立跨平台 Koopman 数据集；最后引入 online Koopman-KF update，把项目主线从“单平台调参优化”提升为“跨平台 Sim2Real 泛化控制框架”。

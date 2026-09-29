# EasyUUV Koopman-MPC-PPO 参数与阶段工作总结

日期：2026-07-05
分支：`isaaclab2-migration`
服务器：`agentic-AUV`
Isaac 环境：Isaac Sim 5.0 + Isaac Lab 2.2.1

这份文档做两件事：

1. 整理目前代码中已经形成合同的主要参数。
2. 解释到 Phase 5.4 为止我们实际做过的代码工作、上下游连接和遇到的难点。

本文只写已经在代码、summary 或服务器结果中有依据的内容。不声明 LLM 已接入，不声明 PPO 已收敛，不声明 Koopman-MPC 已优于 legacy。

## 1. 当前控制链路总览

目前项目里已经形成的主链路是：

```text
9D observation
  -> RSL-RL PPO policy
  -> 4D action
  -> heuristic_reference_delta_v0 adapter
  -> 5D Koopman reference
  -> direct_state Koopman+MPC
  -> 8D PWM
  -> EasyUUV Isaac physics
```

各层含义：

| 层 | 当前实现 | 输入 | 输出 | 说明 |
|---|---|---|---|---|
| PPO | RSL-RL PPO | `obs_9d` | `action_4d` | 高层策略，不直接输出 PWM。 |
| Adapter | `heuristic_reference_delta_v0` | `action_4d + base_reference_5d` | `adapted_reference_5d` | 把 PPO correction 转成 Koopman-MPC reference。 |
| Koopman model | `direct_state` selected manifest | `state_11d + reference_5d + pwm_8d` | predicted next state | 当前默认低层模型。 |
| MPC | Pure NumPy bounded PWM optimizer | current state/reference/model | `pwm_8d` | 有 timeout、fallback、latency diagnostics。 |
| Isaac env | EasyUUV / Isaac Lab 2.2.1 | `pwm_8d` | next sim state | 保留原 EasyUUV 推进器、流体动力学后处理。 |

当前没有进入主链路的内容：

| 内容 | 当前状态 |
|---|---|
| LLM | 尚未接入代码链路。后续可做任务规划或低频调参，但目前不是控制闭环的一部分。 |
| paper-style lifted EDMD | 已做论文风格对照和闭环 smoke，但当前结果不能作为默认底层控制器。 |
| online Koopman learning | 没有实现实时增量训练/RLS/Kalman 更新。当前 Koopman 是离线训练、离线选择、在线固定使用。 |

## 2. 数据、维度与日志参数

### 2.1 Koopman JSONL 单条样本

Phase 1 定义了离线可读的 Koopman 数据格式：

```text
t
state
reference
action_4d
pwm_8d
next_state
trajectory_type
controller_mode
```

核心维度：

| 字段 | 维度 | 用途 |
|---|---:|---|
| `state` | 11 | 当前 AUV 状态。 |
| `reference` | 5 | 深度和姿态参考。 |
| `action_4d` | 4 | legacy/PPO 的中间高层动作。 |
| `pwm_8d` | 8 | Koopman 训练和 MPC 控制使用的实际控制输入。 |
| `next_state` | 11 | 下一步状态监督信号。 |

训练 Koopman 时使用的是 `pwm_8d`，不是 `action_4d`。原因是 `pwm_8d` 更接近进入推进器映射前的实际控制量；`action_4d` 是 legacy controller 或 PPO 的中间语义。

### 2.2 PPO/Koopman JSONL 补充字段

Phase 4.5 之后，PPO/Koopman 日志额外记录：

| 字段 | 含义 |
|---|---|
| `adapter_mode` | 当前 adapter 版本，例如 `heuristic_reference_delta_v0`。 |
| `ppo_evidence_level` | 证据等级，例如 `stub_only`、`phase5_4_pareto_matched_eval`。 |
| `policy_mode` | `stub` 或 `checkpoint`。 |
| `backend_used` | Koopman backend，例如 `direct_state`。 |
| `solver_diagnostics` | MPC fallback、latency、fallback reason 等。 |
| `policy_action_clip_rate` | PPO 4D action 被 adapter clip 的比例。 |
| `checkpoint_provenance_valid` | checkpoint 是否来自对应训练阶段。 |

## 3. Koopman 模型参数

### 3.1 Direct-state Koopman

当前工程默认 Koopman-MPC backend 是 `direct_state`。形式是：

```text
phi_k = lift(x_k, r_k)
z_k   = [phi_k, u_k]
x_hat_{k+1} = W z_k
```

训练用 ridge EDMD：

```text
W* = argmin_W || Z W^T - Y ||_2^2 + lambda || W ||_2^2
```

其中：

```text
x_k in R^11
r_k in R^5
u_k in R^8
x_{k+1} in R^11
```

对应代码职责：

| 文件 | 职责 |
|---|---|
| `koopman/dataset.py` | 从 JSONL 构建 `X/U/R/Y/t` 数据矩阵。 |
| `koopman/lifting.py` | direct-state 模型使用的 lifting。 |
| `koopman/edmd.py` | ridge EDMD 拟合。 |
| `koopman/model.py` | direct-state 模型保存、加载、预测。 |
| `koopman/runtime.py` | 根据 selected manifest 加载模型并做维度/gate 检查。 |

### 3.2 Paper-style lifted EDMD

论文风格对照 backend 使用 lifted observable evolution：

```text
f_k = psi(x_k, r_k, u_k)
f_hat_{k+1} = Theta^T f_k
x_hat_{k+1} = state_slice(f_hat_{k+1})
```

当前 observable 至少包含：

```text
x_k
x_k[:5] - r_k
u_k
selected velocity/rate squared terms
u_k squared
bias
```

对应代码职责：

| 文件 | 职责 |
|---|---|
| `koopman/observables.py` | paper-style observable 构造。 |
| `koopman/lifted_edmd.py` | lifted EDMD 训练和预测。 |
| `workflows/evaluate_paper_lifted_backend.py` | paper lifted backend 对照评估。 |

结论依据：Phase 4 controller-only evaluation 中，`paper_lifted_edmd` 的 depth RMSE 约为 `13-14`，明显不能作为 Phase 4.5/5 默认底层控制器。

## 4. MPC 参数

MPC 目标函数的工程形式：

```text
min sum_t [
  tracking_cost(x_t, r_t)
  + control_energy_cost(u_t)
  + control_smoothness_cost(u_t - u_{t-1})
]
```

约束：

```text
x[t+1] = KoopmanPredict(x[t], u[t], r[t])
-1 <= u[t,i] <= 1
|u[t,i] - u[t-1,i]| <= delta_pwm_limit
```

当前 MPC profile：

| Profile | `delta_pwm_limit` | `depth_weight` | `attitude_weight` | `control_weight` | `smoothness_weight` | 用途 |
|---|---:|---:|---:|---:|---:|---|
| `mpc_default_v0` | 0.35 | 1.0 | 1.0 | 0.01 | 0.05 | 默认工程 profile。 |
| `mpc_health_v1` | 0.35 | 1.0 | 1.0 | 0.03 | 0.10 | 增强 control/smoothness 健康约束。 |
| `mpc_delta_limit_probe_v1` | 0.25 | 1.0 | 1.0 | 0.03 | 0.10 | 更强 PWM 变化限制的 probe，未作为默认。 |

常用运行参数：

| 参数 | 常用值 | 来源/说明 |
|---|---:|---|
| `mpc_horizon` | 5 | Phase 3/4 默认，Phase 5.4 有 `horizon=4` probe。 |
| `mpc_timeout_ms` | 12.0 | 默认 timeout。Phase 5.4 测过 14/16。 |
| `mpc_delta_pwm_limit` | 0.35 | 默认 actuator delta guard。 |
| latency hard gate | mean < 20 ms, max < 50 ms | Phase 5.4 selection gate。 |
| latency violation gate | `<= 0.10` | Phase 5.4 selection gate。 |

MPC fallback reason 当前重点记录：

| Reason | 含义 |
|---|---|
| `timeout` | 求解超时或时间预算触发 fallback。 |
| `no_cost_improvement` | MPC 候选没有比 fallback/hold baseline 更好。 |

Phase 5.4 证明：只增加 timeout 或减小 regularization 不一定更健康，因为可能把 `timeout` fallback 转移成 `no_cost_improvement` fallback。

## 5. Adapter 参数

当前 adapter 固定为：

```text
heuristic_reference_delta_v0
```

映射逻辑：

```text
policy_output_4d = [roll_delta, pitch_delta, yaw_delta, depth_delta]
base_reference_5d = [depth_ref, qw, qx, qy, qz]

adapted_depth = clip(base_depth + depth_delta_scale * clipped_depth_delta)
adapted_quat = normalize(base_quat * quat_from_scaled_rpy_delta)
adapted_reference_5d = [adapted_depth, adapted_quat]
```

Adapter profiles：

| Profile | `policy_action_limit` | `rpy_delta_scale` | `depth_delta_scale` | `depth_min/max` | 状态 |
|---|---:|---:|---:|---|---|
| `heuristic_reference_delta_v0_default` | 1.0 | 0.35 | 0.50 | -3.0 / 3.0 | 默认。 |
| `adapter_scale_soft_v1` | 1.0 | 0.30 | 0.40 | -3.0 / 3.0 | Phase 5.2/5.3 probe。 |
| `adapter_scale_soft_v2` | 1.0 | 0.25 | 0.30 | -3.0 / 3.0 | 预留更强 soft 版本。 |

边界：

```text
adapter 只是工程桥接，不声明旧 PPO 的 action 语义已无损迁移。
```

## 6. Reward 参数

Phase 5.2 增加了 Koopman-MPC training health reward：

```text
total_reward = legacy_reward - health_penalty
```

其中：

```text
health_penalty =
  w_fallback * fallback_used
  + w_pwm_sat * pwm_saturation_excess
  + w_latency * latency_ratio
  + w_action * ||action||^2
  + w_delta_action * ||action_delta||^2
```

`koopman_mpc_stability_v1` 默认参数：

| 参数 | 值 | 含义 |
|---|---:|---|
| `pwm_soft_limit` | 0.90 | 超过该绝对 PWM 后开始计 saturation penalty。 |
| `latency_ref_ms` | 20.0 | latency penalty 的参考阈值。 |
| `latency_clip` | 3.0 | latency penalty ratio 上限。 |
| `w_fallback` | 0.30 | fallback 惩罚。 |
| `w_pwm_sat` | 0.20 | PWM saturation 惩罚。 |
| `w_latency` | 0.05 | latency 惩罚。 |
| `w_action` | 0.01 | action magnitude 惩罚。 |
| `w_delta_action` | 0.02 | action delta 惩罚。 |

Reward profiles：

| Profile | 含义 |
|---|---|
| `legacy_easyuuv_v0` | 原 EasyUUV reward，不加入 Phase 5.2 health penalty。 |
| `koopman_mpc_stability_v1` | 在 legacy reward 上扣除 fallback、PWM saturation、latency、action、action delta penalty。 |

## 7. PPO 参数

当前 PPO 来自 RSL-RL，配置在 `agents/rsl_rl_ppo_cfg.py`。

基础配置：

| 参数 | 默认值 |
|---|---:|
| `num_steps_per_env` | 24 |
| `max_iterations` | 800 |
| `save_interval` | 50 |
| `empirical_normalization` | false |
| actor hidden dims | [64, 64] |
| critic hidden dims | [64, 64] |
| activation | elu |
| init noise std | 1.0 |

PPO algorithm：

| 参数 | 值 |
|---|---:|
| `value_loss_coef` | 1.0 |
| `use_clipped_value_loss` | true |
| `clip_param` | 0.2 |
| `entropy_coef` | 0.0 |
| `num_learning_epochs` | 5 |
| `num_mini_batches` | 4 |
| `learning_rate` | 5e-4 |
| `schedule` | adaptive |
| `gamma` | 0.99 |
| `lam` | 0.95 |
| `desired_kl` | 0.01 |
| `max_grad_norm` | 1.0 |

实验中实际用过的训练长度：

| 阶段 | 训练长度 | 用途 |
|---|---:|---|
| Phase 4.6 smoke | 1 iteration | 证明 checkpoint 生成和加载路径。 |
| Phase 5 smoke | 1 iteration | 证明 PPO 能进入 Koopman-MPC training path。 |
| Phase 5.2 | 200 iterations | one-factor ablation。 |
| Phase 5.3 sentinel | 50 iterations | cross-combination 安全检查。 |
| Phase 5.3 candidate | 200 iterations | cross-combination matched eval。 |
| Phase 5.4 sentinel | 50 iterations | bounded parameter sweep 安全检查。 |
| Phase 5.4 candidate | 200 iterations | 11 个 profile 的 matched eval。 |

## 8. Phase 5 profile 参数

### 8.1 Phase 5.2 one-factor profiles

| Profile | Reward | Adapter | MPC | 目的 |
|---|---|---|---|---|
| `baseline_rerun` | `legacy_easyuuv_v0` | default | default | PPO-Koopman-MPC baseline rerun。 |
| `reward_v1_only` | `koopman_mpc_stability_v1` | default | default | 单独测试 health reward。 |
| `adapter_soft_v1_only` | legacy | `adapter_scale_soft_v1` | default | 单独测试 softer adapter。 |
| `mpc_health_v1_only` | legacy | default | `mpc_health_v1` | 单独测试更强 MPC control/smoothness。 |
| `mpc_delta_limit_probe_v1` | legacy | default | `mpc_delta_limit_probe_v1` | 预留 delta limit probe，不作为初始主候选。 |

Phase 5.2 matched eval 均值：

| Profile | Fallback | PWM Sat | Clip | Latency ms | Depth RMSE | Attitude RMSE |
|---|---:|---:|---:|---:|---:|---:|
| `baseline_rerun` | 0.2333 | 0.2293 | 0.0517 | 11.8990 | 0.8564 | 0.8135 |
| `reward_v1_only` | 0.1248 | 0.3379 | 0.1393 | 11.7225 | 0.9360 | 0.7434 |
| `adapter_soft_v1_only` | 0.1114 | 0.3963 | 0.1088 | 11.7759 | 1.0074 | 0.7449 |
| `mpc_health_v1_only` | 0.1524 | 0.3731 | 0.4952 | 11.7458 | 2.0573 | 0.7004 |

Phase 5.2 结论：

```text
reward_v1_only 是 best balanced candidate，但不能 full promotion。
主要原因：fallback 明显改善，但 PWM saturation 从 0.2293 升到 0.3379。
```

### 8.2 Phase 5.3 cross-combination profiles

| Profile | Reward | Adapter | MPC | 风险 |
|---|---|---|---|---|
| `cross_reward_v1_adapter_soft` | reward v1 | soft v1 | default | medium |
| `cross_reward_v1_mpc_health` | reward v1 | default | health v1 | high |
| `cross_adapter_soft_mpc_health` | legacy | soft v1 | health v1 | high |
| `cross_reward_v1_adapter_soft_mpc_health` | reward v1 | soft v1 | health v1 | very high，sentinel only |

Phase 5.3 matched eval 均值：

| Profile | Fallback | PWM sat | Clip | Depth RMSE | Attitude RMSE | Latency ms | Health score | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `cross_reward_v1_adapter_soft` | 0.1514 | 0.3748 | 0.0000 | 1.7543 | 0.7512 | 11.7670 | -0.0513 | fail |
| `cross_reward_v1_mpc_health` | 0.3105 | 0.1192 | 0.0400 | 0.7173 | 0.7354 | 11.8692 | 0.1846 | fail |
| `cross_adapter_soft_mpc_health` | 0.2724 | 0.2094 | 0.4683 | 0.5022 | 0.7769 | 11.9155 | -0.1977 | fail |

Phase 5.3 结论：

```text
selection_status = no_selection
best_non_promoted_profile_id = cross_reward_v1_mpc_health
```

有用信号：

```text
MPC health weights 能改善 PWM saturation、clip、depth、attitude，
但会把 fallback 推高到 0.3105。
```

### 8.3 Phase 5.4 bounded Pareto profiles

Phase 5.4 参数距离定义：

```text
parameter_distance_from_parent =
  sum(abs(candidate_value - parent_value) / step_size(parameter))
```

step size：

| 参数 | Step |
|---|---:|
| `phase5_2_w_pwm_sat` | 0.05 |
| `phase5_2_w_fallback` | 0.05 |
| `phase5_2_w_action` | 0.005 |
| `phase5_2_w_delta_action` | 0.01 |
| `mpc_timeout_ms` | 2.0 |
| `mpc_control_weight` | 0.005 |
| `mpc_smoothness_weight` | 0.015 |
| `mpc_horizon` | 1.0 |

Track R parent：

```text
parent = reward_v1_only
w_fallback = 0.30
w_pwm_sat = 0.20
w_action = 0.01
w_delta_action = 0.02
mpc = default
adapter = default
```

Track RM parent：

```text
parent = cross_reward_v1_mpc_health
mpc_horizon = 5
mpc_timeout_ms = 12.0
mpc_control_weight = 0.03
mpc_smoothness_weight = 0.10
reward = reward_v1
adapter = default
```

Phase 5.4 Round 1 参数矩阵和结果：

| Profile | Track | Changed parameters | Distance | Fallback | PWM sat | Clip | Depth | Att | Gate result |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| `r_pwm025` | R | `w_pwm_sat=0.25` | 1.0 | 0.2638 | 0.1625 | 0.1964 | 1.1044 | 0.7596 | lost reward fallback |
| `r_pwm030` | R | `w_pwm_sat=0.30` | 2.0 | 0.2219 | 0.1550 | 0.4664 | 0.5909 | 0.7835 | lost reward fallback |
| `r_pwm035` | R | `w_pwm_sat=0.35` | 3.0 | 0.2895 | 0.0933 | 0.0000 | 0.8239 | 0.7231 | lost reward fallback |
| `r_pwm030_action_smooth` | R | `w_pwm_sat=0.30`, `w_action=0.015`, `w_delta_action=0.03` | 4.0 | 0.2419 | 0.0985 | 0.2655 | 0.4838 | 0.7610 | lost reward fallback |
| `r_pwm030_fallback025` | R | `w_pwm_sat=0.30`, `w_fallback=0.25` | 3.0 | 0.3048 | 0.2199 | 0.1710 | 1.3556 | 0.8000 | lost reward fallback |
| `rm_timeout14` | RM | `timeout=14` | 1.0 | 0.0971 | 0.1156 | 0.2686 | 1.0880 | 0.7696 | lost MPC clip/depth/attitude |
| `rm_timeout16` | RM | `timeout=16` | 2.0 | 0.1171 | 0.3352 | 0.1462 | 0.6524 | 0.8755 | no_cost fallback increased |
| `rm_midweights` | RM | `control=0.02`, `smoothness=0.075` | 3.67 | 0.1971 | 0.2305 | 0.0602 | 0.8739 | 0.7874 | lost MPC strengths |
| `rm_midweights_timeout14` | RM | `control=0.02`, `smoothness=0.075`, `timeout=14` | 4.67 | 0.1248 | 0.2938 | 0.0090 | 1.1573 | 0.7319 | no_cost fallback increased |
| `rm_lightweights_timeout14` | RM | `control=0.015`, `smoothness=0.06`, `timeout=14` | 6.67 | 0.0886 | 0.4219 | 0.1386 | 2.1112 | 0.7936 | lost MPC strengths |
| `rm_horizon4_timeout14` | RM | `horizon=4`, `control=0.02`, `smoothness=0.075`, `timeout=14` | 5.67 | 0.2390 | 0.0206 | 0.0726 | 0.5289 | 0.7391 | no_cost fallback increased |

Phase 5.4 结论：

```text
selection_status = no_selection
selected_profile_id = null
Round 1 sentinel = 11/11
Round 1 candidate = 11/11
matched eval = step/sine/irregular for every candidate
Round 2 = skipped by diagnostic-stop rule because no Round 1 candidate was promotable
```

## 9. Selection gate 参数

Phase 5.4 health score：

```text
health_score =
  0.25 * pwm_saturation_improvement
  + 0.25 * fallback_improvement
  + 0.20 * clip_improvement
  + 0.20 * depth_rmse_improvement
  + 0.10 * attitude_rmse_improvement
  - 0.05 * parameter_distance_penalty
```

硬门槛：

| Gate | 条件 |
|---|---|
| Finite logs | 日志中关键数值不能 NaN/Inf。 |
| PWM bounds | PWM 必须在 `[-1, 1]` 内。 |
| Provenance | checkpoint 必须来自对应阶段。 |
| Matched eval | step/sine/irregular 日志必须验证通过。 |
| Latency mean | `< 20 ms` |
| Latency max | `< 50 ms` |
| Latency violation rate | `<= 0.10` |
| Fallback reason | 不能把 timeout 改善换成 no_cost_improvement 恶化。 |

selection status：

| 状态 | 含义 |
|---|---|
| `full_pass` | 达到 baseline_rerun health floor，并通过 track protected-strength guard。 |
| `track_pass` | 保住本 track 的关键强项，并修复主要短板，但不一定所有指标都赢。 |
| `promising_partial` | 有明确信号，但仍有关键瓶颈。 |
| `no_selection` | 不能推广，只输出 Pareto report。 |

## 10. 到目前为止代码做了什么

### 10.1 Phase 1：legacy controller 边界和 Koopman 数据

目的：

```text
先不替换控制器，只把 legacy/Ssurface 的输入输出边界记录清楚，
为 Koopman 离线训练提供真实 Isaac 轨迹数据。
```

代码思路：

- 在 `easyuuv_env.py` 中保留原 `control_method`，新增 `controller_mode` 概念。
- 在推进器转换前缓存 `_last_pwm_8d`。
- 新增 JSONL helper，把 `state/reference/action_4d/pwm_8d/next_state` 统一写出。
- 改造 `play_controller.py` 等 workflow，使 direct controller 不依赖 PPO checkpoint 也能采数据。

证据：

```text
Phase 1 local tests: 5 passed
Phase 1 sample schema validated later on server
```

### 10.2 Phase 2：离线 Koopman identification

目的：

```text
把 Phase 1 的日志变成可训练的 Koopman 模型。
```

代码思路：

- JSONL 转矩阵。
- 实现 direct-state lifting。
- 实现 ridge EDMD。
- 保存/加载模型，并做 one-step/multi-step RMSE 评估。

证据：

```text
Phase 2 local tests: 36 passed
CLI train/evaluate help passed
```

### 10.3 Phase 2.5：模型准入 gate

目的：

```text
不让一个只在训练日志上好看的模型直接进入闭环 MPC。
```

代码思路：

- 增加 log-level split，避免 row-level random split 导致时间序列泄漏。
- 增加 persistence/simple-linear baseline。
- 增加 direct_state 与 paper_lifted_edmd sweep。
- 增加 divergence-aware multi-step evaluation。
- 输出 `selected_model_manifest.json` 和 gate report。

重要原则：

```text
Phase 3 只读 selected manifest，不手写模型路径或维度。
```

### 10.4 Phase 3：Koopman+MPC 控制器接入

目的：

```text
把离线选出的 Koopman 模型放进 EasyUUV 闭环控制，替代 pre-thrust PWM 选择。
```

代码思路：

- runtime loader 负责 manifest-first 加载和维度检查。
- MPC 负责有界 PWM、delta limit、tracking/control/smoothness cost。
- controller adapter 把当前 state/reference/previous PWM/legacy fallback PWM 送入 MPC。
- `easyuuv_env.py` 增加 `controller_mode == "koopman_mpc"` 分支，但不改推进器和水动力后处理。

服务器 smoke：

```text
samples = 2
backend_used = direct_state
fallback_count = 0
latency_avg_ms = 11.8577
latency_max_ms = 11.8963
pwm_min = 0.65
pwm_max = 1.0
```

边界：

```text
Phase 3 证明链路能跑，不证明性能优于 legacy。
```

### 10.5 Phase 4：controller-only baseline

目的：

```text
在 PPO/LLM 进入前，先测低层控制器本身。
```

链路：

```text
scripted trajectory/reference -> controller -> 8D PWM -> AUV
```

服务器矩阵：

| Controller | Backend | step | sine | irregular |
|---|---|---:|---:|---:|
| legacy | Ssurface | pass | pass | pass |
| Koopman+MPC | direct_state | pass | pass | pass |
| Koopman+MPC | paper_lifted_edmd | pass | pass | pass |

核心指标：

| Trajectory | Controller | Backend | Depth RMSE | Attitude RMSE | Fallback | Max latency ms |
|---|---|---|---:|---:|---:|---:|
| step | legacy | legacy | 0.3988 | 0.9542 | 0.000 | 0.000 |
| step | Koopman+MPC | direct_state | 1.0372 | 2.0443 | 0.118 | 13.957 |
| step | Koopman+MPC | paper_lifted_edmd | 14.2359 | 1.0990 | 0.166 | 13.385 |
| sine | legacy | legacy | 0.3980 | 0.7840 | 0.000 | 0.000 |
| sine | Koopman+MPC | direct_state | 0.8985 | 2.2372 | 0.106 | 13.657 |
| sine | Koopman+MPC | paper_lifted_edmd | 13.4571 | 0.9059 | 0.171 | 12.868 |
| irregular | legacy | legacy | 0.3742 | 1.0556 | 0.000 | 0.000 |
| irregular | Koopman+MPC | direct_state | 0.5514 | 1.3625 | 0.387 | 16.155 |
| irregular | Koopman+MPC | paper_lifted_edmd | 14.2464 | 1.0831 | 0.199 | 12.901 |

结论：

```text
legacy/Ssurface 仍是 controller-only 最稳 baseline。
direct_state Koopman+MPC 可跑，但 fallback/tracking 仍需优化。
paper_lifted_edmd 目前不能作为默认低层控制器。
```

### 10.6 Phase 4.5：PPO/RL reference adapter

目的：

```text
让 PPO 的 4D action 能进入 Koopman+MPC，但不假设旧 action 语义无损迁移。
```

代码思路：

- 新增 `heuristic_reference_delta_v0`。
- 新增 PPO/Koopman log validator。
- 新增 checkpoint discovery。
- 新增 `play_ppo_koopman.py`，支持 stub/checkpoint。
- 先做 stub smoke，再找 PPO checkpoint。

服务器 stub smoke：

```text
samples = 350
ppo_evidence_level = stub_only
backend_used = direct_state
pwm_min = -1.0
pwm_max = 1.0
policy_action_clip_rate_max = 0.0
fallback_count = 98
fallback_rate = 0.28
latency_ms_mean = 11.8720
latency_ms_max = 12.3861
```

重要结论：

```text
adapter/control boundary 可跑，但这不是 PPO 性能证据。
```

### 10.7 Phase 4.6：PPO checkpoint evidence gate

目的：

```text
先证明 RSL-RL PPO 能在 Isaac Lab 2.2.1 下生成 checkpoint，并能被加载评估。
```

代码思路：

- 迁移 `train.py`、`play_eval.py`、`gen_policy.py` 到 Isaac Lab 2.2.1 app/import pattern。
- 增加 `--save_interval`，让 1-iteration smoke 能生成 checkpoint。
- checkpoint discovery 明确 `selected_checkpoint` 和 `selected_rule`。
- legacy PPO baseline smoke 与 old-checkpoint adapter smoke 分开记录。

服务器结果：

```text
training entrypoint smoke: checkpoint_found = true
checkpoint generation smoke: selected_rule = latest_mtime_model_pt
legacy PPO baseline smoke: 2 samples, controller_modes = legacy/Ssurface
old-checkpoint adapter smoke: 2 samples, fallback_used = false for both samples
```

边界：

```text
Phase 4.6 证明 checkpoint 机制，不证明 PPO 收敛。
```

### 10.8 Phase 5：Koopman-MPC PPO retraining smoke

目的：

```text
证明 PPO training step 真走 PPO -> adapter -> Koopman+MPC 路径。
```

代码思路：

- 新增 `Phase5KoopmanReferenceWrapper`。
- 在 RSL-RL `env.step(action_4d)` 前刷新 Koopman reference。
- 训练 summary 记录 adapter refresh、checkpoint provenance、维度、PWM bounds。
- evaluation 前验证 checkpoint provenance。

服务器 smoke：

```text
training_iterations = 1
adapter_refresh_count = 24
adapter_refresh_before_env_step = true
training policy_action_clip_rate = 0.5
selected_checkpoint = model_0.pt

eval samples = 2
fallback_rate = 0.0
latency_ms_mean = 11.4967
latency_ms_max = 11.5390
pwm_min = 0.65
pwm_max = 1.0
```

边界：

```text
这是 retrained-policy smoke，不是稳定训练和收敛证据。
```

### 10.9 Phase 5.1：稳定训练 gate 规划与支持

目的：

```text
把 Phase 5 的 1-iteration smoke 扩展为可追溯的 stability_sentinel / stability_candidate / matched_stability_eval gate。
```

已形成的计划和代码方向：

- evidence level：`stability_sentinel`、`stability_candidate`、`matched_stability_eval`。
- provenance：防止 Phase 5 smoke checkpoint 被误标成稳定训练 checkpoint。
- training health summary：记录 fallback、latency、PWM、nonfinite counts、adapter refresh。
- selected checkpoint manifest：让后续 Phase 5.2/5.3 能使用明确的 PPO checkpoint 来源。

注意：本文没有写 Phase 5.1 的服务器指标，因为当前可查证 summary 主要是方案和 gate，不是完整服务器结果表。

### 10.10 Phase 5.2：one-factor reward/adapter/MPC ablation

目的：

```text
稳定训练后，单因素比较 reward、adapter、MPC 哪个方向有改善信号。
```

服务器执行：

```text
4 profiles
200 iterations each
step/sine/irregular matched eval
350 samples per trajectory
all 12 PPO/Koopman logs validated
```

结论：

```text
reward_v1_only 是当前 best balanced candidate，
但 PWM saturation 变差，不能 full promotion。
```

### 10.11 Phase 5.3：cross-combination screening

目的：

```text
测试用户提出的交叉组合，例如 reward_v1 + adapter_soft 是否会更好。
```

服务器执行：

```text
3 pairwise profiles 完成 50-iteration sentinel、200-iteration candidate、matched eval。
triple cross 只跑 sentinel，没有推广。
```

结论：

```text
selection_status = no_selection
best_non_promoted_profile_id = cross_reward_v1_mpc_health
```

有价值信号：

```text
reward_v1 + mpc_health 改善 PWM/clip/depth/attitude，
但 fallback 从 0.1248 升到 0.3105。
```

### 10.12 Phase 5.4：dual-track reward/MPC Pareto sweep

目的：

```text
围绕 reward_v1_only 和 cross_reward_v1_mpc_health 两个信号做 bounded 参数搜索，
希望找到小参数、全指标更均衡的 profile。
```

代码思路：

- 新增 Phase 5.4 profile registry。
- 新增 parameter distance 和 small-parameter-first rule。
- 新增 latency max / violation-rate gate。
- 新增 fallback reason gate。
- 新增 selector 和 refinement planner。
- 新增远程 sweep 脚本，完整执行 sentinel、candidate、matched eval、selection。

服务器结果：

```text
Round 1 sentinels = 11/11 completed
Round 1 candidates = 11/11 completed
matched eval = step/sine/irregular for every candidate
selection_status = no_selection
selected_profile_id = null
```

结论：

```text
只调 reward/MPC 小参数不足以找到全指标 winner。
下一步更可能要诊断 adapter/reference action 语义和 no_cost_improvement fallback 机制。
```

## 11. 遇到的主要难点

### 11.1 Isaac Sim 与 Isaac Lab 版本迁移

问题：

```text
原先预期的 Isaac Lab 版本与服务器实际环境不一致。
服务器最终使用 Isaac Sim 5.0 + Isaac Lab 2.2.1。
```

表现：

- 直接 import `isaaclab` 曾出现 `omni.log` 缺失。
- 需要先通过 `AppLauncher` 启动 Isaac app，再 import Omni/Isaac 相关模块。
- `parse_env_cfg()` 的参数签名和旧代码不一致，需要改成 Isaac Lab 2.2.1 可用方式。

处理：

- 增加 `isaaclab_app.py` / `isaaclab_compat.py` 一类兼容入口。
- 统一 workflow 先启动 app，再注册 task，再创建 gym env。
- 服务器端验证 `pytest` 和 `compileall`。

### 11.2 USD 模型和 articulation/root 类型问题

问题：

```text
最初服务器没有正确拿到 USD；后来放入 model.usd。
USD 中存在 articulation root，但代码按 RigidObject 加载会报错。
```

处理：

- 从代码侧按 Isaac Lab 2.2.1 的资产配置处理 articulation root。
- 之后环境能正常创建并开始 rollout。

### 11.3 EasyUUV API 与 Isaac Lab 2 环境方法差异

问题：

```text
早期 workflow 调用 env.get_observations()，但 DirectRLEnv 路径没有这个方法。
```

处理：

- 改为兼容 Gym/DirectRLEnv 的 observation 获取方式。
- 在 play/train workflow 中统一处理 observation。

### 11.4 Git/TLS/服务器同步不稳定

问题：

```text
服务器 git clone/pull 经常 TLS 断开。
Windows 本地仓库还出现 dubious ownership。
```

处理：

- 服务器验证阶段多次使用 zip/scp 同步，而不是死磕 git。
- 代码和结果通过 `scp` 往返。
- 这导致服务器 summary 中 `git_dirty=true` 是预期状态，不代表实验无效。

### 11.5 PPO checkpoint 从无到有

问题：

```text
原 EasyUUV 仓库/服务器没有可直接使用的 PPO checkpoint。
```

处理：

- Phase 4.6 先补 checkpoint generation smoke。
- discovery 记录 `selected_checkpoint` 和 `selected_rule`。
- Phase 5 之后所有 retrained checkpoint 都必须通过 provenance validator。

### 11.6 旧 PPO action 语义不能直接当作 Koopman reference 语义

问题：

```text
PPO 输出 4D action，Koopman-MPC 需要 5D reference。
二者不是天然同构。
```

处理：

- 明确 adapter 名称是 `heuristic_reference_delta_v0`。
- 文档和 validator 都强调：这只是工程桥接，不声明无损语义迁移。

### 11.7 paper-style lifted EDMD 与工程默认 backend 的差异

问题：

```text
论文风格 lifted EDMD 更贴近文献，但当前数据/observable 下闭环 depth RMSE 很大。
```

处理：

- 保留 paper_lifted_edmd 作为对照 backend。
- 不作为默认低层控制器。
- 默认工程链路继续使用 direct_state。

### 11.8 fallback 不是单一问题

问题：

```text
Phase 5.3/5.4 显示 fallback rate 下降不一定代表控制更健康。
```

依据：

- `rm_timeout16` 和 `rm_midweights_timeout14` 等 profile 能降低 fallback，但 `no_cost_improvement` fallback 增加。
- `rm_horizon4_timeout14` latency 很好、PWM/depth 很好，但 fallback reason gate 失败。

处理：

- Phase 5.4 引入 fallback reason-level gate。
- 后续建议进入 no_cost_improvement 机制诊断，而不是继续盲调权重。

## 12. 当前不能说的结论

不能说：

```text
PPO 已经收敛。
Koopman+MPC 已经优于 legacy/Ssurface。
Phase 5.4 找到了最终参数。
paper_lifted_edmd 可以作为默认控制器。
LLM 已经接入控制链路。
当前 PPO action 到 Koopman reference 的映射已经证明语义正确。
```

可以说：

```text
Koopman 数据采集、离线训练、模型准入、MPC 接入、controller-only 评估、PPO adapter、checkpoint gate、PPO-Koopman-MPC training smoke、one-factor ablation、cross-combination screening、Phase 5.4 bounded Pareto sweep 都已经有代码和验证证据。
```

## 13. 建议下一步

建议规划 Phase 5.5，而不是直接进入 LLM。

Phase 5.5 重点：

```text
diagnose PPO action_4d -> heuristic_reference_delta_v0 -> Koopman reference_5d 的语义瓶颈。
diagnose MPC fallback 中 no_cost_improvement 的形成机制。
```

建议优先做：

1. 固定 PPO checkpoint，离线/短 rollout sweep adapter scale，观察 clip、fallback、depth、PWM 的变化。
2. 给 MPC diagnostics 增加 candidate cost、fallback cost、best cost improvement margin。
3. 区分 timeout fallback 和 no_cost_improvement fallback 的训练侧/评估侧分布。
4. 保持 matched eval 三轨迹，不因为单条 step 轨迹好看就推广。

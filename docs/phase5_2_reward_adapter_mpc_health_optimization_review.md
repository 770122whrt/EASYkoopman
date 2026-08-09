# Phase 5.2 Reward / Adapter / MPC Health Optimization 审核建议

**日期:** 2026-07-05
**审核对象:** Phase 5.2 `Reward / Adapter / MPC health optimization` 计划
**相关文件:** `.planning/phases/05.2-reward-adapter-mpc-health-optimization/05.2-SPEC.md`, `.planning/phases/05.2-reward-adapter-mpc-health-optimization/05.2-PLAN.md`, `docs/phase5_2_reward_adapter_mpc_health_optimization.md`
**结论:** Phase 5.2 的 one-factor ablation 方向合理，但建议在执行前调整 reward fallback 权重、adapter soft 程度、MPC delta limit 处理方式和 candidate 晋级阈值。

## 1. 总体结论

Phase 5.2 不应马上长训练，也不应马上合并 reward、adapter 和 MPC 参数。当前定义的四个小消融方向是正确的：

```text
baseline_rerun
reward_v1_only
adapter_soft_v1_only
mpc_health_v1_only
```

这符合当前核心算法边界：

```text
obs_9d
  -> RSL-RL PPO
  -> action_4d
  -> heuristic_reference_delta_v0
  -> koopman_reference_5d
  -> direct_state Koopman+MPC
  -> pwm_8d
```

Phase 5.2 的目标应保持为：

```text
改善 PPO-Koopman-MPC 闭环的 health metrics，
不是证明 PPO 收敛、不是证明优于 legacy/Ssurface、也不是部署证明。
```

建议状态：

```text
PASS_WITH_PARAMETER_ADJUSTMENTS_BEFORE_EXECUTION
```

## 2. 审核依据

当前代码中的 reward 尺度来自 `easyuuv_env.py`：

```text
rew_scale_pos = 0.15
rew_scale_ang = 0.5
rew_scale_actions = 0.00
```

也就是说，legacy 单步主要正奖励大约来自：

```text
depth reward <= 0.15
attitude reward <= 0.50
max ordinary shaped reward ~= 0.65
```

MPC fallback 的关键来源来自 `koopman/mpc.py`：

```text
timeout
no_cost_improvement
nonfinite_input / nonfinite_baseline
exception
```

其中 `no_cost_improvement` 并不一定全是 PPO 策略错误，也可能来自 MPC candidate set、delta limit、cost function 或 reference 可达性。因此 reward 中对 fallback 的惩罚不能过早设得太重。

## 3. 问题 1: `koopman_mpc_stability_v1` reward 权重

### 当前草案

```text
pwm_soft_limit = 0.90
latency_ref_ms = 20.0
latency_clip = 3.0
w_fallback = 0.50
w_pwm_sat = 0.20
w_latency = 0.05
w_action = 0.01
w_delta_action = 0.02
```

### 审核结论

`w_pwm_sat = 0.20` 可以接受为第一版。
`w_fallback = 0.50` 对第一版 reward-only ablation 偏强。

原因是当前 legacy shaped reward 的常规单步上限大约是 `0.65`。如果每次 fallback 直接扣 `0.50`，PPO 可能学到过度保守的 reference，而不是学到更好的 Koopman-MPC 配合行为。更麻烦的是，当前 fallback reasons 中包含 `timeout` 和 `no_cost_improvement`，它们未必完全由 PPO action 导致。

### 建议调整

推荐第一版改成：

```text
w_fallback = 0.30
w_pwm_sat = 0.20
w_latency = 0.05 but thresholded
w_action = 0.01
w_delta_action = 0.02
```

其中 latency penalty 建议不要惩罚所有正常延迟，而是改成只惩罚超出参考预算的部分：

```text
latency_penalty = w_latency * min(max(0, latency_ms - latency_ref_ms) / latency_ref_ms, latency_clip)
```

如果必须保留 `w_fallback = 0.50`，建议做成 reason-aware fallback penalty：

```text
nonfinite_input / exception: 0.50
no_cost_improvement: 0.30
timeout: 0.15
```

这样不会把 solver timeout 和策略失败混成同一种惩罚。

### 必须记录的 reward diagnostics

reward-only ablation 必须输出每个分量：

```text
r_legacy
fallback_penalty
pwm_saturation_penalty
latency_penalty
action_penalty
delta_action_penalty
r_total
```

否则后续无法判断 reward_v1 到底优化了什么。

## 4. 问题 2: `adapter_scale_soft_v1` 是否过于保守

### 当前草案

```text
rpy_delta_scale = 0.25
depth_delta_scale = 0.30
```

默认值是：

```text
rpy_delta_scale = 0.35
depth_delta_scale = 0.50
```

### 审核结论

这个 profile 不是错误，但对第一版 `adapter_soft_v1_only` 略偏保守，尤其是 `depth_delta_scale = 0.30`。Phase 5.1 的 depth RMSE 已经在 `0.5350 - 0.7057` 区间，过早把 depth reference delta 降低 40% 可能让 tracking 更慢。

还有一个重要点：降低 adapter scale 不会直接降低 raw policy action clip rate。clip rate 是 PPO 原始输出超过 `[-1, 1]` 的比例；scale 变小后，训练中的 PPO 可能为了补偿变小的 reference delta 而输出更大的 action，反而可能继续 clipping。

所以 adapter profile 实际测试的是：

```text
reference aggressiveness
```

而不只是：

```text
action clipping
```

### 建议调整

推荐第一版更温和：

```text
adapter_scale_soft_v1:
  rpy_delta_scale = 0.30
  depth_delta_scale = 0.40
```

把当前草案保留为更强版本：

```text
adapter_scale_soft_v2:
  rpy_delta_scale = 0.25
  depth_delta_scale = 0.30
```

如果仍决定使用 `0.25 / 0.30`，必须把它标记为 aggressive-soft adapter candidate，并用 depth RMSE 和 attitude RMSE regression guard 约束。

### 建议新增指标

adapter-only candidate 除了 action clip rate，还应记录：

```text
reference_delta_norm_mean
reference_delta_norm_max
depth_reference_delta_mean
attitude_reference_delta_mean
depth_rmse
attitude_rmse
```

否则无法判断 adapter scale 是在减少 aggressive reference，还是单纯降低控制能力。

## 5. 问题 3: `mpc_health_v1` 是否允许降低 `mpc_delta_pwm_limit`

### 当前草案

```text
mpc_delta_pwm_limit = 0.25
mpc_control_weight = 0.03
mpc_smoothness_weight = 0.10
```

默认值是：

```text
mpc_delta_pwm_limit = 0.35
mpc_control_weight = 0.01
mpc_smoothness_weight = 0.05
```

### 审核结论

不建议在第一版 `mpc_health_v1_only` 同时降低 `mpc_delta_pwm_limit` 并提高 control/smoothness weights。

原因是当前 fallback 中已经有较多 `no_cost_improvement`。在当前 MPC 实现中，candidate command 会被 `delta_pwm_limit` 投影；delta limit 降低后，candidate 可探索的 PWM 变化范围更小，更容易无法击败 hold baseline，从而增加 `no_cost_improvement` fallback。

### 建议调整

推荐把 MPC ablation 拆成两个层级。

第一版 `mpc_health_v1` 使用 weights-only：

```text
mpc_delta_pwm_limit = 0.35
mpc_control_weight = 0.03
mpc_smoothness_weight = 0.10
mpc_horizon = 5
mpc_timeout_ms = 12.0
```

如果 weights-only 降低 saturation 但还不够，再测试单独的 delta-limit probe：

```text
mpc_delta_limit_probe_v1:
  mpc_delta_pwm_limit = 0.25
  mpc_control_weight = 0.03
  mpc_smoothness_weight = 0.10
```

如果项目坚持把 `0.25` 放入第一版，那么必须增加硬性 reject 条件：

```text
no_cost_improvement fallback rate 不得上升
overall fallback rate 不得上升超过回归阈值
step trajectory 不得超过 Phase 5.1 baseline fallback + 0.02
```

## 6. 问题 4: 是否必须重跑 Phase 5.1 baseline

### 审核结论

必须重跑。

理由：

- PPO 训练有随机性。
- Isaac / GPU / server runtime 状态会影响训练速度和 rollout。
- Phase 5.2 要比较的是小幅 health 改善，不能拿旧日志和新训练直接混比。
- baseline_rerun 可以暴露当前代码改动是否已经改变了 Phase 5.1 行为。

### 推荐约束

`baseline_rerun` 应该和候选 profile 使用：

```text
same server
same code commit
same Koopman manifest
same max_iterations
same save_interval
same seed if available
same matched evaluation trajectory settings
same analyzer version
```

如果无法保证同一服务器会话，至少必须保证同一 commit、同一 manifest、同一 seed 和同一 analyzer。

## 7. 问题 5: candidate 晋级阈值

### 当前草案

```text
主健康指标至少改善 20%
fallback 不得恶化超过 0.03 absolute
depth RMSE 不得恶化超过 10%
```

### 审核结论

方向合理，但需要增加 absolute + relative 双阈值，并且不能只看 depth RMSE。

Phase 5.1 的 sine fallback baseline 只有 `0.0314`，如果允许恶化 `0.03 absolute`，相当于几乎翻倍。对低 baseline 轨迹来说，这个阈值偏松。

### 建议晋级规则

建议改为：

```text
hard gates 全部通过
primary health metric mean across trajectories 至少改善 20%
且 primary health metric absolute improvement 达到最小可见幅度
```

最小可见幅度建议：

```text
pwm_saturation_rate: >= 0.05 absolute
fallback_rate: >= 0.015 absolute if baseline >= 0.05
policy_action_clip_rate_mean: >= 0.03 absolute
```

回归约束建议：

```text
fallback_rate:
  每条 trajectory 不得同时满足 absolute increase > 0.02 且 relative increase > 25%

depth_rmse:
  mean depth RMSE 不得恶化超过 10%

attitude_rmse / quaternion_error:
  不得恶化超过 10%

PWM bounds:
  仍必须在 [-1, 1]

matched evaluation:
  step/sine/irregular 都必须完成，或者不能晋级，只能标记为 partial/fail
```

也就是说，`20%` 可以保留，但不能单独作为晋级条件。

## 8. 问题 6: 是否允许 combined profile

### 审核结论

初始 Phase 5.2 不应允许 combined profile。

当前最需要的是 attribution。如果 reward、adapter、MPC 同时改，成功和失败都很难解释。

### 建议策略

Phase 5.2 初段只允许：

```text
baseline_rerun
reward_v1_only
adapter_soft_v1_only
mpc_health_v1_only
```

combined profile 只能在以下条件满足后进入 Phase 5.2 后半段，或者更干净地推到 Phase 5.3：

```text
至少一个 single-axis candidate 通过晋级 gate
没有 single-axis candidate 引入明显 tracking regression
用户再次确认合并组合
combined profile 使用新的 profile_id 和 provenance
```

推荐命名：

```text
Phase 5.2b: reviewed combined health candidate
```

或者：

```text
Phase 5.3: combined health profile and longer PPO training
```

## 9. 额外 P0 代码契约缺口

Phase 5.2 目前是合理计划，但当前代码还不能直接执行。

### 9.1 `train_ppo_koopman.py` 仍拒绝新 reward

当前训练入口仍要求：

```text
reward_profile == legacy_easyuuv_v0
```

因此 `--reward_profile koopman_mpc_stability_v1` 在实现前会被拒绝。

必须补齐：

```text
reward_profile choices
koopman_mpc_stability_v1 config
legacy reward behavior regression tests
reward component diagnostics
```

### 9.2 Phase 5.2 evidence labels 还未进入 adapter/log validators

当前 `VALID_PPO_EVIDENCE_LEVELS` 已有 Phase 5.1 labels，但还没有：

```text
phase5_2_health_sentinel
phase5_2_health_candidate
phase5_2_matched_eval
```

必须补齐：

```text
koopman/policy_adapter.py
koopman/ppo_training_adapter.py
workflows/train_ppo_koopman.py
workflows/play_ppo_koopman.py
workflows/validate_ppo_koopman_log.py
Phase 5.2 provenance validator
```

### 9.3 Eval log 的 `reward_profile` 不能硬编码 legacy

Phase 5.2 matched evaluation 需要知道 checkpoint 来自哪个 reward profile。
如果 eval 日志继续写死：

```text
reward_profile = legacy_easyuuv_v0
```

那么 `reward_v1_only` 的 checkpoint 会在日志层被误标。应从 source training summary 或 candidate manifest 读取并写入：

```text
source_reward_profile
reward_profile
profile_id
changed_axis
```

## 10. 推荐修正版初始参数

建议 Phase 5.2 review 后采用以下初始值：

### Reward

```text
reward_profile = koopman_mpc_stability_v1
pwm_soft_limit = 0.90
latency_ref_ms = 20.0
latency_clip = 3.0
w_fallback = 0.30
w_pwm_sat = 0.20
w_latency = 0.05 thresholded above latency_ref_ms
w_action = 0.01
w_delta_action = 0.02
```

### Adapter

```text
adapter_scale_soft_v1:
  rpy_delta_scale = 0.30
  depth_delta_scale = 0.40
  policy_action_limit = 1.0
  depth_bounds = [-3.0, 3.0]
```

保留更强版本但不作为第一版：

```text
adapter_scale_soft_v2:
  rpy_delta_scale = 0.25
  depth_delta_scale = 0.30
```

### MPC

```text
mpc_health_v1:
  mpc_delta_pwm_limit = 0.35
  mpc_control_weight = 0.03
  mpc_smoothness_weight = 0.10
  mpc_horizon = 5
  mpc_timeout_ms = 12.0
```

可选 probe：

```text
mpc_delta_limit_probe_v1:
  mpc_delta_pwm_limit = 0.25
```

## 11. 推荐给另一个 agent 的执行清单

执行前先修改计划或实现，使其满足：

- `baseline_rerun` 是 mandatory。
- `reward_v1_only` 使用 `w_fallback = 0.30`，除非实现 reason-aware fallback penalty。
- `adapter_soft_v1_only` 第一版使用 `0.30 / 0.40`，把 `0.25 / 0.30` 标记为更强后备版本。
- `mpc_health_v1_only` 第一版不降低 `mpc_delta_pwm_limit`；降低 delta limit 应作为单独 probe。
- candidate selection 使用 relative + absolute 双阈值。
- depth RMSE 和 attitude RMSE 都是 regression guard。
- combined profile 不进入初始 Phase 5.2 matrix。
- Phase 5.2 evidence labels、provenance、profile metadata 和 eval log reward metadata 先补齐，再跑服务器训练。

## 12. 最终建议

Phase 5.2 是合理的下一阶段，但建议不要按原参数直接执行。

最终建议：

```text
Approve one-factor ablation.
Require fresh baseline_rerun.
Lower first reward fallback penalty from 0.50 to 0.30, or make it reason-aware.
Use milder adapter profile 0.30 / 0.40 first.
Keep MPC delta limit at 0.35 for first mpc_health_v1; test 0.25 separately.
Keep 20% improvement threshold, but add absolute improvement and regression guard.
Defer combined profile until single-axis results are reviewed.
```

这样 Phase 5.2 的结果才有可解释性：如果 health 指标变好，我们知道是哪一个环节起作用；如果失败，也能定位是 reward、adapter 还是 MPC profile 导致。

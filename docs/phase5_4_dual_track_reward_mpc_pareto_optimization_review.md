# Phase 5.4 Dual-Track Reward/MPC Pareto Optimization 审核文档

**日期:** 2026-07-05
**审核对象:** `.planning/phases/05.4-dual-track-reward-mpc-pareto-optimization/05.4-SPEC.md`, `.planning/phases/05.4-dual-track-reward-mpc-pareto-optimization/05.4-PLAN.md`
**审核结论:** Phase 5.4 的核心目标合理，双轨 Pareto 优化方向成立；执行前建议补齐参数距离定义、延迟 gate、fallback reason gate、选择状态分层和 Round 2 例外条件。
**建议状态:** `PASS_WITH_REVISIONS_BEFORE_IMPLEMENTATION`

## 1. 审核范围

本审核只检查 Phase 5.4 文档层面的规划合理性，不审核 Python 实现代码，也不要求开始服务器训练。

重点问题：

```text
1. 核心目标是否准确。
2. Track R / Track RM 是否从 Phase 5.2 / 5.3 证据自然推出。
3. Pareto selection gate 是否足够清楚。
4. small-parameter-first 是否能被实现为可计算规则。
5. Round 1 + Round 2 的执行要求是否合理。
6. 是否存在过严、过松或容易误导后续 agent 的地方。
```

## 2. 总体判断

Phase 5.4 的目标是准确的。

它不再做 Phase 5.3 那种 cross-combination screening，而是进入更明确的参数优化阶段：

```text
Track R:
  从 reward_v1_only 出发。
  保住低 fallback。
  修 PWM saturation / clip / depth RMSE。

Track RM:
  从 cross_reward_v1_mpc_health 出发。
  保住 PWM saturation / clip / depth / attitude 优势。
  修 fallback。
```

这正好对应已有证据：

- Phase 5.2 `reward_v1_only` 的优势是 fallback 低，但 PWM saturation、clip、depth RMSE 变差。
- Phase 5.3 `cross_reward_v1_mpc_health` 的优势是 PWM saturation、clip、depth、attitude 好，但 fallback 过高。

因此 Phase 5.4 不应该直接进入 LLM、不应该直接长训、不应该只选一个看起来不错的 profile。它应当做一个受限的、可解释的 Pareto 参数搜索。

## 3. 核心算法边界

Phase 5.4 必须继续守住项目核心算法链：

```text
obs_9d
  -> RSL-RL PPO policy
  -> action_4d
  -> heuristic_reference_delta_v0
  -> koopman_reference_5d
  -> direct_state Koopman+MPC
  -> pwm_8d
  -> Isaac EasyUUV physics
```

它允许调的是 profile metadata：

```text
reward weights
MPC weights / timeout / horizon
evidence label
provenance
selector gate
```

它不允许：

```text
重写 PPO
改变 PPO observation/action 维度
让 PPO 直接输出 8D PWM
重写 MPC solver
把 paper_lifted_edmd 设为默认 controller
引入 LLM 实时控制
声明最终收敛、部署或广泛优于 legacy/Ssurface
```

这一点在 SPEC/PLAN 中已经基本写清楚，应当保留。

## 4. 健康设计点

### 4.1 双轨结构合理

Track R 和 Track RM 是从真实结果中拆出来的两个方向，不是凭空增加搜索空间。

```text
Track R = reward 路径的保守修补
Track RM = reward + MPC 路径的 fallback 修补
```

这种设计比一次性做大网格搜索更适合当前阶段，因为它保留了 attribution。

### 4.2 small-parameter-first 是必要规则

用户提出的小参数优先非常关键。Phase 5.4 如果没有这个规则，很容易变成：

```text
更大 penalty
更长 timeout
更强 MPC regularization
```

只要某一次 matched eval 看起来好，就错误晋级。当前计划要求更大的参数必须证明明显综合收益，这是合理的。

### 4.3 Round 1 + Round 2 合理

不能一组好就停是正确的。Phase 5.4 的目标不是找到一个偶然跑好的 checkpoint，而是判断参数附近是否稳定：

```text
Round 1:
  broad sweep, understand global direction

Round 2:
  local refinement, test nearest smaller / interpolation neighbor
```

这能降低“偶然 profile 胜出”的风险。

### 4.4 no_selection 是正确出口

`no_selection + Pareto report` 是必要的。当前问题很可能存在真实 tradeoff：

```text
低 fallback 与低 saturation 可能互相拉扯
低 depth RMSE 与低 clip 可能不一致
MPC regularization 可能改善 PWM 但增加 fallback
```

如果没有候选能同时守住优势并修短板，强行选择会误导后续阶段。

## 5. 必须补充的问题

### 5.1 `parameter_distance_from_parent` 需要可计算定义

当前 SPEC/PLAN 已要求：

```text
parameter_distance_from_parent
minimal_parameter_selected
nearest_smaller_candidate_result
larger_parameter_justification
```

但还没有定义距离如何计算。不同参数单位不同，不能直接相加：

```text
w_pwm_sat: 0.20 -> 0.30
mpc_timeout_ms: 12 -> 16
mpc_control_weight: 0.03 -> 0.02
mpc_horizon: 5 -> 4
```

建议加入公式：

```text
parameter_distance_from_parent =
  sum(abs(candidate_value - parent_value) / step_size(parameter))
```

建议初始 step size：

```text
w_pwm_sat: 0.05
w_fallback: 0.05
w_action: 0.005
w_delta_action: 0.01
mpc_timeout_ms: 2.0
mpc_control_weight: 0.005
mpc_smoothness_weight: 0.015
mpc_horizon: 1
```

同时记录：

```text
changed_parameter_count
parameter_step_count
parameter_distance_from_parent
```

这样 small-parameter-first 才能被 selector 自动执行，而不是人工解释。

### 5.2 latency gate 不能只看 mean

当前 hard gate 有：

```text
latency_ms_mean < 20.0
```

但 Track RM 会测试：

```text
mpc_timeout_ms = 14.0
mpc_timeout_ms = 16.0
```

如果只看 mean，可能漏掉偶发超时或控制周期尖峰。建议补：

```text
latency_ms_mean < 20.0
latency_ms_max < 50.0
latency_budget_violation_rate <= 0.10
```

并且必须区分：

```text
training_loop_latency
matched_eval_latency
```

Phase 5.4 的选择应以 matched eval latency 为主。

### 5.3 fallback reason 必须进入 Track RM gate

Track RM 的目标是修 fallback。fallback 不是一个单一原因，当前 Koopman-MPC 可能出现：

```text
timeout
no_cost_improvement
nonfinite_input
nonfinite_baseline
exception
```

如果 `rm_timeout14` 降低了 timeout fallback，但导致 `no_cost_improvement` 增加，这不能算真正修复 fallback。

建议加入 gate：

```text
fallback_reason_counts must be reported per trajectory.

If mpc_timeout_ms is increased:
  timeout fallback should decrease.
  no_cost_improvement fallback must not materially increase.

If control/smoothness weights are reduced:
  no_cost_improvement fallback should decrease or remain stable.
  PWM saturation must not lose the Track RM advantage.
```

建议定义 material increase：

```text
absolute increase > 0.02
or relative increase > 25 percent
```

### 5.4 Round 2 mandatory 需要合理例外

Round 2 必须做，这个原则正确。但如果 Round 1 所有候选都多指标失败，并且没有“单一可修 bottleneck”的候选，强行 Round 2 会浪费训练资源。

建议补充：

```text
Round 2 is mandatory if:
  a candidate passes hard gates and has one dominant remaining bottleneck
  or a non-promoted candidate has exactly one fixable bottleneck.

Round 2 may be skipped only if:
  every Round 1 candidate has multiple protected-strength failures
  and selector outputs no_selection + Pareto report
  and user accepts diagnostic stop.
```

这样既保留“不能一组好就停”，也避免“没有好方向还硬扫”。

### 5.5 选择状态需要分层

当前有 `selected_phase5_4_profile` 和 `no_selection`，中间状态还可以更清楚。

建议分成：

```text
full_pass:
  同时达到 baseline_rerun floor，并通过 track protected-strength guards。

track_pass:
  保住本 track 的 protected strength，并明显修复主要短板。

promising_partial:
  一个方向有明显信号，但仍有一个关键短板未过 gate。

no_selection:
  没有候选可晋级，只输出 Pareto report。
```

这样能避免把 `promising_partial_rm` 误读为可默认使用的 profile。

### 5.6 初始 Phase 5.4 不应混入 adapter tuning

SPEC 写了：

```text
adapter terms:
  only if Round 1 evidence shows adapter is the remaining bottleneck
```

这个方向对，但建议再写硬一点：

```text
Initial Phase 5.4 Round 1 does not change adapter_profile.
Adapter changes require a reviewed addendum or a later Phase 5.5.
```

原因是 Phase 5.4 已经有 reward 和 MPC 两个轴，再加入 adapter 会扩大搜索空间并破坏当前双轨归因。

## 6. 推荐 Gate 模型

建议 Phase 5.4 使用以下 9 层 gate。

### Gate 1: Entry Evidence Gate

必须固定输入证据：

```text
Phase 5.2 baseline_rerun metrics
Phase 5.2 reward_v1_only metrics
Phase 5.3 cross_reward_v1_mpc_health metrics
Phase 5.3 no_selection conclusion
```

所有后续比较都必须引用这些 source result paths。

### Gate 2: Architecture Gate

每个 profile 都必须保持：

```text
observation_dim = 9
action_dim = 4
adapter_mode = heuristic_reference_delta_v0
koopman_backend = direct_state
pwm_dim = 8
```

任何改变 observation/action 或 PPO 输出 PWM 的方案都不属于 Phase 5.4。

### Gate 3: Profile Contract Gate

每个 Phase 5.4 profile 必须记录：

```text
profile_id
track = R | RM
parent_profile_id
reward_overrides
mpc_overrides
adapter_profile
sweep_round
protected_strengths
parameter_distance_from_parent
changed_parameter_count
```

### Gate 4: Sentinel Gate

50 iteration sentinel 必须先通过：

```text
checkpoint exists
finite rewards / observations / actions
bounded PWM
adapter refresh before env.step
valid Phase 5.4 provenance
classified failure if stopped
```

### Gate 5: Candidate Gate

200 iteration candidate 必须通过：

```text
checkpoint reloads
matched step/sine/irregular logs validate
latency_ms_mean < 20.0
latency_ms_max < 50.0
latency_budget_violation_rate <= 0.10
fallback_reason_counts reported
```

### Gate 6: Track R Gate

Track R 必须保住 `reward_v1_only` 的 fallback 优势：

```text
fallback_rate_mean <= 0.1448
```

并且至少修复一个主要短板：

```text
pwm_saturation_rate_mean improves toward baseline_rerun
or policy_action_clip_rate_mean improves
or depth_rmse_mean improves
```

不允许只靠 attitude RMSE 或 composite score 晋级。

### Gate 7: Track RM Gate

Track RM 必须修 fallback：

```text
interim pass:
  fallback_rate_mean <= 0.2333

full pass:
  fallback_rate_mean <= 0.1448
```

同时保住 Track RM 的强项：

```text
pwm_saturation_rate_mean <= 0.1500
policy_action_clip_rate_mean <= 0.0600
depth_rmse_mean <= 0.7500
attitude_rmse_mean <= 0.7434
```

如果只达到 interim pass，可以标记：

```text
promising_partial_rm
```

但不能作为默认 profile。

### Gate 8: Small-Parameter Gate

当多个候选通过同一级 gate：

```text
if health_score difference < 0.03:
  choose smaller parameter_distance_from_parent

if larger parameter wins:
  require larger_parameter_justification
```

更大参数必须满足：

```text
health_score improves by >= 0.03
or at least two bottleneck metrics improve by >= 10 percent
```

并且不得破坏 protected strengths。

### Gate 9: Round 2 / Final Selection Gate

最终 selection 必须满足：

```text
Round 1 completed or skipped with written hard-failure reason.
Round 2 refinement completed around the best candidate or best single-bottleneck non-promoted candidate.
nearest smaller candidate was tested.
Pareto frontier was reported.
selection_status is one of full_pass, track_pass, promising_partial, no_selection.
```

如果没有 profile 通过，必须输出：

```text
no_selection + Pareto report
```

## 7. 建议补充到 SPEC/PLAN 的内容

建议另一个 agent 在修改 05.4 文档时补入以下条款。

### 7.1 参数距离公式

```text
parameter_distance_from_parent =
  sum(abs(candidate_value - parent_value) / step_size(parameter))
```

并在 profile summary 中记录：

```text
parameter_step_count
changed_parameter_count
nearest_smaller_candidate_result
```

### 7.2 延迟 gate

```text
latency_ms_mean < 20.0
latency_ms_max < 50.0
latency_budget_violation_rate <= 0.10
```

### 7.3 fallback reason gate

```text
fallback_reason_counts_by_trajectory
timeout_fallback_delta
no_cost_improvement_fallback_delta
exception_fallback_count
```

### 7.4 选择状态分层

```text
full_pass
track_pass
promising_partial
no_selection
```

### 7.5 Round 2 例外条件

```text
Round 2 may be skipped only when all Round 1 candidates show multiple
protected-strength failures and the user accepts diagnostic stop.
```

### 7.6 初始 Round 1 禁止 adapter tuning

```text
Initial Round 1 changes reward and MPC only.
Adapter tuning requires reviewed addendum or later phase.
```

## 8. 最终建议

Phase 5.4 是一个合理的下一阶段。它比 Phase 5.3 更接近真正的参数优化，但仍然保持研究工程上的克制：

```text
不改核心控制链
不假装收敛
不强行选赢家
不一组好就停
优先小参数
保留 Pareto report
```

建议在实施前把上述 gate 写回 SPEC/PLAN。补齐后，Phase 5.4 可以作为一个清晰的 Pareto optimization phase，用来判断 PPO-Koopman-MPC 是否能在低 fallback、低 PWM saturation、低 clip 和可接受 RMSE 之间找到稳定折中。

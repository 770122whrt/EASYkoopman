# Phase 5.1: Koopman-MPC PPO 稳定训练方案

**日期:** 2026-07-05
**文档类型:** 中文方案说明 + 执行边界 + 执行前 gap 修正
**当前结论:** `PASS_WITH_MUST_FIXES_BEFORE_EXECUTION`

## 1. 一句话结论

Phase 5.1 的方向是正确的：先证明 `PPO -> adapter -> Koopman+MPC` 可以稳定训练，再逐个优化 reward、fallback、latency、adapter scale 和 MPC 参数。

但当前代码还不能直接跑 Phase 5.1。原因是现有 gate 仍然把 PPO-Koopman-MPC 的训练证据当作 Phase 5 smoke 来处理，只支持 `retrained_policy_smoke`，还没有支持：

```text
stability_sentinel
stability_candidate
matched_stability_eval
```

所以服务器执行前，必须先补齐 evidence level、Phase 5.1 provenance、training health summary、stability validator 和 selected checkpoint manifest。

## 2. 这一阶段到底训练什么

Phase 5.1 不是发明新的 PPO 算法。PPO 仍然来自 RSL-RL。

这一阶段要获得的是：

```text
Koopman-MPC-conditioned PPO policy checkpoint
```

也就是一组在下面这条闭环里训练出来的 PPO 权重：

```text
9D observation
  -> RSL-RL PPO
  -> 4D high-level action/correction
  -> heuristic_reference_delta_v0
  -> 5D Koopman reference
  -> direct_state Koopman+MPC
  -> bounded 8D PWM
  -> Isaac EasyUUV physics
```

这个 checkpoint 必须可追溯、可加载、可评估。它不是旧 EasyUUV PPO checkpoint 的改名，也不是 PPO 直接输出 PWM。

## 3. 当前固定不变的合同

第一轮稳定性证明固定这些条件：

```text
PPO 算法: RSL-RL PPO
PPO 输入: 9D EasyUUV observation
PPO 输出: 4D action
Adapter: heuristic_reference_delta_v0
低层控制器: direct_state Koopman+MPC
PWM 输出: 8D bounded PWM
Reward: legacy_easyuuv_v0
```

禁止把本阶段理解为：

```text
PPO 直接输出 8D PWM
PPO 输出 Koopman latent state
PPO 替代 MPC
Koopman 替代 PPO observation
paper_lifted_edmd 成为默认底层控制器
LLM 进入实时控制环
```

## 4. 执行前必须补齐的 P0

### 4.1 Evidence level 支持

当前 `koopman/policy_adapter.py` 和相关 workflow 还不认识 Phase 5.1 的新证据等级。必须让这些 level 成为一等公民：

```text
stability_sentinel
stability_candidate
matched_stability_eval
```

涉及文件：

```text
koopman/policy_adapter.py
workflows/train_ppo_koopman.py
workflows/play_ppo_koopman.py
workflows/validate_ppo_koopman_log.py
tests/test_policy_adapter.py
tests/test_ppo_koopman_logging.py
```

最低要求：

```text
adapt_policy_reference(..., ppo_evidence_level="stability_sentinel") 可以通过
adapt_policy_reference(..., ppo_evidence_level="stability_candidate") 可以通过
adapt_policy_reference(..., ppo_evidence_level="matched_stability_eval") 可以通过
未知 evidence level 仍然失败
```

### 4.2 Phase 5.1 provenance

Phase 5 的 provenance 是：

```text
phase5_train_koopman_mpc
```

Phase 5.1 需要更明确的 provenance：

```text
phase5_1_stability_sentinel
phase5_1_stability_candidate
```

这样可以防止 Phase 5 smoke checkpoint 被误贴成 Phase 5.1 stability checkpoint。

`matched_stability_eval` 必须要求：

```text
--policy_mode checkpoint
--play_checkpoint <selected Phase 5.1 checkpoint>
--source_training_summary_path <Phase 5.1 stability_candidate summary>
checkpoint_provenance_valid = true
```

### 4.3 Training health summary

Phase 5 的 summary 主要证明 checkpoint 和 adapter refresh 存在。Phase 5.1 需要证明训练过程健康，所以 summary 必须记录：

```text
checkpoint_found
selected_checkpoint
selected_rule
checkpoint_provenance
adapter_refresh_count
adapter_refresh_before_env_step
policy_action_clip_rate
training_loop_fallback_rate
training_loop_latency_ms_mean
training_loop_latency_ms_max
training_loop_pwm_min
training_loop_pwm_max
nonfinite_observation_count
nonfinite_action_count
nonfinite_reward_count
episode_reward_mean_start
episode_reward_mean_end
episode_reward_nan_count
training_reference_source
training_goal_distribution
depth_reference_source
training_latency_warning_threshold_ms
control_loop_budget_ms
latency_budget_violation_rate
selected_weight_status
completion_status
```

可选 RSL-RL 指标采不到时可以写：

```text
"unavailable"
```

但这些字段不能是 `unavailable`：

```text
checkpoint_found
selected_checkpoint
adapter_refresh_count
adapter_refresh_before_env_step
nonfinite_observation_count
nonfinite_action_count
completion_status
```

### 4.4 Stability validator

新增 validator，硬失败条件包括：

```text
没有 checkpoint
checkpoint 不能加载
observation/action/reward/PWM 出现 NaN 或 Inf
PWM 超过 actuator bounds
adapter 没有在 step path 刷新
缺少 Phase 5.1 provenance
```

警告条件包括：

```text
policy_action_clip_rate > 0.5
training_loop_fallback_rate > 0.2
training_loop_latency_ms_mean > 20 ms
training_loop_latency_ms_max > 50 ms
latency_budget_violation_rate > 0.1
```

注意：`20 ms` 是训练阶段 warning，不是实时部署标准。实时控制预算要单独记录为 `control_loop_budget_ms`。

### 4.5 Selected PPO checkpoint manifest

Phase 5.1 的最终交接物不是口头说“某个 model.pt 看起来能用”，而是机器可读的 manifest：

```text
source/results/koopman_phase5_1/selected_ppo_checkpoint_manifest.json
```

最低字段：

```json
{
  "phase": "05.1",
  "selected_checkpoint": ".../model_*.pt",
  "selected_rule": "latest_valid_after_stability_validator",
  "source_training_summary_path": ".../stability_candidate_summary.json",
  "ppo_evidence_level": "stability_candidate",
  "checkpoint_provenance": "phase5_1_stability_candidate",
  "reward_profile": "legacy_easyuuv_v0",
  "adapter_mode": "heuristic_reference_delta_v0",
  "koopman_backend": "direct_state",
  "observation_dim": 9,
  "action_dim": 4,
  "selected_weight_status": "candidate_only",
  "matched_eval_status": "pending"
}
```

这个 manifest 会驱动 matched evaluation，也会作为 Phase 5.2 的输入。

## 5. 两级训练阶梯

补齐 P0 后，服务器上先跑两个训练阶梯。

Sentinel run：

```text
num_envs = 1
max_iterations = 50
save_interval = 10
reward_profile = legacy_easyuuv_v0
ppo_evidence_level = stability_sentinel
checkpoint_provenance = phase5_1_stability_sentinel
```

它的目的不是训练出好策略，而是检查长于 smoke 的训练会不会卡住、日志是否完整、checkpoint 是否可用。

Stability candidate：

```text
num_envs = 1
max_iterations = 200
save_interval = 25
reward_profile = legacy_easyuuv_v0
ppo_evidence_level = stability_candidate
checkpoint_provenance = phase5_1_stability_candidate
```

它的目的是产生第一组可用于 matched evaluation 的候选 PPO 权重。

## 6. Matched Evaluation

稳定训练后，用同一组 reference 比较三条链：

```text
legacy/Ssurface
direct_state Koopman+MPC controller-only
PPO -> heuristic_reference_delta_v0 -> direct_state Koopman+MPC
```

reference 至少包括：

```text
step
sine
irregular
```

评估侧指标和训练侧指标必须分开：

```text
matched_eval_fallback_rate
matched_eval_latency_ms_mean
matched_eval_latency_ms_max
matched_eval_pwm_min
matched_eval_pwm_max
eval_reference_set
matched_eval_status
```

这一轮 matched evaluation 主要用于诊断，不急着写“谁最好”。如果 PPO-Koopman-MPC 弱但训练稳定，下一阶段可以调 reward 或 adapter；如果训练本身不稳定，就不能先调性能。

## 7. 稳定之后怎么优化

稳定门通过后，再按瓶颈选择下一步。

如果 fallback 高：

```text
检查 MPC 可行性、fallback 触发条件、fallback-aware reward。
```

如果 latency 高：

```text
调整 MPC horizon、控制频率、solver 设置或 warm start。
```

如果 action clipping 高：

```text
调 adapter scale，或加入 action magnitude/action delta penalty。
```

如果训练稳定但 tracking 差：

```text
进入 reward v1，加入 tracking、energy、smoothness、fallback、latency 的权衡。
```

如果训练稳定且警告很少：

```text
可以进入 reward ablation 和更长训练。
```

## 8. 执行顺序

推荐顺序：

```text
1. 补 evidence level 枚举和 CLI choices。
2. 补 Phase 5.1 provenance validator。
3. 补 training health summary writer。
4. 补 stability summary validator。
5. 本地跑 pytest/compileall。
6. 服务器跑 50-iteration sentinel。
7. validator 通过后跑 200-iteration stability candidate。
8. 写 selected_ppo_checkpoint_manifest.json。
9. 用该 manifest 驱动 step/sine/irregular matched evaluation。
10. 根据 primary bottleneck 决定 Phase 5.2。
```

不要在第一次 200 iteration 前同时改 reward、adapter scale、MPC horizon 或 fallback 规则，否则失败时无法归因。

## 9. Phase 5.1 的成功声明

成功时只能这样说：

```text
Phase 5.1 证明 PPO 可以在 Koopman-MPC 闭环下完成长于 smoke 的稳定训练。
所选 checkpoint 可追溯、可加载，并能进入 matched evaluation。
训练和评估记录了 fallback、latency、action clipping、PWM bounds 和 non-finite counts。
```

不能说：

```text
PPO 已经收敛。
PPO+Koopman-MPC 已经优于 legacy。
这个策略可以部署。
reward 已经最终确定。
```

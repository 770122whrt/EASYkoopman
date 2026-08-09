# Phase 5.1 稳定训练计划补充审核

**日期:** 2026-07-04
**审核对象:** `.planning/phases/05.1-koopman-mpc-ppo-stability-training/05.1-CONTEXT.md`, `05.1-SPEC.md`, `05.1-PLAN.md`, `docs/phase5_1_koopman_mpc_ppo_stability_training.md`
**审核结论:** 计划方向正确，但执行前必须补齐 evidence level、provenance、training health summary 和 validator，否则 05.1 的命令会被当前代码 gate 拒绝，无法证明“适配 Koopman-MPC 的 PPO 权重”。

## 1. 总体判断

Phase 5.1 的阶段目标是合理的：

```text
先证明 PPO -> adapter -> Koopman+MPC 可以稳定训练，
再分别优化 reward、fallback、latency、adapter scale、MPC 参数等。
```

这个顺序符合当前项目目标，也符合两篇论文的组合边界：

- EasyUUV 论文中的 PPO 不是直接输出推进器 PWM，而是输出高层 4D 修正，由底层控制器执行。
- Koopman-Sim2Real 论文中的 Koopman 模型承担环境/动力学预测能力，并服务 MPC 预测控制。
- 当前项目的正确融合形态应是 `PPO policy -> reference adapter -> Koopman-MPC controller`，而不是 `PPO -> 8D PWM`，也不是绕过 adapter 直接替换低层输入语义。

因此，Phase 5.1 的目标不应表述为“发明新的 PPO 算法”，而应表述为：

```text
获得一版 Koopman-MPC-conditioned PPO policy checkpoint。
```

也就是一组在 Koopman-MPC 闭环训练路径下产生、可追溯、可加载、可评估的 PPO 权重。

## 2. 当前计划的健康点

以下内容可以保留：

- Phase 5.1 插在 Phase 5 和 Phase 6 之间，避免 LLM 或 reward redesign 过早进入控制闭环。
- 50 iteration `stability_sentinel` 和 200 iteration `stability_candidate` 的两级阶梯合理。它们不是性能证明，而是训练稳定性 gate。
- 固定 `legacy_easyuuv_v0` reward、9D observation、4D action、`heuristic_reference_delta_v0` adapter、`direct_state` Koopman-MPC，可以避免 attribution 混乱。
- matched evaluation 同时比较 `legacy/Ssurface`、controller-only Koopman+MPC、PPO-Koopman+MPC，这是必要的诊断结构。
- 计划明确禁止 PPO 直接输出 8D PWM、禁止把 `paper_lifted_edmd` 设为默认、禁止直接宣称收敛或部署。

## 3. P0: 执行前必须补齐

### 3.1 Evidence level 与当前代码不匹配

05.1 计划引入了：

```text
stability_sentinel
stability_candidate
matched_stability_eval
```

但当前代码仍只接受 Phase 5 smoke 级别：

- `koopman/policy_adapter.py` 的 `VALID_PPO_EVIDENCE_LEVELS` 只包含 `stub_only`, `checkpoint_smoke`, `training_entrypoint_only`, `retrained_policy_smoke`。
- `workflows/train_ppo_koopman.py` 中 `configure_phase5_env()` 强制 `args_cli.ppo_evidence_level == PHASE5_EVIDENCE_LEVEL`，而 `PHASE5_EVIDENCE_LEVEL` 仍是 `retrained_policy_smoke`。
- `workflows/play_ppo_koopman.py` 的 `--ppo_evidence_level` choices 不包含 05.1 新等级。
- `workflows/validate_ppo_koopman_log.py` 依赖同一组 `VALID_PPO_EVIDENCE_LEVELS`。

**必须修改:**

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
VALID_PPO_EVIDENCE_LEVELS += (
  "stability_sentinel",
  "stability_candidate",
  "matched_stability_eval",
)
```

并且 training/eval CLI 不得把 05.1 evidence level 拒绝掉。

### 3.2 Provenance gate 仍停在 Phase 5 smoke

当前 `workflows/validate_phase5_checkpoint_provenance.py` 的 expected values 仍固定为：

```text
ppo_evidence_level = retrained_policy_smoke
checkpoint_provenance = phase5_train_koopman_mpc
```

这会导致 05.1 的 `stability_candidate` checkpoint 即使真实训练完成，也不能被当前 provenance validator 接受。

**必须修改:**

增加 Phase 5.1 provenance 语义，推荐两种方式之一。

方式 A，使用更明确的 provenance label：

```text
phase5_1_stability_sentinel
phase5_1_stability_candidate
```

方式 B，保留 `phase5_train_koopman_mpc`，但 summary 必须额外记录：

```text
phase = "05.1"
training_ladder = "sentinel" | "stability_candidate"
ppo_evidence_level = "stability_sentinel" | "stability_candidate"
```

建议优先使用方式 A，因为它能更直接防止 Phase 5 smoke checkpoint 被重新贴标签成 Phase 5.1 权重。

### 3.3 Training health summary 还不足以证明稳定训练

05.1 spec 要求 summary 记录：

```text
fallback_rate
latency_ms_mean
latency_ms_max
pwm_min
pwm_max
nonfinite_observation_count
nonfinite_action_count
episode_reward_mean_start
episode_reward_mean_end
episode_reward_nan_count
completion_status
```

但当前 Phase 5 training summary 主要记录 checkpoint、config、adapter refresh 和少量 adapter diagnostics。它还不能证明训练过程中没有 fallback 暴涨、latency 超预算、PWM 越界或 NaN/Inf。

**必须修改:**

新增或实现：

```text
workflows/write_phase5_1_stability_summary.py
workflows/validate_phase5_1_stability_summary.py
tests/test_phase5_1_stability_summary.py
tests/test_phase5_1_stability_validator.py
```

训练 summary 中不能默默省略关键字段。字段采不到时，应写：

```text
"unavailable"
```

但以下字段不建议允许 `unavailable`，否则不能证明稳定性：

```text
checkpoint_found
selected_checkpoint
adapter_refresh_count
adapter_refresh_before_env_step
nonfinite_observation_count
nonfinite_action_count
completion_status
```

### 3.4 Matched evaluation 的 provenance 需要接受 `matched_stability_eval`

计划中 Wave 5 使用：

```text
--ppo_evidence_level matched_stability_eval
--source_training_summary_path stability_candidate_summary.json
```

但当前 `play_ppo_koopman.py` 的 preflight provenance 逻辑只把 `retrained_policy_smoke` 视为需要 Phase 5 provenance 的 retrained evidence。`matched_stability_eval` 也应强制要求：

```text
--policy_mode checkpoint
--play_checkpoint <selected Phase 5.1 checkpoint>
--source_training_summary_path <Phase 5.1 stability_candidate summary>
checkpoint_provenance_valid = true
```

否则 matched evaluation 可能加载旧 checkpoint 或未验证 checkpoint。

## 4. P1: 建议补强

### 4.1 明确“稳定训练通过”与“可用权重”的关系

200 iteration `stability_candidate` 不能等价于收敛或性能优越，但可以作为第一版候选权重。

建议在 05.1 summary 中增加：

```text
selected_weight_status = candidate_only | rejected | promoted_for_phase5_2
```

判定逻辑：

```text
candidate_only:
  training validator 无 hard failure
  checkpoint reload 成功
  step matched evaluation 完成

rejected:
  checkpoint 不存在、无法加载、出现 NaN/Inf、PWM 越界、adapter 未刷新

promoted_for_phase5_2:
  candidate_only 且 warnings 可解释，允许进入 reward/latency/adapter/MPC 单项优化
```

### 4.2 区分 training-loop metrics 和 evaluation metrics

fallback、latency、PWM bounds 在训练循环和评估循环中含义不同：

```text
training_loop_fallback_rate
training_loop_latency_ms_mean
training_loop_pwm_min/max
matched_eval_fallback_rate
matched_eval_latency_ms_mean
matched_eval_pwm_min/max
```

建议不要只写一个 `fallback_rate`，否则后续无法判断问题发生在训练采样期间，还是 checkpoint reload 后的 matched rollout。

### 4.3 记录 reference distribution

训练时当前 base reference 来自：

```text
env_goal_quat_plus_zero_depth
zero_depth_default
```

matched evaluation 使用 step/sine/irregular reference。两者分布不同，可能导致“训练稳定但 matched tracking 差”。

建议 summary 增加：

```text
training_reference_source
training_goal_distribution
eval_reference_set
depth_reference_source
```

这样如果 `stability_candidate` 在 matched eval 中表现差，可以判断是 reward 问题、reference curriculum 问题，还是 adapter scale 问题。

### 4.4 记录 checkpoint selection manifest

Phase 5.1 的最终产物是权重，因此必须有一个可机器读取的 selected model manifest。

建议新增：

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
  "matched_eval_status": "pass|fail|partial",
  "allowed_claims": [],
  "disallowed_claims": []
}
```

### 4.5 Latency threshold 要和控制周期分开解释

当前 warning threshold 是：

```text
latency_ms_mean > 20.0
latency_ms_max > 50.0
```

如果控制频率按 60 Hz 估计，一个控制周期约为 16.67 ms。20 ms 可以作为训练阶段 warning，但不能作为实时控制通过标准。

建议增加两个字段：

```text
training_latency_warning_threshold_ms = 20.0
control_loop_budget_ms = <from controller config or env dt>
latency_budget_violation_rate
```

这样后续不会把“训练能跑”误解为“实时控制可部署”。

## 5. 需要在计划中补一句的算法边界

建议把以下表述补到 05.1 计划或最终 summary：

```text
Phase 5.1 不修改 PPO 算法本身。它训练的是在 Koopman-MPC 闭环环境下工作的 PPO policy checkpoint。
PPO 仍输出 EasyUUV 论文语义下的 4D high-level correction/action。
Adapter 将该 4D action 映射为 Koopman-MPC 所需的 5D reference。
Koopman-MPC 负责从 state/reference/baseline PWM 中求解 bounded 8D PWM。
```

这能避免后续 agent 把“适配 Koopman 的 PPO”误解成：

```text
PPO 直接输出 Koopman latent state
PPO 直接输出 8D PWM
PPO 替代 MPC
Koopman 替代 PPO observation
```

这些都不是当前阶段目标。

## 6. 推荐执行顺序

执行前顺序应调整为：

```text
1. 补 evidence level 枚举和 CLI choices。
2. 补 Phase 5.1 provenance validator。
3. 补 stability summary writer。
4. 补 stability summary validator。
5. 本地跑 pytest/compileall，只验证契约，不跑 Isaac 长训。
6. 服务器跑 50 iteration sentinel。
7. 通过 validator 后再跑 200 iteration stability candidate。
8. 写 selected_ppo_checkpoint_manifest.json。
9. 用该 manifest 驱动 matched evaluation。
10. 根据 primary bottleneck 决定 Phase 5.2。
```

不要在第 1 次 200 iteration 前同时改 reward、adapter scale、MPC horizon 或 fallback 规则。否则失败时无法归因。

## 7. 给另一个 agent 的验收清单

执行 Phase 5.1 前，必须能回答以下问题：

- `stability_sentinel` 是否能通过 `adapt_policy_reference()` 的 evidence validation？
- `stability_candidate` 是否能通过 `train_ppo_koopman.py` 的 argument validation？
- `matched_stability_eval` 是否能通过 `play_ppo_koopman.py` 和 `validate_ppo_koopman_log.py`？
- Phase 5 smoke checkpoint 是否无法被误标为 Phase 5.1 stability checkpoint？
- `stability_candidate_summary.json` 是否记录 training-loop fallback/latency/PWM/nonfinite/reward health？
- `validate_phase5_1_stability_summary.py` 是否会对 NaN/Inf、PWM 越界、无 checkpoint、adapter 未刷新直接 hard fail？
- matched evaluation 是否使用同一个 selected checkpoint manifest？
- 最终报告是否只声明 stability-level evidence，而不声明 convergence、superiority 或 deployment？

## 8. 最终建议

Phase 5.1 计划可以继续，但当前状态应标记为：

```text
PASS_WITH_MUST_FIXES_BEFORE_EXECUTION
```

补齐 P0 后，Phase 5.1 才能产生可信的第一版：

```text
Koopman-MPC-conditioned PPO policy checkpoint
```

这组权重如果通过 50/200 iteration 训练、provenance、reload 和 matched evaluation gate，就可以作为 Phase 5.2 reward/latency/fallback/adapter/MPC 单项优化的输入，而不是作为最终性能结论。

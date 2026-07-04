# Phase 4.6 PPO 训练与 Checkpoint 证据门

**日期:** 2026-07-03
**文档类型:** 解释 + 执行边界
**读者:** 项目负责人、后续执行 Phase 4.6 的代理、Isaac 服务器操作者

## 1. 一句话结论

Phase 4.6 不是“证明 PPO+Koopman 更强”的阶段，也不是最终的 PPO 训练阶段。

它只做一件很具体的事：

```text
把 PPO/RSL-RL 的训练入口、checkpoint 生成、checkpoint 发现、checkpoint 加载
在当前 Isaac Sim 5.0 + Isaac Lab 2.2.1 环境下重新跑通。
```

它的后续阶段是 Phase 5：

```text
在 Koopman-MPC 闭环中重新训练 PPO，得到真正属于新控制链路的 checkpoint。
```

前面的 Phase 4.5 已经证明：

```text
stub policy -> heuristic_reference_delta_v0 -> Koopman+MPC -> 8D PWM
```

可以在服务器上跑通。但它没有证明 PPO，因为服务器上没有 PPO checkpoint。

## 2. 为什么还需要 Phase 4.6

原 EASYUUV 的 PPO 链路是：

```text
PPO observation 9D
  -> PPO policy
  -> 4D action
  -> legacy S-Surface/PID controller
  -> 8D PWM
  -> AUV
```

我们现在的 Koopman+MPC 链路是：

```text
4D policy output
  -> heuristic_reference_delta_v0
  -> 5D Koopman reference
  -> Koopman+MPC
  -> 8D PWM
  -> AUV
```

这两个链路的 USD 资产可以相同，但 PPO 学到的是 “action 如何通过低层控制器影响下一步状态”。低层控制器换了以后，PPO 面对的 transition 就变了。

所以旧 checkpoint 可以做兼容性 smoke，但不能直接证明新控制结构已经训练成功。

## 3. 三类结果必须分开

Phase 4.6 最重要的文档约束是分桶。

| 结果桶 | 链路 | 可以说明什么 | 不能说明什么 |
| --- | --- | --- | --- |
| `legacy_ppo_baseline` | PPO -> legacy/Ssurface -> PWM | 原 EASYUUV PPO 路线能训练/加载/短跑 | Koopman+MPC 有效 |
| `old_checkpoint_adapter_smoke` | 旧 PPO checkpoint -> adapter -> Koopman+MPC -> PWM | 旧 checkpoint 能穿过 adapter 跑一小段 | 旧 PPO 语义无损迁移 |
| `retrained_ppo_koopman_mpc` | PPO 训练时就走 adapter + Koopman+MPC | 新训练链路可运行 | 已经收敛或超过 legacy |

如果后续报告里把这三类混在一起，就会误导。

## 4. PPO 的输入输出暂时不改

Phase 4.6 不改 PPO 的 observation 和 action。

PPO 输入仍是 9D：

```text
goal_quat(4) + current_depth_z(1) + current_quat(4)
```

PPO 输出仍是 4D：

```text
roll / pitch / yaw / depth correction
```

不做这些改动：

```text
不把 PPO observation 改成 11D Koopman state
不让 PPO action 变成 8D PWM
不直接手写 PPO 算法
不同时大改 reward
```

我们要复用 RSL-RL 的 PPO，只改训练入口、控制路径和证据记录。

## 5. 旧 checkpoint 能做什么

如果我们先训练出一个 legacy checkpoint，它的训练链路是：

```text
PPO -> legacy/Ssurface -> PWM
```

这个 checkpoint 可以做两件事：

1. 作为原 EASYUUV baseline，证明原始 PPO 路线可运行。
2. 通过 Phase 4.5 adapter 跑一次短 smoke，看看旧 policy 输出会不会让 Koopman+MPC 立刻失稳。

但旧 checkpoint 不能证明：

```text
PPO 已经适配 Koopman+MPC
PPO 性能比 legacy 更好
PPO 的 4D action 语义已经无损迁移
```

因为它不是在 Koopman+MPC 低层控制器下训练出来的。

## 6. 真正的 PPO+Koopman 训练需要什么

如果要训练真正属于我们方案的 PPO，训练时必须走完整路径：

```text
obs_9d
  -> PPO policy
  -> action_4d
  -> heuristic_reference_delta_v0
  -> refresh env._koopman_reference_5d
  -> env.step(action_4d)
  -> Koopman+MPC
  -> PWM
```

关键点是：

```text
不能只把 controller_mode 改成 koopman_mpc。
```

因为普通 RSL-RL training loop 只会调用 `env.step(action)`。如果训练 wrapper 没有在每步 step 前把 action 转成 `_koopman_reference_5d`，PPO 的 action 可能没有真正成为 MPC 目标，只是影响 legacy fallback。

这是 Phase 4.6 最容易走偏的地方。

## 7. Reward 暂时怎么处理

Phase 4.6 默认不改 reward。

默认标签：

```text
reward_profile = "legacy_easyuuv_v0"
```

原因是我们已经在改低层 controller path。如果同时改 reward，就很难判断结果变化来自哪里。

后续可以新增 reward：

```text
legacy_easyuuv_v1_with_fallback_penalty
koopman_mpc_v1_with_latency_penalty
koopman_mpc_v1_with_action_clip_penalty
```

但这些应该是后续单独阶段，不要塞进 Phase 4.6。

## 8. 必须记录的字段

Phase 4.6 的日志或 summary 必须包含：

```text
checkpoint_found
checkpoint_path
selected_checkpoint
selected_rule
training_iterations
result_bucket
ppo_evidence_level
reward_profile
controller_path
adapter_mode
action_clip_rate
fallback_rate
latency
pwm_bounds
allowed_claims
disallowed_claims
```

其中 `ppo_evidence_level` 至少包括：

```text
stub_only
training_entrypoint_only
checkpoint_smoke
retrained_policy_smoke
```

注意：

```text
legacy_ppo_baseline 是 result_bucket，不是 ppo_evidence_level。
```

## 9. 推荐执行顺序

1. 修复 `workflows/train.py`，让它能在 Isaac Lab 2.2.1 下启动。
2. 用 `--num_envs 1 --max_iterations 1 --headless` 做训练入口 smoke，只证明入口可用。
3. 单独做 checkpoint generation smoke。因为当前 `save_interval=50`，所以需要 `--save_interval 1`、显式 final save，或者运行到足够触发保存。
4. 确认生成 `model_*.pt`。
5. 用 `discover_ppo_checkpoints.py --json` 找到 checkpoint，并读取 `selected_checkpoint`。
6. 用 legacy eval 跑一次 `legacy_ppo_baseline`，同时写 summary sidecar。
7. 再用 `play_ppo_koopman.py --policy_mode checkpoint --play_checkpoint "$SELECTED_CHECKPOINT"` 跑一次 `old_checkpoint_adapter_smoke`。
8. 如果要做新 PPO+Koopman 训练，先写 training wrapper，确保每步 adapter reference refresh。

## 9.5 Checkpoint 保存与选择规则

当前 PPO 配置在 `agents/rsl_rl_ppo_cfg.py` 中设置：

```text
max_iterations = 800
save_interval = 50
experiment_name = "easyuuv"
```

因此：

```text
--max_iterations 1 只能证明 train.py 能启动和跑一小步。
它不保证生成 checkpoint。
```

生成 checkpoint 必须满足至少一个条件：

```text
1. 训练脚本支持 --save_interval 1；
2. 训练脚本在 smoke 结束后显式 runner.save(...)；
3. 训练至少运行到当前 save_interval。
```

发现 checkpoint 时必须输出：

```json
{
  "checkpoint_found": true,
  "selected_checkpoint": ".../model_*.pt",
  "selected_rule": "explicit_path|latest_mtime_model_pt"
}
```

多 checkpoint 时优先级：

```text
显式 --play_checkpoint > 最新 model_*.pt > 其他 *.pt
```

## 9.6 Legacy PPO Baseline Sidecar

legacy PPO baseline 的 JSONL 可能只包含控制数据，不一定包含 Phase 4.6 所需的证据字段。因此需要一个 sidecar summary，例如：

```json
{
  "result_bucket": "legacy_ppo_baseline",
  "ppo_evidence_level": "checkpoint_smoke",
  "reward_profile": "legacy_easyuuv_v0",
  "controller_path": "legacy/Ssurface",
  "checkpoint_path": ".../model_*.pt",
  "selected_checkpoint": ".../model_*.pt",
  "selected_rule": "explicit_path",
  "action_dim": 4,
  "observation_dim": 9,
  "pwm_dim": 8
}
```

## 10. 允许和禁止的说法

允许说：

```text
PPO/RSL-RL checkpoint workflow is restored.
A legacy PPO checkpoint can be generated and loaded.
The checkpoint can be routed through the Koopman adapter for guarded smoke testing.
```

禁止说：

```text
PPO+Koopman 已经优于 legacy。
旧 PPO checkpoint 已经无损迁移到 Koopman+MPC。
短训练 1 iteration checkpoint 是有效策略。
Phase 4.6 已经证明训练收敛。
```

## 11. Phase 4.6 完成标准

Phase 4.6 完成时，应该能回答：

1. PPO training 入口在服务器上是否可运行？
2. 是否生成了 checkpoint？
3. checkpoint discovery 是否能找到它？
4. checkpoint 是否能被 legacy eval 加载？
5. checkpoint 是否能通过 adapter 跑短 smoke？
6. 如果做 Koopman-MPC retrain，训练时 adapter 是否真的在 loop 里？
7. summary 是否严格区分了 evidence level？

只要这些答案清楚，Phase 4.6 就没有走偏。

## 11.5 和 Phase 5 的关系

现在的 PPO 阶段主线应该这样理解：

```text
Phase 4.6:
  让 PPO/RSL-RL 工具链重新可用。
  生成、发现、加载 checkpoint。
  旧 checkpoint 只作为 legacy baseline 或 adapter smoke。

Phase 5:
  训练 Koopman-MPC 专属 PPO。
  训练时必须走 adapter + Koopman+MPC。
  这是我们的最终 PPO 主线。
```

因此，Phase 4.6 结束时不能说：

```text
PPO 已经适配 Koopman-MPC。
```

只能说：

```text
PPO 工具链和 checkpoint 证据链已经恢复，可以进入 Phase 5 训练专属 PPO。
```

## 12. Source Map

- `workflows/train.py`: PPO/RSL-RL training entrypoint.
- `agents/rsl_rl_ppo_cfg.py`: `max_iterations`、`save_interval`、`experiment_name` 的来源。
- `workflows/discover_ppo_checkpoints.py`: checkpoint 搜索根目录和后续 `selected_checkpoint` 合同。
- `workflows/play_eval.py`: legacy PPO checkpoint eval path，当前包含 `--eval_name` 和 `--koopman_log_path`。
- `workflows/play_ppo_koopman.py`: old-checkpoint adapter smoke path。
- `koopman/policy_adapter.py`: `heuristic_reference_delta_v0` 和当前 `ppo_evidence_level` 枚举。
- `.planning/phases/05-koopman-mpc-ppo-retraining/05-SPEC.md`: Phase 5 专属 PPO 训练合同。
- `docs/phase5_koopman_mpc_ppo_training_strategy.md`: Phase 5 中文策略说明。

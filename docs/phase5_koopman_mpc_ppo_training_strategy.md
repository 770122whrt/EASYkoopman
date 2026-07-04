# Phase 5 Koopman-MPC 专属 PPO 训练策略

**日期:** 2026-07-03
**文档类型:** 解释 + 执行边界
**读者:** 项目负责人、后续执行 Phase 5 的代理、Isaac 服务器操作者

## 1. 一句话结论

Koopman-MPC 这条链路需要自己的 PPO checkpoint。

这里的“自己的 PPO”不是手写 PPO 算法，而是：

```text
继续使用 RSL-RL PPO
但让 PPO 在 Koopman-MPC 闭环里重新训练
```

也就是说，最终要得到的是：

```text
obs -> PPO -> adapter -> Koopman+MPC -> PWM -> AUV
```

这条链路下训练出来的 checkpoint。

## 2. 为什么旧 PPO checkpoint 不够

原 EASYUUV PPO 学到的是：

```text
9D observation
  -> PPO
  -> 4D action
  -> legacy S-Surface/PID
  -> 8D PWM
  -> AUV
```

我们的目标链路是：

```text
9D observation
  -> PPO
  -> 4D action
  -> heuristic_reference_delta_v0
  -> 5D Koopman reference
  -> Koopman+MPC
  -> 8D PWM
  -> AUV
```

USD 模型可以相同，但 PPO 面对的 transition 已经变了。低层控制器不同，PPO action 对下一步状态的影响就不同。

所以旧 checkpoint 可以做：

```text
legacy_ppo_baseline
old_checkpoint_adapter_smoke
```

但不能作为最终的 Koopman-MPC PPO。

## 3. Phase 4.6 和 Phase 5 的分工

Phase 4.6 只负责恢复证据链：

```text
train.py 能启动
checkpoint 能生成
checkpoint discovery 能找到
checkpoint 能被 legacy eval 加载
旧 checkpoint 能做 adapter smoke
```

Phase 5 才负责训练真正属于新控制器的 PPO：

```text
PPO 训练时就走 adapter + Koopman+MPC
```

这两个阶段不能合并着说。否则很容易把“能加载旧 checkpoint”误写成“PPO 已经适配 Koopman-MPC”。

## 4. Phase 5 的固定输入输出

第一版暂时不改 PPO 的输入输出。

PPO 输入仍然是 9D：

```text
goal_quat(4) + current_depth_z(1) + current_quat(4)
```

PPO 输出仍然是 4D：

```text
roll / pitch / yaw / depth correction
```

不做这些事：

```text
不把 PPO observation 改成 11D Koopman state
不让 PPO action 直接变成 8D PWM
不手写 PPO 算法
不一开始就大改 reward
```

## 5. 真正的训练链路

Phase 5 训练时必须满足：

```text
obs_9d
  -> RSL-RL PPO policy
  -> action_4d
  -> heuristic_reference_delta_v0
  -> refresh env._koopman_reference_5d
  -> env.step(action_4d)
  -> Koopman+MPC
  -> PWM
```

最重要的检查点是：

```text
不能只设置 controller_mode = koopman_mpc。
```

如果每一步训练前没有把 PPO 的 4D action 转成 Koopman 的 5D reference，那么 PPO 并没有真正学会如何驱动 Koopman-MPC。

## 6. 第一版 reward 怎么处理

第一版保持：

```text
reward_profile = "legacy_easyuuv_v0"
```

原因是这一步已经改变了低层控制器。如果同时改 reward，就很难判断训练变化来自控制链路、reward，还是 PPO 超参数。

后续可以单独开 reward 版本，例如：

```text
koopman_mpc_v1_with_fallback_penalty
koopman_mpc_v1_with_latency_penalty
koopman_mpc_v1_tracking_energy_tradeoff
```

但不要塞进 Phase 5 第一版 smoke。

## 7. 第一版成功标准

Phase 5 第一版不是证明最优控制效果，而是证明训练链路成立。

它完成时应该能回答：

1. PPO 是否在 Koopman-MPC 闭环里训练？
2. adapter 是否真的在每个 training step 前刷新 reference？
3. 是否生成了新的 Koopman-MPC PPO checkpoint？
4. 这个 checkpoint 是否能被加载？
5. 它是否能短跑 `PPO -> adapter -> Koopman+MPC -> PWM`？
6. PWM 是否有界？
7. fallback 和 latency 是否被记录？

## 8. 允许和禁止的说法

允许说：

```text
已经训练出 Koopman-MPC 闭环下的 PPO smoke checkpoint。
checkpoint 可以加载并通过 PPO -> adapter -> Koopman+MPC -> PWM 短跑。
```

禁止说：

```text
PPO 已经收敛。
PPO+Koopman-MPC 已经优于 legacy。
这个 checkpoint 可以部署。
旧 PPO checkpoint 已经等价迁移。
```

## 9. 推荐阶段顺序

```text
Phase 4.6:
  修复 PPO train/checkpoint/load 证据链

Phase 5:
  训练 Koopman-MPC 专属 PPO

Phase 5.x:
  做更长训练、reward 调整、超参调整和性能评估

Phase 6:
  再接入 LLM 低频任务规划/调参
```

这个顺序的好处是每一步的证据都很干净：先知道 PPO 工具链能跑，再知道新闭环能训练，最后再让 LLM 进入更高层。

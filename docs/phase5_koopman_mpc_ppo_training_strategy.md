# Phase 5: Koopman-MPC 专属 PPO 训练策略

**日期:** 2026-07-04
**文档类型:** 中文解释 + 执行边界 + 服务器运行准备
**适用对象:** 项目负责人、后续实现 agent、Isaac 服务器操作者

## 1. 一句话结论

Phase 5 要训练的是“属于 Koopman-MPC 闭环的 PPO checkpoint”。

这不是手写 PPO 算法。我们继续使用 RSL-RL PPO，只是把训练时的低层控制链路从原来的 `legacy/Ssurface` 换成：

```text
PPO -> heuristic_reference_delta_v0 -> Koopman+MPC -> PWM
```

最终要证明的是：

```text
RSL-RL PPO 可以在 Koopman-MPC 闭环里训练；
训练能产出一个新的 checkpoint；
这个 checkpoint 能被加载，并短跑 PPO -> adapter -> Koopman+MPC -> PWM。
```

它仍然不是收敛证明、性能优越证明或部署证明。

## 2. 为什么旧 PPO checkpoint 不够

原始 EasyUUV PPO 学到的链路是：

```text
9D observation
  -> PPO
  -> 4D action
  -> legacy S-Surface/PID
  -> 8D PWM
  -> AUV physics
```

我们现在的目标链路是：

```text
9D observation
  -> PPO
  -> 4D action
  -> heuristic_reference_delta_v0
  -> 5D Koopman reference
  -> Koopman+MPC
  -> 8D PWM
  -> AUV physics
```

虽然 USD 模型相同，但 PPO 面对的 transition 已经变了。低层控制器不同，`action_4d` 对下一步状态的影响就不同。

所以旧 checkpoint 可以作为：

```text
legacy_ppo_baseline
old_checkpoint_adapter_smoke
```

但不能作为：

```text
retrained_ppo_koopman_mpc
```

## 3. Phase 4.6 和 Phase 5 的分工

Phase 4.6 已经解决的是“PPO 工具链是否能跑”：

```text
train.py 能启动；
checkpoint 能生成；
checkpoint discovery 能找到；
旧 checkpoint 能被 legacy eval 加载；
旧 checkpoint 能做一次 guarded adapter smoke。
```

Phase 5 解决的是“PPO 是否在新控制链路里训练”：

```text
训练时每一步 action_4d 都进入 adapter；
adapter 每步刷新 5D Koopman reference；
Koopman+MPC 用这个 reference 计算 8D PWM；
PPO 在这个闭环 transition 下更新参数。
```

这两件事不能混在一起说。能加载旧 checkpoint，不等于 PPO 已经适配 Koopman-MPC。

## 4. 固定输入输出

Phase 5 第一版不改 PPO 的输入输出。

PPO 输入仍然是 9D observation：

```text
obs_9d = [goal_quat_wxyz(4), current_depth_z(1), current_quat_wxyz(4)]
```

PPO 输出仍然是 4D action：

```text
action_4d = [roll_delta_cmd, pitch_delta_cmd, yaw_delta_cmd, depth_delta_cmd]
```

Adapter 输出是 5D Koopman reference：

```text
koopman_reference_5d = [depth_ref, quat_ref_w, quat_ref_x, quat_ref_y, quat_ref_z]
```

Koopman-MPC 输出是 8D PWM：

```text
pwm_8d = [thruster_0, ..., thruster_7]
```

禁止在 Phase 5 第一版做这些事情：

```text
把 PPO observation 改成 11D Koopman state；
让 PPO 直接输出 8D PWM；
手写 PPO 算法；
一开始就大改 reward；
把 paper_lifted_edmd 当默认底层控制器。
```

## 5. Adapter 的核心公式

当前 adapter 名称固定为：

```text
heuristic_reference_delta_v0
```

它的含义是：先暂时把 PPO 的旧 4D action 解释为一个“有界参考增量”，再转成 Koopman-MPC 能吃的 5D reference。

公式上可以理解为：

```text
a = clip(action_4d, -limit, limit)

delta_q = quat_from_euler_xyz(
    roll_scale  * a[0],
    pitch_scale * a[1],
    yaw_scale   * a[2],
)

depth_ref = clip(base_depth + depth_scale * a[3], depth_min, depth_max)
quat_ref  = normalize(base_quat * delta_q)

koopman_reference_5d = [depth_ref, quat_ref]
```

其中：

```text
base_depth 来自任务目标深度；
base_quat 来自 observation 里的目标四元数；
action_4d 来自 PPO；
reference_5d 交给 Koopman+MPC；
```

这个 adapter 是一个工程桥接假设，不是“旧 PPO 语义无损迁移”的证明。

## 6. 最重要的训练合同

Phase 5 的训练合同必须是：

```text
obs_9d
  -> RSL-RL PPO policy
  -> action_4d
  -> heuristic_reference_delta_v0
  -> refresh env._koopman_reference_5d
  -> env.step(action_4d)
  -> Koopman+MPC
  -> pwm_8d
  -> physics
```

关键点是：adapter 必须在 RSL-RL 真正的 `env.step(action_4d)` 路径上执行。

因为 RSL-RL 的 `OnPolicyRunner.learn()` 内部拥有 rollout loop，外层训练脚本无法逐步手动控制 action。如果只是写：

```text
env_cfg.controller_mode = koopman_mpc
```

但没有在训练 step 前刷新 `_koopman_reference_5d`，那就是假闭环。

## 7. 推荐实现方式

优先实现一个训练 wrapper：

```text
gym.make(...)
  -> Phase5KoopmanReferenceWrapper.step(action_4d)
       -> 根据当前目标构造 base_reference_5d
       -> 调用 adapt_policy_reference(...)
       -> 写入 env._koopman_reference_5d
       -> 调用底层 env.step(action_4d)
  -> RslRlVecEnvWrapper(...)
  -> OnPolicyRunner.learn(...)
```

如果 Isaac Lab 的 wrapper 属性透传出现问题，再退一步把 hook 放进 `EasyUUVEnv._pre_physics_step()`，但必须用显式配置打开，避免影响旧 controller 和 Phase 4.5 的 inference workflow。

无论实现在哪，source-contract test 都必须证明：

```text
action_4d -> adapter -> reference refresh -> env.step
```

而不是只证明 `controller_mode=koopman_mpc` 被设置了。

## 8. Checkpoint provenance gate

Phase 5 必须防止旧 checkpoint 被误贴标签。

一个 checkpoint 只有在 source training summary 里同时满足以下字段时，才能被称为 `retrained_policy_smoke`：

```text
result_bucket = retrained_ppo_koopman_mpc
controller_path = koopman_mpc/direct_state
adapter_mode = heuristic_reference_delta_v0
reward_profile = legacy_easyuuv_v0
checkpoint_provenance = phase5_train_koopman_mpc
observation_dim = 9
action_dim = 4
```

评估脚本需要读取这个 summary，并记录：

```text
source_training_summary_path
source_result_bucket
source_controller_path
source_adapter_mode
source_koopman_backend
source_reward_profile
source_log_dir
source_git_commit
source_checkpoint_mtime
```

如果 discovery 找到的是 Phase 4.6 的 checkpoint，它只能作为：

```text
old_checkpoint_adapter_smoke
```

不能改名成 Phase 5 retrained checkpoint。

## 9. Reward 处理

Phase 5 第一版保持：

```text
reward_profile = legacy_easyuuv_v0
```

原因是这一步已经改变了低层控制器。如果同时改 reward，就无法判断结果变化来自哪里：

```text
adapter 变了？
Koopman-MPC 变了？
reward 变了？
PPO 超参变了？
```

后续可以单独开 Phase 5.x 做 reward 版本，例如：

```text
koopman_mpc_v1_with_fallback_penalty
koopman_mpc_v1_with_latency_penalty
koopman_mpc_v1_tracking_energy_tradeoff
```

但 Phase 5 第一版不做这个。

## 10. 服务器第一轮命令形态

训练 smoke 命令形态：

```bash
cd /root/IsaacLab
source /opt/conda/etc/profile.d/conda.sh
conda activate isaaclab
WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/train_ppo_koopman.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --max_iterations 1 \
  --save_interval 1 \
  --controller_mode koopman_mpc \
  --adapter_mode heuristic_reference_delta_v0 \
  --koopman_backend direct_state \
  --koopman_manifest_path /root/EASYkoopman/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json \
  --result_bucket retrained_ppo_koopman_mpc \
  --ppo_evidence_level retrained_policy_smoke \
  --reward_profile legacy_easyuuv_v0 \
  --phase5_summary_path /root/EASYkoopman/source/results/koopman_phase5/training_smoke_summary.json
```

评估 smoke 命令形态：

```bash
cd /root/IsaacLab
SELECTED_CHECKPOINT=/path/to/phase5/model_*.pt
WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_ppo_koopman.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --policy_mode checkpoint \
  --play_checkpoint "$SELECTED_CHECKPOINT" \
  --source_training_summary_path /root/EASYkoopman/source/results/koopman_phase5/training_smoke_summary.json \
  --controller_mode koopman_mpc \
  --koopman_manifest_path /root/EASYkoopman/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json \
  --trajectory_type step \
  --trajectory_cycles 1 \
  --steps_per_action 50 \
  --result_bucket retrained_ppo_koopman_mpc \
  --ppo_evidence_level retrained_policy_smoke \
  --ppo_koopman_log_path /root/EASYkoopman/source/results/koopman_phase5/retrained_ppo_koopman_step.jsonl
```

实际实现时命令可能微调，但这些字段不能少。

## 11. Phase 5 成功标准

Phase 5 第一版成功时，应该能回答：

1. PPO 是否在 Koopman-MPC 闭环里训练？
2. Adapter 是否真的在 RSL-RL `env.step()` 路径上每步刷新 reference？
3. 是否生成了新的 Koopman-MPC PPO checkpoint？
4. 这个 checkpoint 的 provenance 是否能排除旧 checkpoint？
5. 这个 checkpoint 是否能被加载？
6. 它是否能短跑 `PPO -> adapter -> Koopman+MPC -> PWM`？
7. PWM 是否有界？
8. fallback、latency、action clipping 是否被记录？

允许说：

```text
已经得到 Koopman-MPC 闭环下的 PPO smoke checkpoint。
该 checkpoint 可以加载并短跑 PPO -> adapter -> Koopman+MPC -> PWM。
```

禁止说：

```text
PPO 已经收敛；
PPO+Koopman-MPC 已经优于 legacy；
这个 checkpoint 可以部署；
旧 PPO checkpoint 已经等价迁移；
reward 已经最终确定。
```

## 12. 下一阶段关系

推荐顺序：

```text
Phase 5:
  短训闭环 smoke，证明 retrained PPO 链路成立。

Phase 5.x:
  长训练、reward 版本、超参搜索、性能评估。

Phase 6:
  LLM 低频任务规划/调参，不进入实时控制。
```

这个顺序的核心好处是证据干净：先证明训练闭环存在，再谈 PPO 训练效果，最后再让 LLM 进入更高层的规划或调参。

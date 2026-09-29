# Phase 2: Offline Koopman Identification - Specification

**Created:** 2026-06-30
**Ambiguity score:** 0.13 (gate: <= 0.20)
**Requirements:** 6 locked

## Goal

从已经验证过的 EasyUUV Koopman JSONL 日志中，离线训练、保存并评估一个可被 Phase 3 Koopman+MPC 使用的受控 Koopman/EDMD 动力学模型。

## Background

Phase 1 已经建立 legacy controller boundary 和 Koopman JSONL schema。Phase 1.5 已经在服务器 Isaac Sim 5.0 + Isaac Lab 2.2.1 上跑通 direct-controller smoke rollout，并用 `workflows/validate_koopman_log.py` 验证了日志结构。

当前已经存在：

- `koopman_data.py`: JSONL sample 构造、验证、读取和 replay tuple 重建。
- `workflows/koopman_logging.py`: 从 Isaac 环境记录 state/reference/action/PWM/next_state。
- `workflows/validate_koopman_log.py`: 离线验证 JSONL schema 和时间戳。

当前缺口：

- 没有把 JSONL 转换为训练矩阵的数据集模块。
- 没有 Koopman lifting 函数。
- 没有 EDMD/ridge regression 训练器。
- 没有模型保存/加载格式。
- 没有 one-step 和 multi-step prediction 评估。

## Requirements

1. **Dataset ingestion**: JSONL 日志必须能被转换为固定维度训练矩阵。
   - Current: `reconstruct_training_tuples()` 只返回 Python list tuple，不能直接用于矩阵训练。
   - Target: 新增离线数据集模块，把一个或多个 JSONL 文件转换为 `X`, `U`, `R`, `Y` 矩阵，其中 `X/Y` 为 11 维状态，`U` 为 8 维 PWM，`R` 为 5 维参考。
   - Acceptance: fixture JSONL 通过单元测试转换为形状确定的矩阵，并拒绝空日志、非递增时间戳和维度不匹配样本。

2. **Lifting function**: Koopman 特征映射必须确定、可配置、可复现。
   - Current: 项目中没有 lifting 模块。
   - Target: 新增 `koopman/lifting.py`，至少支持 raw state/reference features、reference error features、可选二次项，并暴露 feature dimension metadata。
   - Acceptance: 单元测试确认相同输入产生相同 feature，输出维度与配置一致，非法维度输入抛出清晰异常。

3. **EDMD training**: 离线训练器必须拟合受控 Koopman 预测模型。
   - Current: 项目中没有 EDMD 训练逻辑。
   - Target: 新增 `koopman/edmd.py`，用 ridge regression 拟合 `phi(x_{k+1}, r_{k+1}) = A phi(x_k, r_k) + B u_k` 或等价受控形式。
   - Acceptance: 在线性合成 fixture 上训练后，one-step prediction error 低于测试阈值，并且训练过程不导入 Isaac/Omniverse。

4. **Model artifact**: 训练结果必须能保存和加载。
   - Current: 没有模型 artifact。
   - Target: 保存矩阵、正则系数、特征配置、状态/参考/控制维度、训练数据摘要和版本号。
   - Acceptance: 保存后重新加载模型，对同一 batch 的预测结果与保存前一致。

5. **Prediction evaluation**: 必须报告 one-step 和 multi-step 预测误差。
   - Current: 没有预测评估。
   - Target: 新增评估模块，输出 depth、quaternion/state、velocity 的 one-step 和 rollout metrics。
   - Acceptance: CLI 或测试能生成 metrics JSON，包含样本数、one-step RMSE、multi-step horizon 和 multi-step RMSE。

6. **Offline workflow commands**: 训练和评估必须能在本地运行，不依赖 Isaac。
   - Current: 只有 Isaac rollout workflow 和日志 validator。
   - Target: 新增本地 workflow，例如 `workflows/train_koopman.py` 和 `workflows/evaluate_koopman.py`。
   - Acceptance: `--help` 可运行；fixture 日志可完成训练、保存模型、加载模型并输出评估文件。

## Boundaries

**In scope:**

- 离线 JSONL 数据加载和矩阵化。
- Koopman lifting 函数。
- EDMD/ridge regression 训练。
- 模型保存/加载。
- one-step 和 multi-step 离线预测评估。
- 适用于本地开发机的纯 Python 测试和 CLI。
- 使用服务器采集到的 legacy-controller logs 作为训练输入。

**Out of scope:**

- 在本阶段替换 Isaac 中的控制器 - 这是 Phase 3。
- MPC 求解器和闭环控制 - 这是 Phase 3。
- 强化学习调参 - 当前目标是 system identification，不是 RL。
- 在线 Kalman/RLS adaptation - 这是 Phase 5。
- 重新设计 EasyUUV 物理模型或 USD 结构 - 当前只消费已有日志。
- 用两条 smoke samples 训练正式模型 - 它们只用于 schema 验证。

## Constraints

- Phase 2 代码不得导入 Isaac、Omniverse、Kit、Gym task registration。
- 数据维度沿用 Phase 1.5 验证结果：`state=11`, `reference=5`, `pwm=8`。
- PWM 必须视为控制输入 `u_k`，范围为 `[-1, 1]`。
- 当前 smoke log 只有 2 samples，只能用于 validator 和 fixture，不足以训练正式模型。
- 训练器应优先使用轻量依赖；如需新增依赖，必须先说明原因。
- 模型 artifact 必须记录 schema/version，避免 Phase 3 加载错误模型。

## Acceptance Criteria

- [ ] 本地测试能从 fixture JSONL 构造训练矩阵。
- [ ] 本地测试能验证 lifting 输出维度和确定性。
- [ ] 本地测试能在合成线性系统上训练 EDMD 并达到误差阈值。
- [ ] 本地测试能保存并加载模型，预测结果保持一致。
- [ ] 本地 CLI 能用 fixture 日志完成训练和评估。
- [ ] `python -m pytest -q` 通过。
- [ ] `python -m compileall koopman workflows tests` 通过。
- [ ] Phase 2 代码路径不依赖 Isaac runtime。

## Ambiguity Report

| Dimension | Score | Min | Status | Notes |
|---|---:|---:|---|---|
| Goal Clarity | 0.90 | 0.75 | met | 输出是可保存、可评估、可供 MPC 使用的 Koopman model |
| Boundary Clarity | 0.88 | 0.70 | met | 明确不做 MPC、RL、在线 adaptation |
| Constraint Clarity | 0.82 | 0.65 | met | 维度、离线约束、输入范围已经锁定 |
| Acceptance Criteria | 0.86 | 0.70 | met | 每项都有测试或 CLI 验证 |
| **Ambiguity** | **0.13** | **<=0.20** | met | 可以进入 plan |

## Interview Log

| Round | Perspective | Question summary | Decision locked |
|---|---|---|---|
| 1 | Researcher | 当前代码已经有什么？ | 已有 JSONL schema、validator、Isaac smoke log；缺 EDMD/lifting/model artifact |
| 2 | Simplifier | 最小成功版本是什么？ | 先做离线 EDMD，不做 MPC，不做 RL |
| 3 | Boundary Keeper | 什么不属于本阶段？ | Isaac 闭环控制、MPC solver、在线 adaptation 全部推迟 |
| 4 | Failure Analyst | 最容易失败在哪里？ | 用 2 samples 误以为能训练；用错维度；模型 artifact 缺版本 |
| 5 | Seed Closer | 服务器和本地边界怎么定？ | Phase 2 本地完成；只有采集更多数据需要服务器 Isaac |

---

*Phase: 02-offline-koopman-identification*
*Next step: implement Phase 2 plan locally, then use longer server logs for real training.*


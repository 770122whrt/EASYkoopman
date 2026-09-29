# EASYkoopman 阶段进展与当前困难汇报

**汇报对象：** 学长 / 项目组
**更新时间：** 2026-09-02
**当前阶段：** Phase 8.2 实验与独立 closeout 已完成，终局结果为 `NO_SELECTION`

## 1. 先说结论

目前项目在工程上取得了比较明确的进展：八种 AUV 构型的数据采集、统一控制接口、模型训练、八折留一构型评估、测试集隔离和独立结果核验都已经跑通。Phase 8.2 的 closeout 状态为 `VERIFIED`，说明这次实验过程完整、结果可追溯，不是因为数据缺失或程序中断而结束。

但是，模型层面的结论是负面的。现有 pooled Koopman 没有超过 simple linear；八折最终选中的 pooled 候选都属于 `so3_linear_increment_ridge_v1` 等价类，因此它实际上没有体现出比线性模型更强的建模能力。conditional Koopman 在八个 fold 中都没有产生可以进入最终测试的候选。因此，最终结果是 `NO_SELECTION`，没有模型可以交接给 Phase 9。

这两点需要同时讲清楚：**我们的实验和控制基础设施是有效的，但当前 Koopman 方案的跨构型优势没有被实验支持。**

## 2. 当前研究方向是否合理

当前大的研究方向仍然合理：我们不是只在一台固定 AUV 上调参数，而是在研究同一套模型与控制架构能否跨不同质量、几何尺寸和推进器拓扑迁移。这个问题比单构型 nominal tuning 更接近项目希望讨论的“多构型迁移、环境感知和 Agentic 控制”。

但本轮结果也说明，原先隐含的一个假设过强：**仅靠固定的 `state_11 + actuator_memory_4 + virtual_control_4` 输入和当前 observables，就能完成跨 4/6/8 推进器拓扑的零样本预测迁移。** 目前证据并不支持这个假设。

所以，方向本身不需要推翻，但下一步应该从“继续扩大 Koopman-MPC”改成“先定位模型为什么没有获得非线性和跨构型收益”。在定位完成前直接进入闭环 MPC，只会把预测误差、控制优化误差和执行器分配误差叠加在一起，反而更难解释问题。

## 3. 实验设计、参数与数据采集

### 3.1 实验问题

本轮 Phase 8.2 要回答的是：

> 在固定的八种 EasyUUV 构型中，使用其中七种构型的训练和验证数据完成模型选择后，该模型能否在完全留出的第八种构型上取得优于线性基线的开环多步预测性能？

八种构型为：

- 参数变化：`base`、`long_body`、`heavy_moderate`、`asymmetric`；
- 推进器拓扑变化：`uuv6`、`uuv6_angled`、`uuv4`、`uuv4_angled`。

其中 `uuv4*` 是无偏航控制能力的欠驱动构型，实验和控制接口中都显式屏蔽了 yaw 通道，不能把不可实现的偏航跟踪作为正常控制目标。

### 3.2 采集参数

| 项目 | 固定设置 |
|---|---|
| 仿真任务 | `EasyUUV-Direct-v1` |
| 数据版本 | `easyuuv-koopman-transition-v2.1` |
| 控制方式 | `deterministic_bounded_excitation` |
| 激励类型 | independent PRBS、bounded multisine、coupled chirp |
| 每构型训练集 | 3 类激励 × 2 次重复，共 6 个 episode |
| 每构型验证集 | 3 类激励 × 1 次重复，共 3 个 episode |
| 每构型测试集 | 3 类激励 × 1 次重复，共 3 个 episode |
| 总数据量 | 8 × 12 = 96 个 episode |
| 单 episode 长度 | 512 个 transition |
| transition 总量 | 49,152 |
| 原始控制幅值 | `abs(raw_action) <= 0.25` |
| 物理仿真周期 | `1/120 s` |
| 控制周期 | `1/60 s`，decimation = 2 |
| 环境条件 | 无扰动、无传感器噪声、无 domain randomization |
| reference | step reference |
| actuator memory 初值 | `[0, 0, 0, 0]`，无未记录 warm-up |

不同构型在相同 role、激励类型和重复次数下使用匹配的随机种子。这样可以减少“某个构型刚好遇到了更难初始状态”造成的不公平比较。

### 3.3 模型候选与指标

模型输入固定为 19 维：

```text
state_11 + actuator_memory_4 + virtual_control_4
```

候选模型包含 pooled 和 conditional 两个可晋级 family。每个 family 组合以下参数：

- fit episode prefix：`2 / 4 / 6`；
- observables：`so3_identity_v1 / so3_kinematic_v1`；
- ridge：`1e-8 / 1e-6 / 1e-4 / 1e-2`；
- normalization：`none / standard_v1`。

因此每个 family 每折有 48 个候选，pooled 与 conditional 合计每折 96 个候选。conditional 额外使用 source 7 构型生成的二维物理描述 PCA，但不允许读取 held-out 构型统计量来帮助选择。

正式预测长度为 5、20、60 步和完整 episode。六项主要指标均为越低越好：

- depth RMSE；
- linear velocity RMSE；
- angular velocity RMSE；
- SO(3) geodesic mean、RMSE 和 max error。

除平均性能外，还检查最差构型、单构型非劣性以及 divergence、non-finite、非法四元数等健康指标。晋级至少要求 1% 改善，单构型允许的非劣性边界为 10%；Bootstrap 使用 2,000 次 episode-block 重采样。

## 4. 数据如何验证

验证不是只看程序最后有没有输出文件，而是分成五层：

1. **采集前冻结实验。** 实验 ID、96 个 episode 的角色和种子、候选空间、指标、阈值及 Bootstrap 参数在正式采集前由 D-23 固定。
2. **服务器真实采集。** 从验证过的 Git bundle 建立全新 server checkout 和结果目录；只有 96 组 episode、manifest、log 全部通过时才生成 inventory。
3. **本地 staged pullback。** 回传后重新检查 source commit、协议哈希、文件数量、相对路径哈希、schema、manifest 和 LOCO split，然后才原子提升为 canonical dataset。
4. **八折 LOCO 隔离。** 每折只使用七个 source 构型的 fit/validation 选择候选；source ledger 和模型冻结后才允许打开 held-out test。每折在独立进程中运行，八折全部通过后才组装正式 evaluation。
5. **终局独立 closeout。** 再检查 dataset、evaluation、selection、八折完整性、测试读取顺序和模型路径语义。当前记录为 `zero_test_read_audit=true`、`fold_count=8`、`status=VERIFIED`。

因此，本轮可以支持的结论仅限于：**在修复后的模拟器中新采集的数据上，对固定八构型目录进行留一构型开环预测评估。** 它还不能证明任意新 AUV、环境迁移、闭环控制、硬件或 Agent 能力。

## 5. 当前控制链路

### 5.1 仿真器中实际运行的低层控制链

```text
任务目标 / 上层 raw_action_4
        ↓
S-surface / PID
        ↓
通道修正 + 构型可控自由度 mask
        ↓
virtual_control_4 = [roll, pitch, yaw, depth]
        ↓
构型对应的 TAM / thrust allocation
        ↓
4、6 或 8 路 PWM，限制在 [-1, 1]
        ↓
推进器滞后、死区、推力映射与效率模型
        ↓
机体 force / torque
        ↓
水动力学 + Isaac physics
        ↓
next state_11
```

八推进器构型沿用 legacy allocation；六推进器构型使用 pseudoinverse；四推进器构型使用带可控自由度权重的 WLS。拓扑差异发生在 `virtual_control_4` 之后，因此 Koopman 面向的控制语义可以在 4/6/8 推进器之间保持统一。

### 5.2 Phase 8.2 中 Koopman 学习的链路

```text
(state_11[t], actuator_memory_4[t], virtual_control_4[t])
                         ↓
                 Koopman predictor
                         ↓
                    state_11[t+1]
```

`actuator_memory_4` 是由过去控制递推得到的因果执行器代理，用来描述控制作用不会瞬时到达推进器的滞后。本轮评估采用递归开环 rollout：预测得到的状态继续作为下一步输入，因此长时域误差会逐步累积。

### 5.3 与历史 v1 控制链的区别

v1 已经验证过的闭环链为：

```text
observation_9d
  -> PPO
  -> action_4d
  -> heuristic_reference_delta_v0
  -> reference_5d
  -> direct_state Koopman + bounded MPC
  -> PWM_8d
  -> Isaac physics
```

这条链只适用于固定八维 PWM 的单构型系统。v2.1 把跨构型模型控制量改成 TAM 前的 `virtual_control_4`，解决了不同推进器数量下控制维度不一致的问题。

如果未来进入 Phase 9，MPC 应直接优化有界的 `virtual_control_4`，然后在 TAM 前注入。不能把 MPC 输出再次送进 S-surface/PID，否则会形成双重控制，也会使模型输入和真实执行输入不一致。

## 6. 当前实验结果

终局选择结果为：

```text
status              = NO_SELECTION
selected_family     = null
selected_candidate  = null
selected_model_path = null
model_handoff       = false
```

pooled 候选、simple linear 和 persistence 在完整时域 equal-configuration macro 上的结果如下，所有指标均为越低越好：

| 指标 | pooled Koopman | simple linear | persistence |
|---|---:|---:|---:|
| depth RMSE | 0.5061 | 0.5061 | **0.4728** |
| linear velocity RMSE | 0.0966 | 0.0966 | **0.0846** |
| angular velocity RMSE | 0.8376 | 0.8376 | **0.7613** |
| SO(3) mean | 1.2977 | 1.2977 | **1.0731** |
| SO(3) RMSE | 1.4236 | 1.4236 | **1.1453** |
| SO(3) max | 2.1764 | 2.1764 | **1.7352** |

pooled 模型的 divergence、non-finite、非法四元数和单位范数漂移计数都为 0，所以它不是“数值崩溃”，而是“稳定地预测，但预测得不够好”。

conditional family 的 48 个候选在每一折都无法通过 source validation rollout；`heavy_moderate` 留出折中还有 6 个候选因 regularized condition 超限而提前失败。因此 conditional 没有资格进入 held-out primary test，最终以 `source_candidate_unavailable` fail closed。

## 7. 为什么 Koopman 仍然比不过线性

目前能确认的事实是：八折 source selector 最终选出的 pooled 候选全部使用 `so3_identity_v1`，并属于与 simple linear 相同的 estimator equivalence class。换句话说，候选空间虽然包含更丰富的 Koopman observables，但验证集认为这些非线性候选更差，最后保留下来的仍是线性形式，所以两者六项指标完全相同。

至于为什么更丰富的候选没有胜出，目前只能提出待验证的解释，不能当成已经证明的原因：

- 当前无扰动、小幅值激励可能主要覆盖局部近线性区域，非线性 observables 得不到足够辨识信号；
- 一次把质量、尺寸、推进器数量、推进器角度和欠驱动性都作为零样本迁移目标，跨域跨度可能过大；
- `virtual_control_4` 统一了控制语义，但 TAM、推进器动态和水动力差异仍然会产生不同的状态响应；
- 当前二维 conditional descriptor 可能不足以表达这些差异，交互特征又带来了条件数和长时 rollout 稳定性问题；
- full rollout 对微小的一步误差非常敏感，而 persistence 在短而平滑的局部轨迹上本身就是很强的基线。

因此，当前结论不能写成“Koopman 理论无效”，更准确的说法是：**当前 observable、条件化方式、数据覆盖范围和零样本迁移设定的组合，没有产生超过线性基线的可验证收益。**

## 8. Phase 进展

| Phase | 主要工作 | 当前判断 |
|---|---|---|
| Phase 1–5.4 | 单构型数据、EDMD、模型门、Koopman-MPC、PPO adapter 和参数评估 | 工程闭环已打通；最终也是 `NO_SELECTION`，legacy 仍是强基线 |
| Phase 6 | 八构型、推进器拓扑、TAM rank 和可控自由度资格检查 | 完成并验证 |
| Phase 7 | schema v2、`virtual_control_4`、拓扑独立 Bridge 和服务器证据 | 完成并验证 |
| Phase 8 | 第一轮 exact-eight LOCO identification | 完成，得到有效负结果，并暴露时序与模型语义问题 |
| Phase 8.1 | 修复首步执行器时序，引入 causal actuator memory、SO(3) backend 和新 conditional 设计 | 本地修复与 D-23 协议完成 |
| Phase 8.2 | 新服务器数据、96 episodes、八折 LOCO、outer selection 和独立 closeout | 实验产物完成；`VERIFIED + NO_SELECTION`；无模型 handoff |
| Phase 9 | configuration-aware Koopman-MPC | 原计划执行被阻塞；不能在没有 handoff 模型时直接开始 |
| Phase 10–12 | 环境适应、Agent Supervisor、最终 matched evaluation | 尚未进入实验，不能作为当前成果 |

Phase 8.2 的规划状态现已同步：`.planning/ROADMAP.md` 和 `.planning/STATE.md` 均记录 4/4 plans complete，四份 plan summary 与独立 `08.2-VERIFICATION.md` 已补齐。canonical 科学结论仍以 `source/results/koopman_phase8_2/{selection,closeout}` 为准，planning 文档负责解释阶段进展和证据边界，不替代原始实验产物。

## 9. 当前困难与下一步建议

当前真正的困难不是程序是否能运行，而是如何把“统一跨构型接口”进一步变成“有预测价值的跨构型模型”。建议下一步分成两个层次。

### 9.1 先做失败归因，不直接进入 Phase 9

冻结并保留 Phase 8.2 负结果，建立新的实验 ID，依次回答：

1. 非线性候选是在 one-step、5/20/60 还是 full horizon 开始失效；
2. 失败主要来自参数变化，还是来自 4/6/8 推进器拓扑变化；
3. conditional 是因为 descriptor 表达不足、设计矩阵病态，还是递归 rollout 不稳定；
4. 扩大激励幅值或加入更有针对性的轴向组合后，非线性收益是否出现。

这些诊断应优先使用现有 source fit/validation 数据，不重新读取 held-out test 来调参。若需要改变激励、observable、candidate 或 threshold，应创建新的 protocol，而不是回改本轮结果。

### 9.2 根据诊断结果选择新的科学问题

如果零样本跨拓扑仍明显弱于线性，可以考虑三条方向：

- 把目标收窄为“同拓扑跨参数迁移”，先验证 `base/long_body/heavy/asymmetric` 是否存在可靠收益；
- 从纯零样本 LOCO 改为少量目标构型数据的 few-shot adaptation，研究适应效率而不是强行声称零样本泛化；
- 使用 linear/physics baseline 负责主体动态，Koopman 只学习 residual 或环境变化，并保留 legacy fallback。

如果经过上述诊断后 Koopman 仍然不如线性，就应诚实地把 simple linear 或 physics-informed linear 作为 Phase 9 的研究基线，并将项目贡献转向：统一跨拓扑控制接口、严格无泄漏评估、失败归因和安全模型拒绝机制。不能为了进入后续 Phase 而放宽当前晋级门。

## 10. 可直接向学长汇报的版本

目前我们已经完成八种 AUV 构型的数据采集和正式评估，共采集 96 个 episode、49,152 个状态转移。实验采用八折留一构型验证：每次只用七种构型训练和选模型，模型冻结后才打开第八种构型的测试数据。最终数据、八折结果和测试隔离都通过了独立核验，因此实验流程是可信的。

控制方面，我们已经把不同推进器数量统一到 TAM 前的四维虚拟控制量。上层动作先经过 S-surface/PID，得到 roll、pitch、yaw、depth 四维控制，再由不同构型的推力分配器转换为 4、6 或 8 路 PWM，最后进入推进器、水动力和 Isaac 物理仿真。Koopman 当前学习的是这四维控制作用下的状态变化，但本轮验证的还是开环预测，不是 Koopman-MPC 闭环效果。

本轮结果是 `NO_SELECTION`。pooled Koopman 最终退化到了与 simple linear 等价的模型，六项主要指标完全相同，而且完整时域上没有超过 persistence；conditional Koopman 则没有通过源构型验证。因此现在不是实验没有跑通，而是严格实验跑通以后，现有 Koopman 方案确实没有表现出足够的跨构型优势。

下一步建议先暂停 Phase 9，针对激励覆盖、非线性 observables、构型描述和跨拓扑零样本假设做失败归因。如果改进后仍不如线性，就保留这个负结果，并把后续方向转为同拓扑迁移、few-shot adaptation 或 linear/physics + Koopman residual，而不是为了继续 Phase 强行放宽模型门槛。

> **一句话总结：我们已经建立了一条能够可靠采集、比较并拒绝不合格模型的跨构型实验链，但还没有证明现有 Koopman 能够跨构型优于线性基线。**

## 11. 主要证据入口

- 实验角色与采集矩阵：[`protocols/phase8_1/main_role_assignment_protocol.json`](../protocols/phase8_1/main_role_assignment_protocol.json)
- 候选、指标与晋级门：[`protocols/phase8_1/analysis_policy.json`](../protocols/phase8_1/analysis_policy.json)
- D-23 固定记录：[`protocols/phase8_1/d23_approval.json`](../protocols/phase8_1/d23_approval.json)
- 正式选择结果：[`source/results/koopman_phase8_2/selection/selection_result.json`](../source/results/koopman_phase8_2/selection/selection_result.json)
- 独立 closeout：[`source/results/koopman_phase8_2/closeout/closeout.json`](../source/results/koopman_phase8_2/closeout/closeout.json)
- Phase 8.2 运行边界：[`docs/phase8_2_fresh_server_evaluation_runbook.md`](phase8_2_fresh_server_evaluation_runbook.md)
- Phase 8.2 独立验证：[`08.2-VERIFICATION.md`](../.planning/phases/08.2-phase-8-1-fresh-server-evaluation-and-closeout/08.2-VERIFICATION.md)

# Phase 8.2 后控制合同问题审计与路线转折点

**Checkpoint ID:** `phase8.2-post-closeout-control-contract-turning-point-20260903`  
**记录日期:** 2026-09-03  
**当前分支:** `no-selection`  
**性质:** 外部问题清单转写 + 针对当前代码的静态审计 + roadmap 变更建议  
**状态:** 讨论稿；本文件不修改已冻结的 Phase 8.2 证据，也不授权进入 Phase 9

## 0. 结论先行

PDF 提出的方向总体成立，但六个问题需要分层处理：

1. **问题 2、问题 3 是当前代码可以直接确认的 transition/reset 缺陷，优先级最高。** 一个 `env.step()` 包含两个 physics substep，低层控制在两个 substep 都会重算，而 Bridge 只保存最后一次 telemetry；同时 episode reset 没有清零 `old_actions`。这会使一部分训练行的“输入—状态转移”关系不严格成立。
2. **问题 1、问题 4、问题 5 是建模合同不充分，不等于 TAM 设计错误。** `virtual_control_4` 统一了控制通道名称和维度，却不是跨构型一致的物理力/力矩；现有 `actuator_memory_4` 只是可部署的 4D 滤波代理，不是 4/6/8 个推进器的真实动态状态；平台条件特征虽包含质量、惯量、推数、控制 rank 等信息，但没有完整表示分配矩阵、控制权威和非线性执行器链。
3. **问题 6 是真实风险，但现有 roadmap 已经认识到它。** 历史 MPC 是固定 8D PWM 接口，而 Phase 9 已明确要求在 TAM 前的 4D virtual-control 空间优化。因此不能复用旧 MPC 控制链，但无需因此推翻 Phase 9 的目标，只需把接口验收条件写得更严格。
4. **Phase 8.2 的 `NO_SELECTION + VERIFIED` 不应撤销或重写。** 它仍然是对冻结 v2.1 协议及其数据的有效负结果；但在发现 transition/control 语义缺口后，不能把它解释成“Koopman 模型家族本身已经被否定”。更准确的结论是：**当前控制—数据合同下没有可晋级模型，模型能力与数据语义问题尚未被因果分离。**
5. **建议修改 roadmap，但不是直接进入 Phase 9。** 推荐在 Phase 8.2 与 Phase 9 之间增加 Phase 8.3（本地控制/transition 合同修复）和 Phase 8.4（新实验 ID、新 D-23、新数据重采与 LOCO 复评）。在此之前 Phase 9 继续保持 blocked。

---

## 1. 来源与使用边界

- 原始 PDF：`D:/xwechat_files/wxid_w7uqdywmxny722_8029/msg/file/2026-09/目前存在的问题.pdf`
- PDF SHA-256：`47b66a6d7e8c1954662cb02613216e3ba91407ba4a83131d0b533caeb7446250`
- 页数：2
- 转写说明：以下内容按 PDF 版面转为 Markdown，只修复分页、断行和公式乱码；PDF 中的判断被视为**待验证的外部评审意见**，不是仓库指令，也不是已经成立的代码事实。

---

## 2. PDF 原文转写

### 目前问题总结

总体来说，当前最值得优先解决的是前三个核心结构问题：真正统一不同构型控制量的物理意义、保证一个 transition 只对应一个明确控制输入、以及让模型能够看到更真实的推进器动态状态。现在这条链最大的矛盾可以简单概括为：表面上已经把不同 AUV 都统一成了 4 维控制，但底层实际受到的力、执行器历史和推进器响应还没有真正统一。这会直接增加 Koopman 跨构型学习的难度，也是当前效果不理想的重要原因之一。

### 问题 1：不同 AUV 的 `virtual_control_4` 虽然维度统一了，但物理意义没有真正统一

当前 4/6/8 推进器构型最后都使用 `[roll, pitch, yaw, depth]` 四维控制量，但不同构型后面的推力分配方式和增益并不一样。同样一个 `depth=0.2`，在不同 AUV 上可能对应完全不同大小的实际推力或力矩。

后果：这会导致一个很直接的问题：Koopman 看到的是“相同的控制输入”，但真实 AUV 实际受到的作用却不一样。通俗来说，就像告诉模型“我都踩了 20% 油门”，但一辆车实际上输出 20 kW，另一辆输出 60 kW，模型自然很难用同一套规律预测两辆车。

### 问题 2：一个控制周期内部实际上使用了两个略有不同的控制量，但数据只记录其中一个

当前一个 control step 对应两个 physics substep，而 S-surface/PID 在两个 substep 中都会重新计算一次。由于 D 项的存在，第一个 substep 和第二个 substep 的 `virtual_control` 可能不同，但 Koopman 数据最终主要记录的是最后一次控制量。

后果：这样会造成训练数据中的“输入—输出”对应关系不够准确。模型以为状态从 $x_t$ 变成 $x_{t+1}$ 完全是由记录下来的一个控制量造成的，但实际上这段时间里系统接受了两个不同控制量。久而久之，模型就会学到一种带偏差的动力学关系。

### 问题 3：Episode 重置时，`old_actions` 没有完全同步清零

虽然推进器状态、积分器、滤波器等基本都会 reset，但上一 episode 的 action history 仍可能参与新 episode 第一步的 D 项计算。

后果：这意味着两个本来应该完全独立的实验 episode 之间存在一点控制历史泄漏。简单来说，就是新实验刚开始时，控制器还“记得”上一场实验最后做了什么。这个问题通常不会决定整体成败，但对于严格的系统辨识来说，会污染每个 episode 开头的数据。

### 问题 4：当前 `actuator_memory_4` 过于简化，不能完整表示真实推进器状态

现在模型只保存 TAM 之前的 4 维 virtual-control memory，但真实控制链后面还有 4、6 或 8 个推进器，各自经历推力分配、死区、非线性映射和执行器滞后。因此即使模型看到相同的 `state + actuator memory + virtual control`，真实推进器内部状态也可能不同。

后果：这会造成模型输入信息不完整。通俗来说，就是模型只知道“驾驶员刚才怎么打方向盘”，却不知道四个车轮现在各自在什么状态，因此有时候同样的输入会得到不同的下一状态，模型自然很难预测准确。

### 问题 5：当前不同构型虽然经过 TAM 统一接口，但推进器几何差异并没有真正被控制链消除

不同 AUV 的推进器数量、安装角度、力臂和分配矩阵都不一样。因此同一个 virtual control 经过不同 TAM 后，会产生不同的推进器工作状态和实际 wrench。

后果：这会让所谓的“统一控制接口”更像是统一了格式，而不是统一了真实动力学行为。这也是为什么 pooled Koopman 很容易发现：相同输入在不同构型上对应不同响应，从而最终只能退回更保守的线性模型。

### 问题 6：当前控制链与未来 Koopman-MPC 的接口还没有完全统一

现在 Phase 8.2 Koopman 学习的是 TAM 前的 4D `virtual_control`，而历史 MPC 主要面向固定 8D PWM。如果以后直接把旧 MPC 接回来，很容易出现输入维度和控制语义不一致；如果 MPC 输出之后又进入 S-surface/PID，还会形成双重控制。

后果：这样会导致模型预测的控制量和实际执行的控制量不是同一个东西。即使 Koopman 本身预测正确，MPC 最后执行出来也可能完全变样，所以 Phase 9 不能直接沿用旧的 MPC 控制链。

---

## 3. 当前代码中的真实控制与采集链

### 3.1 控制链

```text
raw_action_4 / reference error
        │
        ▼
S-surface / PID（每个 physics substep 重算）
        │
        ▼
virtual_control_4 = [roll, pitch, yaw, depth] × control_mask
        │
        ▼
legacy mixer 或 configuration-specific TAM：B⁺ / WLS
        │
        ▼
motor command N（N = 4 / 6 / 8）
        │
        ▼
clip → deadzone → 非线性 PWM/转速映射 → 一阶推进器滞后
        │
        ▼
推进器几何合成 applied_wrench_6
        │
        ▼
叠加浮力、水动力、边界/扰动 → physics integration
```

关键代码位置：

- `easyuuv_nc/env/easyuuv_env.py:1482-1549`：一次外部 action 写入后，`_apply_action()` 调用 `_compute_dynamics()`。
- `easyuuv_nc/env/easyuuv_env.py:2301-2331`：D 项使用 `actions - old_actions`，并在每次 dynamics call 后更新 `old_actions`。
- `easyuuv_nc/env/easyuuv_env.py:2220-2229`：生成 `virtual_control_4`，再进入 config-specific allocation。
- `easyuuv_nc/env/easyuuv_env.py:2373-2406`：执行死区、非线性映射、推进器滞后与实际 wrench 合成。
- `easyuuv_nc/thrust_allocation.py:93-144`：由推进器位置/方向构造 $B$，使用伪逆或 WLS 分配。

### 3.2 数据链

```text
Bridge 读取 state_t
        │
        ▼
env.step(raw_action_4)
        │  内部执行 decimation=2 个 physics substep
        ▼
Bridge 读取“最后一次 dynamics call”的 telemetry
        │
        ├─ virtual_control_4（最后一个 substep）
        ├─ motor_pwm_n（最后一个 substep、clip 后/非线性映射前）
        ├─ applied_wrench_6（最后一个 substep）
        └─ step_token
        │
        ▼
Bridge 读取 state_{t+1}，写一条 v2.1 transition
```

关键代码位置：

- `workflows/koopman_bridge_v2.py:245-267`：先读取状态与 token，再执行一次 `env.step()`，之后读取 telemetry。
- `workflows/koopman_bridge_v2.py:323-368`：transition 使用 step 后 snapshot 中的 `virtual_control_4`、PWM 与 wrench。
- `workflows/koopman_bridge_v2.py:432-453`：step 后状态作为 `next_state_11`。
- `easyuuv_nc/env/easyuuv_env.py:770-790`：snapshot 明确只返回 latest telemetry。
- `easyuuv_nc/env/easyuuv_env.py:2459-2460`：每次 dynamics call 都递增 telemetry token。
- Phase 8.2 manifest 固定 `physics_dt_s=1/120`、`decimation=2`、`control_dt_s=1/60`。

### 3.3 模型主输入

Phase 8.2 v2.1 的 primary view 是：

```text
[state_11, actuator_memory_4, virtual_control_4]
```

其中 `actuator_memory_4` 的递推为：

$$
m_{t+1} = \alpha m_t + (1-\alpha)u_t,
\qquad
\alpha = \exp(-\Delta t_{control}/\tau).
$$

它跟踪的是 TAM 前 `virtual_control_4`，并非运行时 `DynamicsFirstOrder.state` 的 N 维推进器状态。代码对此边界已有明确说明：`koopman/actuator_memory_v21.py:1-5,32-62,111-126`。

---

## 4. 六个问题与代码的差距审计

| PDF 问题 | 审计结论 | 代码证据与修正 | 对 Phase 8.2 的影响 | 优先级 |
|---|---|---|---|---|
| 1. 4D 控制物理意义未统一 | **部分确认，核心方向正确** | 通道名、mask 和维度已统一，但 `control_channels_to_wrench()` 只把无量纲通道放入 6D 轴位；不同 $B$、clip、非线性映射、质量/惯量会产生不同真实响应。PDF 所说“各构型 PID 增益不同”在 `EMBODIMENT_CONFIGS` 中没有直接证据：当前默认 PID/S-surface 参数主要是共享的；已确认的差异是几何、分配模式、控制 mask、质量/惯量、阻力和时间常数。 | 说明 pooled/conditional 模型需要更强的控制权威/几何条件信息，但不能单独证明它是 NO_SELECTION 的唯一原因。 | P1 |
| 2. 一个 transition 内有两个控制量，只记录一个 | **代码级确认** | `decimation=2`；`_compute_dynamics()` 每个 physics substep 执行。第一次 D 项使用本次 action 与上次 action 的差，随后立刻更新 `old_actions`；第二次 D 项因此不同。telemetry 每次覆盖，Bridge 只在 `env.step()` 后读取最后一次值。现有 Bridge 测试只模拟一次 snapshot 更新，没有覆盖真实 decimation 内两个控制值。 | 这是 transition 输入语义缺陷。现有 49,152 行不能从日志中恢复未记录的第一 substep `virtual_control`，因此不能靠离线重标注完全修复。 | **P0** |
| 3. reset 未清零 `old_actions` | **代码级确认** | `_reset_idx()` 清零 telemetry、动作平滑缓存、D 滤波、深度积分和推进器状态，但没有 `old_actions[ids]=0`；`old_actions.zero_()` 只在切换 control profile 时执行。现有 reset 测试没有锁定该状态。 | 每个 episode 第一条 transition 的第一 physics substep 可能继承上一 episode 的 D 历史。96 个 episode 对应最多 96/49,152 ≈ 0.195% 的 transition 直接受此边界污染；比例小，但违反 episode 独立性，且不能据此断言影响一定可忽略。 | **P0** |
| 4. `actuator_memory_4` 太简化 | **确认其信息缺口；这是已知设计近似，不是实现偏离规格** | 代理只滤波 4D virtual control；真实执行器状态是 N 维，并位于 allocation、死区、非线性映射之后。v2.1 主输入有意禁止 diagnostic PWM、applied wrench 和 simulator actuator truth 参与选模。 | 当前模型可能非 Markov。同一 `[x,m,u]` 在不同几何/饱和历史下对应不同 `x+`。修复必须增加一个部署时可重建的因果执行器状态，而不能直接使用仿真 oracle。 | P1 |
| 5. TAM 未消除几何差异 | **现象确认，但目标表述需修正** | TAM 的职责是把目标 wrench 分配到当前推进器，不是把不同平台变成相同动力学。现有条件模型包含 19D physical core，并折叠为 source-fold PCA2；它包含质量、惯量、推数、rank、mask、allocation mode 等，但没有 exact $B$、轴向控制权威、饱和裕量或局部 `virtual_control→wrench` 增益。 | 这可能解释条件信息不足，但与问题 1 高度重叠。应修的是“可辨识的跨构型控制合同”，而不是要求 TAM 抹掉真实平台差异。 | P1 |
| 6. 旧 MPC 与新模型接口不一致 | **确认，而且 roadmap 已预见** | `koopman/mpc.py` 的历史接口固定使用 `PWM_DIM`，输入/输出是 8D PWM；现有 Phase 9 目标已要求优化有界 4D virtual control，再经过构型 TAM、mask 和 fallback。 | 不能直接复用旧 MPC；但这不是 Phase 8.2 NO_SELECTION 的原因，也不要求推翻 Phase 9，只要求 Phase 9 从新接口实现。 | P1（Phase 9 前） |

### 4.1 审计中新发现的附带风险

低层控制器被放在 physics-substep 路径中，但若开启 D 低通或 depth integral，其更新公式使用的是 `control_dt = physics_dt × decimation`。由于相同逻辑每个 physics substep 都会执行一次，这些内部状态可能在一个 control step 中按 control dt 更新两次。Phase 8.2 默认 `d_filter_tau=0`、`depth_integral_gain=0`，所以不能把该风险直接归因于本次数据；但未来控制配置一旦开启这些功能，必须一起审计。

---

## 5. 这如何改变我们对 `NO_SELECTION` 的理解

不改变的事实：

- Phase 8.2 的 96 episodes、49,152 transitions、八折 LOCO、冻结/防泄漏流程和 `NO_SELECTION` closeout 仍是完整、可复现、不可改写的证据链。
- `VERIFIED` 表示该证据链符合冻结协议，不表示控制接口在物理上已经充分，也不表示 Koopman-MPC 已经有效。
- 当前没有可以 handoff 给 Phase 9 的 Koopman 模型。

需要收窄的解释：

- 原先可以说：“在 v2.1 冻结协议和当前数据上，没有 Koopman 候选通过晋级门。”
- 现在仍然不能说：“Koopman 在这个问题上本质上不如线性。”
- 更不能把 pooled Koopman 与 simple linear 数值相同，直接解释为 Koopman 理论无效；它也可能来自候选可观测量、控制语义和执行器状态表达不足。
- 因为问题 2 使记录的 $u_t$ 不完全等于整个 $x_t\rightarrow x_{t+1}$ 区间内施加的控制，当前结果无法严格分离“模型表达能力不足”和“训练 transition 语义不闭合”。

因此，这个 checkpoint 是一个真正的 milestone 转折点：**项目从“继续调 Koopman 候选”转为“先修复并验证辨识合同，再决定是否值得重采和重评”。**

---

## 6. 是否需要修改 roadmap / phase

### 建议：需要，但先记录决策，再改 roadmap

不建议把这些内容塞回已经完成的 Phase 8.1/8.2，也不建议直接解除 Phase 9 的 blocked 状态。推荐结构如下：

### Proposed Phase 8.3：Control-Transition Contract Repair

**性质：** 本地设计、代码修复和小规模 Isaac 验证；不做正式 LOCO，不产生模型晋级结论。

建议交付项：

1. **重新定义一条 transition 的控制输入。** 将“控制器求值”和“physics/actuator 更新”拆开：每个 control step 只求一次 S-surface/PID/TAM 命令，两个 physics substep 持有同一控制命令；推进器一阶动态和物理力仍按 physics dt 更新。若不采用 hold 语义，则必须完整记录 substep control sequence，并让离散模型显式消费它，不能继续只记最后一次值。
2. **修复 episode reset。** 对 `old_actions`、`actions_i` 及所有 controller/allocator/actuator history 做逐 env 的 reset contract；增加“第一步与独立冷启动完全一致”的测试。
3. **定义 4D 控制的物理合同。** 明确 `virtual_control_4` 究竟是无量纲控制器输出、期望 generalized wrench，还是按每个平台控制权威归一化后的命令；不能在文档和模型中混用这三种含义。
4. **补足可部署的执行器状态。** 比较至少两种方案：
   - N 维 per-thruster causal memory + `thruster_mask_8`；
   - 由 PWM、TAM、deadzone、非线性映射和已知 $\tau$ 推算的固定维 generalized-force/wrench memory。
   选择标准是可部署、因果、跨构型可比较，而不是离线预测分数最高。
5. **建立控制权威诊断。** 对每个构型测量局部 `virtual_control_4 → applied_wrench_6` 映射、饱和率、headroom 和 substep 差值，验证是否需要 exact $B$、轴向 authority 或其他平台条件特征。
6. **只做 bounded micro-evidence。** 先在 base/uuv6/uuv4 上做短 A/B trace，证明 transition、reset 和 actuator memory 合同成立，再决定是否申请正式服务器重采。

### Proposed Phase 8.4：Fresh Identification Recollection and LOCO Re-evaluation

**性质：** 只有 Phase 8.3 合同通过后才启动的新科学实验。

硬约束：

- 使用新的 schema/experiment ID、结果根目录和 D-23 审批；
- 不覆盖、不追加、不重新解释 Phase 8.2 的冻结数据；
- fresh collection 后重新建立 inventory、split、freeze、LOCO、selection 和 independent closeout；
- 预注册对照至少包括：当前 4D proxy、修复后的 actuator-state representation、simple linear、persistence，以及 eligible Koopman；
- 只有新的模型通过门，才能形成 Phase 9 model handoff。

### Phase 9：保持 blocked，但补强入口条件

Phase 9 的目标方向无需改成 8D PWM。后续规划必须额外写死：

- 优化变量、模型输入和实际执行信号必须是同一个 4D pre-TAM 语义；
- MPC 输出不得再次进入会重新解释它的 S-surface/PID；
- TAM/mask/饱和约束必须位于预测和执行的同一位置；
- 历史 `koopman/mpc.py` 只能作为算法参考，不能作为接口实现直接复用；
- 无新模型 handoff 时，若用户选择线性 nominal + fallback 路线，必须把它记录为显式的新控制决策，不能借用 Phase 8.2 的 Koopman 晋级名义。

---

## 7. 在正式改 roadmap 前建议回答的三个决策问题

1. **控制语义选择：** 我们希望模型学习“上层 4D 命令到状态”，还是“实际 generalized wrench 到状态”？前者更接近未来 MPC 接口，后者更物理，但部署时需要可靠的 TAM/执行器估计。
2. **执行器状态表示：** 接受 `8D padded thruster memory + mask` 的拓扑显式表示，还是坚持固定维 wrench-memory？前者信息更完整，后者跨构型语义更干净。
3. **新实验的停止条件：** 若 Phase 8.3 的 A/B trace 证明 contract 修复显著降低一阶预测误差，再进入 8.4；若没有显著改善，则优先转向“线性/分构型模型 + bounded fallback”，而不是无限扩展 Koopman lift。

---

## 8. 严格注意事项

- 不修改或删除 Phase 8.2 的数据、selection、closeout 和 checkpoint。
- 不把本次静态代码审计表述为已经完成的 Isaac runtime A/B 证明。
- 不把 simulator-only actuator truth 直接放进未来可部署模型。
- 不在同一实验 ID 下更换 transition、actuator memory 或 platform descriptor 定义。
- 不把 `NO_SELECTION` 当作项目失败；它是进入新协议或线性控制分支的科学分叉点。
- 不进入 Phase 9，除非有新的模型 handoff，或用户明确批准线性 nominal + fallback 的替代入口。

## 9. 一句话总结

**我们已经完成了一次严格但结果为负的 Koopman 跨构型评估；新的代码审计表明，下一步不应继续盲目调模型，而应先让“一条数据对应一个真实控制过程”、让 episode 真正独立，并把不同推进器系统的控制权威和执行器记忆表达清楚，再用新协议决定 Koopman 是否还有继续投入的价值。**

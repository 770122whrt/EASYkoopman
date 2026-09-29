> **最新修复进展：** 已完成一次稳定性约束修复对照，发散20/21→0/21，但预测精度仍不合格；参见[修复结果](phase8_3_repair_results.md)。以下保留前一阶段的事实与当时边界。

> **最新执行状态（2026-09-12）：** 后续用户已授权本地查错与补漏；固定候选失败已定位、可选reset修复及observer通过本地测试。当前入口为[控制链调查与缺口表](phase8_3_control_chain_findings.md)。以下保留原阶段分析，不能用旧的“未开始实现/回放”代替当前状态。

> **后续更新（2026-09-12）：** 本文保留首轮只读审查结论及当时边界。本轮用户进一步授权后，原PDF已直接阅读/视觉核对，roadmap与phase已修订；参见[学长建议解析](phase8_3_senior_advice_analysis.md)。本文的“未核验PDF/未改规划”描述的是首轮审查，不代表当前规划状态。

# Phase 8.2 后控制合同与下一步方向：独立批判性审查

审查日期：2026-09-12。对象是 `phase8_3_critical_review_prompt.md`、交接文件及 2026-09-03 转折点讨论稿；不将其中的 P0/P1、因果解释或 8.3/8.4 建议视为已批准结论。本报告仅新增审查意见，没有实施建议中的实验或修改。

## 1. Executive verdict

**建议否决“先按既定方案修复，再进入 fresh LOCO”的默认顺序，改为有明确终点的 forensic 工作：先确认当前到底识别了什么系统，再选择一个控制接口。** 保留 Phase 8.2 的负结果和 Phase 9 阻塞状态。

原讨论稿最重要的正确点是：latest telemetry 不是完整控制区间的记录，reset 的 action history 存在遗漏，历史 8D PWM MPC 不符合既定 4D 接口。最重要的过度推断是：从这些缺口跳到它们解释了模型失败、4D memory 必须扩维，以及 hold 后重采是最佳路线。

本次发现两项需要直接改写既有叙事的事实：

1. **Phase 8.2 的默认采集不是“每子步重算状态误差的姿态闭环”。** 采集器发送不读取轨迹的确定性 raw-action 激励；默认 S-surface 使用 action 及其差分。SO(3) 反馈、角速度 D、深度积分等另一套路径没有在该采集配置中启用。hold 会改变实际控制波形，但“降低反馈频率”的批判需限定到启用真实状态反馈的模式。
2. **pooled 与 simple linear 相等有直接的候选定义解释。** 八折选中的 pooled 均为 `so3_identity_v1 + conditioning=none`；代码明确将其归为同一个线性增量 ridge estimator。不能用这种相等证明 TAM 差异把 Koopman “逼退”成线性。

当下不支持晋级 Koopman，也不支持直接晋级现有 simple-linear。后者在正式比较中同样未胜过 persistence；更换为线性路线必须有自己的控制与验证理由。

## 2. Current-state evidence snapshot

| 项目 | 当前核查结果 | 边界 |
|---|---|---|
| Git root / branch | `E:/code for project/Agentic AUV/EasyUUV` / `no-selection` | 在嵌套仓库执行 |
| HEAD | `782c15a68574bfd923707e499320e7b611e950bd` | 当前本地核验 |
| Upstream | `origin/no-selection`；本地 ahead/behind = `0/0` | 未 fetch，不能声称实时远端一致 |
| 原有 dirty files | `.planning/.continue-here.md`、`.planning/HANDOFF.json`、`.planning/checkpoints/phase8.2-post-closeout-control-contract-turning-point-2026-09-03.md`、`docs/phase8_3_critical_review_prompt.md`，均为 untracked | 保留原文件；本任务另外新增本报告 |
| Closeout | `status=VERIFIED`，`terminal_decision=NO_SELECTION`，`fold_count=8`，`model_handoff=false` | 读取 canonical JSON，未重跑完整 closeout validator |
| Selection | `selected_family=null`，`selected_candidate_id=null`，`selected_model_path=null`，`zero_test_read_audit=true` | 当前没有获晋级的 model handoff |
| 实验身份 | `phase8.1-main-identification-v1`，采集 source commit `4f3b4cbeb3a76b0ae82ce57d8c444f33795d2162` | 环境、v2/v2.1 Bridge、v2.1 collector 这四个核查路径与该提交相比无 diff |
| Roadmap | 已有 8.2 完成和 Phase 9 阻塞条件；没有 8.3/8.4 | 后续阶段仍是建议 |
| 本地 runtime | 项目 `.venv/Lib/site-packages` 未找到 Isaac Lab | 未穷举全机安装路径，也未运行 Isaac |
| 已存 runtime provenance | 检查的一个 canonical manifest 记录 Isaac Lab 2.2.1 / Sim 5.0；Lab repo commit 为 `c91a125c73c8b574878419a9583afc0b63b99f0a`，parent/release 为 `0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20` | 它不是本机 runtime，且不是完全未修改的上游 checkout；未逐一复核 96 个 manifest 的运行环境 |
| 后台任务 | 本地快照看到 python PID `12416/30632/31216/32844` 和 ssh PID `24512` | CIM 命令行读取被拒绝，不能确定归属；未连接服务器，远端运行状态未知。交接中的“无后台进程”不能继承为当前事实 |

文档漂移：`STATE.md:21` 仍写分支 `v2.0-multi-configuration`；frontmatter 的 `status: executing`、`percent: 100` 不能解释成整个 milestone 已完成或当前正在跑实验。正文对 8.2 closeout 的描述与 canonical JSON 一致。`PROJECT.md` 是较早的目标/约束入口，并非最新实验结果索引。本次没有修正文档漂移。

## 3. Claim-by-claim audit table

证据索引 E1–E12 位于文末；Verdict 针对完整命题，避免把“其中一半确认”升级为整句确认。

| Claim | Verdict | Direct evidence | Missing evidence / confound | Corrected wording | Decision impact |
|---|---|---|---|---|---|
| 1. 一次 env.step 内两次 `_apply_action/_compute_dynamics` | PARTIALLY_SUPPORTED | E3 的 decimation=2 和调用链；E12 上游 v2.2.1 的真实 step 源码在 decimation 循环内调用 `_apply_action` | 本机没有目标 runtime 源码；服务器使用带本地提交的 Lab，尚未取得实际加载方法/hash 与 trace | 上游目标版本和项目代码强支持两次调用；目标运行实例尚待确认 | 优先 trace 调用计数，不靠 fake env 升级成 runtime 证据 |
| 2. 两次 virtual control 会不同，Bridge 只记录最后一次 | PARTIALLY_SUPPORTED | E3:2301–2331 首次使用 action 差分，之后更新 old_actions；E4 step 后取 latest snapshot | 不是每个区间都不同：恒定动作、被 mask 通道等可相等；默认采集不以两次姿态反馈误差变化为机制 | action 变化时，两子步控制可能不同；末值覆盖记录机制成立 | 测非零比例与幅值，不能写“每条都错” |
| 3. 末值不能严格代表整个转移 | PARTIALLY_SUPPORTED | 没有显式 hold/sequence 合同；第一子步不在记录内，推进器滞后逐子步更新 | “不是恒定物理输入”不等于“任何离散模型都无效”；给定足够历史可能定义合法输入映射 | 不能把记录末值直接当作全区间 ZOH 输入；当前状态充分性未经证明 | 优先核查输入时间语义与可预测历史 |
| 4. reset 漏 old_actions，污染首条 transition | PARTIALLY_SUPPORTED | E3:1701–1793 无清零；E3:528 初始化、818 profile 切换清零；E5 同一 env 连采 12 episodes | fresh env 首次 reset 无上一 episode；常值/零历史不一定产生差异；实际数值影响未测 | reset 缺口成立，warm reset 下可把上段 action 带入首子步 D 项 | 做 cold/warm 成对比较；区分代码漏洞与已发生影响 |
| 5. 最多 96/49,152 条受 reset 直接污染 | PARTIALLY_SUPPORTED | E5 每构型一个 env、12 次 episode reset、num_envs=1；初始化 old_actions=0 | 96 是粗上界；正常每构型独立进程仅 11 个跨 episode 边界，即 88 个。边界 reset 仍可能触发，但 E4 valid/token 检查通常会拒绝对应行；影响可经物理状态延续 | 无额外 reset/warm-up 时，至多 88 个跨 episode 首子步注入点，约 0.179%；96/49,152≈0.195% 不是受影响数据比例 | 不据比例小断言可忽略，也不把多环境当作本数据已发生的额外污染 |
| 6. 4D 通道语义统一，物理 wrench/authority 未统一 | CONFIRMED | E3:2220–2406 的 legacy/TAM 分支、clip、非线性转速和力映射；E7 平台几何与 mask | 实际数值 authority 未量测；质量/惯量改变运动响应而非相同推进器 wrench 本身 | 这是统一命令坐标，不能当作跨构型统一的 N/N·m 标定 | 明确单位、符号、可达集合；无需要求所有平台同动力学 |
| 7. actuator_memory_4 不能充分表示 post-TAM 执行器状态 | PARTIALLY_SUPPORTED | E6 是 pre-TAM 单一 EMA；E3/E6 真状态在非线性 PWM→转速之后，维度 N | N>4 本身不证明最小状态维数>4；同 tau 的线性特例可存在4D充分状态；本分布实际充分性未测 | 不等于真实转速状态，不能保证充分；预测受损程度是待验证假设 | 先反例/残差历史诊断，再决定扩维 |
| 8. physical core/PCA2 缺几何，所以 conditioning 不充分 | PARTIALLY_SUPPORTED | E6 的19D表无 exact B/authority，PCA降到2D | 描述缺字段不自动证明现有八点 context 冲突；质量/惯量/推数等可能间接区分构型；PCA保方差不保证保预测信息 | 几何覆盖不完整已确认；它是否是瓶颈尚未确认 | 比较描述信息增量，并先查候选 rollout 失败 |
| 9. 旧8D PWM MPC不能直接复用4D接口 | CONFIRMED | E8 `PWM_DIM`、固定shape、previous/legacy PWM状态；E2 Phase9规定4D TAM前输出 | 优化器策略可参考，不等于所有算法必须重写 | 新接口、模型输入、限制器和实际执行必须一致 | Phase9前必须完成；不是8.2失败根因 |
| 10. 8.3修复→8.4 fresh LOCO是最佳结构 | UNCERTAIN | E1/E2只确认无晋级模型；E9说明候选具体失败位置 | 无架构选择、因果消融、成本收益证据；hold/扩memory/加context同时改会混淆 | 先做有限 forensic；新实验是否存在及采用何架构取决于发现 | 不立即新增实施phase或承诺全量重采 |

## 4. Strongest criticisms of the current Markdown and Prompt

### 4.1 “反馈频率变化”不是对当前采集路径的准确描述

`collect_koopman_v21_identification.py:153` 使用 `EasyUUVEnvCfg`。协议冻结 `deterministic_bounded_excitation`、无传感噪声/扰动/随机化；`deterministic_policy_action()` 不读取状态。默认 `attitude_error_mode="euler"`、`d_use_ang_vel=False`、`self_adapt=False`、`d_filter_tau=0`、`depth_integral_gain=0`。

在这些限定下，设本区间 raw action 为 a，上区间末 action 为 a_prev，通道尺度为 L，mask 为 M，则主要控制关系可写成逐元素形式：

```text
s(v) = 2 / (1 + exp(-v)) - 1
u1 = M * s(s_ratio * [Kp * L*a + Kd * L*(a-a_prev)])
u2 = M * s(s_ratio * [Kp * L*a])
```

这来自源码代数推导，不是 Isaac trace。constant action 的第二个及后续区间可以 u1=u2；动作变化时的差值来自 D 状态更新。默认路径中的 action 是外部激励，不应凭控制器名称称其为实时姿态误差。

把 u1 hold 两子步会把 D 的作用延长；把 u2 hold 两子步则移除首子步差分贡献。两者都改变实际输入波形。**改变的是控制包装后的离散系统，未必改变 AUV 的物理方程。** 在 SO(3)、角速度反馈或积分等模式下，hold 还会改变反馈/状态更新频率；不能混用这些模式的论证。

### 4.2 “没有记录就不可能恢复”过强

原稿 §4 称 49,152 行无法恢复首子步 virtual control。上述默认路径中，raw action、相邻 action、固定增益、mask 与 episode 执行顺序原则上足以重建主要控制命令；warm reset 的前史须跨文件按采集顺序处理。恢复的是推导值，不是历史实测值。

因此应先核查是否存在未记录的配置改变、随机化、隐藏状态、缺行或额外 reset，再决定可恢复范围。即使恢复 u1/u2，也不能凭此恢复完整的真实中间物理状态、证明新实验有效，或重写冻结数据。本任务没有运行数据重标注。

### 4.3 采集经过控制器，不自动排除用于 direct pre-TAM 模型

必须区分“信号如何产生”和“被辨识系统的边界”。若完整输入序列已知、状态充分、激励覆盖足够，控制器可作为行为策略产生 plant 输入；这不必把控制器并入 plant。对于带噪真实闭环，还需处理反馈相关性和可辨识性，但不能把一般闭环风险硬套到这次无噪声的预设激励上。

本项目真正的障碍是：当前用一个 control interval 末值代表两个子步；未来 MPC 可能对整个 interval 直接 hold 一个4D命令。这两个离散输入语义尚未等价。不能仅凭“绕过S-surface”断言更换了物理plant，也不能断言现有数据已经支持新接口。

### 4.4 候选账本提供了比 TAM 猜想更直接的检查入口

本次只读聚合八份 `source_candidate_ledger.json`，没有重拟合：

| Family | 候选记录总数（跨折，非独立重复） | source validation rollout failed | regularized condition above limit | 未被这些门拒绝 |
|---|---:|---:|---:|---:|
| pooled | 384 | 187 | 5 | 192 |
| conditional | 384 | 378 | 6 | 0 |

八折 selected pooled 都是 identity：`asymmetric` 留出折使用 prefix4，其余 prefix6；均 ridge0.01、normalization none。E8 的 `simple_linear_equivalent` 与 E9 的 baseline 构造说明两者估计器等价。此处没有证据支持“因为跨构型物理差异，所以两个不同模型意外学成一样”。

E9 `_configuration_errors()` 取 full-horizon artifact；只要某个 status 不为 success 就返回 None，最终汇总成 `source_validation_rollout_failed`。**这个总括原因不能区分最早失败步、物理发散、姿态数值故障或其他失败。** 当前 source ledger 不能支持把 8.2 的失败进一步定性为旧 Phase8 的 quaternion-projection 故障。

后续最小模型诊断应在单一 source-only sandbox 案例中保留最早失败的 horizon、step、状态、reason，明确是否在长递推后才失败。不能改阈值让它通过，也不能用这项诊断替代八折正式结果。

### 4.5 TAM 不负责抹去平台差异；“wrench”也不能仅靠名称保证单位

如果 B 把真实推进器力映射到 wrench，则未饱和的理想力分配可以讨论 BB⁺ 的投影。但当前分配结果接着作为 PWM 经 clip、死区、转速多项式、一阶转速滞后、`k*abs(ω)*ω`，并非直接当作推进器力。不能从 `control_channels_to_wrench` 的函数名推断已实现物理力标定，也不能据此宣布 TAM 错误。

相同无量纲命令产生不同 wrench 并不妨碍条件模型学习 f(x,u,c)。需要的是明确上下文、激励与可达性。相同 wrench 作用在不同质量/惯量上仍产生不同加速度；“统一wrench”和“统一动力学”不是同一目标。

### 4.6 memory 的维度和可部署性不能靠直觉决定

线性反例：若 post-TAM command=Lc*u，所有执行器同 alpha，初值在 Lc 的像空间，则 s=Lc*m 可由4D memory精确表示。当前非线性/饱和链通常不满足该特例，但反例足以否定“4/6/8数量不同，所以4D必然不充分”的论证方式。

8D padding+mask 可以是已知目录内的工程表示，但mask只标记存在性，不告诉模型安装位置/方向。需要每个槽位的几何语义，或可处理置换的表示；不能默认不同构型的第 i 个推进器具有同一功能。

固定6D wrench-memory 也不自动充分。实际 lag 状态是转速，当前净力映射为 B[k|s|s]；不同速度向量可能有同一个净 wrench，却在下一控制下演化不同。null-space、反向转换和饱和的历史可被聚合丢掉。线性同tau特例中部分null-space可能始终不可见，因此同样应以反例测试和预测收益决定，而非一概否定。

命令驱动的转速估计器有望部署，但需已知每子步PWM、模型参数、实际dt及初始状态。仿真 reset 到零不等于实机切换控制器时转子归零。simulator actuator truth / applied wrench 在当前部署合同中只能作 oracle诊断参考；若未来有经验证的传感/估计通路，则可另建接口。oracle也不是保证更优的数学上界，有限数据与训练误差可能让分数更差。

### 4.7 Prompt 的实验与决策门仍有五处需要收窄

1. **“相同 seed/reference/excitation”不足以公平比较 A/B/C。** A输入是命令，B输入是reference或raw action，C可能输入序列；相同四个数不代表相同物理刺激。辨识比较要匹配实际plant输入和初始状态，控制比较要匹配外部任务与预算。
2. **C不是与A/B完全互斥的第三个控制架构。** 它是时间分辨率/状态表示选择，可用于A或B。将三者当作三个完整实现同时试验会增加成本和混淆。
3. **平均控制或generalized impulse不是自动充分统计量。** 即使线性连续系统，输入贡献也是带状态转移权重的积分；一般不只取决于无权重冲量。非线性、水动力、姿态变化与执行器滞后更不能保证顺序无关。
4. **修复正确性不以预测分数改善为条件。** reset隔离或时间标签正确性应由合同证据验收；它没有改善模型误差，不意味着不值得修复。全量重采的投资门才需要收益证据。
5. **没有显著改善不等于线性/per-config已胜出。** 小pilot可能功效不足；可执行的停止条件是停止扩大预算并记录“无足够理由继续”，不能据此宣布Koopman无效。per-config若使用目标构型训练数据，也已改变零样本LOCO科学问题。

## 5. Architecture A/B/C comparison

| Dimension | A：direct pre-TAM | B：保留命令/参考到内环 | C：substep-aware 表示 |
|---|---|---|---|
| 学习输入的物理含义 | bounded/masked 无量纲virtual control；一个interval内hold语义显式 | 必须选定reference或raw action之一，不能混名；默认采集raw action不是reference | 有序u1/u2、子步模型，或可因果推出序列的增广状态 |
| 与Phase9一致性 | 最接近现有4D pre-TAM目标 | MPC若优化reference/raw action则改变Phase9目标 | 可服务A的两次子步rollout，也可服务B的内环复现 |
| 对baseline plant的影响 | 保留AUV/TAM/执行器；旁路内环并改变命令保持规则，控制包装变化 | 若保留原调用/状态更新则保持包装；若新增真正reference闭环仍是变更 | 纯trace不改变行为；只改建模表示可不改physics；不能把未来实测u2偷渡进在线预测 |
| 所需状态 | x、部署可估执行器状态、限制器/分配器必要记忆 | 在A基础上增加old_actions、目标/误差、启用的积分/滤波/自适应状态 | 序列源若为真实反馈，需预测中间状态并运行控制器；不能只增加一个数组字段 |
| 4/6/8难点 | 各构型可达集、增益/几何context、mask | 内环与平台耦合更重；共享控制增益不保证共享闭环 | 输入维度扩大或两步复合误差；跨平台context仍存在 |
| 部署可观测性 | 命令已知，actuator estimate需验证 | controller内部状态可读，但必须reset/时间一致 | raw-action默认路径可因果计算u1/u2；真实反馈路径的未来u2不能预先观测 |
| 最小代码改动（估计） | 已有cascade_control=False分支可借鉴，但其下游仍有符号/积分/优先级钩子；需独立且显式的bounded入口与telemetry | 当前raw-action包装相对少；真正reference MPC还需适配器和模型状态扩充 | 先加只读substep trace最小；正式模型/优化器改动可能最大 |
| 最小验证成本 | 先做同序列replay证明旁路入口等价，再测新的hold行为 | 重用当前激励做历史状态充分性诊断 | 同一trace比较末值与有序序列；先不实现完整MPC |
| 主要失败风险 | 状态估计不足、输入覆盖变窄、控制切换冲击 | 误把reference和error同义；把内环自身预测优势当作物理模型优势 | future-input泄漏、冲量丢顺序、训练/部署不同采样率 |

A的baseline/fallback应使用并联仲裁：MPC命令或Legacy/S-surface命令，经明确转换进入共同的限制器、mask、TAM和执行器链。一次只选一个命令来源，执行器估计持续消费真正施加的命令；fallback切换需定义控制器状态接管，不再把MPC的virtual control串行送入S-surface重新解释。高层PPO/Agent仍不能绕过有界低层控制直接下发PWM。

如果目标是尽快获得有限范围控制能力，per-config/local-linear nominal + Legacy fallback值得作为候选，但必须用同样的任务、预算、约束验证，并明确放弃或收窄原LOCO主张。现有persistence预测基线不是可直接接入的控制器。

## 6. Bounded validation ladder and stop/go gates

以下全部是后续建议，除已报告的本地测试外均未执行。阈值、样本数和资源预算是 **provisional**，应在看新pilot结果前固定。选择架构不能使用旧test调参；旧账本仅定位历史失败。新pilot明确分fit/validation，并按episode分组，不把相邻transition当独立样本。

| 级别 | 目的 / 输入 | 输出与量化指标 | 失败条件与决策 | 证据等级 / 资源 |
|---|---|---|---|---|
| 0. source-only failure forensic | 一个预先选定source fold/candidate；固定历史配置，在新sandbox诊断，保持冻结结果不动 | 最早失败step/horizon/reason；有限性、SO(3)状态、增量尺度；1/5/20/60/full误差分解 | 不能定位失败就停止扩候选；不允许放宽门或反复试旧test | exploratory diagnosis；CPU分钟到小时，尚未实测 |
| 1. static/unit contract | 真实控制函数的最小fixture；默认模式与显式开启反馈的模式分开；2个env的selective reset | interval/token计数、u1/u2解析关系、zero/mask不变量、actuator recurrence；reset另一env不变 | 需要两次调用却只一次、valid对应跨reset、错误dt、历史未隔离则接口门不通过 | local contract；已有114项7.41s通过，新fixture实现量暂估0.5–1人日 |
| 2. Isaac micro-trace | base/uuv6/uuv4；cold与dirty-tail reset；零/常值/阶跃/短PRBS；2 seeds；每case32 intervals | 每interval两子步完整trace、命令差/impulse差、reset差、oracle vs估计误差 | 实际调用/输入不符静态假设则先修订诊断；trace本身改变轨迹则不得用于因果结论 | real Isaac micro-evidence；3×2×4×2×32=1,536观测intervals，加最多768个dirty准备intervals；aggregate约38.4模拟秒；启动/记录开销未知，暂估一次GPU会话0.5–2h |
| 3. matched architecture pilot | 先同plant replay，再分别运行选定接口；每种候选3构型×3fit+3validation seeds×128 intervals | 部署输入递推下的1/5/20/60预测；每构型与macro；有效激励、饱和、历史残差信息；必要时同外部任务跟踪 | 不可部署输入胜出只说明缺失信息；预算内无确定性收益则停止扩大。128步不能验证512步full-horizon表现 | exploratory fit/validation；最多3候选=6,912 intervals≈115.2 aggregate模拟秒；暂估1–3人日准备、1–4 GPU小时，无实测保证 |
| 4. investment gate | 预先固定的新pilot结果与复杂度成本 | 下述合同门、表示门、模型门分别报告 | 只有有理由的路线继续；“证据不足”允许作为终态 | 决策证据，不是模型晋级 |
| 5. formal recollection | 用户选择科学问题并批准；接口/schema语义变化则新版本、新experiment ID、新D-23和结果根 | fresh inventory/split/freeze/LOCO/selection/closeout；若改为per-config则另定相应评估 | 不能复用旧ID/旧test名义；不因pilot通过自动晋级Phase9 | formal protocol evidence；规模按pilot重新估计，不在本报告承诺96 episodes |

### 6.1 Micro-trace字段与因果对照

每条记录含 `(run, configuration, seed, env_id, episode, interval, substep, physics_time)`，reset generation、实际加载的env/DirectRLEnv路径/hash、完整生效cfg，以及：raw action、old_actions前后、controller error（默认路径未消费则明确N/A）、virtual control、分配前后与clip后PWM、转换后的转速命令、实际转速状态/部署估计、thruster-only wrench、施加总wrench和state before/after。明确wrench坐标系和单位。

先比较“原实现无trace”与“原实现只加trace”，不改任何控制计算；然后才比较 reset-only、hold-first、hold-last或direct入口。每个对照一次只改变一个因素；memory表示比较优先在同一批trace上离线进行。

逐通道报告 `abs(u1-u2)` 的均值/p95/max和超过预设容差的比例，并报告向量范数；非零阈值暂取float32绝对1e-6、同时报告1e-5敏感性。实际lag非线性后，不能用u差替代受力差。报告 `J=sum(w_j*dt_j)` 与 `J_last=w2*(2dt)` 的各分量差，力冲量与角冲量分开归一化，不能直接混单位求范数。body与world-frame分析需标明变换，J仅是诊断压缩量。

cold/warm实验固定重置后的物理状态、目标、参数和随机源，只改变前一段action历史；验证是否真正matched。比较首子步控制、首步末状态，并跟踪后续32步差异衰减。已reset的转速状态相同也不保证下一步相同，因为old_actions仍可不同。实际首次运行和warm reset不能简单都要求所有历史“归零”：部署切换需要状态继承或观测器，而非虚构物理reset。

### 6.2 公平的A/B/C pilot与部署输入限制

先用B的短trace得到完整u序列，再在相同初始物理/执行器状态下用A入口逐子步replay同一序列，只检验旁路是否改变下游plant。这是诊断replay，不代表A的60Hz hold策略已验证。

随后B的raw-action模型、A的hold模型各用自己的因果输入训练/验证，不能把同一raw-action数值强行当作A命令。C可在同一trace上作为时间表示消融，比较末值、完整序列、增广controller state；若下一子步命令依赖未来实际状态，正式预测必须从预测状态算出它。消费历史实测未来命令的teacher-forced分数单列为diagnostic，不能当作MPC可执行rollout。

若比较控制能力，匹配外部reference/task、初态、扰动、可控DOF、命令/计算预算，比较跟踪误差、约束违反、饱和占比、fallback率和求解延迟。不同plant包装各自的预测RMSE不能直接排名控制价值。

### 6.3 分开的stop/go门

- **合同门：** 期望substep数/token增量严格一致（当前假设为2）；mask违反、错配episode、非有限输入均为0；reset后函数输出符合规定的初始化状态。matched replay差异必须落在先测得的数值重复性区间。合同错误即使预测分数不变也应记录为应修项。
- **表示投资门：** 用同一轨迹/同一模型家族比较状态或输入表示；暂以20/60步归一化macro误差降低至少10%、每构型退化不超过5%、至少2/3 validation seeds同方向为“值得继续”的筛查阈值。归一化尺度只能由fit确定；近零分母采用预先指定的工程尺度。它不是统计显著性声明，也不证明严格Markov。
- **模型投资门：** 在选定且可部署的表示上，非线性候选需相对同表示的simple-linear及persistence表现出额外收益；暂用同样10%/5%筛查，并要求零硬失败。若只有线性改善，则继续线性候选评估，不声称Koopman成功。
- **停止：** 约定的一轮micro-trace和一轮pilot后，若只有oracle改善、未来命令依赖无法去除、rollout仍失败或收益不一致，则停止全量重采。输出“该预算下无足够go证据”，选择更窄模型或关闭研究分支；不追加无限轮lift/PCA/门限尝试。

小样本不能支撑可靠episode bootstrap显著性判定；需要更大预算时另行说明预期信息收益。formal门及其阈值须重新预注册，不能把上述探索阈值替换进旧D-23。

新ID和新episode也不会把研究者已经见过的八个构型重新变成未知平台。后续fresh LOCO仍只能支撑预注册的固定目录内新轨迹评价，不能恢复“研究者未见构型”或任意AUV泛化主张。

## 7. Recommended next direction

推荐 **forensic + 条件触发的新实验**。优先使用C式的只读trace保护原行为；把A视为与现有Phase9最一致的后续候选，而不是现在批准实现A。B的raw-action/state-augmented模型作为低改动可辨识性对照。没有证据支持立即同时建设三套MPC。

第一项最小、可逆、可验证的后续动作：围绕一个预先选定的source-only失败案例保留最早failure detail，并为现有默认控制路径准备32-step的只读substep-trace规范/fixture。前者回答模型到底在哪一步失效，后者回答末值丢了什么；不得顺带修改hold、增益、TAM或memory。

本次已经完成该动作的只读前半部分：定位总括失败原因及丢失细节的汇总位置，推导默认u1/u2关系，确认现有测试覆盖边界。诊断replay、fixture新增、trace实现和Isaac运行留待后续明确授权。

这比原8.3/8.4顺序更好，因为它不把“发现缺口”预设为“修好就值得重采”，同时允许获得否定A、支持B、支持更窄线性模型或停止投入的信息。

## 8. Proposed roadmap impact（proposal only）

以下为建议文本，没有写回roadmap或phase：

> 在Phase8.2负结果之后设立一个有限的控制/辨识forensic阶段（编号待定）。交付：目标runtime调用trace、reset边界结论、source候选最早失败证据、明确的控制输入与状态合同、预算内的stop/go决定。阶段成功不要求预测分数提高或产生新模型；可合法以“不继续全量实验”结束。
>
> 只有接口已选定且pilot支持继续时，另立新的辨识实验阶段。Phase8.4不预设为必然的96-episode LOCO重采。若采用per-config或local-linear路线，明确改变科学问题、数据访问规则和Phase9入口。
>
> Phase9继续禁止以Phase8.2结果晋级模型；有效新handoff或用户明确选择的替代控制路线，均须满足模型输入—实际执行一致性、有界控制、mask、fallback及匹配闭环验证。

不建议现在关闭整个v2.0：目前有尚可低成本定位的失败链。也不建议因已建立大量工程设施而继续投入Koopman；设施完整是可复用工程价值，不是非线性模型会成功的证据。

## 9. Open user decisions

后续授权前最多需要三项决策，本报告不要求用户在阅读途中作答：

1. 主目标优先级：保留跨构型LOCO科学问题，还是优先在已知构型获得可靠控制？后者允许per-config，但必须改写迁移主张。
2. 是否接受一次有上限的forensic/pilot投入，且失败后停止全量重采？默认建议接受该分段决策，不预承诺8.4。
3. 若证据支持A，是否保留Phase9 direct pre-TAM接口作为目标？若选B，则需要显式改变Phase9的优化变量和模型边界。

## 10. Evidence and claim boundary

本次执行的是只读代码/协议/已存结果审查、账本聚合和focused local tests。没有重算Phase8.2模型或指标，没有重读原始test轨迹做调参，没有修改原Prompt、handoff、roadmap/state/phase/code/tests或冻结证据，没有启动服务器/SSH/监控/后台任务，没有commit/push。测试在独立 `.pytest-tmp/phase83-independent-review-20260912` 下生成常规临时fixture。

执行命令：

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_koopman_bridge_v2.py tests/test_koopman_bridge_v21.py tests/test_koopman_actuator_memory_v21.py tests/test_koopman_model_v21.py tests/test_thruster_dynamics.py --basetemp=.pytest-tmp/phase83-independent-review-20260912
```

结果：**114 passed in 7.41s**。Bridge测试主要使用fake runtime；v2.1 fake cfg虽写decimation=2，其step仍只递增一次snapshot token。thruster tests含纯函数/提取类和源码连接检查。它们支持测试所覆盖的实现合同，不支持Isaac两子步实测、reset影响规模、模型根因或闭环有效性。

证据索引（仓库路径均相对于本报告所在 `docs/`）：

- **E1 — 正式终态：** [closeout.json](../source/results/koopman_phase8_2/closeout/closeout.json)、[selection_result.json](../source/results/koopman_phase8_2/selection/selection_result.json)、[负结果checkpoint](../.planning/checkpoints/phase8.2-no-selection-2026-09-02.md)。JSON关键字段在本次重新读取，非重新认证整个证据包。
- **E1a — 抽查的runtime provenance：** [asymmetric fit multisine manifest](../source/results/koopman_phase8_2/dataset/manifests/phase8.1-main-asymmetric-fit-bounded-multisine-r1-es8201-rs9221.manifest.json)。仅用于明确目标运行环境与上游源码证据之间的差别。
- **E2 — 当前约束：** [AGENTS.md](../AGENTS.md)、[PROJECT.md](../.planning/PROJECT.md)、[ROADMAP.md](../.planning/ROADMAP.md)（234–252行）、[STATE.md](../.planning/STATE.md)；[Phase8.1 context](../.planning/phases/08.1-phase-8-1-local-simulator-and-koopman-identification-repair/08.1-CONTEXT.md)、[Phase8.2 context](../.planning/phases/08.2-phase-8-1-fresh-server-evaluation-and-closeout/08.2-CONTEXT.md)。后两者的历史“尚未采集”文字按其阶段时间解读。
- **E3 — 环境实现：** [easyuuv_env.py](../easyuuv_nc/env/easyuuv_env.py)：108行decimation；215–273默认增益/模式；528–529历史初值；770–790 latest snapshot；793–820 profile reset；1482–1550 action调用；1674–1793 done/reset；2090–2157实际控制模式；2220–2248 TAM和记录；2301–2331 D历史；2373–2406 actuator/wrench；2459 token。
- **E4 — Bridge：** [v2 Bridge](../workflows/koopman_bridge_v2.py)：245–267只检查token严格增加，而非增加1或2；432 next state。[v2.1 Bridge](../workflows/koopman_bridge_v21.py)：166–202 reset/step/memory推进。
- **E5 — 采集与协议：** [v2.1 collector](../workflows/collect_koopman_v21_identification.py)：153–165环境、195–237同env逐episodereset；[action generator / collect loop](../workflows/collect_koopman_v2_identification.py)：66起确定性激励、150起episode循环；[server collector](../scripts/phase8_2_server_collect.sh)：71起按构型启动进程；[role protocol](../protocols/phase8_1/main_role_assignment_protocol.json)、[analysis policy](../protocols/phase8_1/analysis_policy.json)、[D-23 binding](../protocols/phase8_1/d23_approval.json)。proposal字段保留是冻结设计，正式授权由独立binding承担，不应只看pending字段误报无授权。
- **E6 — 状态和描述：** [actuator_memory_v21.py](../koopman/actuator_memory_v21.py)、[platform_features_v2.py](../koopman/platform_features_v2.py)、[platform_features_v21.py](../koopman/platform_features_v21.py)、[thruster_dynamics.py](../easyuuv_nc/env/thruster_dynamics.py)：198 reset、243 update、270–275 recurrence、298–299转速到力。
- **E7 — 分配/构型：** [thrust_allocation.py](../easyuuv_nc/thrust_allocation.py)：93–144；[embodiments.py](../easyuuv_nc/embodiments.py)：38起目录。目录“相近参数”不等于同动力学。
- **E8 — 模型/MPC：** [model_v21.py](../koopman/model_v21.py)：626–640等价类；[mpc.py](../koopman/mpc.py)、[mpc_controller.py](../koopman/mpc_controller.py)的PWM_DIM接口。
- **E9 — 实际候选拒绝：** [八折结果目录](../source/results/koopman_phase8_2/evaluation/folds/)中八份source_candidate_ledger.json；[evaluation_v21.py](../koopman/evaluation_v21.py)：1289–1314 full-horizon状态汇总、1384–1443基线及拒绝原因。计数来自已有JSON，不是新实验。
- **E10 — focused tests：** [Bridge v2](../tests/test_koopman_bridge_v2.py)、[Bridge v2.1](../tests/test_koopman_bridge_v21.py)、[memory](../tests/test_koopman_actuator_memory_v21.py)、[model](../tests/test_koopman_model_v21.py)、[thruster dynamics](../tests/test_thruster_dynamics.py)。
- **E11 — 待审核材料：** [转折点讨论稿](../.planning/checkpoints/phase8.2-post-closeout-control-contract-turning-point-2026-09-03.md)、[Prompt](phase8_3_critical_review_prompt.md)、[human handoff](../.planning/.continue-here.md)、[HANDOFF.json](../.planning/HANDOFF.json)。未独立核验原始微信PDF转写的准确性。
- **E12 — 上游源码佐证：** [Isaac Lab v2.2.1 DirectRLEnv源码](https://raw.githubusercontent.com/isaac-sim/IsaacLab/v2.2.1/source/isaaclab/isaaclab/envs/direct_rl_env.py)，2026-09-12读取：step方法先preprocess，再在decimation循环内apply/physics/update，循环后计算done并reset。这证明该上游版本的定义；不能替代服务器实际加载源码和micro-trace。

公式、架构比较和stop/go设计是基于上述实现的独立推导与提案；未报告的runtime差异、state sufficiency和控制性能均保持未验证状态。

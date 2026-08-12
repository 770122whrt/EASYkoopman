# Phase 8: Multi-Configuration Koopman Identification and OOD Gate — Specification

**Created:** 2026-08-13
**Revised:** 2026-08-13 after knowledge-alignment review
**Ambiguity score:** 0.12 (gate: ≤0.20)
**Requirements:** 5 locked (`KID-01`..`KID-05`)

## Goal

在不改变 Phase 7 数据/控制语义和 v1 `PWM_8` 路径的前提下，建立一条可审计的 v2 Koopman 识别链：先用独立 pilot 判断数据量、激励覆盖、候选 horizon 和物理条件特征是否足以支持正式实验；再冻结主实验协议，以完整 configuration 和完整 episode 为隔离单位，对 persistence、simple linear、per-configuration、pooled、conditional 与 expert upper-bound 角色进行同清单比较。最终只依据八个 held-out-configuration 外层折的预测证据选择可进入 Phase 9 的 pooled/conditional 候选；若证据不足或任何硬门失败，则输出 `no_selection`。

## Knowledge Alignment: What Each Name Means

Phase 8 中的名称不是“六种 Koopman 算法”。它们分为三类：

| 类别 | 名称 | 含义 | 是否 Koopman | 是否可被选入 Phase 9 |
|---|---|---|---|---|
| 基线 | `persistence` | 假设下一状态等于当前状态，用来判断学习是否真的有增益 | 否 | 否 |
| 基线 | `simple_linear_v2` | 直接在线性状态/控制空间拟合一步动力学，不做 Koopman lifting | 否 | 否 |
| Koopman 训练制度 | `per_configuration_koopman_v2` | 每个已见构型单独训练，用来判断单构型数据是否可学 | 是 | 否 |
| Koopman 训练制度 | `pooled_koopman_v2` | 多个训练构型共享一个模型，不显式输入构型物理描述 | 是 | 是 |
| Koopman 训练制度 | `conditional_koopman_v2` | 多个训练构型共享模型，并输入部署时可获得的物理平台描述 | 是 | 是 |
| 评估角色 | `per_configuration_expert_upper_bound_v2` | 在被测构型自己的预声明 fit/validation episode 上训练，回答“有本构型数据时最多能学到什么” | 复用 per-configuration Koopman 实现 | 否 |

Phase 8 首先实现一个新增且版本化的 v2 Koopman backend，再用上述 per-configuration、pooled、conditional 三种训练制度组织它。现有 `direct_state` 与 `paper_lifted_edmd` 属于 v1/既有研究链；除非 Phase 8 research 在主实验冻结前给出明确必要性、独立成本和无泄漏方案，否则不得把它们与所有训练制度做笛卡尔积，避免没有研究问题支撑的模型数量膨胀。

`leave-one-configuration-out`（LOCO）表示八次外层实验：每次完整留下一个机器人构型作为“从未见过”的测试构型，其余七个构型才能用于 pooled/conditional 模型的训练与内部验证。八个构型轮流被留下，因此产生八个外层折。它验证的是跨构型预测泛化，不是闭环控制效果。

## Evidence Already Established

- Phase 7 已在真实 Isaac Sim 5.0 / Isaac Lab 2.2.1 上验证 schema v2、原子 `KoopmanBridgeV2` 与 `KoopmanDatasetV2`。
- `KoopmanDatasetV2.U` 的冻结语义是 post-mask/pre-TAM `virtual_control_4 = [roll,pitch,yaw,depth]`；padded PWM 与 post-actuator wrench 是独立 diagnostics。
- Phase 7 server artifact 只有 `base`、`uuv6`、`uuv4` 各 8 条连续 transition，共 24 条，等级为 `server_isaac_smoke`。它证明接口与采集链可运行，不证明数据充分、Koopman 可识别、跨构型泛化或 MPC 有效。
- Phase 7 smoke 只可作 schema/Bridge 回归证据；不得重新标记成 Phase 8 pilot、identification dataset 或 promotion evidence。
- 现有 `koopman/model.py`、`koopman/lifted_edmd.py`、`koopman/splits.py`、`koopman/evaluation.py` 与 `koopman/selection.py` 是 v1 单构型/PWM_8 链。Phase 8 使用 additive v2 模块，不原地改变 v1 默认维度或历史结论。

## Scientific Status: Fact, Design Choice, Hypothesis, Deferred Value

| 类型 | Phase 8 中的内容 |
|---|---|
| 已证事实 | schema-v2 字段与 `virtual_control_4` 已接通真实 simulator；八个公开构型已在 Phase 6 qualified；三种代表拓扑已在 Phase 7 产生真实 transition。 |
| 锁定设计 | exact-eight LOCO；configuration/episode 隔离；SO(3) geodesic；v1/v2 隔离；`no_selection`；固定名义环境；主候选只从 pooled/conditional 中选择。 |
| 待检验假设 | pooled 模型能跨构型泛化；physical-context conditional 比 pooled 更好；`state_11 + virtual_control_4` 足以作为可部署 plant predictor；加入 reference 的诊断模型是否只是在利用控制器/任务相关信息。 |
| pilot 后冻结 | 主实验 episode 数、episode 长度、seed/scenario 矩阵、具体 horizon、v2 lifting/hyperparameter 网格、物理条件特征向量、归一化规则、promotion margin 与 divergence/projection 阈值。 |

任何“待检验假设”都不能在报告中写成已知事实；任何“pilot 后冻结”的值都不能在看到主实验 outer-test 结果后修改。

## Two-Stage Experimental Contract

### Stage A — Identification pilot

Pilot 的唯一目的，是为正式主实验选择一个足够且可执行的数据/评估协议，而不是产生最终 OOD 结论。

- pilot protocol 在采集前固定 exact-eight configuration 清单、独立 episode/seed/scenario ID、激励边界、最小运行健康门、data-adequacy 诊断和停止/扩充规则，并产生不可变 hash。
- pilot 必须覆盖全部八构型，但规模可以小于主实验；具体规模由 plan/research 给出并在 pilot 采集前冻结，而不是由本 SPEC 凭空猜测。
- adequacy report 至少检查：严格 schema/连续性；有限值；每个可控通道的激励幅度与变化；状态/控制覆盖；回归矩阵 rank、奇异值或 condition diagnostics；随着数据增多的 validation/rollout 误差趋势；`uuv4*` yaw mask 一致性；逐构型失败原因。
- pilot 可以比较少量预声明 backend/feature/horizon 候选以决定主协议，但不得读取或创建主实验 outer-test episode，也不得参与最终 selection/promotion。
- pilot 结束后必须形成 `protocol_decision.json`：列出保留/拒绝的候选、证据、限制、最终主实验所需规模与阈值。若 adequacy 仍不足，结果是 `pilot_insufficient`，Phase 8 停在 checkpoint，而不是继续收集一个未经证明的固定规模。

### Stage B — Frozen main identification and OOD evaluation

- 只有经审核的 `protocol_decision.json` 才能生成 `collection_protocol.json`、`split_manifest.json`、`candidate_grid.json`、`metric_protocol.json` 与 `promotion_gate.json`。
- 这些文件及其 SHA-256 必须早于主数据采集、candidate fitting 和 outer-test evaluation；任一后改都要求新 experiment ID，从 Stage B 重新开始，旧结果保留且不得覆盖。
- main dataset 使用与 pilot 完全不同的 episode/seed IDs；pilot rows 不得并入 main fit/validation/test。
- 每个构型必须有预先分配且数量充分的完整 fit、validation、test episodes。具体数量、长度、seed/scenario 和 horizon 由冻结主协议给出；validator 检查协议本身的一致性、对称性与完整性，而不是依赖本 SPEC 中未经验证的常数。
- 主实验 inner validation 只读取当前外层折的七个训练构型；被留下的构型在 outer-test 打开前对 pooled/conditional 的拟合、归一化、特征选择和 hyperparameter 选择完全不可见。

## Locked Modeling Semantics

### State, control and diagnostics

- `state_11` 顺序固定为 `[depth_z, quat_w, quat_x, quat_y, quat_z, lin_vel_b_x, lin_vel_b_y, lin_vel_b_z, ang_vel_b_x, ang_vel_b_y, ang_vel_b_z]`。
- 所有 selection-eligible v2 plant predictors 的控制输入固定为 post-mask/pre-TAM `virtual_control_4`。
- `motor_pwm_padded_8`、`thruster_mask_8`、`applied_wrench_6`、saturation 与 energy 保留用于覆盖、执行链、饱和和误差归因，不得静默成为 selection-eligible 模型输入。
- measured `applied_wrench_6` 是动作经过 TAM、执行器动态和 efficiency 后的结果。若未来 MPC 在规划未来控制时没有另一个可验证的 actuator/wrench predictor，它就不是直接可用的未来输入；因此本阶段不把 measured wrench 当作主模型 oracle。
- `uuv4*` 的 virtual yaw 必须保持为零；yaw underactuation 作为拓扑事实和诊断报告，但不可作为可实现控制目标评分。

### Reference hypothesis

“主模型不使用 `reference_5`”是可部署 plant-model 的设计假设，不是已被证明的自然规律：理想 Markov dynamics 在给定当前状态和实际控制后不需要目标 reference，但实际日志可能因 PID 内部状态、观测缺失或闭环采样而让 reference 带来预测信息。

- primary selection 路径固定使用 `state_11 + virtual_control_4`；conditional 再增加冻结的 platform context。
- protocol 可以预声明一个 `reference_conditioned_diagnostic_v2` 消融，检验 reference 是否暴露缺失状态或闭环数据偏差。
- 该 diagnostic 必须有独立 model ID、输入 schema、结果与声明；不得参与 pooled/conditional promotion，也不得在看到 outer-test 结果后临时加入。
- 若它显著优于 primary，正确结论是“当前 plant state/control contract 可能不充分，需要后续独立建模决策”，而不是静默把 reference 塞回主模型。

### Platform and environment context

- persistence、simple linear、per-configuration 与 pooled 只使用 `state_11` 和 `virtual_control_4`。
- conditional 额外使用部署时可由 catalog/runtime 获得、与配置名称无关、能描述物理差异的固定长度 platform features。
- 具体 feature vector 必须由 research 与 pilot 的可用性、无泄漏性、尺度和消融结果决定，并在 Stage B 前冻结。候选可来自质量/惯量/浮力几何、推进器拓扑/TAM、mask/rank 与动力学参数，但本 SPEC 不把未经验证的完整列表写成事实。
- configuration name/one-hot identity 只用于 provenance 与分组，不能冒充能对未见构型泛化的物理条件输入。
- feature normalization 只能由当前外层折的训练构型计算。
- Phase 8 固定名义环境；oracle/estimated environment context 均不进入 selection-eligible 输入。跨环境建模与估计属于 Phase 10。

## Locked OOD and Evaluation Semantics

- OOD 隔离单位是完整 configuration；时间隔离单位是完整 episode。
- exact-eight LOCO 产生八个外层折，每个公开构型恰好作为一次完全未见的 test configuration。
- pooled/conditional 在任一折中不得读取 held-out configuration 的任何 row、统计量、特征选择结果或 identity-derived feature。
- per-configuration expert upper bound 可以使用 held-out configuration 预先声明的 fit/validation episodes，但仅用于测量“有本构型数据时的可学性上界”；它与 held-out test episodes 仍隔离，且永不 selection-eligible。
- one-step、multi-step 和 full-episode open-loop rollout 均须报告。具体 finite horizon 在 pilot 后、主实验拟合前冻结；`5/20/60` 仅是历史候选，不是无需证据的定律。
- multi-step window 不跨 episode；open-loop rollout 只在起点使用真实状态，之后使用模型预测与该 episode 已记录的 `virtual_control_4`，不能以中间真值重置冒充 rollout。
- aggregate 同时报告逐构型、八构型等权 macro 与 worst-configuration；row-weighted global 只能作为 diagnostic。
- 正式姿态误差使用 sign-invariant SO(3) geodesic radians：`2 * acos(clamp(abs(dot(normalize(q), normalize(q_hat))), 0, 1))`。四元数分量 RMSE 只能明确标记为 diagnostic。
- truth quaternion 必须有限且可归一化；预测 quaternion 非有限或小于冻结 epsilon 时 reason-coded fail。有效但非单位预测可在下一 rollout step 前投影回单位球，但需记录 correction norm，超过冻结上限即 divergence。

## Requirements

### KID-01 — Configuration/episode-isolated identification dataset and split

- **Current:** Phase 7 只有 3 个 configuration、各 1 个 8-transition smoke episode；现有 v1 split 不理解 configuration、episode role 或 outer fold。
- **Target:** 先形成 exact-eight pilot 与 `protocol_decision.json`，再按冻结的 Stage B protocol 采集与 smoke/pilot 分离的真实 Isaac main identification dataset、episode inventory 和 exact-eight outer-fold split manifest。完整 episode 不跨 role；任何拟合前冻结 inventory/split hash。
- **Acceptance:** validator 拒绝 row-level random split、episode 跨 role、缺失/重复/额外构型、role/hash 后改、smoke/pilot relabel、held-out row/normalization/feature leakage；数据未达到冻结 protocol 时返回 `data_insufficient`，不补行、不重分配 test role。

### KID-02 — Comparable model-role matrix under one frozen protocol

- **Current:** v1 只提供 PWM_8 单构型研究链，没有 v2 LOCO 训练制度与可比矩阵。
- **Target:** 同一 dataset/split/grid/budget/metric/gate 下区分 persistence、simple linear、per-configuration Koopman、pooled Koopman、conditional Koopman 与 expert upper-bound 六个角色；Koopman 角色默认共享一个 additive v2 backend。只有 pooled/conditional selection-eligible。
- **Acceptance:** 每 outer fold/角色恰好有成功或 reason-coded failure，并绑定相同 hashes；validator 拒绝遗漏角色、不同 split/budget、expert promotion、configuration one-hot 冒充 physical conditioning、静默加入 reference/PWM/wrench/oracle 或 v1 默认维度漂移。

### KID-03 — Held-out one-step, multi-step and rollout evaluation

- **Current:** v1 evaluation 没有 exact-eight OOD aggregation，也不充分防止跨 episode rollout 或 row-count 权重掩盖弱构型。
- **Target:** 在冻结 horizon 协议下，对相同 held-out episodes/control sequences 报告 one-step、multi-step、full rollout；至少含 depth、body linear/angular velocity、SO(3)、non-finite、invalid quaternion、divergence 与样本清单，并给出 per-configuration、equal-weight macro、worst-configuration。
- **Acceptance:** validator 拒绝跨 episode window、teacher forcing 冒充 rollout、遗漏构型/horizon/worst result、只给 row-weighted aggregate、把 `uuv4*` yaw 当作可实现目标、非有限预测或 source/control/hash 不一致。

### KID-04 — Quaternion-correct SO(3) orientation metric

- **Current:** v1 的 `attitude_angle_rmse` 来自 quaternion component slice，不是合法旋转角误差。
- **Target:** v2 正式姿态指标只使用归一化、符号不变的 SO(3) geodesic radians，并显式处理零范数、NaN/Inf 与 projection correction。
- **Acceptance:** unit/property tests 证明 `q`/`-q` 误差为零，0°/90°/180° 正确，clamp 数值稳定，零范数/非有限/超限 projection 被拒绝；selector 不接受 component RMSE 的 angle/orientation 别名。

### KID-05 — Provenance-checked selection or explicit no-selection

- **Current:** v1 selector 不绑定 exact-eight dataset、LOCO folds、physical feature contract、SO(3) metrics 或 test-before-retune 边界。
- **Target:** pilot 后、main candidate fitting 前冻结 promotion gate 和具体 margins。只有完成八折、通过 baseline improvement、per-configuration/worst-config、SO(3)、finite/quaternion/divergence 与 provenance 硬门的 pooled/conditional 才可选择；conditional superiority 只在达到预声明相对 pooled margin 时成立。
- **Acceptance:** manifest 绑定 source/runtime、pilot decision、dataset inventory、collection/split/grid/metric/gate、model/result/report hashes。post-test retune、缺 fold、阈值后改、expert promotion、test episode refit、stale artifact 或伪造 selected 均被拒绝；失败时必须 `no_selection` 且无可加载 selected-model path。

## Evidence Levels and Claim Boundaries

| Evidence level | 能证明 | 不能证明 |
|---|---|---|
| `local_contract` | schema、split、metric、model/selector 逻辑和 mutation gates | Isaac 可运行、数据充分、OOD 性能 |
| `server_isaac_identification_pilot` | exact-eight pilot 在真实 simulator 运行并产生 adequacy evidence | 最终训练集充分、模型可选 |
| `server_isaac_identification_dataset` | 冻结 Stage B 协议下的 exact-eight main dataset 完整且 provenance 通过 | Koopman 一定优于 baseline、MPC 有效 |
| `offline_koopman_ood_evaluation` | frozen data/splits/grid/gates 上的八折预测结果 | 闭环控制、环境适应、Agent 效果 |
| `koopman_selection` / `no_selection` | 候选是否满足 Phase 8 promotion gate | Phase 9 闭环性能或硬件有效性 |

低等级 artifact 不能重命名或补字段后满足更高等级。Phase 8 不得声称 MPC、闭环 tracking/stability、环境迁移、在线适应、Agentic 或 Sim2Real 效果。

## Contract-Drift and Failure Defenses

| Failure mode | Required disposition |
|---|---|
| Phase 7 smoke 或 Phase 8 pilot 被用于 main fit/test/promotion | `evidence_level_mismatch` / `dataset_role_forbidden` |
| 本 SPEC 直接把 episode 数、长度、horizon、feature list 或 margins 当成已知最佳值 | planning/spec audit failure；必须由 pilot decision 冻结 |
| 同一 episode 的 rows 被拆到不同 role | split validator 非零失败 |
| held-out 构型参与 normalization、feature selection 或 hyperparameter tuning | leakage reason code；整 fold 无资格 |
| reference diagnostic 被写成主模型或参与 promotion | model-role/selection validator 非零失败 |
| PWM、measured wrench、environment oracle 静默成为 selection 输入 | model-contract validator 非零失败 |
| conditional 只使用 configuration one-hot | conditional candidate 无 selection 资格 |
| candidate grid/gate 在 outer-test 后改变 | hash mismatch；experiment 无资格并输出 `no_selection` |
| quaternion component RMSE 被命名为 orientation angle | metric-schema validator 非零失败 |
| 只报告 row-weighted average | aggregate 无资格 |
| expert/per-config 被选为跨构型模型 | selector 非零失败 |
| 无候选通过仍输出模型路径 | manifest validator 非零失败 |

## Boundaries

**In scope:**

- exact-eight identification pilot、data-adequacy report、protocol decision 与 human/research freeze checkpoint。
- frozen Stage B main dataset collection contract、server runbook、inventory/hash 和 staged pullback。
- configuration/episode-aware split、exact-eight LOCO、leakage validators。
- 一个 additive v2 Koopman backend 及 per-configuration/pooled/conditional regimes；persistence、simple linear 与 expert evaluation roles。
- 可选但预声明、non-promoting 的 reference-conditioned diagnostic ablation。
- physical platform conditioning contract 与 fold-local normalization。
- one-step/multi-step/full rollout、SO(3)、per-config/equal-macro/worst evaluation。
- provenance-checked selected manifest 或 `no_selection`；通过时生成不含 test episodes 的 Phase 9 refit。

**Out of scope:**

- 4D Koopman-MPC、TAM closed-loop、Legacy/S-Surface matched control comparison — Phase 9。
- oracle/estimated environment modeling、RLS/KF online update — Phase 10。
- PPO/Agent Supervisor/LLM runtime — Phase 11。
- final nominal/OOD/environment/combined-shift paper matrix — Phase 12。
- 把 reference、PWM 或 measured wrench 静默升级为主模型输入；若 pilot 证明 state/control contract 不充分，必须新增显式 design checkpoint/版本，而不是在本阶段暗改。
- 修改 v1 `KoopmanDataset.U=PWM_8`、`KoopmanModel.control_dim=8`、v1 MPC/selection 或冻结 evidence。
- 硬件、Sim2Real、独立 CAD/USD 外观或真实海试结论。

## Constraints

- pilot/main 使用不同 experiment、episode、seed IDs 和 canonical directories；测试不得预创建成功 evidence 目录。
- pilot protocol 必须先于 pilot collection；main protocol/gates 必须先于 main collection/fitting；所有时间关系由 manifest hash、source commit 和 immutable inventory 验证。
- Stage B 数值由 pilot decision 冻结。冻结后任何变更创建新 experiment version，不覆盖旧数据或结果。
- local code/tests/bundle 在请求服务器执行前全部通过；服务器按隔离目录运行，GitHub 网络不可用时使用离线 bundle；pullback 后本地再次验证 hash/inventory/semantics。
- 模型输入、预测、统计和指标必须有限；禁止 silent clipping、silent quaternion replacement、silent row drop、silent episode repair。
- 八构型 macro 等权；更多 rows/episodes 不改变构型权重。
- planning、local implementation、pilot evidence、main dataset evidence、offline evaluation/selection 和 closeout 分离提交。
- v1.0 tag、milestone reports、Phase 6/7 canonical evidence 与 v1 model/MPC semantics 保持冻结。

## Acceptance Criteria

- [ ] `KID-01`..`KID-05` 均由至少一个执行 plan 和 machine-verifiable artifact 覆盖。
- [ ] exact-eight pilot protocol、真实 server pilot evidence 和 adequacy report 存在；pilot rows 不具备 main training/test/promotion eligibility。
- [ ] `protocol_decision.json` 在 main collection 前冻结 episode/seed/scenario/length、horizons、platform features、candidate grid、metric thresholds 与 promotion margins；证据不足时停止为 `pilot_insufficient`。
- [ ] main dataset 精确覆盖八构型并满足冻结 protocol；完整 episode 不跨 fit/validation/test，outer folds 各 hold out 一个 configuration，held-out data/statistics/features 不进入训练选择。
- [ ] persistence、simple linear、per-configuration、pooled、conditional、expert 六个角色在同一 manifest 下完整成功或 reason-coded fail；一个 v2 backend 不被无依据扩展成组合爆炸。
- [ ] primary candidates 只使用 `state_11 + virtual_control_4`，conditional 只增加冻结的 physical platform features；reference diagnostic 独立且 non-promoting；PWM/wrench/environment/one-hot 不静默进入 selection。
- [ ] frozen horizons 上报告 one-step、multi-step、full rollout；不跨 episode、不用中间真值重置，并报告 per-config/equal-macro/worst。
- [ ] SO(3) geodesic、`q/-q`、0°/90°/180°、零范数、NaN/Inf 与 projection-limit tests 全部通过。
- [ ] candidate grid、metrics、gates 在 main fitting/outer-test 前冻结；post-test retune 或 hash disagreement 使 experiment 无资格。
- [ ] 只有 pooled/conditional 可被选择；通过时 Phase 9 refit 只用八构型 fit+validation，失败时明确 `no_selection` 且无 selected path。
- [ ] v1 PWM_8 contracts 与 Phase 6/7 evidence 无差异；Phase 8 不产生闭环、环境适应、Agent 或 Sim2Real 声明。
- [ ] Phase 8 SUMMARY、server evidence records、selection/no-selection artifact 与 goal-backward VERIFICATION 分别给出 KID-01..05 的 PASS/FAIL；缺 pilot、main dataset 或完整 OOD gate 时不得关闭 Phase 8。

## Ambiguity Report

| Dimension | Score | Min | Status | Notes |
|---|---:|---:|---|---|
| Goal Clarity | 0.94 | 0.75 | PASS | 目标仅为 v2 identification 与 held-out-configuration prediction gate。 |
| Boundary Clarity | 0.95 | 0.70 | PASS | Phase 7 data contract、Phase 9 MPC、Phase 10 environment、Phase 11 Agent 与 Phase 12 final matrix 分离。 |
| Constraint Clarity | 0.82 | 0.65 | PASS | 未猜测实验常数，但冻结时点、决策 artifact、泄漏边界和失败行为确定。 |
| Acceptance Criteria | 0.87 | 0.70 | PASS | pilot checkpoint、main protocol、LOCO、metrics、selection 与 negative outcome 均可验证。 |
| **Ambiguity** | **0.12** | **≤0.20** | **PASS** | 未知数值由显式 pilot→freeze 决策程序管理，而非留作执行时自由发挥。 |

## Interview Log

用户指出原规格推进过快，特别询问“为何有多种 Koopman”“LOCO 是什么”“为什么主模型不用 reference/PWM/wrench/environment oracle”。本次修订据此纠正：基线、训练制度与评估角色不再混称 Koopman 类型；reference exclusion 被标记为可部署 plant-model 假设并增加独立 diagnostic 位置；PWM/wrench/oracle 的排除给出运行时可用性与阶段隔离原因；未经 pilot 证明的实验数值不再伪装成事实。

| Round | Perspective | Decision locked |
|---|---|---|
| 1 | Knowledge alignment | persistence/linear 是 baseline；per-config/pooled/conditional 是同一 v2 backend 的训练制度；expert 是 non-promoting evaluation role。 |
| 2 | OOD semantics | exact-eight LOCO = 八次完整构型留一；完整 episode 是时间隔离单位。 |
| 3 | Input semantics | primary 使用 state+实际 virtual control；reference 只允许预声明 diagnostic；PWM/wrench/oracle 为 diagnostic/non-primary。 |
| 4 | Scientific caution | episode 数、长度、horizon、features 与 margins 先经 exact-eight pilot，再冻结 main protocol。 |
| 5 | Claim boundary | Phase 8 证明 prediction/OOD gate，不证明 MPC、闭环、环境适应或 Agentic 效果。 |
| 6 | Negative outcome | `pilot_insufficient` 与 `no_selection` 都是合法且必须保留的研究结果。 |

---

*Phase: 08-multi-configuration-koopman-identification-and-ood-gate*
*Spec revised: 2026-08-13*
*Next step: independent SPEC audit; only after pass, create executable Phase 8 plans*

# Phase 8: Multi-Configuration Koopman Identification and OOD Gate — Specification

**Created:** 2026-08-13
**Ambiguity score:** 0.08 (gate: ≤0.20)
**Requirements:** 5 locked (`KID-01`..`KID-05`)

## Goal

在严格绑定真实 Isaac schema-v2 数据、按 configuration 与完整 episode 隔离且不允许测试集反向调参的条件下，对 persistence、simple linear、per-configuration Koopman、pooled Koopman、physical-context conditional Koopman 与 per-configuration expert upper bound 进行同清单比较；用八个 held-out-configuration 外层折的 one-step、multi-step、full-rollout 与 SO(3) 指标，决定是否存在可进入 Phase 9 的跨构型 Koopman 模型，否则生成可审计的 `no_selection`。

## Background

Phase 7 已建立并在真实 Isaac Sim 5.0 / Isaac Lab 2.2.1 服务器上验证 schema v2、原子 `KoopmanBridgeV2` 与 `KoopmanDatasetV2`。当前 v2 模型数据含 `state_11`、`reference_5`、post-mask/pre-TAM `virtual_control_4`、PWM/wrench diagnostics、platform/environment context 和 episode provenance；`KoopmanDatasetV2.U` 的唯一默认语义是 4D `[roll,pitch,yaw,depth]`。

Phase 7 的服务器 artifact 仅有 `base`、`uuv6`、`uuv4` 各 8 条连续 transition，共 24 条，证据等级为 `server_isaac_smoke`。它证明真实数据/控制合同已接通，不具备 configuration/episode train-validation-test 切分能力，也不具备模型识别或 OOD 性能证明能力。该 artifact 可继续作为 schema/Bridge 回归输入，但不得被重新命名为 Phase 8 identification dataset 或用于模型 promotion。

现有 `koopman/model.py`、`koopman/lifted_edmd.py`、`koopman/splits.py`、`koopman/evaluation.py` 和 `koopman/selection.py` 属于 v1 单构型链：默认控制仍为 `PWM_8`，模型显式接收 `reference_5`，split 只隔离日志路径，姿态评估仍包含不适用于四元数的分量 RMSE，selector 也没有跨构型外层折、物理平台条件输入或八构型等权聚合。Phase 8 必须增加 v2 专用识别/评估路径，不得原地改变这些已验证 v1 默认值。

## Locked Scientific Semantics

### State and control

- `state_11` 的顺序保持为 `[depth_z, quat_w, quat_x, quat_y, quat_z, lin_vel_b_x, lin_vel_b_y, lin_vel_b_z, ang_vel_b_x, ang_vel_b_y, ang_vel_b_z]`。
- 所有 Phase 8 可准入模型的控制输入固定为 post-mask/pre-TAM `virtual_control_4 = [roll,pitch,yaw,depth]`。
- `motor_pwm_padded_8`、`thruster_mask_8`、`applied_wrench_6`、saturation 和 energy 只能进入诊断与结果解释，不得进入可准入模型的训练输入。
- `reference_5` 保留用于 episode/scenario 分层、误差解释和将来 Phase 9 控制任务，但不进入 Phase 8 可准入动力学模型。若以后研究 reference-conditioned predictor，必须使用独立模型版本、独立声明和独立阶段，不得静默改变本阶段输入合同。

### Platform and environment context

- persistence、simple linear、per-configuration 与 pooled 模型只使用 `state_11` 与 `virtual_control_4`。
- conditional Koopman 额外使用由权威 catalog/runtime 事实构成的固定长度物理平台描述，包括质量、体积、惯量、COM/COB 偏置、阻力倍率、推进器动力学时间常数、推进器数、控制 rank/mask 和 catalog-derived topology/TAM descriptor。
- configuration 名称和 one-hot identity 只保留在 provenance/报告中，不能作为 conditional 模型唯一或直接的可准入输入。条件特征的归一化统计只能由当前外层折的训练构型计算。
- Phase 8 固定名义环境。`environment_context_oracle` 与 `environment_context_estimated` 均不得进入可准入模型输入；oracle 只能用于验证本阶段数据确实处于声明的固定环境。环境条件建模属于 Phase 10。

### OOD unit of evidence

- OOD 的基本隔离单位是完整 configuration；时间泄漏的基本隔离单位是完整 episode。
- Phase 8 使用 exact-eight leave-one-configuration-out 外层评估：八个公开构型各恰好作为一次完全未见的 test configuration。
- 在任一外层折中，pooled/conditional 模型不得读取 held-out configuration 的任何 fit/validation/test row、归一化统计或 identity-derived feature。
- per-configuration expert upper bound 可使用 held-out configuration 预先声明的 fit/validation episodes，但只能作为可学性上界，永远不能参与跨构型模型选择。

## Requirements

### KID-01 — Configuration/episode-isolated identification dataset and split

Phase 8 必须形成与 Phase 7 smoke 分离的真实 Isaac identification dataset、collection manifest、episode inventory 与 exact-eight outer-fold split manifest，并在任何模型拟合前完成哈希冻结。

- **Current:** Phase 7 只有 3 个 configuration、每个 1 个 8-transition episode；`KoopmanDatasetV2` 只负责加载一个严格 episode pair；v1 `SplitManifest` 只检查日志路径重叠，不理解 configuration、episode role 或 outer fold。
- **Target:** identification dataset 精确覆盖 `base`、`long_body`、`heavy_moderate`、`asymmetric`、`uuv6`、`uuv6_angled`、`uuv4`、`uuv4_angled`。每个构型至少包含 6 个完整 episode、至少 3 个 seed、至少 2 类预先声明的有界激励/参考 scenario；每个 episode 至少 128 条连续有效 transition。每个构型在采集前被固定分配至少 3 个 `fit`、1 个 `validation`、2 个 `test` episode，且所有构型使用同一 collection matrix。若任一 episode、seed、scenario、transition count、配置或 hash 缺失，dataset 状态必须为 `data_insufficient`，不能通过补行或重新分配测试角色继续。
- **Acceptance:** strict dataset/split validator 证明 exact-eight 覆盖、每构型最小 episode/seed/scenario/transition 数量、完整 episode 不跨 role、八个外层折各恰好 hold out 一个构型、训练输入不含 held-out 构型 row；mutation tests 对 row-level random split、同一 episode 跨 split、缺失/重复/额外构型、角色后改、短 episode、Phase 7 smoke relabel、stale hash 与 held-out normalization leakage 返回稳定 reason code 和非零退出状态。

### KID-02 — Comparable model-family matrix under one frozen protocol

所有模型族必须共享同一 dataset inventory、outer-fold split、候选网格、训练预算、horizon 集和 gate manifest；模型类别不能在看到 outer-test 结果后增加、删除或改变输入语义。

- **Current:** v1 sweep 仅比较 PWM_8 direct-state/paper-lifted 候选与 persistence/simple-linear，并在日志级 validation/test 上排序；没有 v2 per-configuration、pooled、physical-context conditional 或 expert upper-bound 矩阵。
- **Target:** 每个外层折至少产生六类可区分结果：`persistence`、`simple_linear_v2`、`per_configuration_koopman_v2`、`pooled_koopman_v2`、`conditional_koopman_v2`、`per_configuration_expert_upper_bound_v2`。除模型类别天然不适用的输入外，所有可比候选使用相同 `state_11`、`virtual_control_4`、episode roles、训练/验证预算和 frozen candidate-grid manifest。只有 pooled 与 conditional 是跨构型 selection-eligible；per-configuration 与 expert 只用于解释 in-distribution 可学性和 OOD gap。所有 v2 模型使用新增版本/loader/runtime，v1 `PWM_8` model/MPC 默认合同保持不变。
- **Acceptance:** machine-readable matrix 对每个 outer fold 和每个模型族恰好记录一个成功或 reason-coded 失败结果，并绑定相同 dataset/split/grid hashes；validator 拒绝遗漏模型族、使用不同 split、把 expert 标为 eligible、把 reference/PWM/wrench/oracle context 作为可准入输入、使用 configuration one-hot 冒充 physical conditional、在 test 后修改候选网格，以及任何 v1 model/MPC 默认维度漂移。

### KID-03 — Held-out one-step, multi-step and rollout evaluation

每个可比较模型必须在相同的 held-out episode 与记录控制序列上生成 one-step、固定 horizon multi-step 和 full-episode open-loop rollout 结果，并同时报告逐构型、八构型等权 macro 与 worst-configuration 指标。

- **Current:** v1 evaluation 主要报告整体 RMSE 和固定日志 rollout，可能按 row count 加权；它不会禁止跨 episode rollout，也不会生成 exact-eight OOD fold aggregation。
- **Target:** horizon 集在 candidate fitting 前固定为 `1, 5, 20, 60, full_episode`。multi-step window 不得跨 episode；rollout 从真实 episode 起始状态出发，逐步使用该 episode 已记录的 `virtual_control_4`，不能重置为真实中间状态。报告至少包含 depth RMSE、body linear-velocity RMSE、body angular-velocity RMSE、SO(3) geodesic mean/RMSE/max、non-finite count、invalid-quaternion count、rollout divergence count/rate、每构型 transition/episode count，以及每构型等权的 macro 与 worst-configuration 汇总。row-weighted global 指标可以作为诊断，但不能单独用于 promotion。
- **Acceptance:** evaluation validator 证明每个 outer fold 的模型、episode、control sequence 与 horizon 一致；测试拒绝跨 episode window、真值 teacher-forcing 冒充 rollout、缺构型、仅 row-weighted aggregate、把不可行 `uuv4*` yaw 当成可实现评分目标、非有限预测和遗漏 worst-configuration 结果。

### KID-04 — Quaternion-correct SO(3) orientation metric

姿态预测的正式误差必须是四元数归一化、符号不变的 SO(3) geodesic angle；原始 quaternion-component RMSE 不能再被命名为 angle/orientation RMSE 或进入 promotion gate。

- **Current:** v2 状态使用 wxyz 四元数，但 v1 evaluation 的 `attitude_angle_rmse` 来自分量 slice RMSE，不能处理 `q` 与 `-q` 表示同一旋转的事实，也没有统一的零范数/非单位预测门。
- **Target:** 对 truth 与 prediction 使用 `2 * acos(clamp(abs(dot(normalize(q), normalize(q_hat))), 0, 1))`，单位为 radians；truth quaternion 必须有限且可归一化，预测 quaternion 若非有限或范数小于冻结 epsilon 则该 rollout reason-coded fail。允许在 rollout 下一步前把有效非单位预测投影回单位球，但必须记录 projection correction norm，超过冻结上限时判定发散。quaternion-component RMSE 仅可作为明确命名的 diagnostic。
- **Acceptance:** 单元/性质测试证明 `q` 与 `-q` 误差为零，0°/90°/180° 旋转得到正确弧度，dot clamp 数值稳定，零范数/NaN/Inf/过大 projection 被拒绝；报告 schema 和 selector 不包含把 quaternion component RMSE 当作 orientation gate 的字段或别名。

### KID-05 — Provenance-checked selection or explicit no-selection

Phase 8 必须在 outer-test 打开前冻结 machine-readable promotion gate，并只从完整通过全部硬门的 pooled/conditional 候选中选择；任何证据、模型或逐构型保护门失败都必须输出 `no_selection`。

- **Current:** v1 selector 可记录 held-out logs 和 negative result，但不绑定 Phase 8 dataset inventory、exact-eight folds、physical-context feature contract、candidate grid、SO(3) report 或 test-before-retune 边界。
- **Target:** gate manifest 在任何候选拟合前冻结并记录正的 baseline-improvement margin、允许的逐构型最大 regression、SO(3) 与 motion primary metric 集、divergence/invalid hard limits、conditional-versus-pooled claim margin 和所有 aggregation rules。候选至少必须：完成八个 outer folds；在 frozen primary OOD macro metrics 上按声明正 margin 优于 persistence 与 simple linear；不突破任一逐构型 regression/worst-config 门；产生零 non-finite、零 invalid quaternion 和零未声明 divergence；若选择 conditional，还必须按正 margin 优于 pooled。test fold 结果出现后不得扩展网格或重新拟合 fold candidate。通过后可按已选 family/hyperparameters 在八构型 `fit+validation` episodes 上生成一个 Phase 9 candidate refit，但不得使用 test episodes；若失败，selection manifest 必须为 `no_selection` 且不得提供可被 Phase 9 runtime 加载的 selected-model path。
- **Acceptance:** strict selector/manifest validator 绑定 tested source commit、server dataset inventory SHA-256、collection/split/gate/grid hashes、model/config/training seed、Python/numerical dependency versions、逐 fold model/result hashes、final refit hash（若有）和 report hash；mutation tests 拒绝 post-test retune、缺 fold、平均值掩盖逐构型失败、expert promotion、threshold 后改、test episode refit、stale model、hash/source/runtime disagreement、伪造 `selected` 和失败时残留 selected-model path。

## Contract-Drift and Failure Defenses

| Failure mode | Required disposition |
|---|---|
| Phase 7 的 24 行 smoke 被用于训练或重新标为 dataset evidence | `evidence_level_mismatch` / `data_insufficient`，Phase 8 不得关闭 |
| 同一 episode 的相邻 row 被拆到 train/test | split validator 非零失败 |
| held-out 构型参与归一化、feature selection 或 hyperparameter tuning | leakage reason code，整折无资格 |
| conditional 只记住 configuration one-hot | 不具备 selection eligibility |
| `reference_5`、PWM、wrench 或 oracle environment 静默成为输入 | model-contract validator 非零失败 |
| 四元数分量 RMSE 被命名为 orientation angle | metric-schema validator 非零失败 |
| candidate grid/gate 在 outer-test 后改变 | provenance/hash mismatch，必须 `no_selection` |
| 只报告 row-weighted average，隐藏弱构型 | aggregate artifact 无资格 |
| expert upper bound 或 per-config model 被选为跨构型模型 | selector 非零失败 |
| Phase 9 MPC/闭环结果被混入本阶段预测证明 | claim-boundary failure；留给 Phase 9 |
| 无模型通过却仍输出模型路径 | manifest validator 非零失败 |

## Boundaries

**In scope:**

- exact-eight、multi-episode、真实 Isaac schema-v2 identification dataset 的采集合同、质量门、inventory、hash、runbook 与 staged pullback。
- configuration/episode-aware collection manifest、episode roles、exact-eight outer-fold split 与 leakage validator。
- additive v2 persistence/linear/per-config/pooled/conditional/expert 模型和统一候选矩阵。
- physical platform conditioning contract；训练折专属 normalization 与 feature provenance。
- one-step、`5/20/60` multi-step、full-episode rollout、SO(3) geodesic、逐构型/macro/worst-config 报告。
- frozen gate、模型/结果/数据 provenance、selected manifest 或显式 `no_selection`。
- 若 gate 通过，生成一个不使用 test episodes 的 Phase 9 candidate refit；若不通过，不生成可加载 selected path。
- Phase 8 SUMMARY、server-data evidence record 与 goal-backward VERIFICATION，逐项映射 `KID-01`..`KID-05`。

**Out of scope:**

- 4D Koopman-MPC 优化、TAM 分配、闭环 tracking/stability 和 Legacy/S-Surface matched control comparison — Phase 9 负责。
- 使用 oracle 或 estimated environment context 训练跨环境模型、估计环境或在线更新 — Phase 10 负责。
- RLS/KF、frozen prior、rollback、adaptation recovery curve — Phase 10 负责。
- PPO retraining、Agent Supervisor、LLM 决策或实时 `env.step()` agent participation — Phase 11 负责。
- nominal/OOD/environment/combined-shift 最终论文矩阵 — Phase 12 负责。
- reference-conditioned dynamics、PWM-input v2 model 或 applied-wrench-input model — 不属于本阶段 locked model family；未来如需研究必须独立版本化。
- 修改 v1 `KoopmanDataset.U=PWM_8`、`KoopmanModel.control_dim=8`、v1 runtime/MPC/selection 语义或改写冻结的 v1/Phase 6/Phase 7 evidence。
- 硬件、Sim2Real、八套独立 CAD/USD 外观或真实海试声明。

## Constraints

- 数据源必须是 strict schema v2 episode/manifest pair；v1 compatibility view 和 Phase 7 smoke 均无 Phase 8 training/promotion eligibility。
- collection manifest、episode roles、outer folds、candidate grid、metric schema 和 gate thresholds 必须在对应结果产生前冻结并哈希绑定；任何后改都需要新实验 ID 和从头重跑，不能覆盖旧结果。
- 本地负责纯 Python/NumPy 模型、split/evaluation/selector 合同和测试；Isaac 服务器负责八构型 identification rollout。离线拟合可在本地或服务器执行，但必须记录精确环境和数据 hash，二者不能改变证据等级。
- 服务器数据证据使用与 `server_isaac_smoke` 不同的明确等级（例如 `server_isaac_identification_dataset`）；离线 OOD 结果使用独立 evaluation evidence level。低证据层不能满足高证据层。
- `uuv4*` 的 virtual yaw 必须保持为零；其 yaw 不参与可行控制覆盖或可实现目标评分，但 yaw underactuation 事实必须出现在逐构型报告中。
- 所有模型输入、预测、归一化统计和指标必须有限；silent clipping、silent quaternion replacement、silent row drop 和 silent episode repair 均被禁止。
- 所有八构型在 macro aggregate 中等权；episode/row 更多的构型不能获得更高聚合权重。
- planning、实现、服务器 raw dataset/pullback、offline model evaluation/selection 与 planning closeout 保持独立可审计提交；本地测试不得预创建 canonical `source/results/koopman_phase8` 成功目录。
- v1.0 tag、`.planning/milestones`、`.planning/reports`、canonical v1 results、Phase 6/7 evidence 与 `koopman/model.py`、`koopman/mpc.py` 的 v1 默认语义保持冻结。

## Acceptance Criteria

- [ ] Phase 8 dataset 精确覆盖八个公开构型；每构型至少 6 个完整 episode、3 个 seed、2 类预声明 scenario，每 episode 至少 128 条连续 strict-v2 transition，并通过独立 server inventory/pullback hash 验证。
- [ ] collection/split validator 证明每构型至少 `3 fit / 1 validation / 2 test` episode，完整 episode 不跨 role，exact-eight outer folds 各恰好 hold out 一个 configuration，且任何 held-out row/normalization/identity feature 不进入训练。
- [ ] Phase 7 smoke、v1 log/adapter 和任何 local mock 均不能满足 Phase 8 dataset/promotion evidence level。
- [ ] persistence、simple linear、per-configuration、pooled、physical-context conditional 和 expert upper-bound 六类结果在同一 frozen split/grid/gate 下完整生成或 reason-coded fail。
- [ ] 所有 selection-eligible 模型仅使用 `state_11`、`virtual_control_4`，conditional 额外只使用训练折物理 platform features；reference、PWM、wrench、oracle/estimated environment 和 configuration one-hot 不进入可准入输入。
- [ ] 每个模型/outer fold 报告 one-step、5/20/60-step 和 full-episode rollout，且 window 不跨 episode、rollout 不使用中间真值重置。
- [ ] 正式姿态指标是 sign-invariant SO(3) geodesic radians；`q/-q`、90°/180°、零范数、NaN/Inf 和 projection-limit 测试全部通过。
- [ ] 报告包含逐构型、八构型等权 macro 和 worst-configuration 的 depth、linear/angular velocity、SO(3)、divergence 与样本清单；仅 row-weighted aggregate 无资格。
- [ ] gate/grid/metric/split hashes 早于 candidate fitting 固定；outer-test 后改阈值、改网格或重新调参被 validator 拒绝。
- [ ] selector 只允许完整通过 baseline-improvement、worst-config、SO(3)、finite/quaternion/divergence 与 provenance 门的 pooled/conditional candidate；expert/per-config 永不具备 selection eligibility。
- [ ] 通过时 selected manifest 绑定完整 dataset/split/gate/grid/model/result provenance，并只用八构型 `fit+validation` 生成 Phase 9 refit；失败时明确输出 `no_selection` 且不存在可加载 selected-model path。
- [ ] v1 `U=PWM_8` model/MPC 默认合同、冻结历史/evidence 和 Phase 7 canonical artifact 无差异；Phase 8 不产生任何 MPC/闭环、环境适应或 Agent 效果声明。
- [ ] Phase 8 runbook、machine-readable dataset/evaluation artifacts、SUMMARY 和 VERIFICATION 存在，并对 `KID-01`..`KID-05` 分别给出 PASS/FAIL；真实 server dataset 或完整 OOD gate 缺失时不得关闭 Phase 8。

## Ambiguity Report

| Dimension | Score | Min | Status | Notes |
|---|---:|---:|---|---|
| Goal Clarity | 0.95 | 0.75 | PASS | 目标被限定为真实 v2 数据上的 held-out-configuration prediction gate，不包含 MPC/闭环效果。 |
| Boundary Clarity | 0.94 | 0.70 | PASS | 与 Phase 7 数据合同、Phase 9 MPC、Phase 10 context/adaptation、Phase 11 Agent 和 Phase 12 最终矩阵逐项隔离。 |
| Constraint Clarity | 0.87 | 0.65 | PASS | exact-eight、多 episode 最低规模、输入禁区、八折隔离、horizon、SO(3)、证据等级和提交边界均已锁定。 |
| Acceptance Criteria | 0.90 | 0.70 | PASS | dataset、split、模型矩阵、指标、selector、provenance 与 negative result 均有 machine-verifiable PASS/FAIL 条件。 |
| **Ambiguity** | **0.08** | **≤0.20** | **PASS** | 加权 clarity=0.9215，满足规格生成门。 |

## Interview Log

本规格采用已批准设计加自动收口路径。用户先要求解释 Phase 8 最难的技术点、成因和解决方式；在数据激励、reference 语义、物理构型描述、SO(3)、闭环辨识偏差和 split leakage 得到逐项说明后，用户明确要求撰写 Phase 8 SPEC 与 PLAN，并强调防止契约漂移。因此无需重复询问 WHAT/WHY；未决定的代码结构与数值实现细节留给 research/plan，但会影响研究结论的输入、证据和门均已在本规格冻结。

| Round | Perspective | Question summary | Decision locked |
|---|---|---|---|
| 1 | Researcher | Phase 7 已证明什么，为什么不能直接训练？ | 24-row exact-three artifact 只保留 smoke 身份；Phase 8 另采 exact-eight multi-episode dataset。 |
| 2 | Simplifier | Phase 8 最小但有效的研究主张是什么？ | 只验证 held-out-configuration prediction；不迁移 MPC、不声明闭环收益。 |
| 3 | Boundary Keeper | 主模型应接收哪些输入？ | `state_11 + virtual_control_4`；conditional 额外接收物理 platform features；reference/PWM/wrench/environment/one-hot identity 不可准入。 |
| 4 | Failure Analyst | 哪些错误最容易制造虚假迁移结论？ | row/episode leakage、held-out normalization、test 后调参、row-weighted average、expert promotion、quaternion component RMSE 和 evidence relabel。 |
| 5 | Seed Closer | 如何判定跨构型模型可进入 Phase 9？ | 八折完整通过 frozen baseline/worst-config/SO(3)/finite/provenance 门才 selected，否则 `no_selection`。 |
| 6 | Compatibility Keeper | 如何避免 v2 识别破坏 v1？ | 新增 v2 model/eval/runtime；冻结 v1 PWM_8 model/MPC/selection 默认语义与历史 evidence。 |

---

*Phase: 08-multi-configuration-koopman-identification-and-ood-gate*
*Spec created: 2026-08-13*
*Next step: user review, then Phase 8 research/context/pattern mapping and executable plan creation*

# Phase 7: Cross-Configuration Koopman Data and Control Contract — Specification

**Created:** 2026-08-11  
**Ambiguity score:** 0.14 (gate: ≤ 0.20)  
**Requirements:** 5 locked (`CONT-01`..`CONT-05`)

## Goal

建立一个可版本化、可严格验证、可由真实 EasyUUV 2.0 运行时产生的 Koopman transition schema v2 与 Koopman Bridge，使 4、6、8 推进器构型共享固定的拓扑无关控制语义 `virtual_control_4 = [roll, pitch, yaw, depth]`，同时保留真实执行器、平台、环境和 episode provenance；继续显式读取 v1 日志，但不把 v1 数据伪装成 schema v2 或跨构型证据。

## Background

Phase 6 已经通过本地合同和真实 Isaac 服务器证据确认八个公开构型可安装、可注册、可 reset/step，并验证了 8/6/4 推进器拓扑、TAM rank 与 `uuv4*` yaw 欠驱动事实。Phase 6 没有证明 Koopman 已经跨构型工作，也没有改变 v1 的 `state=11/reference=5/control=PWM_8` 语义。

当前 v1 数据链仍由 `koopman_data.py` 和 `koopman/dataset.py` 定义：日志字段是 `action_4d` 与固定 `pwm_8d`，训练输入 `U` 默认为 8D PWM。现有 `koopman/model.py`、`koopman/mpc.py`、`koopman/mpc_controller.py` 等模块也仍属于 v1 单构型基线。直接修改这些默认行为会提前侵入 Phase 8 的模型识别和 Phase 9 的 MPC 迁移，并破坏 v1 可复现性。

EasyUUV 2.0 环境已经暴露建立 Bridge 所需的主要运行时事实：`_last_pid_value` 是 4D 低层控制输出，`_last_motor_values_raw` 与 `_last_motor_values_clipped` 是当前构型的 N 路推进器命令，`_alloc_B`/布局描述当前 TAM，`thruster_efficiency_factors`、流体速度、水密度、阻力倍率等描述平台和环境。当前环境尚未把“实际执行后的推进器 body wrench”作为稳定遥测字段暴露，也没有 schema v2 logger、validator 或显式 v1 compatibility adapter。

Phase 7 因此只解决数据与控制语义边界：它建立可供 Phase 8 使用的 v2 数据接口，但不在本阶段训练、选择或宣称一个跨构型 Koopman 模型；它为 Phase 9 固定 MPC 将要使用的 4D 控制含义，但不在本阶段改变现有 MPC 优化器。

## Canonical Schema Semantics

schema v2 的单条 transition 必须至少包含以下稳定语义；具体序列化格式可在实现计划中选择，但字段名和含义不得改变：

| Field | Required semantic |
|---|---|
| `schema_version` | 精确且唯一的 v2 schema 标识；不得接受模糊的 `2`、未声明版本或未来版本。 |
| `state_11` | 当前时刻的 11D Koopman 状态，全部为有限数。 |
| `reference_5` | 当前时刻的 5D 参考量，全部为有限数。 |
| `raw_action_4` | 提交给环境的高层 4D 动作，顺序固定为 `[roll, pitch, yaw, depth]`；这是控制器输入，不等于电机命令。 |
| `virtual_control_4` | 低层控制器实际产生、完成构型可控自由度 mask/优先级处理后、进入 TAM 之前的 4D 控制，顺序固定为 `[roll, pitch, yaw, depth]`。`uuv4*` 的 yaw 必须为零，即使 `raw_action_4.yaw` 非零。 |
| `motor_pwm_padded_8` | 实际裁剪后 N 路 PWM 按 catalog/TAM 的 canonical thruster order 排列，再在尾部补零到 8D。它只用于执行器诊断、饱和与能耗分析。 |
| `thruster_mask_8` | 与 `motor_pwm_padded_8` 同序；真实推进器位置为 1，padding 为 0。支持集只允许对应 8、6、4 推进器的 canonical mask。 |
| `applied_wrench_6` | 经过 PWM 映射、推进器动态、效率/故障/通风等执行链后，由推进器实际施加的 body-frame wrench `[Fx,Fy,Fz,Tx,Ty,Tz]`；不得用 TAM 的期望 wrench 或包含流体/边界外力的总环境 wrench 代替。 |
| `platform_context` | 当前构型的可审计平台事实，至少含 configuration identity、thruster count、control mask、allocation mode/rank、质量、惯量、COM、COB、体积、阻力倍率和推进器动态时间常数；值必须与当次 episode 实际应用的 catalog/runtime 配置一致。 |
| `environment_context_oracle` | 仿真可直接读取的 ground-truth 环境/执行器上下文，带显式 availability 与坐标系/单位元数据；至少容纳实际流体速度、水密度、粘度、阻力倍率和推进器效率。不可用值必须显式标记，不得伪造。 |
| `environment_context_estimated` | 仅由部署时控制器可观测信号推导的估计上下文，使用与 oracle 分离的对象和 provenance；Phase 7 可以记录 `available=false`，但不得复制 oracle 数值冒充估计。 |
| `next_state_11` | 同一步动作执行后的 11D 下一状态，全部为有限数。 |
| episode provenance | 至少含 configuration identity、scenario、episode id、step index、seed、simulation time、control `dt`、task id、controller mode、source commit 与 evidence level；同一 episode 内不变量必须一致，step/time 必须单调。 |

## Requirements

### CONT-01 — Versioned schema v2

一个严格版本化的 transition schema 必须覆盖状态、参考、高层动作、4D virtual control、padded PWM/mask、实际 wrench、平台/环境上下文、下一状态、构型身份和 episode provenance。

- **Current:** v1 logger 只定义 `state/reference/action_4d/pwm_8d/next_state` 等单构型字段；没有 schema v2 标识、拓扑 mask、实际 wrench、上下文分离或逐 episode provenance 约束。
- **Target:** 新增独立的 v2 record/logger/loader/validator；validator 对字段集合、版本、类型、shape、有限性、范围、坐标系/单位、构型一致性、episode 不变量和 transition 连续性 fail closed。v1 writer/loader 不被原地改写。
- **Acceptance:** 正例覆盖八个公开构型；反例至少覆盖缺字段/额外字段、错误版本、shape、NaN/Inf、PWM 越界、padding 非零、mask/构型冲突、错误 wrench 维度、context 缺 provenance、step/time 不单调、跨 episode 不变量漂移，并返回稳定 reason code 与非零退出状态。

### CONT-02 — Topology-independent 4D control contract

Koopman Bridge 与后续 v2 consumer 的唯一默认 learned-control 含义必须是 TAM 之前的 `virtual_control_4 = [roll, pitch, yaw, depth]`。

- **Current:** v1 `KoopmanDataset.U` 固定读取 `pwm_8d`；EasyUUV 2.0 能产生 4D 低层控制和 N 路推进器命令，但没有稳定 Bridge 将二者与 transition 对齐。
- **Target:** Bridge 从同一 `env.step()` 的运行时遥测构造原子 transition：保存 raw action，读取 post-mask/pre-TAM virtual control，记录实际 N 路 PWM、mask 和 applied wrench，并为 v2 dataset 明确返回 `U.shape[-1] == 4`。现有 v1 dataset/model/MPC 默认值保持不变。
- **Acceptance:** 8/6/4 推进器构型的本地合同证明同一 virtual control shape 与通道顺序；TAM 输出长度分别为 8/6/4；`uuv4*` 非零 raw yaw 必须产生零 virtual yaw；v2 dataset consumer 无法在不显式选择 diagnostics API 的情况下把 padded PWM 作为 `U`。

### CONT-03 — Diagnostic-only padded PWM

`motor_pwm_padded_8` 必须可用于饱和、能耗和执行器诊断，但不能静默成为跨构型 learned-control 输入。

- **Current:** v1 用固定 8D PWM 作为训练控制量；如果直接复用该接口，4/6 推进器构型的 padding 会把拓扑差异和虚假零通道混入模型语义。
- **Target:** v2 API 在类型、命名和访问路径上分离 `control.virtual_control_4` 与 `diagnostics.motor_pwm_padded_8`；任何请求 PWM 作为训练输入的路径都必须显式声明非默认 experimental feature set，并在 provenance 中记录。
- **Acceptance:** 默认 v2 training tuple 只返回 4D control；静默别名（如 `action`, `u`, `control` 指向 PWM）被合同测试拒绝；mask 为 0 的 PWM 必须精确为零；诊断 API 能在保留 mask 的前提下计算 per-thruster 饱和率/能耗代理，不改变 model-facing control。

### CONT-04 — Oracle/estimated context separation

数据必须把仿真 oracle context 与可部署 estimated context 分开记录，并让不可用状态显式可判定。

- **Current:** 环境内部可访问流体速度、水密度、阻力和推进器效率等 ground truth，但没有统一导出；当前也没有 Phase 10 所需的 deployable context estimator。
- **Target:** 两个 context 对象使用独立 namespace、availability、method/version、source signals、units/frame 与 value provenance。Phase 7 负责结构与验证，不负责实现或评估 estimator；默认 estimated context 可以 unavailable/null。
- **Acceptance:** validator 拒绝省略 context 类别、oracle/estimated 共用同一对象、estimated 标记 available 却缺 method/source-signals、把 oracle source 标记成 deployable estimate，以及未声明坐标系/单位的向量；`available=false` 的 estimated context 可合法读取但不会被当成有效估计输入。

### CONT-05 — Explicit v1 compatibility without relabelling

现有 v1 日志必须继续可读，但只通过显式兼容路径，并保留其证据能力限制。

- **Current:** v1 日志和模型仍是项目已验证基线；这些日志通常没有 configuration identity、TAM mask、actual wrench 或环境 context，无法证明跨构型 schema v2。
- **Target:** 新增只读 v1 compatibility adapter，输出明确的 `source_schema=v1`、缺失字段清单和 `eligible_for_v2_cross_configuration_training=false`；不得猜测或补造 virtual control、actual wrench、context 或多构型身份。原 v1 writer/loader、模型与 MPC 行为保持兼容。
- **Acceptance:** canonical v1 fixture 可通过显式 adapter 读取；直接交给 strict v2 validator 必须失败；adapter 输出不能通过 v2 promotion/training eligibility gate；v1 regression suite 继续通过，且 v1.0 tag、归档规划和既有 `source/results` 证据无改写。

## Boundaries

**In scope:**

- schema v2 record、logger、loader、strict validator 与 reason-coded CLI。
- EasyUUV 2.0 Koopman Bridge，将一次真实 step 的状态、4D 控制、N 路执行器和 context 原子对齐。
- 为环境补充只读、无行为副作用的实际 thruster wrench/context telemetry。
- 八构型的 catalog/schema/TAM/mask 本地合同测试。
- 独立的 v2 model-facing dataset view，默认 `U=virtual_control_4`。
- 显式只读 v1 compatibility adapter 与 v1 回归隔离。
- 8/6/4 三类拓扑各至少一个真实服务器 schema/Bridge smoke，产出逐行记录、汇总 artifact、hash、runbook 与 validator 结果。
- Phase 7 SUMMARY 与 VERIFICATION，对 `CONT-01`..`CONT-05` 逐条给出 PASS/FAIL 证据。

**Out of scope:**

- 训练、比较、选择或宣称任何多构型 Koopman 模型有效——Phase 8 负责。
- configuration/episode train-validation-test split、OOD 指标或 SO(3) prediction evaluation——Phase 8 负责。
- 修改现有 v1 `KoopmanDataset`、`koopman/model.py`、`koopman/mpc.py` 或 MPC controller 的默认控制维度——Phase 8/9 负责。
- 让 MPC 优化 4D virtual control、加入构型 TAM/mask/fallback——Phase 9 负责。
- 实现 oracle upper bound、环境 estimator、RLS/KF 在线更新或 adaptation promotion——Phase 10 负责。
- Agent/LLM/PPO 实时或低频决策——Phase 11 负责。
- 重复 Phase 6 的八构型完整物理资格测试；Phase 7 server smoke 只证明新 schema/Bridge 在三类拓扑上接入真实运行时。
- 新 CAD/USD、硬件或 Sim2Real 声明。

## Constraints

- Phase 6 的 exact-eight catalog、控制通道顺序、rank/mask 和服务器版本/provenance 合同是上游真值；Phase 7 不复制一套可漂移的构型表。
- `virtual_control_4` 的顺序永久固定为 `[roll,pitch,yaw,depth]`；任何 mask 必须在 TAM 前生效。
- 所有控制、PWM、state、reference、wrench 和 context 数值必须有限；归一化 action/PWM 边界为 `[-1,1]`，容差 `1e-6`。
- v2 采用 additive modules/API；不在 Phase 7 改写 v1 默认训练、模型或 MPC 行为。
- 本地无 Isaac runtime；本地只能声称 `local_contract`。真实 Bridge/telemetry 只能由目标 Isaac Sim 5.0 + Isaac Lab 2.2.1 服务器运行证明。
- server artifact 必须绑定 tested source commit、Isaac/Isaac Lab 版本、task/configuration、runner log 与 SHA-256；local mock 或手工 JSON 不得升级为 server evidence。
- 服务器 smoke 至少覆盖一个 8 推构型（推荐 `base`）、一个 6 推构型（推荐 `uuv6`）和一个 4 推欠驱动构型（推荐 `uuv4`），每个必须完成 create/reset、至少 8 个有效 transition 和 strict validation。
- `uuv4*` 的 yaw 欠驱动不得由 padding、伪逆结果或 v1 adapter 隐藏。
- 已有 `v1.0` tag、`.planning/milestones`、`.planning/reports` 与 canonical v1 `source/results` 保持冻结。
- planning、实现代码和真实 server `source/results` 证据必须保持可审计的提交/推送边界；不得在计划提交中预放成功 server artifact。

## Acceptance Criteria

- [x] schema v2 的必需字段、精确版本、shape、有限性、范围、单位/坐标系、构型一致性和 episode 连续性均由 strict validator 覆盖。
- [x] 八个公开构型的本地合同全部产生固定 4D virtual control，并产生与 catalog 一致的 8/6/4 PWM 长度、mask 与 rank。
- [x] `uuv4` 与 `uuv4_angled` 在非零 raw yaw 输入下记录零 virtual yaw，且该事实进入 validator/verification。
- [x] 默认 v2 dataset/training tuple 的 control 维度精确为 4；padded PWM 只能通过 diagnostics/显式实验 feature set 访问。
- [x] actual applied wrench 来自执行后的推进器 force/torque，而不是 desired TAM wrench 或含流体外力的 total wrench。
- [x] oracle 与 estimated context 在 schema、API 和 provenance 中分离；estimated unavailable 是合法状态，oracle-copy-as-estimate 被拒绝。
- [x] canonical v1 fixture 只通过显式 compatibility adapter 读取，并被标记为不具备 v2 cross-configuration training eligibility。
- [x] 现有 v1 regression suite、Phase 6 qualification contract 和全仓 Isaac-free suite 继续通过；受保护的 v1 历史与结果无差异。
- [x] 真实服务器分别对 `base`、`uuv6`、`uuv4` 产生至少 8 条连续 v2 transition，三份证据均通过 strict validator，且版本、commit、日志与 hash 可复核。
- [x] Phase 7 runbook、machine-readable evidence、SUMMARY 与 VERIFICATION 存在，并对 `CONT-01`..`CONT-05` 每项给出明确 PASS/FAIL；缺少服务器证据时 Phase 7 不得标记完成。

## Ambiguity Report

| Dimension | Score | Min | Status | Notes |
|---|---:|---:|---|---|
| Goal Clarity | 0.91 | 0.75 | PASS | ROADMAP 与 CONT-01..05 将目标限定为 schema/Bridge/兼容边界，不包含模型效果声明。 |
| Boundary Clarity | 0.88 | 0.70 | PASS | 与 Phase 6、8、9、10 的职责已逐项分离；v1 默认行为明确冻结。 |
| Constraint Clarity | 0.82 | 0.65 | PASS | 通道顺序、三类拓扑、版本、证据等级、Git 隔离与缺失 context 行为均已锁定。 |
| Acceptance Criteria | 0.80 | 0.70 | PASS | 本地 exact-eight 合同与三拓扑 server smoke 都有可失败的判据；实现细节留给 research/plan。 |
| **Ambiguity** | **0.14** | **≤ 0.20** | **PASS** | 加权 clarity=0.8625，满足自动生成门。 |

## Interview Log

本 SPEC 使用自动澄清路径：用户已要求继续 Phase 7、优先避免契约漂移，并允许仅在出现阻塞歧义时提问。代码侦察、Phase 6 证据、ROADMAP、REQUIREMENTS 与 v2 milestone design 足以回答当前 WHAT/WHY；未发现需要改变范围或研究主张的阻塞选择。

| Round | Perspective | Question summary | Decision locked |
|---|---|---|---|
| 0 | Researcher (auto) | v1 与 v2 当前最关键的语义断点是什么？ | v1 的 `U=PWM_8` 保持冻结；v2 新增 `U=virtual_control_4`，不原地迁移。 |
| 0 | Boundary Keeper (auto) | Phase 7 是否证明 Koopman 跨构型有效？ | 否。Phase 7 只证明数据/控制契约与真实 simulator telemetry 接通；模型识别和 OOD 效果归 Phase 8。 |
| 0 | Failure Analyst (auto) | 哪些字段最容易被错误重命名或冒充？ | 区分 raw action、post-mask/pre-TAM virtual control、clipped PWM、post-actuator actual wrench；oracle 不得冒充 estimate。 |
| 0 | Simplifier (auto) | server 证据最小但充分的覆盖是什么？ | exact-eight 静态合同 + 8/6/4 三类代表构型真实 schema smoke，不重复 Phase 6 八构型资格测试。 |
| 0 | Compatibility Keeper (auto) | 如何读取 v1 而不制造虚假 v2 数据？ | 只读显式 adapter，记录缺失字段与不具备 v2 training eligibility，strict v2 validator 必须拒绝。 |

---

*Phase: 07-cross-configuration-koopman-data-and-control-contract*  
*Spec created: 2026-08-11*  
*Next step: research implementation details and create executable Phase 7 plans without executing them*

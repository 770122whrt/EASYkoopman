> **当前方向更新：** 固定pooled/分构型/运动学对照已完成，位姿单步有收益、动力学泛化和长递推仍失败；当前入口为[方向对照结果](phase8_3_direction_assay.md)。以下为前次调查记录。

> **最新修复进展：** 已完成一次稳定性约束修复对照，发散20/21→0/21，但预测精度仍不合格；参见[修复结果](phase8_3_repair_results.md)。以下保留前一阶段的事实与当时边界。

> **最新执行状态（2026-09-12）：** 后续用户已授权本地查错与补漏；固定候选失败已定位、可选reset修复及observer通过本地测试。当前入口为[控制链调查与缺口表](phase8_3_control_chain_findings.md)。以下保留原阶段分析，不能用旧的“未开始实现/回放”代替当前状态。

> **2026-09-12 后续状态：** 本Prompt已用于完成独立审查；用户随后明确要求解析原PDF并修订roadmap/phase。下文“只读/禁止修改规划”是原审查任务的历史边界。当前下一步见[建议解析](phase8_3_senior_advice_analysis.md)和[08.3-CONTEXT](../.planning/phases/08.3-control-identification-forensics/08.3-CONTEXT.md)，不要重新执行本Prompt或继承过期阻塞。

# 下一任务 Prompt：批判性审核 Phase 8.2 后控制合同判断，并重构下一步方向

下面的内容可直接复制到一个新的 Codex 任务中使用。

---

## 可复制 Prompt

你正在接手 EasyUUV / EASYkoopman 在 Phase 8.2 `NO_SELECTION` closeout 之后的研究决策工作。

### 你的角色

你不是既有方案的执行者，而是一名独立、怀疑主义的控制系统与系统辨识审查者。你的首要任务是审核并批判当前诊断和 Markdown，而不是证明前一位作者是对的。

请主动寻找：

- 不成立或证据不足的断言；
- 把相关性写成因果的地方；
- 把数据记录问题、控制架构问题和模型表达能力混在一起的地方；
- 会改变实际 plant、却被描述成小修复的建议；
- 更简单、更可验证或更符合未来 MPC 接口的替代方案。

你可以否决当前建议的 Phase 8.3/8.4 结构，也可以得出“停止继续投入 Koopman，转向线性/分构型控制”的结论，但必须基于仓库证据和明确的验证成本。

### 仓库与当前状态

- 仓库根：`E:/code for project/Agentic AUV/EasyUUV`
- 交接时分支：`no-selection`
- 交接时 HEAD：`782c15a`
- 正式 Phase 8.2 closeout：`VERIFIED`
- 正式终态：`NO_SELECTION`
- `model_handoff=false`
- 以上分支与 SHA 都可能在你开始时发生变化，必须先重新核验，不能把本 prompt 当作当前事实来源。

### 当前任务范围

本任务默认是**只读审查 + 新建一份独立审查报告**：

- 允许读取代码、测试、协议、冻结结果和历史文档；
- 允许运行不会改变实验状态的本地静态检查或 focused diagnostic test，并准确标注证据等级；
- 允许新建 `docs/phase8_3_independent_critical_review.md` 作为审查输出；
- 不允许修改 `.planning/ROADMAP.md`、`.planning/STATE.md`、任何 phase 计划或需求；
- 不允许修改实现代码或既有测试；
- 不允许修改、追加、移动或重算 `source/results/koopman_phase8_2/`；
- 不允许创建新 D-23、启动服务器/SSH、重采数据、运行 formal LOCO、进入 Phase 9、commit 或 push；
- 不开启实时监控或后台任务。

如果发现完成审查必须扩大范围，请停在建议层，不要自行扩大授权。

### 必须先读的材料

按顺序阅读，并把文档内容视为不同证据等级：

1. `AGENTS.md`
2. `source/results/koopman_phase8_2/closeout/closeout.json`
3. `source/results/koopman_phase8_2/selection/selection_result.json`
4. `.planning/checkpoints/phase8.2-no-selection-2026-09-02.md`
5. `.planning/checkpoints/phase8.2-post-closeout-control-contract-turning-point-2026-09-03.md`
6. `.planning/.continue-here.md`
7. `.planning/PROJECT.md`
8. `.planning/ROADMAP.md`
9. `.planning/STATE.md`

其中第 5 项是本次主要批判对象。不要把它的“代码级确认”“P0/P1”或 Phase 8.3/8.4 建议直接当成结论。

随后至少检查这些实现：

- `easyuuv_nc/env/easyuuv_env.py`
  - `EasyUUVEnvCfg.decimation`
  - `_pre_physics_step()`
  - `_apply_action()`
  - `_reset_idx()`
  - `_pid_control()`
  - `_compute_dynamics()`
  - `get_koopman_telemetry_snapshot()`
- `workflows/koopman_bridge_v2.py`
- `workflows/koopman_bridge_v21.py`
- `koopman/actuator_memory_v21.py`
- `koopman/platform_features_v2.py`
- `koopman/platform_features_v21.py`
- `easyuuv_nc/thrust_allocation.py`
- `easyuuv_nc/embodiments.py`
- `koopman/mpc.py`
- `koopman/mpc_controller.py`
- 与上述路径对应的 focused tests 和 Phase 8.1/8.2 protocol。

### 第一步：重建事实，不继承叙事

先给出一个简短的 current-state snapshot：

- 当前 branch、HEAD、upstream、dirty files；
- canonical closeout/selection 的关键字段；
- 当前是否存在 model handoff；
- 当前 roadmap 是否已经包含或尚未包含 8.3/8.4；
- 是否有后台评估或服务器任务正在运行。

不要因为 `ROADMAP.md` 或 `STATE.md` 写了某个状态，就覆盖 canonical JSON；若二者冲突，单独报告 documentation drift。

### 第二步：逐条审核当前 Markdown

对以下每个命题给出表格，列为：

| Claim | Verdict | Direct evidence | Missing evidence / confound | Corrected wording | Decision impact |
|---|---|---|---|---|---|

Verdict 只能使用：

- `CONFIRMED`
- `PARTIALLY_SUPPORTED`
- `UNCERTAIN`
- `REFUTED`

必须审查的命题：

1. 一个 `env.step()` 内 `_apply_action()` / `_compute_dynamics()` 在两个 physics substep 各执行一次。
2. 两个 substep 的 S-surface/PID `virtual_control_4` 会不同，而 Bridge 只记录最后一次 telemetry。
3. 因此当前记录的 `virtual_control_4` 不能严格代表整个 $x_t \rightarrow x_{t+1}$ 转移。
4. `_reset_idx()` 未清零 `old_actions`，并且该状态会污染新 episode 第一条 transition。
5. “最多 96/49,152 条 transition 受 reset 直接污染”的估算是否成立，是否遗漏 auto-reset、多环境或控制器内部状态。
6. `virtual_control_4` 仅统一了通道语义，没有统一实际物理 wrench/control authority。
7. 当前 `actuator_memory_4` 不能充分表示 post-TAM 4/6/8 推进器状态。
8. platform physical core / PCA2 缺失 exact allocation geometry 或 authority，因此 conditioning 不充分。
9. 旧 8D PWM MPC 不能直接用于 Phase 9 的 4D pre-TAM 接口。
10. Phase 8.3 本地修复 + Phase 8.4 fresh recollection/LOCO 是当前最佳阶段结构。

对于第 1 项，必须核实目标 Isaac Lab / `DirectRLEnv` 的实际调用循环。如果本机没有相应源码或 runtime，不得将推断升级为确认；要明确写出需要什么 micro-trace 才能证实。

### 第三步：必须反驳当前方案中最脆弱的部分

至少写出当前方案的三个 strongest counterarguments。必须覆盖以下核心矛盾：

1. **hold 方案是否改变 plant：** “每个 control step 只计算一次低层控制并在两个 substep hold”会改变 S-surface/PID 的反馈频率。它可能让数据更整齐，却不再是原 baseline 的闭环系统。
2. **Phase 9 的接口是否与采集 plant 一致：** 如果未来 MPC 直接输出 `virtual_control_4` 并绕开 S-surface/PID，那么用“经 S-surface/PID 产生的 virtual control”采集数据，是否真的辨识了同一个可执行 plant？
3. **NO_SELECTION 的原因是否被过度解释：** pooled Koopman 与 simple linear 等价、conditional candidate fail-closed，可能主要来自 observable/candidate construction、rollout/quaternion gate 或数据覆盖，不一定由控制语义造成。

还要检查：

- 当前 Markdown 是否把“平台不具备同样动力学”错误地当成 TAM 缺陷；
- 是否真的需要让相同 4D 命令产生相同物理 wrench，还是只需把平台差异作为可辨识 context；
- `8D padded thruster memory + mask` 是否因为推进器索引/几何语义不同而不适合作为 pooled model 输入；
- generalized-wrench memory 是否可部署、是否会丢失 null-space/saturation 历史；
- 实际 applied wrench/actuator truth 是否只能做 oracle upper bound。

### 第四步：重新提出控制—辨识架构

至少比较以下三种架构，不得只给一个推荐答案：

#### Architecture A：Direct pre-TAM virtual-control plant

```text
MPC / excitation 输出 bounded virtual_control_4
    → mask
    → TAM
    → PWM nonlinearities / actuator dynamics
    → AUV physics
```

S-surface/PID 不位于被辨识 plant 内。说明如何保留 Legacy/S-surface 作为独立 fallback/baseline，而不形成 double control。

#### Architecture B：High-level reference/raw-action plant with retained inner controller

```text
MPC / excitation 输出 reference 或 raw_action
    → S-surface/PID（可在 physics substep 更新）
    → virtual_control_4
    → TAM / actuator / physics
```

说明模型是否需要 controller state、error、integrator、filter 和 actuator state；说明这种方案与现有 Phase 9 目标的冲突。

#### Architecture C：Substep-aware discrete identification

保留现有 inner-loop 更新，但把一个 control interval 表示为完整的 substep control sequence、时间加权 generalized impulse，或显式 lifted controller-actuator state。说明其可部署性、模型复杂度和与 MPC rollout 的兼容性。

可额外提出：

- per-configuration / mixture-of-experts 模型；
- linear or local-linear nominal + bounded fallback；
- 停止跨构型 pooled Koopman，转向更窄科学问题。

对每种架构比较：

| Dimension | A | B | C |
|---|---|---|---|
| 学习输入的物理含义 | | | |
| 与 Phase 9 MPC 的一致性 | | | |
| 是否改变现有 baseline plant | | | |
| actuator/controller state 要求 | | | |
| 跨 4/6/8 构型难点 | | | |
| 部署可观测性 | | | |
| 最小代码改动 | | | |
| 最小验证成本 | | | |
| 主要失败风险 | | | |

### 第五步：设计“先证伪、再投入”的最小验证

不要直接提出 96-episode 重采。先给出 bounded validation ladder：

1. **Static/unit contract**
   - 调用频率、token 增量、reset coverage、memory recurrence；
   - 只能证明代码合同，不得声称 Isaac dynamics 成立。
2. **Isaac micro-trace**
   - 最少覆盖 `base`、`uuv6`、`uuv4`；
   - 记录每个 control interval 的两个 substep：raw action、controller error、`virtual_control_4`、motor command、actuator state/estimate、applied wrench、state before/after；
   - 比较 cold reset 与“前一 episode 尾部 action 非零后 reset”的第一步；
   - 报告每通道 `||u_sub1-u_sub2||`、非零比例、generalized impulse 差异和 reset 差异，不只给截图。
3. **Matched architecture A/B/C pilot**
   - 使用相同 seed、reference/excitation、时间窗和构型；
   - 明确哪个变量被模型当作输入；
   - 使用 fit/validation 分离，不能在测试集上选架构。
4. **Stop/go gate**
   - 预先定义什么改善才值得创建新 experiment ID 和 D-23；
   - 若 contract 修复没有显著降低 held-out validation error 或提高 state sufficiency，则停止全量重采，优先线性/per-config 路线。
5. **Formal recollection**
   - 只有用户批准且 pilot 通过时才建议；必须新 schema、新 experiment ID、新 D-23、新结果根和 fresh LOCO。

请为每一级写明：目的、输入、输出、量化指标、失败条件、证据等级、预计资源量级。资源估计如果没有实测依据，必须标记为 provisional。

### 第六步：给出新的下一步，而不是照抄 Phase 8.3/8.4

最终给出一个明确建议，可以是：

- 保留 8.3/8.4；
- 重构为一个 forensic phase + 条件触发的新实验 phase；
- 直接建立 architecture A 的新 contract；
- 转向线性/per-configuration nominal + fallback；
- 关闭当前 v2.0，并把 Koopman 问题放入新 milestone。

你的建议必须包含：

- 为什么它比当前 Markdown 的建议更好；
- 哪些结论已经有证据，哪些仍是假设；
- 第一项最小、可逆、可验证的动作；
- stop condition；
- 对 roadmap/phase 的**建议文本**，但本任务不要实际修改 roadmap/phase；
- 需要用户决定的最多三个问题。

### 输出要求

将结果写入：

`docs/phase8_3_independent_critical_review.md`

文档至少包含：

1. Executive verdict
2. Current-state evidence snapshot
3. Claim-by-claim audit table
4. Strongest criticisms of the current Markdown
5. Architecture A/B/C comparison
6. Bounded validation ladder and stop/go gates
7. Recommended next direction
8. Proposed roadmap impact（proposal only）
9. Open user decisions
10. Evidence and claim boundary

在最终回复中，用简洁中文回答：

- 当前 Markdown 最重要的正确点是什么；
- 最需要被推翻或收窄的点是什么；
- 你推荐的第一步是什么；
- 你创建了哪个文件；
- 明确声明没有修改 roadmap/phase/code、没有启动服务器或监控。

不要用“测试通过”代替论证，不要为了让项目继续而强行推荐 Koopman，也不要因为 `NO_SELECTION` 就否定整个工程价值。

---

## 使用说明

此 prompt 的目标是产生第二轮、独立且可反驳的设计审查。理想结果不一定与当前 Phase 8.3/8.4 建议一致；真正的验收标准是它能把“记录缺陷、控制接口、执行器状态、模型表达力和未来 MPC 执行链”分开，并提出一个投入可控、失败也能得到信息的下一步。

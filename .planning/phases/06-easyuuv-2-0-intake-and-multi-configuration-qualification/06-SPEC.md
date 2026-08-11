# Phase 6: EasyUUV 2.0 Intake and Multi-Configuration Qualification — Specification

**Created:** 2026-08-09
**Ambiguity score:** 0.08 (gate: ≤ 0.20)
**Requirements:** 8 locked
**Completion:** Verified 2026-08-11; QUAL-01..08 passed with real server evidence.

## Goal

把收到的 EasyUUV 2.0 源码变成一个可追溯、可安装、可枚举且可在服务器逐构型资格验证的 `easyuuv_nc` 环境，同时证明该导入不会改写 v1.0 证据或把欠驱动构型误报为全可控。

## Background

当前 `easyuuv_v2-main/` 是约 72.6 MiB 的未跟踪源码快照。源码中的 `__init__.py`、README 和 gym entry points 都声明包名为 `easyuuv_nc`，但物理目录名不是该包名，而且树内没有 `pyproject.toml`、`setup.py` 或 `setup.cfg`，因此还不存在唯一、可复现的安装合同。

新环境已经包含参数型构型 `base`、`long_body`、`heavy_moderate`、`asymmetric`，以及执行器拓扑型构型 `uuv6`、`uuv6_angled`、`uuv4`、`uuv4_angled`。`workflows/train.py` 和 `workflows/adapt.py` 的 CLI choices 精确暴露这八种构型；`heavy_duty` 仅是内部 preset，不属于 Phase 6 的公开支持集合。

`env/easyuuv_env.py` 和 `env/thrust_allocation.py` 已包含 4/6/8 推进器布局、TAM、pinv/WLS 分配和 controllable DOF 声明。`uuv4*` 仅声明 heave/roll/pitch，不支持 yaw。八种构型仍共用 `data/embodiment/embodiment.usd`，所以本阶段验证的是动力学/推进器配置，不是八种独立外观资产。

现有 EASYkoopman 根目录仍是 v1.0 单构型实现：Koopman model 和 MPC 以 `PWM_DIM=8` 为控制维度。Phase 6 只建立新版环境的可信入口和资格证据，不在本阶段修改 Koopman 数据语义或实现跨构型 MPC；这些工作分别属于 Phase 7 和 Phase 9。

## Requirements

1. **Snapshot provenance**: 收到的 EasyUUV 2.0 源码必须作为独立、可识别的 Git 快照进入历史，后续包名/安装/资格验证修改不得混入该快照提交。
   - Current: `easyuuv_v2-main/` 完全未跟踪，源码快照与后续集成工作尚无 Git 边界。
   - Target: 一个只包含收到源码树的 snapshot commit 先于任何 Phase 6 集成修改；v1.0 tag 和归档文件保持不变。
   - Acceptance: `git show --name-only` 证明 snapshot commit 只包含导入树；后续集成 commit 单独可见；`git diff v1.0 -- .planning/milestones .planning/reports` 不显示对 v1.0 归档内容的改写。

2. **Unique package contract**: 服务器安装、import、gym 注册和资产解析必须统一使用一个有文档记录的 `easyuuv_nc` 合同。
   - Current: 源码声明 `easyuuv_nc`，但目录名为 `easyuuv_v2-main`，没有 Python packaging metadata，资产路径依赖源码相对位置。
   - Target: runbook 指定唯一的目录/安装步骤、`PYTHONPATH` 或 editable-install 方式、`import easyuuv_nc` 行为、四个 gym task ID 和 USD 解析规则。
   - Acceptance: Isaac-free import probe 在缺少 Isaac 时只跳过 gym 注册而不吞掉其他 import 错误；服务器 probe 能 import `easyuuv_nc`、解析存在的 `data/embodiment/embodiment.usd`，并确认四个已声明 gym task ID 可查询。

3. **Canonical configuration catalog**: 一个机器可读 catalog 必须精确区分八个公开 CLI 构型和内部 preset。
   - Current: 八个公开名称重复写在 `train.py`/`adapt.py`，九个 preset 写在 `EasyUUVEnvCfg.embodiment_configs`，没有独立 catalog 或一致性检查。
   - Target: catalog 的 supported 列表精确等于 `base,long_body,heavy_moderate,asymmetric,uuv6,uuv6_angled,uuv4,uuv4_angled`；`heavy_duty` 标记为 internal/unsupported，不可由公共 CLI 选择。
   - Acceptance: catalog validator 对 supported 集合做顺序无关的精确相等检查，同时验证 train/adapt CLI choices 与 catalog 无缺项、无额外公开项。

4. **Topology and controllability truth**: 每个公开构型必须报告推进器数量、分配模式、4D 控制 mask 和 declared-control rank。
   - Current: 参数型构型使用硬编码 8 推路径；`uuv6*` 使用 6 推 pinv；`uuv4*` 使用 4 推 WLS 且无 yaw，但这些事实没有统一资格 artifact。
   - Target: `base/long_body/heavy_moderate/asymmetric` 报告 8 推和 `[1,1,1,1]`；`uuv6/uuv6_angled` 报告 6 推和 `[1,1,1,1]`；`uuv4/uuv4_angled` 报告 4 推和 `[1,1,0,1]`，顺序固定为 `[roll,pitch,yaw,depth]`。declared-control rank 对前六种为 4，对 `uuv4*` 为 3。
   - Acceptance: 纯 Python/Torch qualification test 从实际配置构造分配矩阵或等价 mixing matrix，断言上述数量/mask/rank；任何 `uuv4*` yaw 可控声明都会导致测试失败。

5. **Tiered server smoke**: 八种公开构型必须在目标 Isaac 服务器完成分级运行验证。
   - Current: 本地没有 Isaac runtime；收到的源码没有本仓库可审计的八构型 qualification artifact。
   - Target: `base` 完成至少 64 个 physics steps 的最小 rollout；其余七种各完成 environment create、reset 和至少 8 个 physics steps。每次运行记录配置、task ID、Isaac/Isaac Lab 版本、seed、step count 和退出状态。
   - Acceptance: 汇总 artifact 恰好包含八个唯一构型，`base.steps >= 64`，其余各 `steps >= 8`，且全部 environment_create/reset/step 状态为 pass；缺少任一构型时整体验证失败。

6. **Finite and bounded actuation**: 资格运行必须拒绝所有非有限或越界控制量。
   - Current: 新环境存在多条 PID/TAM/推进器路径，但没有统一的跨构型边界 validator。
   - Target: 每步记录或聚合检查 4D action/virtual control 和实际 motor command；所有值必须有限，且归一化控制/PWM 必须位于声明的 `[-1,1]` 边界内。
   - Acceptance: validator 对 NaN、Inf、`abs(value) > 1 + 1e-6`、维度与构型推进器数不一致分别返回非零退出码和 reason code；八构型 smoke artifact 全部通过该 validator。

7. **v1 regression isolation**: 导入与资格验证不得破坏现有 v1.0 Isaac-free 行为。
   - Current: v1.0 关闭时记录 175 个本地测试通过，现有 Koopman/PPO/工作流仍按单构型 8D PWM 合同运行。
   - Target: Phase 6 不改变 v1 Koopman control dimension、选择 manifest 或 archived conclusions；新增代码在缺少 Isaac 时仍可被本地合同测试覆盖。
   - Acceptance: `python -m pytest -q` 退出 0 且运行测试数不少于 175；`python -m compileall` 覆盖现有 v1 Python 路径和新增 Isaac-free qualification 路径并退出 0。

8. **Qualification evidence package**: Phase 6 必须交付可复现 runbook、机器可读结果、SUMMARY 和 VERIFICATION。
   - Current: 设计记录描述了验收方向，但没有 Phase 6 命令、artifact schema 或验证报告。
   - Target: runbook 分开列出本地检查和服务器命令；机器 artifact 保存构型级结果与 provenance；SUMMARY 记录实现与提交；VERIFICATION 逐条回答 QUAL-01..08。
   - Acceptance: artifact validator 退出 0；runbook 包含 base/full-rollout 和 seven-smoke 命令；SUMMARY 与 VERIFICATION 文件存在；QUAL-01..08 每个 ID 在 VERIFICATION 中恰好有一个 PASS/FAIL 状态。

## Boundaries

**In scope:**

- 原样导入收到的 `easyuuv_v2-main/` 快照并保留独立 provenance。
- 建立唯一 `easyuuv_nc` 安装/import/gym/asset 合同。
- 建立八个公开 CLI 构型的机器可读 catalog 与一致性测试。
- 计算并验证推进器数量、TAM/mixing rank 和 4D controllable mask。
- 编写本地 Isaac-free qualification tests 与 artifact validator。
- 编写服务器 runbook，完成 base rollout 和其余七构型 smoke 的证据合同。
- 产出 Phase 6 SUMMARY 和 VERIFICATION。

**Out of scope:**

- schema v2、Koopman Bridge 或 4D virtual-control 数据迁移 — Phase 7 负责。
- 多构型 Koopman 训练或 held-out OOD 比较 — Phase 8 负责。
- configuration-aware Koopman-MPC — Phase 9 负责。
- 环境上下文估计、RLS/KF 更新或 PPO 训练 — 后续阶段负责。
- Agent/LLM runtime — Phase 11 负责。
- 把八个配置描述成八套独立 CAD/外观 — 当前只有共享 USD。
- 将内部 `heavy_duty` 提升为第九个公开构型 — 未经单独需求确认不扩展支持集合。
- 改写或补录 v1.0 的历史结论 — v1.0 tag 与归档保持冻结。

## Constraints

- 本地环境不具备 Isaac Sim；本地只宣称静态合同、纯 Python/Torch 和现有 Isaac-free 测试结果。
- 服务器目标基线为 Isaac Sim 5.0 + Isaac Lab 2.2.1；任何版本偏差必须写入 artifact，不能静默合并证据。
- received snapshot、v1.0 `source/results` 证据和 v2.0 planning 使用三个独立提交/推送边界。
- 不删除 `.planning/phases/` 中仅存的 v1.0 历史 phase 目录；它们没有另一份完整目录归档。
- 不在 Phase 6 改变现有 v1 Koopman `state=11/reference=5/control=PWM_8` 语义。
- 归一化 action/PWM 边界为 `[-1,1]`，验证容差为 `1e-6`。
- 支持集合固定为八个 CLI 构型；内部 `heavy_duty` 不计入通过率分母。

## Acceptance Criteria

- [x] received snapshot commit 与后续 Phase 6 integration commits 可由 Git 文件列表清楚区分。
- [x] `easyuuv_nc` 的安装/import/gym/asset runbook 在目标服务器 probe 中通过。
- [x] supported catalog 精确包含八个公开构型，`heavy_duty` 仅标记为 internal。
- [x] 8/6/4 推进器数量、4D mask 和 declared-control rank 与 Requirement 4 的期望完全一致。
- [x] base 至少完成 64 steps，其余七种各至少完成 8 steps，八个结果均唯一存在。
- [x] 八构型 artifact 中没有 NaN、Inf、越界控制或推进器维度不匹配。
- [x] 本地 `pytest` 退出 0 且测试数不少于 175，`compileall` 退出 0。
- [x] runbook、machine-readable artifact、SUMMARY 和 VERIFICATION 均存在并覆盖 QUAL-01..08。
- [x] `git diff v1.0` 未显示对 v1.0 tag 或 canonical archived planning records 的回写。

## Ambiguity Report

| Dimension | Score | Min | Status | Notes |
|---|---:|---:|---|---|
| Goal Clarity | 0.95 | 0.75 | ✓ | 目标限定为 intake/qualification，不包含 Koopman 集成。 |
| Boundary Clarity | 0.93 | 0.70 | ✓ | 八构型、内部 preset、共享 USD 与后续阶段边界均明确。 |
| Constraint Clarity | 0.88 | 0.65 | ✓ | 本地/服务器职责、版本、控制边界和 Git 隔离已量化。 |
| Acceptance Criteria | 0.91 | 0.70 | ✓ | 步数、构型集合、rank/mask、命令退出码与产物均可判定。 |
| **Ambiguity** | **0.08** | **≤0.20** | **✓** | 加权 clarity=0.92，满足自动生成门。 |

## Interview Log

本 SPEC 使用 `--auto`，因为用户已审阅并确认 `docs/Agentic_AUV_v2_milestone_design.md`，且 Phase 6 的 WHAT/WHY 已由实际源码复核。

| Round | Perspective | Question summary | Decision locked |
|---|---|---|---|
| 0 | Researcher (auto) | 当前源码与目标状态差在哪里？ | 包声明为 `easyuuv_nc`，但缺 packaging/qualification contract；Phase 6 先解决 intake truth。 |
| 0 | Simplifier (auto) | 最小成功范围是什么？ | 八构型 catalog、拓扑/可控性、本地合同、分级 server smoke；不训练 Koopman/PPO。 |
| 0 | Boundary Keeper (auto) | 哪些相邻工作必须后移？ | schema/Koopman/MPC/adaptation/Agent 分别留给 Phase 7–11。 |
| 0 | Failure Analyst (auto) | 最危险的错误声明是什么？ | 把 `uuv4*` 当成 yaw 可控、把共享 USD 当成八套机器人、把本地静态检查当 Isaac 证据。 |
| 0 | Seed Closer (auto) | 怎样让完成条件可复核？ | 固定公开集合、mask/rank、最小 step counts、边界 validator 和 QUAL-01..08 verification mapping。 |

---

*Phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification*
*Spec created: 2026-08-09*
*Next step: `$gsd-plan-phase 6` — research implementation details and create executable plans*

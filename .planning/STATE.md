---

gsd_state_version: 1.0
milestone: v2.0
milestone_name: Multi-Configuration Koopman Transfer and Environment-Aware Control
status: in_progress
last_updated: "2026-09-29"
last_activity: 2026-09-29 -- current modules consolidated and locally verified; file removal awaits user confirmation
progress:
  total_phases: 11
  completed_phases: 7
  total_plans: 36
  completed_plans: 33
  percent: 92
---

# Project State: EASYkoopman

**当前工作：模块合并，等待清除确认。** `codex/consolidate-current-modules` 已合并control、连续MPC、控制器编排及扰动实验入口，27个旧模块不再进入当前148文件源码包；旧文件尚未删除，历史调用与迁移测试尚待退役。279项定向测试通过，v88原24轨迹复算结论不变。`easyuuv_v2-main/` 只ignore，不提交、不删除。资产引用统一到包内，两个重复USD等待用户确认清除。见[合并与清理清单](../docs/phase9_cleanup_proposal_2026-09-29.md)；更早候选不能按版本号直接删除。本次没有新增Isaac或闭环结果。

**2026-09-29：v88三档扰动矩阵。** 用户最终指定0%、10%、30%附加二次阻力，扩大共同控制范围，完成实验结果与代码后PR合并。模型沿用v87冻结参数，物理不重校准；范围仅依据v87训练数据，在新验证/测试前冻结。Phase 9 / 09-04与`no_selection`保持开放。

## 当前入口

- [v88结果报告](../docs/phase9_matrix_v88_report.md)：数字、正负结果与结论边界。
- [v88运行说明](../docs/phase9_matrix_v88_runbook.md)：预先固定的矩阵、范围与准入规则。
- [研究索引](../docs/phase9_research_index.md)：当前代码与历史。
- [项目边界](PROJECT.md)、[控制链合同](../docs/phase9_control_chain_contract.md)。

## 已取得的证据

24条真实Isaac轨迹全部验收；12验证、12测试，三档需求波形配对，模型拟合0次。本地原始复验与冻结预测复算均通过，最大指标差异约1.3e-13。

30%独立测试：物理11/16、纯Koopman2/16、结合16/16窗口通过；结合z/姿态总体误差分别比物理下降53.31%/58.91%。0%/10%下物理更准，纯Koopman三档均未证明可靠优势。16窗口来自4条轨迹，不是16条独立实验。

共同范围由原16条训练轨迹与旧范围加固定余量得到，保留硬约束。原v87四个起点回查均能进入新范围，仅证明筛查拦截解除；本轮12个新状态旧范围允许3/12、新范围12/12；36次调用均保留并独立验收可行新候选，其中23次CPU超时、11次迭代上限。服务器实际加载范围身份与本地一致。

## 当前停止条件与交付

三档均未达到原“三模型预测和求解全部通过”的闭环准入规则，不运行2秒闭环，不看测试重训或扩界。离线求解已完成，308文件证据归档已全部核验，结果与代码通过PR交付；原始未跟踪材料保留。本轮开发分支为`codex/phase9-disturbance-matrix-v88`，交付目标为PR合并main；实时分支状态应以Git为准。此前PR #1已合并main。

本地核心109项、补充支持/求解5项、矩阵6项通过（有重叠，不相加）；服务器109项通过、1项打包测试未选择（本地通过）。仅为相关定向回归，不是全仓库全绿。

## 历史与保留边界

[v87报告](../docs/phase9_diverse_v87_report.md)：20%扰动扩大训练后，测试物理12/16、Koopman4/16、结合16/16；旧范围求解各1/4，未闭环。v88复用其模型，使用新的轨迹与不同强度，不能混算两轮结果。

[v86报告](../docs/phase9_disturbance_v86_report.md)：8条20%轨迹，扫频物理6/6、Koopman3/6、结合5/6，未闭环。旧v82局部闭环收益不构成完整提升Koopman的有效性证明。全部原始材料及负结果保留。

更早入口原文见[历史档案](../docs/history/phase9_status_before_v87_20260929.md)。[交接](checkpoints/phase9-lifted-generalization-handoff-2026-09-29.md)与[Git快照](../docs/phase9_git_snapshot_2026-09-29.md)保留写作时点语境。不同扰动形式、未见构型、长时稳定、实际闭环收益、实时性、自进化与Agent增量仍未证明。

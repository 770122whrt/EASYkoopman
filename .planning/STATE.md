---

gsd_state_version: 1.0
milestone: v2.0
milestone_name: Multi-Configuration Koopman Transfer and Environment-Aware Control
status: in_progress
last_updated: "2026-09-29"
last_activity: 2026-09-29 -- v87 prediction and solver evaluation completed; original gate retained; no closed loop
progress:
  total_phases: 11
  completed_phases: 7
  total_plans: 36
  completed_plans: 33
  percent: 92
---

# Project State: EASYkoopman

**更新：2026-09-29。v87扩大训练、独立预测与求解检查已完成；用户确认保留原门限，本轮不运行闭环。** 用户确认保留物理与 Koopman 结合，物理基线继续冻结；允许共同控制链修复，并要求整理仓库、提交 PR 后合并。尚不能标记 Phase 9 / 09-04 完成或解除 `no_selection`。

## 当前入口

- [研究索引](../docs/phase9_research_index.md)：当前、历史、代码入口和证据边界。
- [v87运行说明](../docs/phase9_diverse_v87_runbook.md)：扩大训练、验证、测试及准入顺序。
- [v87结果报告](../docs/phase9_diverse_v87_report.md)：由本轮实际验证更新，不能用计划代替结果。
- [项目边界](PROJECT.md)、[控制链合同](../docs/phase9_control_chain_contract.md)、[ROADMAP](ROADMAP.md)。

本轮仅 base、同一额外 20% 二次阻力，扩大为 PRBS、多正弦、扫频和脉冲激励及多个幅值。完整 38 维提升、冻结物理＋自主提升残差和共同控制约束保持。所有学习只发生在离线训练；验证和测试参数冻结。

## 最近已经取得的证据：v86

8 条真实 Isaac 扰动轨迹已在服务器及本地验收，模型只训练一次。独立扫频的 6 个预测窗口中，物理 6/6、Koopman 3/6、结合 5/6 通过；结合在同类输入验证上有局部改善，但扫频深度仍有失败，未执行 2 秒闭环。6 次离线求解保留了可行新候选，其中 2 次为 CPU 超时；实际仅覆盖同一共同启动状态的重复求解。完整数字及限定结论见[v86报告](../docs/phase9_disturbance_v86_report.md)。

v86 原始材料、冻结模型和失败证据保留。v87 是单独的新协议与数据，不能将 v86 的两个已看过测试轨迹再次当作盲测。旧 v82 局部闭环收益不构成完整提升 Koopman 的有效性证明。

## v87结果与本轮停止位置

24条真实轨迹全部验收，16条训练只拟合一次；验证/测试分别4条新轨迹。测试16个窗口中物理12/16、纯Koopman4/16、结合16/16通过。结合深度/姿态总体误差比冻结物理下降约63%/78%。仅支持当前同构型同扰动的独立轨迹预测改善。

四个不同求解起点中，三个超出原控制支持域；剩余起点三臂均有独立可行新候选，两个CPU超时候选成功保留。三臂求解均1/4通过。用户明确保留原三臂全部通过准入，不执行2秒闭环，不重训或放宽约束。控制、长时、其他构型/扰动泛化仍未证明。

本地24条原始数据复验和无拟合预测复算通过；307文件归档哈希通过。结果与历史整理经Git提交、PR合并交付；原始未跟踪材料保留。下一轮若继续控制研究，需单独处理数据运动范围与现有控制支持域的差距；本轮不自动开展。

## 历史记录

旧入口全部原文保存在[整理前历史档案](../docs/history/phase9_status_before_v87_20260929.md)，包括 v1.0、Phase 6–8.2 和历次 Phase 9 状态。概括时间线见[研究索引](../docs/phase9_research_index.md)。[2026-09-29交接](checkpoints/phase9-lifted-generalization-handoff-2026-09-29.md)和[Git快照](../docs/phase9_git_snapshot_2026-09-29.md)保留其当时语境，不再作为当前状态表。

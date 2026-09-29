# Phase 9 截至v66的历史索引

2026-09-21归档。此处是引用式归档；所有历史报告、冻结模型、实验包和证据文件均保留原位置，不移动或改写。当前工作从[Phase 9入口](../../phase9_index.md)开始。旧提案中的待批准、旧端口、暂停、下一步和预算，只描述当时状态，不作为本轮运行指令。

## 原始交接快照

[原.continue-here.md完整原文](continue-here.original.txt)保存整理前的全部79500字节，SHA256为`c762fd783feec57eeedc8aaac3fb9a28685e52e6946b64d6e410d89ac479c27d`。采用.txt保留原字节且避免迁移后的相对链接被误认为当前位置的导航；原文链接以原路径`.planning/.continue-here.md`解析。新[简明交接](../../../.planning/.continue-here.md)仅保留当前状态与动作。

## 研究方向与控制接口

- [路线审核](../../phase9_roadmap_review.md)、[同策略跨构型边界](../../phase9_shared_policy_generalization_scope.md)、[启动与控制效果优先级](../../phase9_startup_and_control_evidence_priority.md)。
- [v44有界MPC](../../phase9_bounded_mpc_v44_results.md)、[v45准备命令复用](../../phase9_prepared_commands_v45_results.md)、[v46有界反馈](../../phase9_bounded_feedback_v46_results.md)、[v47有界跟踪](../../phase9_bounded_tracking_v47_results.md)。
- [v49执行与worker](../../phase9_execution_and_worker_v49_results.md)、[v51恢复worker](../../phase9_recovery_worker_v51_results.md)、[v54运行仲裁](../../phase9_runtime_arbiter_v54_results.md)、[v55 Isaac适配](../../phase9_isaac_adapter_v55_results.md)。

## 预测加速、现场接入与失败定位

- [v40预测成本](../../phase9_prediction_cost_v40.md)、[v41批量预测](../../phase9_batch_cost_v41.md)、[v42分配成本](../../phase9_allocation_cost_v42.md)、[v43数值核编译](../../phase9_compiled_cost_v43.md)。
- [v56资产迁移](../../phase9_runtime_assets_v56_results.md)、[v57采集重放](../../phase9_runtime_collector_v57_results.md)、[v58运行发布](../../phase9_runtime_release_v58_results.md)。
- v58：[提案](../../phase9_runtime_preflight_v58_proposal.md)、[运行说明](../../phase9_runtime_preflight_v58_runbook.md)、[现场环境](../../phase9_server_environment_v58_results.md)、[隔离环境修订](../../phase9_runtime_environment_v58_amendment.md)、[初始化失败结果](../../phase9_runtime_preflight_v58_results.md)。
- v59：[修复运行说明](../../phase9_runtime_preflight_v59_runbook.md)、[真实结果](../../phase9_runtime_preflight_v59_results.md)。
- v60/v61：[剖析范围](../../phase9_runtime_profile_v60_runbook.md)、[加速结果](../../phase9_runtime_acceleration_v61_results.md)。
- v62：[运行说明](../../phase9_runtime_v62_runbook.md)、[生命周期与CPU结果](../../phase9_runtime_v62_results.md)。
- v63/v64：[算法效率审核](../../phase9_algorithm_efficiency_review_v63.md)、[编译运行说明](../../phase9_compiled_mpc_v64_runbook.md)、[编译服务器结果](../../phase9_compiled_mpc_v64_results.md)。

## 首次闭环局部收益

- v65/v66：[已结束运行范围](../../phase9_control_effects_v65_runbook.md)、[结果与未完成配对](../../phase9_control_effects_v65_results.md)、[独立复核](../../evidence/phase9/control-effects-v65-20260921/review.json)。
- v65 base俯仰局部收益与v66尾延迟失败分别保留；不能合并版本，也不能把短任务改善推广为多构型泛化或表示优势。

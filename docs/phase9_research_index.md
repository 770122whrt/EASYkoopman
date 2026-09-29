# Phase 9 研究入口与历史索引

2026-09-29。当前为 **v88扩大共同控制范围与0%/10%/30%扰动矩阵**。模型全部沿用v87冻结参数；30%独立测试结合明显更准，0%/10%物理更准。36次求解可行，原预测准入未通过，未运行闭环，Phase 9 / 09-04与`no_selection`继续开放。

## 从哪里开始

| 要了解的内容 | 唯一维护位置 |
|---|---|
| 当前正在做什么、还缺什么证据 | [STATE](../.planning/STATE.md) |
| 项目目标、冻结历史与控制边界 | [PROJECT](../.planning/PROJECT.md) |
| 本轮数据、冻结规则、运行与验收 | [v88运行说明](phase9_matrix_v88_runbook.md) |
| 本轮实际结果和未完成项 | [v88结果报告](phase9_matrix_v88_report.md) |
| 三个模型如何接同一控制器 | [控制链合同](phase9_control_chain_contract.md) |
| 阶段规划与历史里程碑 | [ROADMAP](../.planning/ROADMAP.md)、[MILESTONES](../.planning/MILESTONES.md) |

当前仅base，比较0%、10%、30%附加阻力，使用在20%数据上训练的同一冻结模型。新控制范围在采集前仅依据v87训练轨迹确定，所有模型共同使用；新验证/测试按整轨迹分离，三档需求波形配对。24条新轨迹验收与本地预测复算均通过，36次求解均有独立可行新候选，23次CPU超时保持原标记。

## 当前代码导航

| 内容 | 主入口与复用关系 |
|---|---|
| 数据角色、信号与预先固定的比较条件 | [protocol_v88.py](../workflows/protocol_v88.py) |
| 源码和资源运行包 | [prepare_disturbance_v88.py](../workflows/prepare_disturbance_v88.py) |
| 真实扰动采集与严格验收 | [collect_disturbance_data_v88.py](../workflows/collect_disturbance_data_v88.py)、[disturbance_data_v88.py](../workflows/disturbance_data_v88.py) |
| v88冻结验证/测试；v87训练来源 | [evaluate_disturbance_v88.py](../workflows/evaluate_disturbance_v88.py)；[fit_disturbance_v87.py](../workflows/fit_disturbance_v87.py) |
| 当前三臂求解器入口 | [preview_solver_v87.py](../koopman/preview_solver_v87.py)、[solve_disturbance_v88.py](../workflows/solve_disturbance_v88.py) |
| 同一模型家族 | [disturbance_lifted_v86.py](../koopman/disturbance_lifted_v86.py)复用完整提升与自主残差；v87扩大数据，不新增模型家族 |
| 共同控制核心 | `command_state_v39`、`continuous_prediction_v76`、`continuous_mpc_v76`、`preview_mpc_v79`和`preview_solver_v80`；职责见[控制链合同](phase9_control_chain_contract.md) |

v88保留原预测/求解准入，当前未准入闭环；不能直接把仍读取旧支持域的v87闭环入口当作v88运行入口。共享模块保留旧版本号是依赖关系，不是另一个当前研究方向。旧 `*_v*.py` 和未跟踪实验资料保留，不能仅因名字旧就删除；提交时精确选择当前改动和可复现证据。

## 已有结论与历史时间线

| 阶段 | 得到什么、仍缺什么 | 原始入口 |
|---|---|---|
| v1.0 | 单构型端到端链路与多轮控制实验；最终无 profile 被选中 | [里程碑总结](../.planning/reports/MILESTONE_SUMMARY-v1.0.md) |
| Phase 6–8.2 | 八构型接入、4D接口与冻结数据/LOCO；8.2以NO_SELECTION结束，无合格模型交接 | [历史状态原文](history/phase9_status_before_v87_20260929.md)、[ROADMAP](../.planning/ROADMAP.md) |
| v77/v78 | 小范围2秒闭环、局部构型收益；结构化投影不能证明独特Koopman表示收益 | [v77报告](phase9_reliable_control_v77_report.md)、[v78报告](phase9_common_profile_v78_report.md) |
| v79/v80 | 因果反馈预演、模型/控制分离与共同求解链修复 | [v79诊断](phase9_control_model_separation_v79.md)、[方法审核](phase9_methodology_crosscheck_2026-09-26.md) |
| v82 | 10条2秒闭环；uuv4局部学习收益、base负结果；逐步重提升，不是当前完整提升证明 | [v82报告](phase9_koopman_mpc_v82_report.md)、[v83架构复核](phase9_architecture_v83_review.md) |
| v84/v85 | 完整提升预测与单构型扫频仍失败；求解超时候选缺陷暴露 | [多模型报告](phase9_model_comparison_v84_report.md) |
| v86 | 8条真实20%阻力扰动轨迹，一次训练；扫频窗口物理6/6、Koopman3/6、结合5/6通过，未进入2秒闭环 | [v86报告](phase9_disturbance_v86_report.md)、[证据入口](evidence/phase9/disturbance-v86-20260929/README.md) |
| v87 | 24条新轨迹、一次训练；测试物理12/16、Koopman4/16、结合16/16；求解各1/4通过，原门限保留，无闭环 | [运行说明](phase9_diverse_v87_runbook.md)、[结果报告](phase9_diverse_v87_report.md) |
| v88 | 新范围、24条0%/10%/30%轨迹、零重训；30%测试结合16/16通过、z/姿态总体误差比物理降低约53%/59%，0%/10%物理更准；36次求解可行，原预测准入未通过，无闭环 | [运行说明](phase9_matrix_v88_runbook.md)、[结果报告](phase9_matrix_v88_report.md) |

v86 每组 6 个预测窗口来自 2 条轨迹，不能写成 6 条独立实验。其求解调用采用了重复共同启动状态，因此 v87 改为激励段不同状态；这是验证覆盖修正，不是已获得更好的模型或控制结果。v86 同类验证上混合模型优于冻结物理，扫频深度仍变差，不能概括成整体优势。

## 文档和证据如何区分

- 版本报告是该次结果的数字依据；版本运行说明是该次操作合同。旧文件里的“当前”“下一步”属于其写作时点，不覆盖最新用户范围。
- [2026-09-29交接](../.planning/checkpoints/phase9-lifted-generalization-handoff-2026-09-29.md)与[Git快照](phase9_git_snapshot_2026-09-29.md)保留交接前事实；它们不是持续维护的状态页。
- 整理前 README、PROJECT、STATE 和控制合同全部原文集中在[历史档案](history/phase9_status_before_v87_20260929.md)，包含原文件SHA256；原始报告、数据、失败日志没有搬移或删除。
- `docs/evidence/phase9/`保存版本化实验材料；`source/results/`中的冻结既有证据保持其原验收身份。本地测试、离线求解和真实Isaac控制结果不得互换标签。

尚未证明：单独完整提升稳定胜过冻结物理、结合普遍更好、含扰动闭环收益、长时稳定、未见构型/扰动迁移、实时控制与Agent增量。当前结果不改变这些边界；新报告只能按实际证据逐项更新。

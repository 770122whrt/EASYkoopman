# 当前模块合并与待确认清理

2026-09-29。分支 `codex/consolidate-current-modules`，起点 `main` / `1d7d1f4`。**已实现模块合并；未删除文件。** 用户最新要求：`easyuuv_v2-main/` 只ignore，不提交、不删除；任何清除前单独确认。

## 已完成的合并

| 原实现 | 当前唯一维护入口 |
|---|---|
| control v24/v67 | `easyuuv_nc/control.py`：统一时钟、保持/回放、PWM、复位及执行器记忆 |
| continuous_mpc v76/v80 | `koopman/continuous_mpc.py` + `planning_margin.py`：完整求解与数值余量 |
| reliable_mpc v77、feedback/preview v79、solver v80/v87 | `koopman/control_solver.py`：三个模型、预览、独立检查、进程通信与计划选择 |
| protocol v86/v87/v88 | `workflows/disturbance_protocol.py` + `experiments/phase9/*/protocol.json` |
| 多版数据验收、采集、训练、评估、求解、冻结和打包 | `workflows/{disturbance_data,collect_disturbance_data,fit_disturbance,evaluate_disturbance,solve_disturbance,freeze_support,prepare_disturbance,source_freeze}.py` |

合并模块包含实际算法，不通过继承或导入旧对应模块来伪装合并。当前环境直接使用新control，无需全局monkey patch；七个现用执行器辅助模块也改为引用同一实现。当前模型加载和支持域使用统一训练协议。包初始化改为按需兼容历史导出，不再自动加载旧模型家族。

数学提升、物理项、命令历史、范围等下层公共模块仍保留其既有实现与编号。这些是当前真实依赖，不是“所有旧编号均可删除”。旧运行入口、历史测试与新迁移对照目前也仍在工作树中；全仓清理尚未完成。

## 验证结果

- 279项定向测试通过，0失败、0跳过；不是全仓库测试结论。
- v88原24条轨迹重验并复算，验证/测试各144个模型窗口；通过门限、失败信息、轨迹身份与范围统计均保持一致。
- 最大指标差异：验证 `1.2515317016244254e-13`，测试 `4.654875660273228e-14`；固定数值容差1e-10。
- 新源码包为148文件，已逐项哈希验证，并在独立解压目录中通过模块导入、冻结模型加载与信号生成。
- 包含真实IPOPT超时、正常求解、固定前缀及进程生命周期测试；本次没有新增Isaac仿真、训练或闭环实验。

[机器可读验证结果](../experiments/consolidation-20260929/final/verification.json)、[完整路径清单](phase9_cleanup_inventory_2026-09-29.json)、[统一实验入口](../experiments/README.md)。

## 历史数据与唯一资产地址

历史采集清单由原源码tar逐项核验；当前分析代码的身份另行记录。新代码不冒充旧源码执行，原协议、物理模型、学习模型和控制范围字节不改。v86–v88的原源码/证据归档共146.05 MiB纳入本次明确提交范围，在原位置各保留一份；统一索引位于experiments。未擅自搬移数GB旧原始目录，更多历史材料仍未跟踪。

两个资产配置入口现在统一引用 `easyuuv_nc/data/embodiment/embodiment.usd`，其Props相对依赖也在包内。旧USD文件仍在磁盘，等待确认删除。config.yaml两份字节不同，暂不列为“完全重复文件”。

## 等待确认的清理清单

以下27个原模块已退出当前源码包依赖集合；清理时还需同步处理其历史调用入口和迁移测试的旧版对照，先把对照固定为可恢复基准，再删除。仅凭不在静态集合中，不宣称全仓所有历史入口仍可运行。原实现均可由整理前提交恢复，文件Git对象及SHA见JSON清单。

| 原路径 | 合并去向 |
|---|---|
| `easyuuv_nc/control_v24.py` | `easyuuv_nc/control.py` |
| `easyuuv_nc/control_v67.py` | `easyuuv_nc/control.py` |
| `koopman/continuous_mpc_v76.py` | `koopman/continuous_mpc.py`, `koopman/planning_margin.py` |
| `koopman/continuous_mpc_v80.py` | `koopman/continuous_mpc.py`, `koopman/planning_margin.py` |
| `koopman/reliable_mpc_v77.py` | `koopman/control_solver.py` |
| `koopman/feedback_preview_v79.py` | `koopman/control_solver.py` |
| `koopman/preview_mpc_v79.py` | `koopman/control_solver.py` |
| `koopman/preview_solver_v80.py` | `koopman/control_solver.py` |
| `koopman/preview_solver_v87.py` | `koopman/control_solver.py` |
| `workflows/protocol_v86.py` | `workflows/disturbance_protocol.py` |
| `workflows/protocol_v87.py` | `workflows/disturbance_protocol.py` |
| `workflows/protocol_v88.py` | `workflows/disturbance_protocol.py` |
| `workflows/disturbance_data_v86.py` | `workflows/disturbance_data.py` |
| `workflows/disturbance_data_v87.py` | `workflows/disturbance_data.py` |
| `workflows/disturbance_data_v88.py` | `workflows/disturbance_data.py` |
| `workflows/collect_disturbance_data_v86.py` | `workflows/collect_disturbance_data.py` |
| `workflows/collect_disturbance_data_v87.py` | `workflows/collect_disturbance_data.py` |
| `workflows/collect_disturbance_data_v88.py` | `workflows/collect_disturbance_data.py` |
| `workflows/fit_disturbance_v86.py` | `workflows/fit_disturbance.py` |
| `workflows/fit_disturbance_v87.py` | `workflows/fit_disturbance.py` |
| `workflows/evaluate_disturbance_v88.py` | `workflows/evaluate_disturbance.py` |
| `workflows/solve_disturbance_v87.py` | `workflows/solve_disturbance.py` |
| `workflows/solve_disturbance_v88.py` | `workflows/solve_disturbance.py` |
| `workflows/freeze_support_v88.py` | `workflows/freeze_support.py` |
| `workflows/prepare_disturbance_v86.py` | `workflows/prepare_disturbance.py`, `workflows/source_freeze.py` |
| `workflows/prepare_disturbance_v87.py` | `workflows/prepare_disturbance.py`, `workflows/source_freeze.py` |
| `workflows/prepare_disturbance_v88.py` | `workflows/prepare_disturbance.py`, `workflows/source_freeze.py` |

另外两份逐字节相同的USD待确认清除：

- `data/easyuuv/model.usd` → 保留 `easyuuv_nc/data/embodiment/embodiment.usd`。
- `data/easyuuv/Props/instanceable_meshes.usd` → 保留 `easyuuv_nc/data/embodiment/Props/instanceable_meshes.usd`。

两份合计70.72 MiB。根目录旧环境代码、非相同配置、历史原始材料以及已有缓存不在这两份资产删除范围。`easyuuv_v2-main/` 始终只ignore。迁移阶段新增的测试临时目录及第一轮复算文件也保留，待清理确认时按具体路径处理。

当前仓库中其它537个历史候选来自初始静态盘点，**不是此次已经确认安全的删除清单**。剩余历史源码/测试需继续对照当前依赖整理；仍被使用的实现先合并或保留，不能按版本号批量清空。

## 使用合并后的入口

以下只复算已有数据：

```powershell
.venv/Scripts/python.exe -m workflows.evaluate_disturbance --data docs/evidence/phase9/matrix-v88-20260929/server/data --manifest docs/evidence/phase9/matrix-v88-20260929/release-r1/manifest.json --source-archive docs/evidence/phase9/matrix-v88-20260929/release-r1/source.tar.gz --model docs/evidence/phase9/diverse-v87-20260929/server/model.json --role test --output NEW_TEST_REPORT.json
```

输出必须为新文件。原raw未解压的checkout先按历史证据归档恢复data目录；source archive用于身份校验，不把旧代码导入当前分析进程。新采集只接受当前source freeze，不能用历史tar冒充当前执行。科学结论保持原报告：30%下结合预测更好，0%/10%物理更好，纯Koopman门限未通过，仍无扰动闭环收益证明。

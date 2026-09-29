# 实验入口

实验编号描述数据与协议，不再对应一整套复制的控制代码。当前协议由 `workflows.disturbance_protocol.get_protocol()` 读取以下配置，默认v88。

| 实验 | 固定配置 | 结果报告 | 数据与冻结产物当前位置 |
|---|---|---|---|
| v86：初轮20%扰动 | [protocol.json](phase9/v86/protocol.json) | [报告](../docs/phase9_disturbance_v86_report.md) | [证据](../docs/evidence/phase9/disturbance-v86-20260929/) |
| v87：扩大训练范围 | [protocol.json](phase9/v87/protocol.json) | [报告](../docs/phase9_diverse_v87_report.md) | [证据](../docs/evidence/phase9/diverse-v87-20260929/) |
| v88：0%/10%/30%配对评估 | [protocol.json](phase9/v88/protocol.json) | [报告](../docs/phase9_matrix_v88_report.md) | [证据](../docs/evidence/phase9/matrix-v88-20260929/) |

v88复用v87冻结的学习模型及事前冻结物理模型，没有重训。30%扰动下结合模型预测更好；0%/10%下物理更好；纯Koopman未通过整体预测门限，未运行2秒闭环。模块整理不改变这些结论。

当前实现的入口为 `workflows.collect_disturbance_data`、`fit_disturbance`、`evaluate_disturbance`、`solve_disturbance`、`freeze_support`、`prepare_disturbance`。模型/控制参数以及训练、验证、测试划分保持原协议；旧编号入口留待确认清除。

历史数据保留其原始采集源码清单。用重构后的代码复算时，必须显式提供对应源码归档来核验原始清单，并另外记录当前分析代码身份。原清单的路径与哈希不改写。

物理文件搬移与重复副本清除尚未执行：依照用户要求，先核对归档可恢复性，再提供具体清单确认。当前表格为统一索引，不表示原始数据已经搬到本目录。`easyuuv_v2-main/` 是被忽略的本地参考副本，不进入提交。

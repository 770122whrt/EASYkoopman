# v38正式validation结果：独立复核GO

2026-09-20T00:27:40+08:00

24条×512控制区间的正式validation已完成。服务器评分原生退出0，本地独立复核原生退出0；1152项指标完整，全部24组固定精度/速度门通过。本页保存validation角色结果；后续test也已独立GO，见[最终正式报告](phase8_4_v38_formal_results.md)。两者均非MPC或Agentic有效性证明。

## 实际完成与性能

- 18个v30冻结模型未重新拟合；比较nonlinear pooled/heldout、linear pooled/heldout、known physics、persistence六条路径。
- 576项条件预测由冻结预测器重新递推；576项全段/策略指标由保存数组独立计算；全部原始数据、缓存、模型、源码和原生退出绑定一致。
- 每构型3个episode，在所有主时域、终点/path及pooled/heldout的速度门中均为3/3优于persistence。
- 512区间全段六条路径全部完整，但其精度按原协议只作描述，不把完整性等同于闭环控制能力。

下表为各模式六组主门的目录汇总速度分数比范围（候选/persistence；越小越好），使用预先固定的归一方式，不代表每个单独状态误差比例：

| 模式 | 模型范围 | 速度分数比范围 | 通过门数 |
|---|---|---|---|
| conditional_projected | pooled | 0.000355115–0.0012218 | 6/6 |
| conditional_projected | heldout | 0.000360931–0.00122685 | 6/6 |
| policy_self_recurrence | pooled | 0.00268498–0.00833999 | 6/6 |
| policy_self_recurrence | heldout | 0.00286309–0.00441674 | 6/6 |

128控制区间条件预测终点的机体系线速度分量RMSE，下面每格为该构型3个episode的均值，单位m/s：

| 构型 | nonlinear pooled | nonlinear heldout | known physics | persistence |
|---|---:|---:|---:|---:|
| base | 2.74268e-06 | 2.74519e-06 | 2.72616e-06 | 0.0172662 |
| long_body | 4.57069e-06 | 4.52488e-06 | 4.60769e-06 | 0.016474 |
| heavy_moderate | 0.000310254 | 0.000308441 | 0.000318189 | 0.0759527 |
| asymmetric | 3.53768e-06 | 3.55298e-06 | 3.55943e-06 | 0.0164289 |
| uuv6 | 5.4829e-06 | 5.48244e-06 | 5.53565e-06 | 0.0178849 |
| uuv6_angled | 4.36113e-06 | 4.35634e-06 | 4.41741e-06 | 0.016094 |
| uuv4 | 3.73789e-06 | 3.73927e-06 | 3.7477e-06 | 0.0158647 |
| uuv4_angled | 3.63512e-06 | 3.63572e-06 | 3.68731e-06 | 0.0160157 |

## 能说明什么

当前固定八构型目录中，heldout模型同样通过正式validation，先前“跨构型必然明显变差”的概括不适用于这套修复后的模型和数据合同。已有证据支持实际参数、初始化、因果执行器历史和物理结构约束需要一起落实；本次没有逐项消融，不能把全部收益单独归给某一次修复。

条件预测接收真实轨迹记录的未来已发命令，命令来自反馈控制，因此这些命令不一定在预测起点已知。另列的policy_self_recurrence才由预测状态生成自己的未来命令。代码中planned_commands字段名称不应解读成没有未来命令信息。

实际模型是六个速度观测量的结构化回归与已知位姿积分耦合；它与同D/Q系数物理参数模型等价。当前结果显示其接近已知物理，不能证明额外Koopman算法优势、完整有限维提升闭合或Agentic增益。每构型仅3条轨迹，bootstrap按episode配对并仅作描述；未覆盖流场、噪声、DR或任意新拓扑。

## 当时资源估计与后续完成情况

累计采集1510.428秒、分析2290.438秒，原分析余额1309.562秒。test相同流程按本轮各环节实测预计1509.543秒，超过余额199.981秒。这是资源不足预测，不是模型NO_GO或已经发生的超时。

资源修订已批准并实施；原定24条test现已全部独立复核GO。最终累计分析3296.516秒（54.94分钟），低于获准75分钟，也低于原60分钟；当时预计用时并非实际费用。见[正式关闭报告](phase8_4_v38_formal_results.md)和[资源修订实际结算](phase8_4_v38_analysis_budget_amendment.md)。

2026-09-20文档更正：本表原“世界速度”应为“机体系线速度”；原评分使用state5:8，数值和门不变，原derived JSON保留并由最终关闭记录注明错误键名。

## 证据

- [评分结果](evidence/phase8_4/server-projected-formal-v38-r22/validation-analysis/result.json)、[逐项分数](evidence/phase8_4/server-projected-formal-v38-r22/validation-analysis/scores.json)。
- [独立复核凭证](evidence/phase8_4/server-projected-formal-v38-r22/validation-analysis-audit.json)、[实际退出与时间](evidence/phase8_4/server-projected-formal-v38-r22/validation-analysis-audit-operation.json)。
- [累计账本](evidence/phase8_4/server-projected-formal-v38-r22/live-budget.json)、[资源估计](evidence/phase8_4/server-projected-formal-v38-r22/test-resource-projection.json)、[存储估计](evidence/phase8_4/server-projected-formal-v38-r22/test-storage-projection.json)。

源码`00d01f1eda690d663612be8ff4d571a898b4347d`；freeze `b52e81b2e9f3ad95282ff7041b5b316ce14b3270a539d917e0102376e6474657`；独立审核SHA `70bfc08364b0b53d3dd0c3fe3449c10c9ccf5a1d1e8c7cea4da59f6946cccde5`。

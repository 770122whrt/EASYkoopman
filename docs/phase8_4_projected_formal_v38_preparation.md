# v38正式验证：本地运行包已就绪

**最新执行状态（2026-09-14T10:39:28+08:00）：** 用户已批准本次freeze对应的完整v38范围，并确认服务器开启；SSH连接核对通过，源码上传中，尚未启动新采集。批准记录见[authorization.json](evidence/phase8_4/projected-formal-package-v38-20260914-r20/inputs/authorization.json)。下文准备时的“待批准”表述是历史状态。

2026-09-14。**本地准备完成，等待新的正式实验决定。** 原工作树和隔离clone各497项测试通过（35.67秒／35.61秒，原生退出均0），覆盖63个测试文件。537文件、18个旧模型及新协议已冻结；没有新正式采集、新拟合或MPC/Agentic交接。

承接[正式提案](phase8_4_projected_formal_v38_proposal.md)、[实际运行手册](phase8_4_projected_formal_v38_runbook.md)和[08计划](../.planning/phases/08.4-conditional-identification-experiment/08.4-08-PLAN.md)。研究目标仍是Koopman-UUV／Agentic-AUV；当前候选是六个速度观测量的物理结构回归加已知运动学，不声称完整有限维Koopman闭合或相对等价物理参数模型的独立收益。

## 本轮补齐的内容

| 环节 | 当前实现与证据边界 |
|---|---|
| 正式分析入口 | 最多4个CPU进程；固定18模型，逐病例保留退出、预测数组、评分及哈希。512全段连续携带自身状态、命令/执行器历史；每role要求1152条指标完整。 |
| 原数据归档及拉回 | 保存源码、模型、runtime、输入、逐病例trace与原生退出；本地重新验收全部子步的实际机械参数、时序、输入/执行器记忆及物理语义。新运行时检查在旧r19归档上兼容通过，但本轮尚无新真实归档。 |
| 独立分析复算 | 独立累加全部576条条件预测的误差，并从保存的full/policy数组复算另外576条指标，再重算固定门和bootstrap。它复用冻结预测器数学实现，未完整重新生成全部策略命令序列；不是两个独立模型实现。 |
| test开放 | 缺少独立分析审计、原生失败、角色/源码/模型/数据绑定变化或分数改动均不能开放test；GO必须由完整validation重算得到。 |
| 资源和失败 | 新采集与分析分账、预留后运行、失败仍计费。归档中的旧预算不能代替最新live账本；两端操作串行同步账本并核对SHA。失败档案可在剩余额度内保全，但不得提升可用前缀。 |
| 隔离源码包 | 在专用目录提交源码快照、制作离线bundle并核对clone；原工作树未提交/清理。原树与clone均通过完整相关清单；未把fixture、旧fit或r19重命名成正式数据。 |

新增独立审计先记录4项缺少实现的失败，再补实现。后续针对性检查曾出现1项测试夹具缺少前置文件的失败，补齐夹具后22项通过；最终上述497／497为整套相关检查。被测synthetic集成路径只证明程序连接和拒绝行为，不能当Isaac或模型性能证据。

## 可以核对的实际产物

- [本地就绪核对](evidence/phase8_4/projected-formal-package-v38-20260914-r20/audit.json)：重新核对145项旧v25正式产物、492项v37旧源码与46项输入，全部保持；未批准的包无法进入运行入口。
- [原树测试](evidence/phase8_4/projected-formal-package-v38-20260914-r20/root-tests.json)与[隔离clone测试](evidence/phase8_4/projected-formal-package-v38-20260914-r20/clone-tests.json)：各497通过，无新Isaac运行。
- [实际包清单](evidence/phase8_4/projected-formal-package-v38-20260914-r20/package.json)：bundle79,573,806 bytes，537文件，模型零新拟合。
- [冻结输入](evidence/phase8_4/projected-formal-package-v38-20260914-r20/inputs/freeze.json)与[待决定记录](evidence/phase8_4/projected-formal-package-v38-20260914-r20/inputs/authorization-pending.json)。没有authorization.json，待决定文件不构成批准。
- [磁盘准备测量](evidence/phase8_4/projected-formal-package-v38-20260914-r20/storage-projection.json)：包含本地准备包、两端源码/原数据/归档副本和128MiB分析日志余量，预测约3.61GiB，距4GiB约0.39GiB。原始trace按r19长度线性外推，不是新实验实测；各阶段仍须实际检查，超限停止。

运行源码`1ba1d0e3dc8dcbc83263e678b7eea259672a8f83`；freeze SHA256为`85fda36f7e8ef69502395b8e87b48afc7421d73d153b59454febd83277e9b6d7`。包位置为`.pytest-tmp/phase84-projected-formal-v38-20260914-r20`，使用其`verified-clone`与`inputs`，不能拿继续修改的原工作树冒充冻结运行源。bundle、build和freeze不重复运行。

## 下一步

1. 按既定NID-02提出一次具体新D-23：8构型，8条256区间预检＋24条512区间validation＋仅GO后24条512区间test；90分钟新采集、60分钟新分析墙钟、最多4进程、4GiB总文件。
2. 获准并确认服务器开启后，执行preflight→独立拉回→validation→评分/独立复算；全部门GO才采集test。
3. test按相同门一次性评价并独立复核，据实选择或否决。合格后才审查匹配控制接口交接；不把胜过persistence改写成完整Koopman算子、MPC或Agentic收益。

08任务1已完成，任务2等待范围决定；NID-05与整个goal仍未完成。当前暂不需要服务器，正式执行时再请求开机。

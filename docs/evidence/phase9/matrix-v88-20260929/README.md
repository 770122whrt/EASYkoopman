# v88执行证据

24条新Isaac轨迹全部验收，模型拟合0次。三档0%/10%/30%附加阻力对照使用相同v87冻结模型；共同控制范围只由其16条训练轨迹和旧范围产生。完整结果见[报告](../../../phase9_matrix_v88_report.md)，预先协议见[运行说明](../../../phase9_matrix_v88_runbook.md)。

30%测试结合模型16/16窗口通过，z/姿态总体RMSE比冻结物理下降53.31%/58.91%；0%和10%下物理更准，单独Koopman三档均未合格。16窗口来自4条轨迹。三档原预测准入都未全部通过，闭环0次。

## 范围与求解

`support.json`由训练数据生成，新来源与原物理拟合来源分开记录。文件SHA256 `f7f317119e48adcdda8eddbd1e91b0a8f392e59492c4ca93f706923b6bcc9a89`；服务器实际domain identity为`9cd2476e5210bfd6fcb434a8615e7f6ca5274ce8e7d467ba4276243d91daff1d`，与本地相同。

同一批12个新状态，旧范围允许3/12、新范围12/12；三档每模型4/4求解通过，总计36/36独立可行新候选，全部选择worker候选。23次CPU超时、11次迭代上限、1次成功收敛、1次可接受精度；保留原退出状态，不把超时可行改写成收敛。NumPy/CasADi最大差异3.269e-8以内。

## 核验与封存

- 本地核心109项通过，补充支持/求解5项及矩阵6项通过；彼此有重叠，不相加。服务器109项通过、1项打包测试未选择（本地通过）。不是全仓库全绿声明。
- 本地24条原始复验通过，无拟合预测复算与服务器最大指标差异：验证1.252e-13、测试4.655e-14。见`local/pullback-validation.json`。
- 308个回传文件全部哈希核验通过，见`server/evidence-inventory.json`和`local/archive-validation.json`。
- 完整归档`server-evidence.tar.gz` SHA256 `7a6ff3b7737a8664ae3947d3bd220cfd0b1963e9d87e6f4ea655d033e9d24375`。
- 757文件源码清单`release-r1/manifest.json` SHA256 `82ad974f920e8e4a668d675802b4cecaff5bb1fe4a59ef743a9d101de62c9b45`；源码包SHA256 `65c0e24d801ffc11456191968556834dd69611f03bc5e5a9c015d737a003ef49`。代码提交`c3d7159`与`8562c24`。
- 冻结模型仍为v87 SHA256 `5857a0e8d09cd04e33112b457b6a60f8b4147f3819815634edb6149ac95e137e`，没有训练、测试选择或隐藏扰动输入。
- 服务器目录`/root/shared-nvme/agentic-auv/workspaces/matrix-v88-20260929`，本任务所有worker/IO线程/进程组已停止，GPU恢复1MiB。服务器保持开启。

Git收录代码、协议、报告、范围、全窗口结果、求解结果、验收/退出回执与哈希清单；大型原始trace、源包和完整归档保留本地及服务器原路径，不随Git自动恢复。旧v86/v87数据与负结果均保留。`summary.json`汇总所有固定比较格，完整原始报告位于`server/validation.json`、`server/test.json`、`server/solver.json`。本轮没有实物实验、闭环收益或实时性结论。

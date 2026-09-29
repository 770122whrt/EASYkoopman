# 实验与证据

实验版本用于标识冻结数据与协议；生产代码只有一套。三个模型使用相同任务、状态、命令链与约束。

| 实验 | 协议 | 结果 | 主要结论 |
|---|---|---|---|
| v86：初轮20%扰动 | [配置](phase9/v86/protocol.json) / [说明](phase9/v86/protocol.md) | [报告](phase9/v86/report.md) | 扫频物理6/6、Koopman3/6、结合5/6；负结果保留 |
| v87：扩大20%训练 | [配置](phase9/v87/protocol.json) / [说明](phase9/v87/protocol.md) | [报告](phase9/v87/report.md) | 新测试物理12/16、Koopman4/16、结合16/16；旧范围求解各1/4 |
| v88：0%/10%/30% | [配置](phase9/v88/protocol.json) / [说明](phase9/v88/protocol.md) | [报告](phase9/v88/report.md) | 30%结合更准，0%/10%物理更准；无重新训练，无闭环 |

每个实验目录保留完整预测 `validation.json`、`test.json` 和 `solver.json`，不只收录获胜结果。v88每档16窗口来自4条独立轨迹，不能算成16条独立实验。

## 泛化到什么程度

结合模型在20%阻力数据上离线训练，冻结后用于同一base构型、同一种二次阻力形式的新强度和新轨迹。30%测试的z/姿态总体误差降低53.31%/58.91%，支持这个有限范围的预测泛化。0%/10%下物理更准，所以不能说结合在任意扰动下普遍更好。

未证明：不同扰动形式、未见构型、长时间稳定、实际闭环收益、实时性、硬件及Agent增量。纯完整提升Koopman仍未通过整体预测门限；旧逐步重提升模型的局部闭环收益不算本模型成功。

## 当前冻结工件

[artifacts/](artifacts/) 保存唯一当前物理参数 `physical.json`、v87学习模型 `model.json`、v88共同支持范围 `support.json`。三者字节与实验原文件完全一致。0%/10%/30%评估没有再次拟合或按测试结果调整。

## 原始材料和历史恢复

原始轨迹、失败日志、源码包集中于本地 `results/history/docs/evidence/`；更早结果位于 `results/history/source/results/`。完整搬移清单为本地 `results/history/archive-inventory.json`。历史记录中的路径、哈希和schema不改写；复算用原源码归档验证采集身份，另记当前分析代码身份。

整理前已提交内容可从 [7bbbbef 快照](https://github.com/770122whrt/EASYkoopman/tree/7bbbbef) 恢复，未提交的原始大文件保留本地，不能声称全都已上传Git。原v86/v87/v88的源码和服务器证据压缩包均在该提交中。

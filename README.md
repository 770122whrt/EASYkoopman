# EASYkoopman

基于 EasyUUV / Isaac 的完整提升 Koopman 预测与共同 MPC 控制研究。当前比较冻结物理、完整提升 Koopman、物理＋Koopman 三个模型；自进化和 Agent 尚未实施。

当前结论：在 20% 附加二次阻力上训练后，结合模型在新的 30% 阻力轨迹上，z/姿态预测误差比冻结物理降低 **53.31% / 58.91%**；0% 和 10% 时物理更准。纯 Koopman 未通过整体预测门限，本轮没有进入闭环。这是同构型、同扰动形式下的有限预测泛化证据。

| 目录 | 内容 |
|---|---|
| `easyuuv_nc/` | 唯一仿真环境、机械构型、控制接入与 USD 资产 |
| `koopman/` | 物理/提升预测、执行器记忆、共同 MPC、独立候选检查 |
| `workflows/` | 采集、验收、训练、预测评估、求解验证与源码打包 |
| `tests/` | 当前契约、冻结数值对照和边界测试 |
| `experiments/` | 协议、冻结模型、正负结果与整理验证 |
| `docs/` | 当前运行说明、控制合同、目录整理记录 |
| `.planning/` | 研究目标、当前状态及阶段历史 |
| `results/`（本地忽略） | 集中存放原始轨迹、日志、历史源码包与旧资料 |

- [运行与复算](docs/runbook.md)
- [实验结果与泛化边界](experiments/README.md)
- [控制链合同](docs/control-contract.md)
- [目录整理与恢复](docs/repository-layout.md)
- [项目目标](.planning/PROJECT.md)与[当前状态](.planning/STATE.md)

当前使用 Isaac Sim 5.0 / Isaac Lab 2.2.1，主服务器为 `suanliyun-agentic-AUV`。本地测试不依赖 Isaac，但不证明仿真运行或闭环效果。实验工作流从本仓库或经过核验的源码包运行；`pip install -e .` 安装环境包。

旧实现可从 Git 提交 `7bbbbef` 恢复。`easyuuv_v2-main/` 为本地参考，始终忽略，不提交。实验编号只标识冻结协议与证据，不再维护多套版本化生产代码。

## 上游来源

仿真基于 [EasyUUV](https://github.com/360ZMEM/EasyUUV-Isaac-Simulation) 与 [warplab Isaac AUV](https://github.com/warplab/isaac-auv-env)。保留原项目 LICENSE；上游部署与论文引用原文见 [整理前 README](https://github.com/770122whrt/EASYkoopman/blob/7bbbbef/README.md)。上游硬件成果不代表本项目已完成硬件验证。

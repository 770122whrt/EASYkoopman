# 算力云环境与连续MPC迁移状态

2026-09-22。结论：`suanliyun-agentic-AUV` 适合作为后续主要开发/计算环境，已建立独立代码快照；不等于新MPC已实现、旧实验已复现或30Hz已合格。主线见[09-04计划](../.planning/phases/09-configuration-aware-koopman-mpc/09-04-PLAN.md)。

## 本轮实际检查

通过SSH密钥实际连接 `root@219.146.211.42:25048`，别名 `suanliyun-agentic-AUV`。旧 `agentic-AUV:31348` 本轮未连接，保留历史用途；不会在两台服务器之间静默切换实验。

| 项目 | 实测或核验结果 |
|---|---|
| GPU | RTX4090，驱动580.105.08，可见显存23028MiB |
| 容器配额 | CPU 10核、内存60GiB；宿主机128逻辑CPU/503GiB不能作实例额度 |
| 存储 | 系统盘约30GiB；`/root/shared-nvme` 为50GiB **NFS**，检查时剩余约29.7GiB |
| Isaac环境 | Python3.11.13，IsaacSim5.0.0，IsaacLab源码发布2.2.1；Python包内部版本0.45.9单独记录 |
| 研究解释器 | `/root/shared-nvme/agentic-auv/runtime/bin/python` |
| 研究依赖 | NumPy1.26.4、Numba0.61.2、llvmlite0.44.0、SciPy1.15.3 |
| 优化依赖 | OSQP0.6.7.post3已有；CasADi尚未安装。现有模型不能仅因OSQP可用就直接当作QP |
| 环境限制 | 研究环境相对Isaac元数据有NumPy/Numba/llvmlite三项已知冲突；实际smoke是限定运行证据，不称依赖完全一致 |

证据：[只读环境审计](evidence/phase9/suanliyun-v75-20260922/environment-audit.json)。未修改SSH配置、原Isaac环境或依赖；本轮未新增物理实验、训练或模型拟合。

## 已有部署证据与边界

远端已存在 `/root/shared-nvme/agentic-auv/deployments/auv-smoke-20260922-01`。本轮读取其原始验收及pytest XML，核实65项通过、0跳过，base完成32控制区间/64物理子步并正常退出。它是已有的部署smoke，本轮没有重新运行这些测试或仿真。

该smoke使用 `authored_static_v1`、`direct_pre_tam_v24` 与 `local_cuboid` 地面，60Hz控制/120Hz物理；没有运行MPC worker。它不等于30Hz闭环收益、八构型稳定性或v73重现；新研究协议应固定场景，在同环境重新配对，避免把地面/依赖差异算成算法收益。

原部署624个代码/资产文件逐项核验远端哈希，并与本地当前工作树比较，均一致。快照包含既有未提交代码，不等同于Git HEAD。新环境根README中的“公网密钥尚未打通”已被本轮实际BatchMode密钥连接事实更新，但本轮不改写原环境记录。

## 第一批迁移已完成

- 新开发目录：`/root/shared-nvme/agentic-auv/workspaces/continuous-mpc-v75-20260922`。
- 从核验后的原部署复制624个源文件/资产，79,323,935字节，逐文件校验；未覆盖原smoke目录。
- 这是工作树快照，**不是Git checkout**。当前本地为规划编辑源，远端用于开发验证；在确定Git同步方式前不同时编辑两端同一文件。
- 当前入口文档单独同步到该目录；冻结模型、fit数据和历史实验大包尚未迁移。既有本地证据仍为结果依据，下一批只迁移离线原型所需模型及数据并核验来源。
- `MIGRATION_SOURCE_MANIFEST.json`、`MIGRATION_SEED.json` 记录源与复制范围；本地[复制记录](evidence/phase9/suanliyun-v75-20260922/migration-seed.json)与[源清单](evidence/phase9/suanliyun-v75-20260922/prior-deployment-source-manifest.json)可复核。

进入环境：

```bash
ssh suanliyun-agentic-AUV
source /root/shared-nvme/agentic-auv/activate.sh
cd /root/shared-nvme/agentic-auv/workspaces/continuous-mpc-v75-20260922
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
python --version
```

## 新开发快照验证

本轮在新目录使用研究解释器运行 `test_bounded_mpc_v44.py`、`test_inexact_tracking_v66.py`、`test_rate30_v67.py`，**72 passed，退出0**。这是实际新主机上的CPU合同测试，不包含Isaac，也未实现连续优化器或修复v74缺陷；原测试通过不代表已覆盖并修好该缺陷。[日志](evidence/phase9/suanliyun-v75-20260922/cpu-checks/pytest.log)、[退出与范围](evidence/phase9/suanliyun-v75-20260922/cpu-checks/result.json)。

## 后续顺序

1. 迁移所需冻结模型/fit子集与来源记录；不会默认复制全部历史结果。
2. 为连续优化原型准备隔离开发依赖，保持现有Isaac基础环境与研究运行环境可复现；CasADi等版本在实际实现时锁定。
3. 建立模型/执行器的可微求解表达，先通过同输入预测等价及精确约束复核，再讨论求解性能。
4. 使用独立输出目录作项目级预检和新闭环对照；沿用旧支持域与硬约束，不复用v73停止队列的剩余名额。

NFS不应被当作低延迟本地盘；如启动或日志I/O成为瓶颈，先计时，再把临时缓存/热路径放到容量受控的本地盘，原始结果回写并校验。GPU适合Isaac仿真，MPC求解主要先评估CPU；换4090并不自动保证完整控制周期达标。

# v58 真实接口短预检：base 初始化接口失败，已停止

2026-09-20，端点 `root@183.147.142.40:31348`。用户批准原 v58 和隔离环境修订后，已执行一次真实服务器预检。结果为 **stopped_runtime_no_go**：只尝试 base，后续七构型未启动；没有训练、重新拟合或自动重试。它不是 Koopman 控制性能的负结果，因为尚未发出第一条受控命令。

## 已完成及证据

隔离环境 `/root/EASYkoopman-phase9-runtime-env-v58` 准备和验收耗时 **16.57 秒**，使用 NumPy 1.26.4、Numba 0.61.2、llvmlite 0.44.0。实际导入路径、子进程版本、Numba 编译、Torch/CUDA 检查通过；原三个依赖的 **2,965 个文件**在安装后及预检后哈希未变，IsaacLab 补丁保持。环境占用约 235 MiB，未改原 conda 环境。

冻结 release `8a08093a6f07d1630691d4aa5d9871137e1dd9bab116cdbba49404628bf4a7a3` 在两端核验一致。新运行目录为 `/root/EASYkoopman-phase9-runtime-v58-20260920`；没有覆盖旧 Phase8.4 或修改冻结模型。服务器环境检查和真实 Linux 超时/孤儿进程清理探针通过。

阶段耗时 **22.76 秒**，外层包含 check-only 的记录为 **27 秒**。base collector 原生退出 0，validator 退出 1，阶段退出 1；接受病例为 **0/8**。已有真实 reset 快照，但记录的受控区间和受控物理子步均为 **0**；reset/初始化的物理动作不冒充 MPC 执行。

18 个结果/日志/授权文件已拉回并逐项核对 SHA256。相关进程组已清理，结束后未发现该实验 worker/collector/validator 残留。本地运行包及本次证据约 105 MiB，远端研究包约 80 MiB，加独立环境及报告预留，两端约 420 MiB，低于修订后的 1 GiB；各分项也在原对应上限内。

## 失败定位

第一处异常发生在 `bind_runtime -> check_runtime_context`，报 `runtime_context:shape_or_finite`。

| 字段 | 真实 reset 回读 | v57 验收及本地 fixture 的假设 |
|---|---|---|
| `thruster_dynamics_time_constant_s` | 单环境向量 `(1,)`，约 `[0.05]` | 按每推进器展开 `(1,8)` |
| `drag_multiplier` | 单环境向量 `(1,)`，`[1.0]` | 二维 `(1,1)` |

生产 telemetry 本来就输出这两个单环境量，见 [easyuuv_env.py](../easyuuv_nc/env/easyuuv_env.py:797)。[v57 context 验收](../workflows/runtime_episode_v57.py:27)与[测试 fixture](../tests/test_runtime_episode_v57.py:15)却共享了错误的形状假设，因此旧本地回归没有发现这个接口问题。

对原始快照做只读诊断：不转换、仅转换 tau、仅转换 drag 均拒绝；只在副本中同时转换两项表示，原有质量/惯量/重力/水动力数值和容差全部通过。这支持“接口表示不匹配”的定位，不支持篡改原始快照或把原运行改记为通过。下一修复应按真实 telemetry 合同检验单环境量，并保留维度、有限值和机械参数拒绝门；不能盲目 squeeze 任意数组。

第二处是证据落盘问题：`trace-before-cleanup.json` 保留了上述异常，但应用结束后没有最终 `trace.json`，导致 validator 报文件缺失。已安装 SimulationApp 默认 `fast_shutdown=True`，关闭路径调用原生 shutdown；这与 collector 原生退出 0、Python 后续写报告未完成的现象一致，但当前没有逐资源关闭标记，尚不能确定精确退出边界。修复需保留关闭前后记录、正常/异常退出和进程组清理的独立证据；不能把缺失报告的原生退出 0 当成功。

外层传输还有独立包装问题：PowerShell 提供给 Bash 的最后一行带 CR，导致最终 `exit` 解析失败、SSH 包装退出 2。远端原始终态明确记录阶段退出 1，两者均保留；这不改变更早发生的 context 和报告缺失问题。下一次运行入口应以明确 UTF-8/LF 字节传输，不能覆盖本次退出记录。

## 下一步与结论边界

本次按“失败即停、无自动重试”结束，现有服务器执行授权的这一次尝试已使用。优先在本地以真实 reset 记录补充回归，版本化修复单环境参数形状合同和关闭报告，再准备具体修复版的有界复测；不改本次冻结源码或结论，不新增训练、不扩大模型字典、不提前推进自适应/Agent。

此次确认了隔离环境、真实 App 启动/reset、来源检查及进程清理可执行；尚未证明任何 MPC 控制周期、计划激活、跟踪收益或跨构型控制能力。Phase8.4 预测结论保持，MPC2-01..04 均不关闭。

证据入口：[独立复核](evidence/phase9/server-preflight-v58-20260920/review.json)、[原始阶段结果](evidence/phase9/server-preflight-v58-20260920/remote/runtime-stage-v58/stage-result.json)、[清理前真实快照](evidence/phase9/server-preflight-v58-20260920/remote/results/p9-v57-base/trace-before-cleanup.json)、[形状反事实诊断](evidence/phase9/server-preflight-v58-20260920/context-shape-diagnostic.json)、[环境验收](evidence/phase9/server-preflight-v58-20260920/environment-records/validation.json)。

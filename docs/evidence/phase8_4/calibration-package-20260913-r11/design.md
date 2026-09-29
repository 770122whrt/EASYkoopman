# Phase8.4-06：八构型工作点与激励校准

2026-09-13。用户明确继续“适配+校准测试”。承接[接触/高度诊断](phase8_4_free_water_runtime_results.md)，本轮使用新的v27源码和r10独立服务器目录；旧r8/e2/r9结果保持冻结。全部新病例为`calibration`，不属于fit、validation或test，不产生模型拟合或Phase9 handoff。

## 校准设计

按当前目录质量、惯量、体积、浮心偏置和实际pre-TAM→PWM→稳态转速→六维wrench计算控制工作点。静态目标同时抵消重浮力差及恢复力矩，不能只抵消Fz。通过[实际控制源码](../workflows/control_seam_v23.py)构造稳态曲线；48步单调PWM逆变换初始化、最多64步确定性Newton迭代并保留不收敛结果。没有读取旧validation、拟合轨迹或改变plant参数。

静态误差以质量/惯量归一化：线加速度各轴≤0.025m/s²、角加速度各轴≤0.1rad/s²；原始PWM余量至少0.05，virtual control绝对值≤0.95。欠驱动uuv4/uuv4_angled禁止yaw目标。base微小负浮力在PWM死区内，选择等价零输入并如实保留约−0.00925m/s²残差，不能称精确悬停。

纯升沉只能处理heavy的静态负浮力，不能处理asymmetric约[+11.13,−11.13,0]Nm恢复力矩。本轮先试完整四维恒定偏置。闭环采集和短段设计是后续可比较方案；恒定输入若不能从冷启动保持合适状态，应由本轮明确拒绝，不隐式热启动或修改浮心。

原拟定横滚2rad/s²在long_body的小惯量/PWM死区附近未通过源码逆变换；运行任何GPU病例前，固定源码检查2/3/4三个值，选定共同横滚4rad/s²。最终脉冲目标为roll/pitch/yaw/heave的±[4,2,1,0.5]rad/s²、rad/s²、rad/s²、m/s²，在静态抵消wrench之上添加。每个目标均重新核对实际六维wrench与非目标轴残差。这是已知控制曲线的校准，不是学习模型参数搜索；同一物理目标并不保证运动范围或输入信息量相同。

## 固定病例与资源

八构型顺序：base、long_body、heavy_moderate、asymmetric、uuv6、uuv6_angled、uuv4、uuv4_angled。

| 阶段 | 种子 | 每构型控制区间 | 命令 | 继续门 |
|---|---|---:|---|---|
| trim | 8510–8517 | 128 | 从执行器零状态开始施加恒定配平命令 | 全段合同与尾段运动检查 |
| excitation | 8520–8527 | 256 | 64区间显式配平前段；四轴各48区间，12正/12配平/12负/12配平，正负先后由种子固定 | 仅对应构型trim获准后执行 |

欠驱动yaw块保留为配平命令，明确记录mask；不以额外激励补足。每条都是新原生冷启动，准备前段全部保留，状态及推进器历史从零因果重建。没有中途reset、删行拼接或真值回灌执行器估计。

上限16个原生进程、3,072控制区间、6,144物理子步；采集累计40分钟，每进程5分钟，病例边界检查新增transfer目录1GiB，CPU静态/拉回检查15分钟。预约未归还、失败与超时均计入账本，病例不重试。未通过trim的构型跳过其excitation并保留原因。未知运行时错误或身份/时钟不一致中止批次，不能当作普通校准失败跳过。

## 运行范围与停止门

原质量/惯量/volume/COB/TAM/地面和物理更新不变；单环境、无DR/噪声/流场，初始z=5.5m、单位四元数、零船体速度及零执行器状态。direct_pre_tam_v24、authored_static_v1、declared_v1、episode_local_v1；control dt=1/60s，physics dt=1/120s，2子步。

逐子步检查已有接触/几何合同：法向接触力严格零、船体净空≥0.1m、actor z≥1m、速度平衡残差≤0.001m/s，完整时钟、源文件、机械参数、命令/PWM/转速/wrench链与连续性。此外限制船体线速度范数≤1.5m/s、角速度范数≤3rad/s、倾角≤60°、水平距初始点≤2m、垂直位移≤2m。超限先保留原始末行再停止。

trim尾部64物理子步的最大线速度≤0.5m/s、角速度≤0.5rad/s、倾角≤30°才允许该构型进入excitation。该门只声明有限时段的有界运动，不是精确悬停、512区间适用性或辨识充分性。完整trace的语义验收、原生exit、失败末行解释及模型角色分开记录。

## 实现与验收入口

- [静态校准与命令](../workflows/workpoint_v27.py)、[采集器](../workflows/collect_calibration_v27.py)、[运行范围检查](../workflows/calibration_trace_v27.py)、[独立验收器](../workflows/validate_calibration_v27.py)。
- [两阶段串行入口](../workflows/run_calibration_v27.py)、[服务器脚本](../scripts/phase8_4_calibration_server.sh)。
- 按[既有运行时/源码/拉回惯例](phase8_4_formal_runbook.md)完成本地与独立clone测试、源码bundle/hash、锁定IsaacSim5.0/IsaacLab2.2.1、原始文件inventory及拉回重验。旧r9接触观测等价试验可支持读取接口；新增范围检查仅读取已记录数据，没有新增step/forward/setter。

通过本轮后仍需决定新fit/validation的角色、初始状态、持续时间与激励覆盖。实际Koopman收益与已知物理/采集修补收益分别检验，旧24test保持未采。

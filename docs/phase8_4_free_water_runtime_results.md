# Phase8.4-06：接触接口、数据适用条件与下一步

2026-09-13。用户开启服务器并确认“先数据适配，再算法”。本轮完成接触/几何接口、6条真实GPU短诊断及逐阶段本地拉回验收；**heavy的触底机制在新对照中直接确认，新的高高度短段通过自由水域必要检查。尚未训练或验证新Koopman模型。**

后续[八构型工作点校准](phase8_4_workpoint_calibration_results.md)已完成限定测试：七构型短段通过，asymmetric暴露状态相关恢复力矩与启动问题。下文保留r9时点结果与当时的下一步依据。

## 这次解决了什么

1. 原链路只记录推进器、水动力和状态，没有直接接触读数。现在逐物理子步读取真实法向接触力，同时记录刚体路径、采样时钟、实际碰撞形状和离地距离，补齐求解器作用的观测缺口。
2. 原采集只检查极端状态上限，没有拒绝接触数据。新接缝在发现接触、净空不足、未解释冲量或不一致的采样身份时保留原始行并停止。低高度对照显式使用诊断模式；其不合格行不会变成训练样本。
3. 固定起始高度1.5m并不能给各构型提供相同工作条件。提高初始高度能够避免这次短段触底，但重构型的负浮力仍在；下一轮必须同时校准初始条件、持续时间和实际激励范围。

这不是“原参数还都是base”的重复问题：当前实际质量和惯量已继承且通过读回/输入重建检查。heavy保留原目录中的45.402kg及未翻倍的volume，因而具有约222.91N负浮力。没有为得到好结果去改体积或删除地面。

## 实际接口与物理场景

[运行时接口](../workflows/free_water_runtime_v26.py)确认唯一刚体`/World/envs/env_0/Robot/base_link`的碰撞体是1m×1m×0.5m盒体；地面碰撞prim为`/World/ground/GroundPlane/CollisionPlane`，水平z=0。离地距离由USD碰撞体尺寸、完整局部变换及每步真实后端姿态计算，不依赖可视网格包围盒。

只添加`physxContactReport:threshold=0`，未使用会同时改休眠阈值的通用传感器激活函数。实际创建后的刚体物理属性在base on/off间除报告属性外一致。场景读回的线性阻尼为0、角阻尼为0.05000000074505806；这是本轮实际场景属性读回，不把此前猜测默认值作为证据，也不等同于独立验证全部离散求解器内部状态。

法向接触读数由当前PhysX contact view直接获得，采样时间与子步后端时间一致。法向力不包含完整切向摩擦，因此下面的力学解释严格限于垂直分量。[Isaac Lab2.2.1的对应定义](https://raw.githubusercontent.com/isaac-sim/IsaacLab/v2.2.1/source/isaaclab/isaaclab/sensors/contact_sensor/contact_sensor_data.py)。

新增[采集器](../workflows/free_water_microtrace_v26.py)、[验收器](../workflows/validate_free_water_v26.py)、[串行入口](../workflows/run_free_water_stage_v26.py)及[服务器脚本](../scripts/phase8_4_free_water_server.sh)。原v25采集器和正式结果没有被原地替换。

## 六条真实诊断的结果

输入仍为direct pre-TAM，control dt=1/60s、physics dt=1/120s、每区间2子步。单环境、无DR/流场/噪声，authored_static_v1初始化、declared_v1惯量和episode_local_v1重置。命令幅度[0.04,0.04,0.08,0.20]，种子8500/8501/8502；具体清单与源码身份见[冻结请求](evidence/phase8_4/free-water-package-20260913-r9/request.json)。

| 对照 | 控制区间 | 直接接触子步 | 最大速度平衡残差 | 结论 |
|---|---:|---:|---:|---|
| base，5.5m，接触观测off/on | 32×2 | off未测；on为0 | 4.73×10⁻⁸m/s | 64子步状态逐分量完全一致 |
| heavy，1.5m / 5.5m | 128×2 | 99 / 0 | 0.69625 / 7.35×10⁻⁸m/s | 提高高度后本短段无接触/异常冲量 |
| asymmetric，1.5m / 5.5m | 256×2 | 0 / 0 | 两者3.73×10⁻⁸m/s | 新种子未重现旧接触，不能声称该旧事件已复现 |

heavy低高度首次接触发生在物理索引150，约1.25秒。此前150子步的姿态和体坐标速度与高高度轨迹完全一致，高度差只产生约1.55×10⁻⁶m的浮点误差。高高度轨迹最低实际碰撞净空3.12890m。

独立标准库脚本没有调用生产的旋转/净空/物理平衡函数，重新计算盒体支持距离及垂直力平衡。heavy低高度的未解释垂直速度增量最大0.6962466m/s；加入实测法向接触力后，最大残差降至**1.8710×10⁻⁷m/s**。这直接支持“地面接触造成该短对照中的异常垂直增量”，不是模型拟合指标或预测改善。[独立核对](evidence/phase8_4/server-free-water-20260913-r9/closeout/independent-audit.json)。

asymmetric低高度虽无接触，但36个子步触发预设actor z≥1m的保守运行限制；最低船体净空仍有0.23656m。应称“运行限制拒绝”，不能把它们计为碰撞。下一协议可在明确版本变更后以已验证几何净空制定运行范围，本轮门槛保持不变。

## 下一批数据需要怎样适配

仅抬高起点不够。新增[固定八构型纯升沉源码检查](evidence/phase8_4/server-free-water-20260913-r9/closeout/steady-heave-screen.json)给出：

- heavy水平静止时需约222.907N向上推力；纯升沉命令+0.2的稳态推力约42.206N，显著不足。纯升沉命令约+0.5352才接近这项静态平衡。这不是实际悬停验证，也未包含姿态恢复力矩和推进器启动过程。
- uuv6同样+0.2命令只有约4.338N，而legacy混控构型约42.206N。相同dimensionless幅度并不产生相同物理输入或可比运动范围。
- base的微小负浮力约0.210N处在公共纯升沉PWM死区附近；这项一维恒定输入检查没有得到精确平衡点。不等于该平台不可控，暂态、脉冲和闭环是不同问题。

下一步按[06计划](../.planning/phases/08.4-conditional-identification-experiment/08.4-06-PLAN.md)依次推进：

1. 先制定八构型工作点/激励校准：重力—浮力差、恢复力矩、可控轴、PWM死区/饱和、允许的实际速度范围。采用可解释的构型参数与因果命令设计，不根据旧validation调参。
2. 设计新角色/种子数据，覆盖冷启动或显式可重建的准备过程；不偷偷把推进器预热后当作零初始状态。提高高度、缩短段长、平衡附近激励各有作用，需要明确对应问题。现有z边界还限制相对初始高度位移7m，不能只增高起点后盲跑512区间。
3. 自由水域、时钟、物理量、初始状态、因果执行器和完整连续性门通过后，才建立新fit/validation矩阵。不得把诊断角色的6条直接改名训练，或删除碰撞行后拼成连续episode。
4. 再处理状态耦合、实际角阻尼/离散位姿时序和范围外推，比较已知物理基线、较小字典与受约束Koopman候选；随后用独立新数据验证。不能把物理公式带来的改善算成新增Koopman贡献。

这批短诊断只覆盖base/heavy/asymmetric，未完成八构型新数据集，更没有证明long_body外推问题或Koopman误差已修复。旧4条fit的接触解释仍基于历史间接证据；本轮直接传感器确认的是新heavy对照。Phase9及后续Agentic评估仍待合格模型handoff。

## 可复现状态

- 6个采集进程均native exit0；共832控制区间、1,664物理子步。累计原生采集103.747秒，低于30分钟上限。没有新增模型拟合，没有打开旧24test。
- 三阶段分别拉回44文件，共132个归档条目，含重复的共享源码/运行时记录；不能称为132个互不重复文件。[on/off验收](evidence/phase8_4/server-free-water-20260913-r9/on-off/acceptance.json)、[heavy验收](evidence/phase8_4/server-free-water-20260913-r9/heavy/acceptance.json)、[asymmetric验收](evidence/phase8_4/server-free-water-20260913-r9/asymmetric/acceptance.json)。
- 采集/验收源码快照`8a73485b33306eb7fe420b87dcfe08df7323b4b2`，407文件；本地/独立克隆各320相关CPU测试。[源码包](evidence/phase8_4/free-water-package-20260913-r9/package.json)、[测试](evidence/phase8_4/free-water-package-20260913-r9/test-results.json)。
- 原仓库HEAD仍为782c15a，没有commit/push。r8/e2和旧负结果保持冻结；本轮只确认有界数据适用条件及接口，不产生model handoff。
- 收尾复核407个源码文件、145个正式结果文件、35+40个旧pilot文件、223个r8原始证据文件及三个新归档均无哈希变化；109个规划/报告本地链接可解析。[完整性核对](evidence/phase8_4/server-free-water-20260913-r9/closeout/integrity.json)。

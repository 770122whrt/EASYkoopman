# Phase8.3 初始化修复：固定构型首步使用正确机械参数

2026-09-12。**已定位并修复本次冷启动/热重置不一致：在当前锁定GPU运行时，创建刚体后才设置质量、惯量，会出现getter已更新而冷启动首步力学响应仍对应原资产参数的现象。新静态初始化模式在PhysX创建刚体前写入参数，四组冷/热对照全部通过。** 这关闭了已复现的初始化反例；尚未证明模型预测接近persistence。

## 1. 原因与证据

uuv6声明质量29.7kg，原USD资产质量22.799999kg。旧初始化先以资产创建刚体，随后通过tensor API修改质量与惯量。只读探针显示：cold/warm初始原始位姿、COM速度、质量及逆质量、惯量及逆惯量、局部COM和重力开关均相同；原始PhysX位姿/速度与IsaacLab缓存逐项差0。因此，缓存显示归零但实际速度未归零这一解释不支持当前反例。

两边首子步施加的合力同为`[-0.0077856337,0,293.492218]N`，dt=1/120s，初始姿态单位四元数、速度0。在本次无接触、无额外扰动的首步条件下，由`m_eff=Fz/(Δvz/dt+9.81)`得到：

| 情况 | getter质量kg | 首步响应反推质量kg | 首步世界vz m/s |
|---|---:|---:|---:|
| 旧初始化cold | 29.699999 | 22.799999 | 0.0255205501 |
| 旧初始化warm | 29.699999 | 29.6999995 | 0.0005991085 |
| 修复初始化cold | 29.699999 | 29.6999995 | 0.0005991085 |
| 修复初始化warm | 29.699999 | 29.6999995 | 0.0005991085 |

独立x轴首步力/加速度也分别反推出22.800000及29.699997kg，支持同一机械参数时序解释。新模式的live-stage读回确认旧值来自原USD资产；源USD文件没有修改。旧模式首步速度差0.02492144m/s，32控制区间后仍可产生约0.01250124m最大深度差。

**证据等级：** 初始化写入时序与首步错误响应之间的因果关系为CONFIRMED（同源码版本化干预，命令不变，反例消失）；把问题精确归到PhysX内部某个GPU缓冲/内核仍为UNCERTAIN，没有内部C++/GPU追踪。所有getter一致不等于所有未暴露求解器状态一致。这个首步机械错误对Phase8.2总预测误差的贡献比例仍未测量。

实际安装的Physics Tensor API中`flush()`明确标记为已弃用且无效，因此没有把它用作同步修复。帧/单位依据安装源码及[NVIDIA 107.3 API](https://docs.omniverse.nvidia.com/kit/docs/omni_physics/107.3/extensions/runtime/source/omni.physics.tensors/docs/api/python.html)核对；已保留实际安装源码副本。

## 2. 修复与验证边界

新增显式`physics_initialization_mode=authored_static_v1`，由`initial_embodiment_type`选择同一份构型目录：在live USD刚体spawn后、克隆及PhysX初始化前设置mass、diagonal inertia、principal axes；构造结束时应用对应的完整控制/推进器配置。没有加入额外物理预热、丢弃首步或改变控制频率。旧`legacy`默认保持，冻结实验可以继续复核。

使用时必须同时选择`inertia_sync_mode=declared_v1`与已验证的`control_history_reset_mode=episode_local_v1`。新静态模式拒绝运行中切换到另一个构型及domain randomization；动态机械参数切换是单独未验证的问题。首步正确性需要检查响应，不能只有setter/getter一致。

| 冷/热对照 | 初态/历史/执行器/命令匹配 | 64个observed物理子步的state11最大分量差 |
|---|---|---:|
| base / seed8201 | 通过 | 0 |
| uuv6 / seed8201 | 通过 | 0 |
| uuv4 / seed8201 | 通过 | 0 |
| uuv6 / seed8202 | 通过 | 0 |

另有新源码legacy与旧源码逐项一致、backend探针on/off逐项一致、修复后的trace on/off逐项一致。修复uuv6 cold的全部observed子步状态也与此前旧初始化warm相同，不仅首行吻合。

本地与独立源码包各210项相关测试通过，耗时10.84s/10.77s。新增13次真实GPU运行共576控制区间：backend诊断128、初始化修复对照448；加上上一批累计1056区间、26个进程。全部原生退出0，105个归档文件逐项SHA/字节数核验通过，1088条新增有日志物理子步通过时序/数值验收。32个trace-off控制区间没有子步日志，未虚计为已观测。

覆盖范围是单环境、固定构型、无DR/噪声/波浪、PRBS幅值0.1、hold4、32个observed控制区间；warm另记录32个准备区间并reset。没有新模型fit，也没有60/512步或真实闭环性能结论。

## 3. 下一步怎么走

初始化应纳入**重置与数据合同**：物理初态、实际机械参数、控制器历史、执行器初值以及reset边界都需明确。固定质量/惯量属于平台上下文；old_actions、积分/滤波状态、N维转速才是随时间变化的记忆状态。当前反例优先通过正确初始化消除，不需要给模型添加用于吸收这一软件缺陷的cold/warm类别。

1. 8.3-02先审查修复后覆盖范围。剩余46个旧plant矩阵病例保持未执行，不再作为默认下一步；必要的新覆盖要用修复后的合同与新run-id。动态换构型/DR与其他未测试构型明确留作缺口。
2. 8.3-03在已匹配的修复轨迹上比较有序两子步输入、末值输入、当前4D proxy与命令驱动的N维执行器状态；明确哪些未来控制可由当前边界因果产生。排除错误初始化后再评估模型表征。
3. 8.4的fresh pilot需在接口决定后冻结整段fit/validation与激励覆盖，比较persistence、简单线性及已知运动学加动力学模型。32步诊断不能用来声称60/512步预测性能；新plant不能靠旧数据证明改善。Phase9继续等待合格handoff。

[机器验收](evidence/phase8_3/server-initialization-repair-20260912/acceptance.json)包含每例清单和全部对照；[拉回复核脚本](evidence/phase8_3/server-initialization-repair-20260912/validate-pullback.py.txt)可在项目Python下重验真实原始trace。归档SHA256为`12ca4649829af069dcb39a8b0ce5fcbb66b2f2ee78889ab5f5bcf8ddb4178378`。

新运行目录`/root/EASYkoopman-phase8-3-initialization-20260912`，独立源码快照`a9a6e20f4ac05b183cf28fd4710f5a21478b9d7c`；[源码包](evidence/phase8_3/runtime-package-20260912-r5/package.json)。原仓库仍为no-selection / 782c15a，未commit/push，历史NO_SELECTION和原始证据未修改。服务器/GPU/后续训练授权持续有效，当前没有等待用户授权的动作。

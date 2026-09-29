# Phase8.3真实GPU调查：惯量与固定构型初始化修复

**最新结论：** 2026-09-12T19:10:47+08:00。已完成新增576区间的初始化诊断与修复验收（累计1056）。固定构型冷启动首步使用旧资产参数的问题已由authored_static_v1修复；四组冷/热对照逐子步state11差0，210本地/clone测试及105文件拉回验收通过。当前下一步是修复后的输入/执行器表征与fresh pilot规划。详见[初始化修复](phase8_3_initialization_repair.md)。下方480区间结论是此次定位之前的历史记录，原始反例保留但不再代表修复模式仍失败。

## 以下保留上一批调查记录


2026-09-12。**服务器已连通并完成480个control interval的真实Isaac调查；确认并修复了惯量未写入PhysX的缺陷，同时发现清除控制历史后仍存在cold/warm状态分歧。依据预先声明的停止条件，暂停扩大采样和训练。** 当前没有新训练模型，也没有证明预测已接近persistence。

运行环境是RTX4090（24564MiB）、IsaacSim5.0、IsaacLab2.2.1，锁定release、repo commit及两处既有setup补丁均通过核验。连接恢复时未改动本机网络或服务器sshd；此前公网握手超时的原因仍未确定。

## 1. 原因是什么

### 已确认：声明惯量与真实刚体惯量不一致

环境`apply_embodiment_config`更新了局部`inertia_tensors`，水动力计算和平台描述使用这些值；原实现没有调用PhysX惯量setter。质量有对应写入，因此这不是整个构型配置完全未生效。

实际读回如下（kg·m²）：

| 构型 | 声明惯量 | 原PhysX惯量 | 相对声明误差 |
|---|---|---|---|
| base | [0.370, 0.970, 1.190] | [0.370, 0.970, 1.190] | 0 |
| uuv6 | [0.484076, 1.269063, 1.556892] | [0.370, 0.970, 1.190] | 约−23.57% |
| uuv4 | [0.354989, 0.930646, 1.141721] | [0.370, 0.970, 1.190] | 约+4.23% |

两个变构型在切换后与reset后都保持base惯量，排除了“只有后续reset才覆盖”的单一解释。官方接口定义了刚体惯量的9分量读写与所选索引；本次仅同步项目声明的body对角惯量，并在写入后做读回检查。[NVIDIA Physics Tensor API](https://docs.omniverse.nvidia.com/kit/docs/omni_physics/107.3/extensions/runtime/source/omni.physics.tensors/docs/api/python.html)

这意味着**当前平台物理描述不能直接当作PhysX刚体实际参数**。其对正式Phase8.2失败的贡献比例仍未测量；不能仅凭这一缺陷宣布找到所有模型误差的根因。

### 已确认：子步输入遗漏在真实控制链中存在

真实uuv6/uuv4 PRBS中，两个子步的depth控制最大差约0.046385。将记录的末子步PWM保持两次，与真实按顺序执行的推进器作用相比，body-z推进器力的L1时间积分差约0.026437N·s，占原积分约9.55%。这是对真实命令的执行器重放，不是对艇体施加held-last的仿真反事实。

这也限定了[此前CPU探针](phase8_3_control_seam_findings.md)的100%数字：那个结果只针对单depth、小幅PRBS、很小的分母；真实混合轴PRBS的这个分量约9.55%，不能混用。base本次使用constant、uuv6/uuv4使用PRBS，也不能直接用跨行比值作纯构型排名。

### 新确认：清除控制历史还不足以得到相同reset演化

uuv6已经启用`inertia_sync_mode=declared_v1`和`control_history_reset_mode=episode_local_v1`。cold与warm观察阶段的初始记录state11、执行器转速、old_actions、actions_i、_actions一致；后续raw action、virtual control、PWM和推进器wrench也逐项完全一致。

但首个物理子步后body-z速度分别约为**0.02552055和0.00059911m/s**，首子步传入的合力同为`[-0.0077856, 0, 293.492218]N`。32区间内最大深度差0.01250124m、垂向速度差0.02489668m/s。

因此，“cold/warm差异全部由old_actions导致”已被该反例否定。**相同初始状态目前只指IsaacLab记录属性相同，尚未通过独立PhysX transform/velocity读回证明完整物理状态相同。** 可能涉及状态缓存、参数应用时序、初始化或其他求解器状态，尚不能选择其中一个作为确定原因。前一份惯量对照报告中的`matched_initial_physical_and_actuator_state`字段应按这一更窄口径理解，不能当成完整PhysX状态匹配证明。

## 2. 修了什么，验证到什么程度

新增默认关闭的`inertia_sync_mode=declared_v1`：构型切换和reset参数随机化完成后，将选定环境的声明惯量写入PhysX；检查形状、正值/有限性及后端读回，同时同步水动力用的惯量均值。`legacy`保持原行为，便于冻结结果复现。没有改控制计算频率、增益、TAM、PWM、传感噪声或旧数据。

本地原工作区196项相关测试通过，独立修复源码包重克隆后同196项通过。实际7个修复病例共256区间通过：

- 三种构型在新源码legacy模式下，状态和telemetry与旧源码对应病例逐分量相同。
- base开启惯量修复后，轨迹逐分量相同。
- uuv6/uuv4开启修复后，PhysX惯量与声明一致；uuv6 warm reset后仍一致。
- 相同raw/virtual控制与推进器wrench下，uuv6角速度分量的最大变化约0.250878rad/s。这是**真实动力学变化**，不是模型预测改善。

源身份：原仓库HEAD仍为`782c15a68574bfd923707e499320e7b611e950bd`、分支`no-selection`，未commit/push。两个独立快照提交是`7fd0f3cd28ca1340cef910a4b00f5e439cf69762`（原控制）与`76a39c3cccea122c94023dd170d942c31dc3edad`（opt-in惯量修复）；它们不是原仓库分支提交。

## 3. 为什么本轮没有进入训练

当前仍存在“记录的状态和完整控制序列相同、后续物理状态却不同”的反例。在查清缺失状态/时间边界前扩大拟合，会把采样或初始化问题混入模型误差，无法回答跨构型性能差的原因。增加GPU算力不会消除这个辨识问题。

这批实际仿真为：首批on/off64区间、两个legacy哨兵64区间、惯量修复256区间、reset反证96区间，**合计480区间、13次有界进程**。均使用GPU；并未启动模型拟合、96-episode重采、PPO或正式LOCO。原48-case矩阵只完成2个哨兵，剩余46个明确暂停，不计为已完成。

下一步的优先级已调整为：

1. 在reset返回、第一/第二个physics substep前后，同时读IsaacLab缓存状态与PhysX原始transform/velocity、质量/惯量及可用逆质量；不增加未记录warm-up，不移动控制计算。首先区分“记录不完整”与“同记录下的求解器初始化差异”。
2. 用同一初始化合同的冷/热重置对照验证修复；若必须让物理引擎推进才能应用参数，全部准备步必须记录并从拟合中排除，不能静默丢弃首行。
3. 完成输入序列、因果执行器状态和物理描述的一致性后，再冻结fresh小型辨识pilot。优先比较已知运动学加增量动力学、简单线性与物理条件化共享模型；对分构型、激励家族和多步递推分别比较persistence。不能沿用旧数据来宣称新plant已改善。

用户对服务器/GPU/训练的授权持续有效，后续无需再询问是否可以连接或开始；当前停止来自运行证据和已声明的验收门，未要求用户额外授权。Phase8.3仍未关闭，Phase8.4保持条件性，Phase9无模型交接。

## 4. 可复核证据

| 证据 | 结果与边界 |
|---|---|
| [首次成对验收](evidence/phase8_3/server-first-pair-20260912/acceptance.json) | base/seed8201/constant；2218数值分量差异均0；34文件归档核验 |
| [惯量修复对照](evidence/phase8_3/server-inertia-repair-20260912/acceptance.json) | 7病例256区间；85文件核验；三构型legacy兼容与两个变构型物理修复 |
| [reset反例](evidence/phase8_3/server-reset-counterexample-20260912/acceptance.json) | 额外96区间；91文件核验；清历史后仍存在未解释状态差 |
| [修复源码包](evidence/phase8_3/runtime-package-20260912-r3/package.json) | 363源码文件哈希；本地与重克隆196测试；bundle SHA256绑定 |

各证据目录保留原始trace、日志、原生退出状态、实际加载源码、inventory和完整归档。原始实测不因新的解释而重写；文档与派生字段的口径以本报告的限制为准。

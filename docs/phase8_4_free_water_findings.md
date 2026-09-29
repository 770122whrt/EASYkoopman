# Phase8.4-06：自由水域假设缺口与路线修正

**后续已更新：** [真实接触/高度对照](phase8_4_free_water_runtime_results.md)已完成。新heavy对照直接确认触底力解释垂直异常，三阶段数据已拉回验收；下文保留首次本地检查时的证据边界，其中“真实接口待完成”已由后续报告接替。

2026-09-13。本轮只做本地代码核对、已验收真实日志的离线分析和CPU测试；没有连接服务器、采集新数据或拟合新模型。

**需要修正上一份报告的归因：错误的学习状态增量确实已经复现，但不能据此把剩余问题主要归结为模型结构。训练数据还混入了未被记录为模型输入的物理作用，且与靠近地面高度一致。当前优先修数据适用条件，再修学习结构。** 正式NO_SELECTION及原始验收记录保持原样；原验收通过的是当时声明的源码、机械、控制、时钟和连续性检查，没有自由水域准入检查。

## 1. 新确认的问题

`starting_depth=1.5`实际写入世界坐标z，代表离地高度，并不是向下为正的水深。[场景初始化](../easyuuv_nc/env/easyuuv_env.py)同时生成地面碰撞体；本地cuboid模式顶面为z=0，默认grid模式也创建ground plane。真实加载USD的碰撞尺寸、地面子prim及接触参数仍需服务器读回。

[构型目录](../easyuuv_nc/embodiments.py)中heavy_moderate将质量和惯量翻倍，但没有覆盖volume。已验收fit日志中的实际质量45.402000kg、排水体积0.022747845m³、水密度997kg/m³，浮力只支持22.679601kg，静态重力比浮力多222.906739N。这说明它具有明显负浮力。没有证据表明体积必须随质量翻倍，不能为了让数据好看就改成中性浮力。

原采集器只拒绝非有限状态及超过100的高度/速度分量；它没有检查碰撞、离地距离或未解释冲量。因此，正常退出和旧合同通过不能证明整段轨迹都是自由水域运动。

```text
命令 → 当前构型TAM/PWM → 因果N推进器状态 → 推进器力/力矩
                                          ↓
                          浮力/阻尼 + 重力 + PhysX约束/接触
                                          ↓
                             下一物理子步状态 → 训练目标
```

现在补查的是最后一段的约束/接触作用。旧11维状态和已知推进器输入没有明确表达接触模式及求解器状态。

## 2. 24条fit数据的检查结果

扫描前固定脚本、阈值和24条fit清单；重算已验收归档及每条trace哈希。没有继续扫描validation或打开test，也没有过滤后重新拟合。[检查配方](evidence/phase8_4/state-dynamics-local-20260913/fit-free-water/recipe.json)、[逐条结果](evidence/phase8_4/state-dynamics-local-20260913/fit-free-water/audit.json)、[保存的脚本](evidence/phase8_4/state-dynamics-local-20260913/fit-free-water/audit_fit_free_water_v26.py)。

每个1/120秒子步，用实际后端世界速度、质量、重力、当步外力和当步姿态计算：

`残差 = v_after_world − v_before_world − dt × (R_before × F_external_body / m + g_world)`

残差代表已记录外力不能解释的速度变化，可能来自接触、其他求解器作用或记录错误；它不是直接接触力测量。筛查使用逐分量残差上限0.001m/s、actor世界z下限1m；两者是本轮工程检查值。1m不是实测船体净空，0.001m/s也不是已标定的接触检测阈值。

| fit轨迹 | 1024子步中异常冲量数 | 最低actor z，m | 最大速度残差，m/s |
|---|---:|---:|---:|
| heavy_moderate / PRBS | 856 | 0.249986 | 0.727581 |
| heavy_moderate / multisine | 850 | 0.249569 | 0.674101 |
| heavy_moderate / chirp | 855 | 0.249823 | 1.102511 |
| asymmetric / chirp | 1 | 0.746303 | 0.205255 |
| 其余20条 | 0 | 均高于1m | 最大5.34405×10⁻⁸ |

共24,576个物理子步、2,562个异常冲量子步；全部发生在actor z低于1m时。heavy三条的首次异常分别在第151/161/143个物理索引，即约1.2–1.35秒；它们在1m以上的最大残差均小于6.2×10⁻⁸m/s。asymmetric的异常发生在物理索引443，actor z约0.746m；不同姿态可能使船体在更高actor位置接近地面，所以不能拿0.25m当作通用碰撞高度。

这**强烈支持地面接触混入fit**，但旧日志没有直接接触读数，仍须真实接触与几何读回确认。不能把2,562这个阈值筛查计数说成2,562次独立碰撞。

## 3. 同时保留的模型问题

[最多四段冻结诊断](evidence/phase8_4/state-dynamics-local-20260913/physical-audit.json)确认，解析浮力/阻尼实现与记录的实际外力基本吻合；heavy片段外力误差小于0.00005N，却有约0.89m/s的世界速度突变。long_body、uuv6及angled片段的平移力平衡没有类似缺口。

因此，触底不能独自解释所有误差：heldout-long_body已有的范围外推、错误横滚增量和失稳仍成立；自由水域模型允许错误跨项自由耦合的问题也仍需修复。接触数据对各模型误差贡献多少，目前没有受控实验给出比例。

另一个局部问题是位姿积分时序：现有投影用当前速度推进位姿，非接触片段用真实下一步速度做诊断时更吻合实际位置变化。这是离散时序线索，不是可部署预测器；将来只能用模型自己预测的下一步速度，不能把未来真实速度传入模型。

## 4. 本地已实现和边界

- [physical_terms_v26.py](../koopman/physical_terms_v26.py)：将已知浮力、恢复力、阻尼、旋转坐标输运和陀螺项独立表达；通过与实际水动力源公式及耗散性对照测试。尚未构成离散预测模型。
- [free_water_v26.py](../workflows/free_water_v26.py)：外力—速度平衡及actor高度检查，缺质量/重力/外力、框架不一致等情况拒绝。通过不等于完整自由水域认证，例如纯角向接触可能无法从平移残差发现。
- [free_water_trace_v26.py](../workflows/free_water_trace_v26.py)：在原observer子步结束位置添加检查；接触getter缺失/时钟或刚体身份改变均拒绝，发现异常先保留原始行再停止。诊断模式允许记录异常，但不会把异常标为可训练。

真实getter、全部碰撞刚体绑定、几何净空、source bundle和GPU on/off等价检查仍待服务器就绪后完成；旧v25采集器没有被原地改写。CPU测试不能证明接触API已经可用。

验证结果：三个新增模块分别经过先失败后通过的合同测试；最后运行原e2相关测试列表并加入33个新测试，**299 passed in 11.22s**。[测试范围与源码哈希](evidence/phase8_4/state-dynamics-local-20260913/test-results.json)、[原生输出](evidence/phase8_4/state-dynamics-local-20260913/related-tests.txt)。这是当前工作区的CPU相关回归，不是全仓库测试、独立新clone或真实Isaac验收。

Isaac Lab2.2.1的`net_forces_w`是**法向接触力**，不包含完整切向摩擦；后续必须按这个语义记录，不能要求它解释全部三轴冲量。[对应版本源码](https://raw.githubusercontent.com/isaac-sim/IsaacLab/v2.2.1/source/isaaclab/isaaclab/sensors/contact_sensor/contact_sensor_data.py)。

## 5. 下一步顺序

1. 按[服务器短对照入口](phase8_4_free_water_microtrace.md)读取实际碰撞几何和接触API，再比较相同构型/命令下1.5m与5.5m初始高度。保留质量、volume、地面和控制更新时序；提高初始高度是明确的新初始条件。
2. 确认自由水域准入与全段持续时间。若负浮力构型仍会触底，先设计明确的深水初始条件、短片段或可识别的悬停附近激励，不能在段内重置高度后继续当连续训练数据。
3. 只有新数据条件可信后，继续fit覆盖/共线性审查、速度项物理约束和位姿离散修复。自由水域、均匀流体中的速度动态不应任意依赖绝对世界高度；需要用高度平移对照检验，而不是仅凭拟合结果设置系数。
4. Koopman候选须分别对比persistence、已知物理基线及相同信息的较小字典，使用独立新证据验证。旧validation仅用于解释失败。Phase9和后续Agentic验证继续等待合格模型handoff。

当前[06计划](../.planning/phases/08.4-conditional-identification-experiment/08.4-06-PLAN.md)已调整为先补数据适用条件，候选拟合暂停。研究目标仍为Koopman-UUV / Agentic-AUV。

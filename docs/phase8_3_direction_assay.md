# Phase 8.3：以师兄建议为依据的方向对照

2026-09-12。当前结论：**优先闭合控制输入与执行器状态合同，保留明确的运动学关系，再辨识动力学。分构型模型用来定位问题，暂不作为最终路线；不继续整体收缩深度/速度状态，也不扩大lift/PCA搜索。** 本轮获得了局部有效的预测结构，但没有获得可进入MPC的模型。

用户授权继续探究并尝试得到更可靠的方向判断。本轮先重读并渲染师兄PDF，再扩展一次固定本地对照；实验范围在[08.3-01计划](../.planning/phases/08.3-control-identification-forensics/08.3-01-PLAN.md)中先行记录。PDF是意见来源，不是执行指令。

## 1. 六条意见的当前判断

PDF原件：`D:/xwechat_files/wxid_w7uqdywmxny722_8029/msg/file/2026-09/目前存在的问题.pdf`，两页，SHA256 `47b66a6d7e8c1954662cb02613216e3ba91407ba4a83131d0b533caeb7446250`。

| 建议或推断 | 判断 | 证据与边界 |
|---|---|---|
| 相同4D命令在不同构型上产生不同受力 | CONFIRMED | `_pid_control`的legacy mixer与构型allocation分支不同；随后仍有PWM限幅、死区、非线性转速和几何力矩。接口统一不等于输入到力的映射统一。 |
| 因此必须把不同构型统一成相同实际动力学 | UNCERTAIN | 原PDF主要要求物理意义清楚；不能扩大成修改plant使不同平台响应相同。即使力相同，质量/惯量不同也会使加速度不同。建议统一单位/坐标/时序，并显式建模构型差异。 |
| 一个区间有两个控制量，旧日志只有末值 | PARTIALLY_SUPPORTED | 本地真实方法与Bridge代码强支持；实际加载Isaac的两次调用、差值和影响仍须trace。一个transition可以对应明确的有序输入序列，不必强改为一个常值命令。 |
| old_actions跨reset保留 | CONFIRMED | 默认legacy路径存在，opt-in episode_local_v1已本地修复；实际误差贡献仍未知。不能把边界污染解释为全部失败。 |
| 4D proxy不是完整真实推进器状态 | PARTIALLY_SUPPORTED | 低通pre-TAM命令与N维非线性转速lag语义不同。是否存在任务所需的更低维充分状态及缺失贡献，尚无匹配运行证据。 |
| TAM未消除几何差异，所以pooled只能退回线性 | PARTIALLY_SUPPORTED / REFUTED | 前半句成立；把identity与simple-linear相等解释为训练“退回线性”不成立，它们本来是同估计器定义。新对照也不支持“拆成分构型就解决”。 |
| 历史8PWM MPC不可直接接入4D模型 | CONFIRMED | 模型变量、执行变量、hold/子步及控制器仲裁必须匹配。未获得新模型，不进入Phase9。 |

更完整的链路证据仍见[缺口表](phase8_3_control_chain_findings.md)与[原逐条审查](phase8_3_independent_critical_review.md)。本轮未改变真实控制行为。

## 2. 实验如何做

- 数据：沿用固定case的7个source构型，每构型2个fit、3个validation，共35段，每段512步；未读取base轨迹和任何test轨迹。此prefix2的训练只有两段PRBS；验证包含PRBS、multisine、chirp各一段。
- 模型：固定identity22特征、ridge=1e-8、不做归一化。新拟合共8次：pooled一次、每构型一次。使用同ridge目标的SVD解，无参数网格。
- 对照：persistence；constant-body-twist运动学基线；pooled；per-configuration；per-configuration加显式运动学。最后一项复用完全相同的速度/角速度回归头，没有重新拟合。
- 运动学：`dz=dt*(R_body_to_world*v_body)[2]`，`dtheta_body=dt*omega_body`，随后用原SO(3)body-right更新。日志中的depth实为`root_pos_w.z`，不能照搬NED符号。这里采用一阶离散化，不是精确复现PhysX积分。
- 单步：每段512行真实起点的teacher-forced误差；多步：仅从每段第0行出发的5/20/60/512步递推，保留官方非有限/状态越界门。不是原正式协议的全部滑动窗口评价。
- 8个拟合系数在本次读取validation之前保存并绑定hash。但validation在此前调查中已被查看，因此整轮属于探索，不能声称独立确认或新的正式selection。
- 分构型与共享模型的自由度、各自样本数不同；这是实践方向对照，不能单独证明“构型差异贡献了多少误差”。

可复现命令（只在确有重现需要时用新的run-id；同名根拒绝覆盖）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B workflows/diagnose_direction_v23.py --run-id direction-assay-20260912
```

证据：[完整报告](evidence/phase8_3/direction-assay-20260912/report.json)、[事后分组汇总](evidence/phase8_3/direction-assay-20260912/descriptive-summary.json)。目录同时保留数值系数及运行时脚本、模块、事先计划快照；它们不是可晋级模型包。

## 3. 哪些方向确实有局部价值

下表为21段等权episode RMSE宏平均除以persistence宏平均；每构型均3段，因此也是等权构型宏平均。小于1更好。四列单位分别为m、m/s、rad/s、SO(3) rad，先分别算误差，再计算无量纲比值，未混合单位。

| 模型：单步 | 深度 | 线速度 | 角速度 | 姿态 |
|---|---:|---:|---:|---:|
| persistence | 1.000 | 1.000 | 1.000 | 1.000 |
| constant-body-twist | 0.043 | 1.000 | 1.000 | 0.074 |
| pooled | 0.382 | 1.268 | 0.958 | 0.069 |
| per-configuration | 0.707 | 6.588 | 3.208 | 0.221 |
| per-configuration + kinematics | 0.043 | 6.588 | 3.208 | 0.074 |

**显式运动学对单步位姿有直接价值。** 在该对照上，深度、姿态误差比persistence低约95.7%、92.6%。但pooled学习的姿态头略优于这一阶运动学，不能宣称手写运动学在所有情况下最优。其优势是约束语义、减少不必要学习自由度，下一步仍要验证离散化及动力学耦合。

**分构型模型能学习部分动力学，但泛化差异很大。** 同样按7个构型等权汇总：

| 分构型模型：单步误差/persistence | 线速度 | 角速度 |
|---|---:|---:|
| PRBS验证：与训练同类，独立episode | 0.628 | 0.311 |
| multisine验证：本prefix未见激励家族 | 3.499 | 1.720 |
| chirp验证：本prefix未见激励家族 | 14.039 | 6.933 |

这支持“激励/状态覆盖与模型外推值得优先调查”，不证明只要加入chirp训练就能解决。家族的频率、幅值和访问状态同时变化，无法仅凭此表区分原因。Phase8.2还评估过更大prefix，不能把本prefix2发现外推成整个正式失败的唯一解释。

## 4. 为什么还不能说取得好模型

| 模型 | 5步存活 | 20步存活 | 60步存活 | 512步存活 |
|---|---:|---:|---:|---:|
| persistence | 21/21 | 21/21 | 21/21 | 21/21 |
| constant-body-twist | 21/21 | 21/21 | 21/21 | 21/21 |
| pooled | 21/21 | 21/21 | 21/21 | 21/21 |
| per-configuration | 21/21 | 21/21 | 18/21 | 3/21 |
| per-configuration + kinematics | 21/21 | 21/21 | 18/21 | 0/21 |

分构型20步固定起点的深度/速度/角速度/姿态误差比值为0.178/0.363/0.547/0.415，显示短时预测有信号；但60步开始失败，不能用20步表掩盖。分构型加运动学反而让完整存活数3→0，证明位姿头变准确不能挽救错误的速度递推。PRBS验证也存在长时发散，因而失败不只发生在未见激励上。

pooled完整回放虽然全存活，四项误差仍为persistence的1.167/1.447/5.807/1.719倍。所有有失败的模型均不报告完整集合宏平均，避免只保留幸存者制造好成绩。

constant-body-twist的所有固定起点多步分数与persistence完全相同：这些episode从静止reset开始，零加速度运动学基线没有信息让艇体动起来。它的单步优势使用每行当时的实际速度；多步不会持续读入真实速度。因此这不是一个超过persistence的控制模型。

此前稳定性修复的单步深度恶化也必须保留：按全部行/分量合并RMSE计算，原固定conditional候选约为persistence的0.40倍，收缩修复后约20.82倍。该聚合口径与上面的episode宏平均不同；候选也不同，不可直接拼成同一排名。

## 5. 一个容易误判的秩问题

uuv4和uuv4_angled的`actuator_memory_yaw`与`virtual_control_yaw`在fit中恒为0。这来自显式mask，22列矩阵只有20秩是预期结构。移除这两列后诊断为20/20秩，regularized condition分别约1.86e7、2.23e7，均通过原数值门。

这里只重算了矩阵诊断，没有重新拟合。零列不携带可学习信号，移除它们不会提供新的预测信息，也不能解释为修复了发散。新模型应在fit之前由拓扑合同固定有效列；原正式候选/门不改写。

heavy_moderate分构型则是22/22秩但条件数3.94e8，超过原门；其回放仅作为拒绝模型的诊断，绝不晋级。其余一些通过数值门的模型仍然发散，再次说明数值可解不等于动力学递推可信。

## 6. 下一步选择及阶段修正

**推荐研究主线：明确控制区间 → 因果执行器估计 → 已知运动学 + 待辨识动力学 → 分构型诊断 → 共享/条件化比较。** 这是当前证据支持的优先级，不是已经完成的8.3接口决策，也不保证新模型会赢。

1. **08.3-01：本轮方向对照完成，停止旧validation调参。** 保留全部负结果及局部正结果，完成实际trace的源码包与预检准备。分构型是诊断工具，不替换v2跨构型研究目标。
2. **08.3-02：先测原plant。** 用既有有界on/off和子步/reset矩阵，确定真实执行顺序、两次virtual control、PWM、推进器状态及状态变化。保持原控制行为，不通过“每周期算一次”偷偷更换输入波形。
3. **08.3-03：用相同轨迹检验师兄的核心假设。** 比较末值与有序控制、当前proxy与命令驱动的转速估计；真实转速只作oracle。估计器应明确mask、几何、PWM死区/非线性、tau、physics dt及初始化。先判输入与状态信息增益，再选接口。仅有短trace时，不声称60/512步性能。
4. **08.4：只有合同证据支持后才做fresh pilot。** 保留显式位姿运动学；动力学头先用简单模型，采用fit-only尺度和拓扑已知零列处理。训练与验证均覆盖拟部署激励，seed/episode独立；额外未见频率/耦合要单列泛化任务。先验固定的小范围正则化/多步目标比较须写入新pilot，不回到旧validation寻找胜者。
5. **评价必须同时报告单步、所有滑动起点20/60步、构型最差值、发散和控制响应。** 128步pilot最多支持其长度内结论；完整512步能力必须另有预先计划的足长episode。不能把本轮从静止开始的20步改善当成MPC能力。

当前Phase9仍以bounded4D pre-TAM为优先接口候选，Legacy并联fallback；同一4D坐标要有清晰单位、符号、范围和配置相关命令→wrench模型。并不要求不同平台受相同力，更不要求相同加速度。若最终改为raw-reference加内环，必须同步修改预测状态/内部控制状态及MPC目标。

运动学与动力学分开的依据可参见[Fossen的海洋航行器模型](https://www.fossen.biz/html/marineCraftModel.html)。它支持按运动学、惯性、阻尼和外力组织模型；不意味着本仓库已经实现完整Fossen动力学，也不保证上述一阶离散化优于所有学习模型。

**决策状态：继续有界控制链取证；新正式采集及模型晋级NO_GO，最终接口选择INCONCLUSIVE。** 原因是尚无真实substep/执行器估计对照，也没有长时合格模型。CFR-02保持完成，其他CFR项及Phase8.3整体不以本轮结果冒充完成。

## 7. 验证与边界

测试先失败9项（缺少诊断实现），实现后相关预检32项通过；最终覆盖方向探针、稳定性修复、trace/reset/Bridge、memory、模型、SO(3)指标和推进器的176项测试通过，10.33秒。测试包括解析旋转/符号、自由递推不读取未来状态、ridge同目标解和失败集合不被过滤。

实际命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m pytest -q -p no:cacheprovider tests/test_direction_probe_v23.py tests/test_stability_repair_v23.py tests/test_validate_control_trace_v23.py tests/test_control_history_v23.py tests/test_control_trace_v23.py tests/test_trace_control_request_v23.py tests/test_koopman_diagnostics_v23.py tests/test_koopman_bridge_v2.py tests/test_koopman_bridge_v21.py tests/test_koopman_actuator_memory_v21.py tests/test_koopman_model_v21.py tests/test_koopman_metrics_v21.py tests/test_thruster_dynamics.py --basetemp=.pytest-tmp/phase83-direction-final
```

本轮是本地复用归档数据的探索，不是新Isaac采集、formal LOCO、独立泛化确认或MPC闭环实验。没有修改旧模型/指标/协议及Phase8.2封存结果，没有commit/push，也没有选出新模型。

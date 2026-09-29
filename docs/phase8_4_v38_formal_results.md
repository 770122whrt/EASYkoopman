# v38正式结果：validation与test均独立复核GO

2026-09-20T02:09:59+08:00

在已批准的八构型范围内，8条预检、24条validation及24条test全部完成。两个正式角色各1152项指标、24组固定门通过，原生评分/数据复核/独立分析均退出0。18个冻结模型没有重新拟合。Phase 8.4按限定预测与接口要求关闭，下一步进入本地控制集成；尚无闭环MPC或Agentic收益结论。

## 相对persistence及跨构型表现

persistence把预测起点的状态保持为常量，不利用命令推进动力学。它在变化很小的短时域上常是强基线；当前比较仍沿用预先冻结的同一指标和归一尺度。下表是每个模式/模型范围的六组主门中，候选归一速度分数除以persistence分数的最小值和最大值，越小越好。这不是每一原始状态量RMSE的比值。

| 数据角色 | 模式 | 范围 | 速度分数比 | 通过门数 |
|---|---|---|---:|---:|
| validation | conditional_projected | pooled | 0.000355115–0.0012218 | 6/6 |
| validation | conditional_projected | heldout | 0.000360931–0.00122685 | 6/6 |
| validation | policy_self_recurrence | pooled | 0.00268498–0.00833999 | 6/6 |
| validation | policy_self_recurrence | heldout | 0.00286309–0.00441674 | 6/6 |
| test | conditional_projected | pooled | 0.00035612–0.00127854 | 6/6 |
| test | conditional_projected | heldout | 0.000361562–0.0012817 | 6/6 |
| test | policy_self_recurrence | pooled | 0.00626599–0.0190311 | 6/6 |
| test | policy_self_recurrence | heldout | 0.00536823–0.0200957 | 6/6 |

正式test中，heldout模型在policy自行递推模式的汇总速度分数约为persistence的0.54%–2.01%。各构型在所有主时域、endpoint/path、pooled/heldout的速度门均为3/3条episode优于persistence。pooled与heldout都通过，因此“单构型好、跨构型必然差”不适用于修复后的这一组实验。每个heldout模型训练时排除对应构型，测试仍来自研究者已知的固定八构型目录，目标构型的实际机械参数、拓扑和已有校准仍作为上下文可用，不能称为完全未知平台的零信息泛化。

下面是test在128控制区间条件预测终点的**机体系线速度分量RMSE**，每格为该构型3条episode的均值，单位m/s；它与上表归一后的综合速度分数不同。

| 构型 | nonlinear pooled | nonlinear heldout | linear pooled | known physics | persistence |
|---|---:|---:|---:|---:|---:|
| base | 3.08601e-06 | 3.08411e-06 | 0.00873673 | 3.10662e-06 | 0.0176559 |
| long_body | 4.61385e-06 | 4.69816e-06 | 0.0135803 | 4.59552e-06 | 0.0202036 |
| heavy_moderate | 0.000266919 | 0.000266196 | 0.0214155 | 0.000273849 | 0.077152 |
| asymmetric | 3.67576e-06 | 3.78232e-06 | 0.00610452 | 3.81577e-06 | 0.0150586 |
| uuv6 | 4.32335e-06 | 4.32269e-06 | 0.0114631 | 4.29034e-06 | 0.0180126 |
| uuv6_angled | 4.64667e-06 | 4.64209e-06 | 0.00913796 | 4.66981e-06 | 0.016936 |
| uuv4 | 3.87043e-06 | 3.87109e-06 | 0.00693988 | 3.89664e-06 | 0.0188381 |
| uuv4_angled | 4.13022e-06 | 4.13e-06 | 0.00648649 | 4.18086e-06 | 0.0175024 |

## 结果支持什么，不能支持什么

先前取证发现的初始化、实际质量/惯量、执行器历史/时钟、控制区间和位姿递推问题均影响正确建模。新数据采集还加入自由水域、接触/净空、配平和覆盖检查。此次正式结果说明这一整套匹配后的结构化预测路线有效；没有逐项控制消融，不能把性能收益精确归因给某一个bug，也不能把旧失败统称为跨构型问题。

当前模型以六个速度观测量的受约束回归配合已知位姿积分推进状态。它与同D/Q系数的物理参数模型等价，结果接近已知物理基线。因而取得了可用预测器和辨识/执行一致性的证据，但尚未证明额外Koopman算法优势，也未证明完整有限维提升闭合。此前完整算子失败和v25/Phase8.2的NO_SELECTION全部保留。

conditional_projected接收真实轨迹记录的未来已发命令，这些反馈命令未必在预测起点可用。policy_self_recurrence由自己的预测状态生成未来命令，提供更接近控制使用场景的证据，仍不是优化器闭环实测。预测API不接收未来真实状态、转速或作用力。主精度门为20/60/128区间；512全段要求六条路径完整，精度只描述，不新增事后晋级条件。

每角色每构型仅3条轨迹；配对bootstrap只作描述。噪声、流场变化、DR、新拓扑、未知转速初态、在线换构型和硬件均未获得本轮资格。独立审核重放576条条件预测并独立计算576条full/policy数组指标，复用了冻结预测器数学实现，没有第二套完全独立预测器或完整policy再生成。

## 正式身份与实际资源

- validation：数据来自r21；修复数值验收、评分和独立分析来自r22。两种身份分别绑定，未将旧数据冒充r23重采。
- test：原定seed9500–9523、24条×512区间，r23原始数据/评分/独立复核完整通过；零追加episode、零新拟合。
- r23源码：`bfe1659f2aee45760b66dbb98884f37fd20ad391`，freeze：`6a6274f9466894871621148573dac6a2fb366cd63442b28a52cac36d29ad37a4`；543个源文件。原树与隔离源码各555项相关预检通过。
- 累计采集2704.782秒，即45.08分钟/90分钟；分析3296.516秒，即54.94分钟/75分钟；最多4分析进程。用户批准的15分钟是额外可用上限，并非实际增加了15分钟开销。实际分析也低于原60分钟上限；独立test审核比validation更快，其速度差原因本轮未诊断。
- 完整125笔账本保留历史native1失败（索引17、68）和所有实际费用。两端预算与审核凭证已同步，无活动仿真/分析任务；服务器可关闭。
- 磁盘以两端真实文件内容计量，真实硬链接每个主机计一次，独立副本照计；同时报告逐路径总量。r22/r23两个未改USD文件在各自主机共享硬链接，旧源文件内容重新核对不变。最终实测文件内容合计4,256,494,995字节（约3.964GiB）；逐路径合计4,404,805,153字节，包含硬链接的重复路径。真实内容量加32MiB元数据/增长预留仍低于4GiB，预留后余4,917,869字节。最终值见[存储记录](evidence/phase8_4/server-projected-formal-v38-r23/final-storage.json)，4GiB上限保持。

## 两处文档元数据更正

原validation表写成“世界速度分量RMSE”，实际`squared_errors`使用state的5:8列机体系线速度。报告已更正；原`validation-descriptive-summary.json`保留，关闭记录绑定原SHA并记录错误键名。数值和精度门均未改变。

本轮生成的首版交接清单误写通道为surge/sway/heave/yaw。实际冻结目录和运行代码始终是`[roll,pitch,yaw,depth]`，uuv4的yaw在index2被mask。首版保留作历史，后续只能消费[交接v2](evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json)；[更正记录](evidence/phase8_4/server-projected-formal-v38-r23/handoff-metadata-correction.json)绑定原件、后继和真实冻结常量。这不是实验控制通道的修复。服务器从已有原件生成了相同SHA的后继清单，[两端更正同步凭证](evidence/phase8_4/server-projected-formal-v38-r23/handoff-metadata-sync.json)已确认；先前上传研究JSON的自动审批拦截已通过不上传载荷的安全替代解决。

## 下一步接口与研究顺序

交接限定为有界归一化4D pre-TAM命令、11D z/四元数/机体系速度状态、N维命令驱动执行器历史、实际PhysX参数和两个物理子步。9个冻结nonlinear pooled/heldout模型均列出，不做test后的重新拟合或逐构型挑最好模型。`prediction_handoff=true`，`closed_loop_controller_promoted=false`。

先按[09-01计划](../.planning/phases/09-configuration-aware-koopman-mpc/09-01-PLAN.md)实现可复制的因果执行器状态，验证与当前重放接口等价，测清候选分支的实际成本。随后做有界命令优化、fallback和Legacy并行仲裁，保留已知物理预测器作为同信息比较器。当前非线性投影不能直接包装成固定A/B线性QP。新的服务器控制实验需要单独具体范围和预算，不能消费本轮剩余分析额度扩展实验。

Koopman-UUV/Agentic-AUV仍是研究主线：预测可用性已取得限定证据；控制提升、相对物理模型的增量及Agentic决策收益仍需按顺序验证。

## 可复核入口

- [机器关闭记录](evidence/phase8_4/server-projected-formal-v38-r23/formal-closeout.json)及[最终账本](evidence/phase8_4/server-projected-formal-v38-r23/live-budget.json)。
- [validation报告](phase8_4_v38_validation_results.md)及[validation独立审核](evidence/phase8_4/server-projected-formal-v38-r22/validation-analysis-audit.json)。
- [test数据验收](evidence/phase8_4/server-projected-formal-v38-r23/test/acceptance.json)、[test评分结果](evidence/phase8_4/server-projected-formal-v38-r23/test-analysis/result.json)、[test独立审核](evidence/phase8_4/server-projected-formal-v38-r23/test-analysis-audit.json)。
- [服务端实际同步及旧源码未改凭证](evidence/phase8_4/server-projected-formal-v38-r23/test-analysis-audit-sync.json)。
- [Phase 8.4验收](../.planning/phases/08.4-conditional-identification-experiment/08.4-VERIFICATION.md)、[ROADMAP](../.planning/ROADMAP.md)。

# v38 预检与浮点容差修复

**当前状态 2026-09-19T23:59:18+08:00：** r22已在真实服务器部署并验证源码、原24条validation数据与修复验收凭证（native0）。源码00d01f1e…347d、freeze b52e81b2…4657保持；原树与隔离源码各542项历史测试及本次540文件字节核对通过。18个冻结模型的正式评分、独立算术审计和test尚未开始。累计采集1510.428秒、分析1332.544秒，分析余额2267.456秒；原失败和预算完整保留。下一步直接运行validation评分与独立审核，通过原固定门后才开放test。SSH已恢复，应用goal实测paused；NID-05未完成，Phase9无handoff。

[真实服务器部署记录](evidence/phase8_4/server-projected-formal-v38-r22/bootstrap.json)。以下按时间保留历史修复过程。

2026-09-14。8条真实预检已完成，修复后的本地数值复核通过。正式validation/test尚未采集；这份结果说明数据检查与容差修复有效，不是预测性能或Phase9交接结论。

用户已批准原v38范围，随后明确要求“完全相等可以换成一个小的容差”。本次修复只改验收摘要的比较方法，物理检查、18个冻结模型、控制输入、种子、预算和精度门保持原样。

1. **失败原因。** `projected_archive_v38.audit_raw`用字典完全相等比较服务器摘要与本地重算摘要。服务器Linux与本地Windows分别使用NumPy1.26.0/1.26.4、Torch2.7.0+cu128/2.8.0+cpu。相同原始数据、相同源码的8条物理检查均通过，但13项派生数值不同：倾角有1 ULP差异，控制分配及转子重建的残差摘要也有微小差异，最大转速残差差约5.517e-6。已确认完全相等是错误的验收要求；尚未把每项数值差异单独归因到具体BLAS或库版本。
2. **修复方法。** 只对列出的测量摘要使用容差；哈希、构型/角色/种子身份、计数、结构、布尔判断和原始门限仍精确比较。保留每个非零差异的两端数值、绝对差和允许差；NaN/Inf、未知字段差异、超差或物理阈值越界均拒绝。每条轨迹仍先经过原有完整物理、实际参数、控制历史和子步检查。
3. **已取得的验证。** 回归测试先复现原错误（1失败、3通过），修复后36项相关测试通过，项目规定的63文件清单共515项通过。随后从未改动的r20源码重新加载8条真实轨迹：4096个物理子步全部通过原检查，13处摘要差异全部满足新容差，原数据、freeze、模型及失败账本未改。

| 摘要数值 | 两端比较容差 | 原物理拒绝阈值 |
|---|---|---|
| 已列出的几何/运动/分配摘要 | `atol=1e-12, rtol=1e-9` | 各原检查照常执行 |
| virtual control/PWM残差 | `atol=1e-7, rtol=0` | `1e-6`，保持 |
| 转速/wrench残差 | `atol=1e-5, rtol=0` | `1e-3`，保持 |

后两项比较额度分别是原拒绝阈值的10%和1%，用于容纳float32重建的数值差异；不是扩大物理误差门或根据预测得分调门。一般摘要采用对称的`atol + rtol * max(abs(server), abs(local))`。正式validation未查看，后续不得根据validation结果不断放宽容差。

证据：

- [8条原始预检归档记录](evidence/phase8_4/server-projected-formal-v38-r20/preflight/preflight-archive.json)：原生8/8退出0，2048控制区间，归档SHA `4c3caa13f7f36d078b9236ed5766ac495ebdd4c6702f72ca9f4003aecf1505aa`。
- [逐项差异定位](evidence/phase8_4/server-projected-formal-v38-r20/pullback-diagnosis/all-cases-difference.json)与[完整物理重算及新容差复核](evidence/phase8_4/server-projected-formal-v38-r20/pullback-diagnosis/tolerance-recheck.json)。后者明确`formal_release=false`；没有手工制造原冻结流程的acceptance。
- [515项源码测试](evidence/phase8_4/server-projected-formal-v38-r20/tolerance-source-tests/tests.json)：native0，pytest32.56秒，监督器33.938秒。这是当前原树测试，不冒称新隔离包或服务器测试。
- [失败原账本](evidence/phase8_4/server-projected-formal-v38-r20/live-budget.json)与[附加诊断账本](evidence/phase8_4/server-projected-formal-v38-r20/pullback-diagnosis/budget.json)：采集累计276.725秒；分析含失败及两轮诊断累计88.340秒。原`pullback:preflight`的native1保留，两端原账本已同步。

接下来把这个已验证的修复接入正式运行入口：显式区分旧采集源码与新验收代码身份，保留旧失败并承接全部已花预算，使用已有8条预检，不换种子重采。还需检查独立评分中派生输入缓存的跨平台相等条件，避免在下一道门重复出现同类问题。完成接入及相应检查后，按用户已批准范围继续24条validation；只有原固定精度门和独立复核都通过才开放24条test。当前没有本任务活动仿真进程，goal/NID-05继续。

## r21接入与正式validation启动

2026-09-14T12:00:43+08:00。r21数值验收修复已接入：原树与隔离源码各535项测试通过，原8条预检正式复核通过并复用；旧失败native1及全部费用保留。新冻结源码0fd19ff2…83da、freeze a592b69b…effa5已通过服务器检查，24条×512区间validation已启动（supervisor32746/start285257166）。固定18旧模型，零拟合；test只在原精度门及独立审计通过后开放。NID-05与goal继续，Phase9无handoff。

- [r21隔离包与535/535测试](evidence/phase8_4/projected-formal-repair-v38-20260914-r21/package.json)，修复delta仅89,485字节；父r20源码保持。
- [正式父预检复核](evidence/phase8_4/projected-formal-repair-v38-20260914-r21/reaudit/parent-preflight-audit.json)：8条完整通过，审计源码身份独立绑定；33.062秒复核计入原预算。
- [真实跨平台缓存比较](evidence/phase8_4/server-projected-formal-v38-r20/numeric-cache-probe-r21/comparison.json)：状态/命令/时钟全0差；最大PWM差8.94e-8、转速差3.02e-5、wrench差3.815e-6。缓存核验换算物理单位，随后用同一生产输入复算分数。
- [继承账本](evidence/phase8_4/projected-formal-repair-v38-20260914-r21/inputs/budget.json)：前18条原样保留，包括pullback失败；开始新validation前累计采集276.725秒、分析129.927秒。
- [两端存储核算](evidence/phase8_4/server-projected-formal-v38-r21/storage-before-validation.json)：当前1,132,672,689字节，完整流程保守估计4,042,213,403字节，未超过4GiB；仍需阶段间实测。

原r20首次失败未改写；新的复核凭证是修复后明确生成的成功证据。正式validation正在运行，尚无新预测性能或MPC/Agentic结论。

## 正式结果的输入信息口径

采集期间复查冻结评分实现后，明确以下解释，既有数据与评分代码保持冻结：`conditional_projected`和`full_episode`把轨迹中已发出的命令序列作为给定未来输入，执行器转速和wrench由完整命令历史重建。这些命令原本由仿真中的状态反馈产生，因此不能声称在预测起点已经由在线规划器给出，也不能把条件预测当作无需未来命令的预测。评分中的`conditional_future_recorded_inputs=false`只应理解为没有读取未来实测转速/wrench；这个字段名容易误解，报告必须同时披露实际命令来源。

`policy_self_recurrence`从起点真实状态及过去命令历史出发，后续命令由自身预测状态和固定外部激励生成；它才检查无需未来真实命令的策略递推。六条模型/基线路径在各自模式下使用同等信息；两类结果分开报告，不把条件信息优势计作Koopman或Agentic贡献。此澄清不改变任何数值门、模型或采集范围。

## r21正式validation的完整定位与r22修复

24/24原物理检查通过；首次独立拉回失败在uuv6_angled、seed9417、chirp。服务端转速残差3.462824e-5，本地4.630751e-5，两端摘要差1.167927e-5；原物理上限1e-3。其余23条摘要在r21容差内。最大PWM摘要差1.49e-8、wrench差2.45e-6、角度归约差2.78e-17。没有碰撞、物理门失败或新预测分数。

原因是摘要容差1e-5比同一转速重算的逐点缓存容差1e-4更严。最大残差是逐点值的1-Lipschitz函数；统一使用已存在的1e-4界有明确依据。wrench、物理门、模型/评分函数与科学门保持原样。新回归先失败再通过，六个相关测试文件共66项通过；完整隔离复核尚待执行。

证据：[完整24条诊断](evidence/phase8_4/server-projected-formal-v38-r21/validation-numeric-diagnosis/result.json)、[219.391秒诊断记录](evidence/phase8_4/server-projected-formal-v38-r21/validation-numeric-diagnosis/operation.json)、[原验收失败](evidence/phase8_4/server-projected-formal-v38-r21/validation/pullback-failure.json)。失败与累计费用已经同步回服务器；评分和test尚未开始。r22只修复审核和身份接线，继续原批准范围。

## r22正式数据验收完成，等待服务器评分

2026-09-14T15:31:53+08:00。r22数值验收修复已冻结：原树与隔离源码各542项完整测试通过，原24条validation经424.718秒正式独立复核全部通过（24576物理子步）；原8预检继续复用，未重采或重拟合。源码00d01f1e…347d、freeze b52e81b2…4657；两次native1及全部费用保留，累计采集1510.428秒、分析1332.544秒，原分析预算还剩2267.456秒。30文件、422894字节部署包已就绪，等待用户通知服务器开启后再连接；尚未评分或采集test。NID-05与goal开放，Phase9无handoff。

- [就绪记录](evidence/phase8_4/projected-formal-repair-v38-20260914-r22/ready.json)
- [24条完整独立验收](evidence/phase8_4/projected-formal-repair-v38-20260914-r22/reaudit/parent-validation-audit.json)
- [原树542项测试](evidence/phase8_4/projected-formal-repair-v38-20260914-r22/root-tests.json)与[隔离源码542项测试](evidence/phase8_4/projected-formal-repair-v38-20260914-r22/clone-tests.json)
- [原失败和修复费用全部继承的账本](evidence/phase8_4/projected-formal-repair-v38-20260914-r22/upload/inputs/budget.json)

后续按原方案执行18个冻结模型的同信息比较，包含条件预测、整段完整性与策略自主递推。数据验收通过不等于预测优于persistence；尚未给出新的模型精度、闭环或Agentic收益结论。

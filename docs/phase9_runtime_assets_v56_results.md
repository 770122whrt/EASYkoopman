# Phase 9 冻结资产迁移 v56

新增显式相对路径的资产加载器及worker工厂。原handoff中的Windows绝对路径作为历史信息原样保留，新加载器不再跟随它。继续验证完整v38 bundle、授权链、冻结源、模型SHA与fit支持域；这些历史授权仅用于解释来源，不授权新的Phase9实验。

620文件、82,702,712字节的资产副本已放在`.pytest-tmp/phase9-runtime-assets-v56-20260920`。原handoff字节不变，八构型支持域身份相同，只增加已有fit缓存，未读取正式test数组或新拟合。该副本是资产包，还不是可执行的服务器release；后续新增代码、运行配置和审批必须另行绑定。

16项新合同包含在69项相关测试中通过，覆盖路径逃逸、错误模型/支持域、禁止回退旧路径、heldout模型不得获得heldout fit域、禁止覆盖既有目录和复制前字节上限。

| 检查 | 结果 | 结论边界 |
|---|---|---|
| 冻结源与迁移副本、八构型支持域 | 一致 | 资产迁移正确，不等于Linux运行成功 |
| 同一base fit起点128：原v53路径 | 父端48.3995ms；selected | 单次Windows请求 |
| 相同请求：迁移v56路径，100ms | timeout，NO_GO | 保留失败；不能以随后诊断覆盖 |
| 迁移路径仅一次1000ms诊断 | 父端81.54ms；端内79.8235ms | 非原100ms准入复测 |
| 诊断与原已存结果 | 命令、预测最大差0；代价在1e-12内一致 | 单一固定请求的等价性证据 |

诊断内基准生成18.4256ms、搜索56.8474ms；它显示该次耗时分布，不能单凭一次记录确定首次超时的根因。没有改模型、支持域、真实运行100ms期限或16.67ms控制计算门。首个诊断脚本因WorkerLimits参数名错误在worker启动前失败；源码快照、失败与费用保留，修正参数后才执行唯一诊断请求。

证据：[首次迁移对照](evidence/phase9/runtime-assets-v56-relocation-20260920/result.json)、[有界诊断](evidence/phase9/runtime-assets-v56-diagnosis02-20260920/result.json)、[69项测试](evidence/phase9/runtime-assets-v56-checks-20260920/related.txt)、[独立核对与预算](evidence/phase9/runtime-assets-v56-checks-20260920/review.json)。

下一项实际collector：保留原Isaac时序与direct pre-TAM plant，使用v55逐子步确认；先审查实际reset、物理context、接触几何与加载来源，记录并验收含readback和env.step的完整周期。原100ms失败不触发无限Windows微调；目标服务器必须重新测量。再按同一优化器区分名义物理、辨识物理和投影模型，并保留Legacy/S-Surface对照，具备具体新实验范围后申请独立资源。当前没有运行进程，不需要用户决策。

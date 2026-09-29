# Phase 9 有界监督与可执行发布 v58

实际接口短预检的监督程序、独立发布包和运行说明已准备。修订后发布目录的回归为**347 passed, 1 skipped**（pytest46.61秒）；本轮没有SSH、Isaac运行、新拟合或正式test访问。下一服务器动作需要批准[具体提案](phase9_runtime_preflight_v58_proposal.md)。

监督程序按base先行逐例采集、离线验收和SHA回读；任一步失败即停后续构型。即使采集进程退出0，也必须通过语义验收与进程组清理。超时后对该次新建的Linux进程组发TERM/KILL并核对`/proc`中仍存活的成员；Windows上的相关测试使用故障注入。真实Linux超时及孤儿进程清理将在启动Isaac前执行两个探针，未通过不能继续。

发布前审阅发现初版把180秒分别分给采集和验收，可能违反每构型合计上限。新反例复现后已修复：每构型的采集、验收、回读和清理共用180秒，验收只获得剩余额度，整阶段上限30分钟。初版未获批准、没有服务器运行，其345项通过记录、清单和受影响源码保留于[初版归档](evidence/phase9/runtime-release-v58-checks-20260920/initial-release-c44f11fe/supersession-reason.json)，不覆盖历史。

最终发布SHA为`8a08093a6f07d1630691d4aa5d9871137e1dd9bab116cdbba49404628bf4a7a3`，绑定676文件，新增代码/测试/运行说明436,475字节。复用原v56资产目录，没有再次复制USD；620个旧资产文件、v57已测源码及Phase8.4关闭/模型交接/预算文件哈希保持一致。打包拒绝旧源冲突、路径越界、复制前超额和复制期间源变化。

发布包未包含新的批准记录，也未将Windows编译器复制给Linux。新服务器端点仍待现场核验；需要既有Isaac环境及NumPy1.26.4、Numba0.61.2、llvmlite0.44.0。运行说明规定不自动升级环境，环境不符时停止并报告具体差异。

证据：[最终发布包347项回归](evidence/phase9/runtime-release-v58-checks-20260920/clone02.txt)、[合计时间上限修复](evidence/phase9/runtime-release-v58-checks-20260920/repackage-budget-fix.json)、[审核与资源账目](evidence/phase9/runtime-release-v58-checks-20260920/review.json)、[运行说明](phase9_runtime_preflight_v58_runbook.md)。22项新增通过测试包含在347项中，不相加；1项真实Linux测试跳过不是通过。本轮测试/打包检查累计179.873秒，本地阶段累计596.070/1200秒，保留128MiB文件上限；v38预算不变。

固定短预检仍只有8构型×32控制区间，每例至少一次MPC激活，失败即停，保持100ms异步期限和16.67ms完整周期门。它不证明持续实时性、恢复性能、控制收益或Koopman/Agentic独特优势；v56首次100ms失败保留。匹配闭环对照尚未完成，需要继续准备同优化器/预算的名义物理、辨识物理和当前投影模型，并保留Legacy/S-Surface对照。MPC2-01..04保持未完成，goal active。

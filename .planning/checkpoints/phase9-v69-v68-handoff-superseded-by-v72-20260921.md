# 最新：v69预热修复有效，但uuv4完整轨迹后原生退出-11；覆盖队列全局停止

Goal仍active。v68已获用户明确批准分构型隔离**支持域**失败。新出现的原生退出不属于隔离范围，不能直接继续其余构型。正在对真实uuv4取证C栈，SSH工具session30362有界120秒；远端/root/EASYkoopman-phase9-native-exit-v69-20260921。先查其collector-native.json及collector-probe.log，不重复启动。

v68首例4物理步因首周期193.533ms和RSS+127.5MiB停止；v69纯数学预热修复后首周期52.416ms、RSS+5.7MiB，60宏/240物理步执行完，初始4步与旧失败轨迹最大状态差0。但进程最终SIGSEGV(-11)，不合格。零物理pinv+AppLauncher诊断正常退出，尚未定位根因。Windows重放物理/因果检查通过，反馈残差真实性比较因最大2.0988e-7跨平台差异触发原1e-7门，仍待处理。

六构型CPU READY可复用原哈希；仍没有新MPC配对。全部旧失败和资源费用保留，原28分钟/24物理启动上限不能重置。阶段结束或继续前核算v68墙钟109.9845秒、v69墙钟53.7345秒、GPU分配诊断保守30秒、退出probe首轮保守35秒、第二轮保守63秒、当前实际collector probe最多120秒、编译预留5秒。新文件两端总8MiB、保留研究包各256MiB上限保持。

# 当前交接：Goal active，v68分构型覆盖已批准并运行

v68离线复现asymmetric第10步启动越界：冻结模型滚转预测与实测相差0.000684rad/s；水平保持及逐轴限速未修复，增大阻尼转为偏航越界。八构型离线筛查中六种未触门，asymmetric/heavy_moderate触门；这些不是新增Isaac结果。

Goal已开启。建议按分构型独立验收补齐真实覆盖；用户已批准把原“任一失败停整个队列”改为“经复核的支持域失败隔离该构型”。最多24个新短案例、28分钟、零拟合，全部单案例安全门不变；v68已部署31348并开始有界运行；CPU六构型READY，物理结果待验收。

先读[诊断报告](../docs/phase9_startup_v68_findings.md)和[具体提案](../docs/phase9_multiconfiguration_v68_proposal.md)。v68已部署并开始物理采集，控制器与r3保持一致；Goal尚未关闭。31348 SSH正常；不要因为离线成功就标记构型通过。

下面是保留的v67事实基线：

# 当前交接：31348主机、base收益与asymmetric启动边界

2026-09-21。用户指定后续固定`root@183.147.142.40:31348`持续更新；30852仅留历史诊断。31348的SSH、Vulkan、项目IsaacLab实际运行均通过，不需要用户再次排查GPU。

先读[本轮真实结果](../docs/phase9_rate30_primary_v67_results.md)、[总账](../docs/evidence/phase9/rate30-primary-v67-20260921/summary.json)、[独立重放](../docs/evidence/phase9/rate30-primary-v67-20260921/r3/review.json)，再读[STATE](STATE.md)、[ROADMAP](ROADMAP.md)。

- 30Hz真实发令、120Hz物理、60Hz预测网格。base四臂完整配对：俯仰综合误差改善18.535%，命令变化1.821倍、力矩平方积分3.871倍；深度仅改善.209%，未达收益门。单seed/2秒，无泛化、独特Koopman或实时资格。
- r2 MPC在第145物理步因generation-2 GC约270ms触发回执计算超时。r3只改变GC安排，控制段前回收、段内暂缓、结束恢复并限RSS64MiB；原失败前缀行为差0，r3完成。完整周期仍约47ms，不能声称30Hz实时通过。
- asymmetric反馈在第10物理步/.0833秒因滚转角速度1.502304超过fit上限1.472868而停止；无触地，总角速度低于3rad/s物理限，MPC请求0。原协议首次失败即停，asymmetric其余和uuv4未运行。
- 下一步先做统一冷启动进入支持范围的离线诊断，比较立即跟踪与先建立配平；保持实际历史与原支持门。确定启动方案后另存有界协议并验证asymmetric，再继续uuv4。不要直接继续旧停止队列、扩fit盒或删除负结果。

远端r3：`/root/EASYkoopman-phase9-rate30-v67-r3-20260921`；Python：`/root/EASYkoopman-phase9-runtime-env-v58/bin/python`。manifest：`899e7f0fa9f9277a241ea00aa9197cdfc30e704b669360e07fc5a75924d5bd4e`。7例物理启动/1355子步，5例完整；案例+分析+CPU预检435.368秒，另通用视口诊断上限90秒。原2965依赖、Isaac补丁和源码复核通过。全部进程退出，无训练；不轮询旧session。

[Phase9文档入口](../docs/phase9_index.md)及[历史分类](../docs/archive/phase9-through-v66/index.md)。8.4保持关闭；Phase9仍开放。零重拟合。当前服务器无需操作；v68停止规则变更已获批准，正在执行。

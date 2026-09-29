# 30Hz适配与30852服务器诊断

**后续更新：用户已指定31348为唯一主服务器。该主机已完成真实base配对及asymmetric尝试；当前进度以[主机结果](phase9_rate30_primary_v67_results.md)为准。下文保留此前30852阶段的记录。**

2026-09-21。30Hz版本已实现并完成本地验证；新服务器上的三构型CPU求解进程均能进入READY。**新物理闭环尚未运行，当前阻塞是服务器图形初始化，尚无新的多构型收益结论。**

## 已完成与证据范围

| 项目 | 结果 | 边界 |
|---|---|---|
| SSH迁移 | `root@183.147.142.40:30852`，现有密钥可用 | 31348不是当前地址；不在文档保存密码 |
| 冻结发布与依赖 | v59发布包完整迁移；隔离环境NumPy1.26.4、Numba0.61.2、llvmlite0.44.0 | 原2965个依赖文件及IsaacLab补丁复核未变；未升级系统驱动 |
| 真正30Hz控制 | 一条命令保持4个120Hz物理子步；每两次回执保留一条60Hz预测历史 | 不是仅将旧16.667ms门改为33.333ms |
| 预测/求解合同 | H20微区间、前缀8微区间不变；候选/基准/前缀按两条微命令成对 | 对应10个/4个宏区间；保持预测时长与因果历史 |
| 变化率与计时 | 每宏区间slew=.02，保持原每秒限幅；求解100ms、反馈10ms | 首周期100ms单列；稳态33.333ms；未证明实测实时通过 |
| 本地验证 | 119项相关回归通过；其后部署命名空间与独立进程启动回归2项通过 | 不是全仓库测试，也不是Isaac实测 |
| Linux真实worker | base、asymmetric、uuv4均READY，分别约10.10/9.82/9.92秒，退出清理通过 | 包括加载/编译的启动耗时，不能当控制周期或效果证据 |

代码入口：[30Hz核心](../koopman/rate30_v67.py)、[成对候选](../koopman/bounded_mpc_v67.py)、[直接控制](../easyuuv_nc/control_v67.py)、[执行桥](../workflows/isaac_execution_v67.py)、[运行时](../workflows/runtime_episode_v67.py)、[独立历史重放](../workflows/runtime_audit_v67.py)。

原v65 base俯仰短任务综合误差改善18.42%的限定结论保持；新v67不继承该结果。原v66失败与代价仍见[旧结果](phase9_control_effects_v65_results.md)。

## 延迟定位与当前环境阻塞

在旧31348实例，将v66两个真实失败状态的反馈输入各重复100次：深度p50=2.512ms、p95=2.889ms、max=7.892ms；俯仰p50=.833ms、p95=.880ms、max=1.248ms，均未超10ms。说明323ms不是该输入下必然发生的计算量；尚不能据此确认GC、调度或Isaac资源竞争哪个是根因。新包记录反馈wall/process/thread CPU及GC事件；默认不禁用GC。原定GC对照未完成，不能声称GC优化有效。[固定状态重放](evidence/phase9/rate30-v67-20260921/feedback-profile.json)

新30852的诊断分层如下：

1. 普通CUDA与系统Warp1.8.1能识别RTX4090。
2. Isaac内置Warp1.7.1复现`cuDeviceGetUuid`报错，但其初始化也能返回；不能把警告当成卡死原因。NVIDIA有对应[已知问题](https://github.com/NVIDIA/warp/issues/851)。未安装新Warp或覆盖旧库。
3. 默认`DISPLAY=:20`时，Isaac停在窗口插件初始化；仅在诊断进程取消DISPLAY后越过该点，但仍停在GPU图形初始化。两次最小应用检查各限90秒，均未启动仿真。
4. 脱离项目独立执行`nvidia-smi -q`在12秒内未返回；`vulkaninfo --summary`在15秒内未返回；仅指定NVIDIA ICD后12秒内仍未返回。因此需要恢复实例的图形/Vulkan环境。具体是宿主驱动、容器映射还是共享资源问题仍未证实，不能据此断言GPU损坏。

已向用户说明需检查/重启实例或提供此前能运行Isaac的实例。所有本任务诊断和CPU工作进程已退出；没有后台训练。

## 已就绪的下一步

运行包：[r2协议](evidence/phase9/rate30-v67-20260921/rate30-bundle-r2/protocol.json)。远端目录`/root/EASYkoopman-phase9-rate30-v67-r2-20260921`，解释器`/root/EASYkoopman-phase9-runtime-env-v58/bin/python`。

- base俯仰、深度各做反馈/MPC匹配配对；全部完整物理与因果验收通过，且至少一个任务达到预设实际收益门，才扩展asymmetric、uuv4。
- 三构型×两任务×两控制器，最多12例；每例60个30Hz区间=240物理步=2秒，固定seed19500，零重拟合。各臂同初态、模型权限、目标和变化率。
- 另有一次三构型CPU预检，r2已完成32.239秒。r2总上限2280秒、每实际案例连同分析180秒、新输出每端16MiB；停止于首个失败，不用失败前缀比较完整轨迹。r1失败启动的.154秒及旧GC/环境诊断另外保留，不抹去。
- 同时报跟踪误差、控制代价、接管率、超时与失败。效益模式仍计入所有真实耗时并报告deadline miss，不将仿真时间运行包装为墙钟实时。
- 有效后再扩展八构型/多seed及名义参数、辨识参数、模型表示对照；当前不进入自适应、训练或Agent阶段。

恢复服务器后先检查Vulkan与一次有界Isaac启动，再使用该包按协议顺序执行；不要自动重启训练或重采旧数据。r1启动失败目录保持原样。r2 manifest为`2c6a7c46fa78c23d9cf015aee56f6873d581095c876f64fe6a4a948af9f48f66`。

## 审计与文档入口

[CPU预检](evidence/phase9/rate30-v67-20260921/cpu-r2/readiness.json)、[原环境/源码复核](evidence/phase9/rate30-v67-20260921/post-audit.json)、[汇总记录](evidence/phase9/rate30-v67-20260921/review.json)。环境准备原记录的`source_sha256`误填了说明字符串，原文件保留；正确脚本SHA为`7cba6bc1527f10ca3790a4db1bf692e9c873f3109bbb097ccae838599e2c2d38`，已在汇总中单独纠正。

文档统一入口为[Phase9索引](phase9_index.md)；34份历史报告按[分类索引](archive/phase9-through-v66/index.md)归档，原路径与内容不变，旧完整handoff另存原文。Phase9仍进行中，8.4不重新打开。

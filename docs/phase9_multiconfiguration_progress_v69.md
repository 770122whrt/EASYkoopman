# 多构型验证进展：启动修复完成，原生退出阻塞

2026-09-21。**这是一份中途进展报告，不是已完成的多构型收益报告。Goal仍未完成。** 用户批准v68分构型隔离支持域失败后已执行；当前因原生退出故障全局停止，未放宽验收条件。

| 构型 | 当前实际证据 | 结论边界 |
|---|---|---|
| base | r3俯仰与深度两组反馈/MPC配对，独立复核通过 | 俯仰综合误差改善18.535%，力矩平方积分3.871倍；深度.209%未达收益门 |
| asymmetric | 反馈在10物理步因滚转支持域越界停止 | NO_GO；MPC未执行。启动诊断否决简单先配平/逐轴限速修复 |
| uuv4 | 原始启动4步失败；预热修复后240步完成；两次退出取证也完成240步，三次最终均SIGSEGV | 不能计为成功、没有MPC配对；目前是退出基础设施阻塞 |
| long_body | CPU READY，尚无本版真实控制运行 | 待验证 |
| uuv6 | CPU READY，尚无本版真实控制运行 | 待验证 |
| uuv6_angled | CPU READY，尚无本版真实控制运行 | 待验证 |
| uuv4_angled | CPU READY，尚无本版真实控制运行 | 待验证 |
| heavy_moderate | CPU READY，离线诊断提示支持域风险；尚无本版真实运行 | 待验证，不能将离线越界计为真实失败 |

## 新增修复及验证

uuv4使用WLS/TAM矩阵分配。原纯数学预热未覆盖实际拓扑的`torch.linalg.pinv`；服务器独立GPU诊断首次调用174.631ms，随后约0.3–0.7ms，并出现一次性内存增长。v69在真实reset之后、计时控制之前，用复制的矩阵、命令和权重调用原分配函数；没有推进物理或执行器，原完整reset不变检查通过。

首周期从193.533降至52.416ms，运行段RSS增长从127.496MiB降至5.656MiB；原失败前4个实际状态与修复后逐值相同。60个控制区间完整执行，稳态中位46.113ms，59/59稳态周期超过33.333ms。因此修复了遗漏预热，**仍未取得30Hz完整周期实时资格**。

新的失败发生在保存最终报告之后。原生退出−11必须保留；3次真实完整uuv4轨迹中，1次来自修复版队列、2次来自原生栈诊断，不能把它们当成三个有效实验或挑选成功。当前没有新增有效Koopman收益结论，已有base限定收益保持。

25项相关本地检查通过，包含纯数学输入隔离/失败传播、失败前缀重建、队列停止规则和剩余预算约束；不是全仓库测试。Windows物理与命令因果重放检查可通过，但反馈残差真实性比较发现最大2.099e−7跨平台差异，超过原1e−7比较门；整体独立验收仍未通过。所有原生退出失败及该数值问题分开记录。

## 后续取证已获批准

用户已批准[最小调试修订](phase9_native_exit_debugger_proposal.md)：服务器隔离调试目录最多64MiB，物理启动上限24→28，总1680秒及研究包限制不变。获取C栈、修复原生对象生命周期、验证uuv4正常退出后，才继续其他构型。调试和旧失败费用继续累计。

## 原始证据

- [启动机制诊断](phase9_startup_v68_findings.md)、[获批覆盖范围](phase9_multiconfiguration_v68_proposal.md)。
- [v68队列停止记录](evidence/phase9/multiconfig-v68-20260921/results/stage-result.json)、[v69队列停止记录](evidence/phase9/multiconfig-v69-20260921/results/stage-result.json)。
- [预热前后实际状态与时间对照](evidence/phase9/multiconfig-v69-20260921/preparation-comparison.json)、[GPU独立诊断](evidence/phase9/allocation-v69-20260921/result.json)。
- [原生退出取证1](evidence/phase9/native-exit-v69-20260921/collector-native.json)、[取证2](evidence/phase9/native-exit-v69-20260921/collector-native-r2.json)、[跨平台残差诊断](evidence/phase9/multiconfig-v69-20260921/cross-platform-residual-diagnosis.json)。
- [新工具的base复核与asymmetric失败重建](evidence/phase9/rate30-primary-v67-20260921/r3/review-v68.json)。

2026-09-21后续：隔离gdb下载和解包完成，约20MiB，未安装系统包。首次有界gdb运行66.516秒，捕获PhysX tensor析构中的SIGSEGV；Python调用链包含仍被保留的cell与frame对象。下一步追查具体引用持有者；尚未确认修复。

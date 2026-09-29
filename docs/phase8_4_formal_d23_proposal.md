# Phase 8.4 正式实验：范围、依据与执行状态

**最新执行结论（2026-09-13）：正式验证NO_GO／NO_SELECTION，68模型及2280评分已独立核对；24test未采，无handoff。见[正式结果与失败定位](phase8_4_formal_validation_results.md)。下方运行步骤保留供复现，不能据此重启已停止实验。**

提案创建于2026-09-12；2026-09-13用户在引用本具体提案时确认继续验证与修复。**D-23已批准；8条短预检已完成真实GPU及63文件独立拉回验收，48条fit/validation进入采集。** 用户已持续授权服务器/GPU/训练和常规实现。本文件对应新的、具体的正式实验决定，依据 [08.4-CONTEXT的NID-02及工作包3](../.planning/phases/08.4-conditional-identification-experiment/08.4-CONTEXT.md)。它不改变Koopman-UUV／Agentic-AUV主线。

继续的依据：新一轮18条GPU轨迹、28个固定模型，留构型预测20/60步的归一化终点宏误差为persistence比较尺度的0.1233/0.2443，9/9条128步预测稳定，独立算术/角色核验通过。剩余弱项是base的60步姿态误差0.508803rad，仍高于persistence的0.435500rad。详见 [完整pilot结果](phase8_4_structured_input_results.md)。本次正式检查将直接约束这类单项退化。

## 固定范围与预算

| 项目 | 本次范围 |
|---|---|
| 构型 | base、long_body、heavy_moderate、asymmetric、uuv6、uuv6_angled、uuv4、uuv4_angled |
| 预检 | 各1条PRBS、seed8450、32控制区间；共8条 |
| fit | 各3条，seed8451/8452/8453对应PRBS/multisine/chirp；共24条 |
| validation | 各3条，seed8461/8462/8463；共24条 |
| test | 各3条，seed8471/8472/8473；共24条，验证及模型冻结后才访问 |
| 正式长度 | 每条512控制区间，约8.53秒；每控制区间2个1/120秒物理子步 |
| 总量 | 80条含预检；37,120控制区间／74,240物理子步 |
| 控制 | direct bounded 4D pre-TAM；两个子步保持同命令；幅值[0.04,0.04,0.08,0.2]，PRBS保持4区间 |
| 初始化 | authored_static_v1 + declared_v1 + episode_local_v1；单环境、固定构型、无流场/噪声/DR |
| 模型 | 自由输入/固定物理输入 × 线性/非线性字典 × 17训练范围；共68个固定拟合，无搜索 |
| 资源上限 | 采集进程累计180分钟，每例10分钟；CPU分析60分钟；结果及传输工作目录4GiB |

GPU用于真实Isaac仿真。当前模型是小型矩阵辨识，CPU SVD已有可复现实现；不会为了使用GPU而另换神经网络或扩大候选空间。磁盘在病例边界检查，单例运行可能短时越过总量检查值；native timeout限制单例持续时间。上传的77.5MB bundle计入传输目录预算。

## 提前固定的继续与晋级条件

主候选为nonlinear_fixed：已知直接受力增量、完整提升状态算子、已知位姿推进与投影。它是结构约束的混合受控提升预测器；不宣称全局有限维常矩阵Koopman闭合。

20/60/128步均检查全部控制起点，终点及整条路径分别计算；512步检查固定起点全程稳定。persistence保持起点状态不变。各episode误差除以同episode persistence误差与预设0.01工程下限中的较大者，再按episode/构型等权汇总。

- 主候选的必需评分全完整，512步不越界；任何必需输入/来源/语义失败均停止。
- 总体归一化宏误差≤1.00，每个构型综合≤1.05；**每个构型×每项误差≤1.10**。
- 综合速度误差≤0.90，且每构型至少2/3验证种子改善。
- 对完整的同信息linear_fixed，非线性总体比值≤0.90，每构型≤1.05；对照不完整时不能宣称数值胜利。
- validation只按固定门决定继续，不调参。通过后冻结68个实际模型、数据/源码哈希与验证结果，test只评价一次。
- 测试后按构型分层、整episode配对bootstrap 2000次，seed8490；三个块的区间只是探索性描述，不把重叠滑窗当独立样本。

若base姿态弱项再次触发新门，就保持NO_SELECTION，不能因为其他指标平均好而放行。正式512步、更广构型和闭环能力目前尚未证明。

## 可核对的执行身份

- 实验ID：`phase8.4-structured-formal-v25-20260912`。
- 独立采集源码：`0986465e92124f1269cbe844327de9189d0513e6`；原工作区HEAD未提交或改写。
- Bundle SHA256：`6356c2fa24bd4e06cccbc3be1763fce8e16446e539ba4014774747b7a33d7dc3`，77,500,334 bytes，385文件。
- 角色协议canonical SHA256：`faa9b1a36048561bab97de5996bdf81057cd4ac66b343f3750327c80364a6584`。
- 分析策略canonical SHA256：`663fd52f9788dd5aacae79a062885954d569d020ca3cf8eea72a3e4363887e96`。
- [角色协议](../protocols/phase8_4/role_protocol_proposed.json)、[分析策略](../protocols/phase8_4/analysis_policy_proposed.json)、[pending记录](../protocols/phase8_4/d23_approval_pending.json)、[包及检查结果](evidence/phase8_4/runtime-package-20260912-r8/package.json)。canonical SHA使用排序紧凑JSON，不是格式化文件原始SHA。

采集包源工作区与独立克隆各229项相关测试通过；80病例dry-run、pending入口拒绝、shell语法和来源哈希核对通过。70个plant源文件与实际验收r7不变。2026-09-13，r8的8条真实GPU预检及48条fit/validation已全部完成原生退出、语义与本地归档验收，累计采集进程耗时1,339.02秒，约22.32分钟。正式68模型评价、bootstrap和pre-test-freeze生成器已在e2中补齐并于首次拟合前独立冻结；固定验证现已启动。test仍未采集，入口要求真实模型freeze。采集源码和分析执行源码分别绑定，采集成功不代表模型已经合格。

## 这次批准的含义

批准上述协议、策略、采集源码及预算后，由本任务继续负责上传、预检、分阶段采集、固定拟合/评估和独立核验。任一硬门失败停止相应后续阶段并报告；不自动换种子、扩预算或修改门槛。批准记录仅绑定来源与协议，不声称密码学身份认证。

它不等于批准模型晋级。Phase9需正式合格handoff，随后才验证MPC控制收益、环境适配和Agentic增益。Phase8.2与两轮pilot负/正证据保持原状。执行细节见 [runbook](phase8_4_formal_runbook.md)，后续任务见 [08.4-05](../.planning/phases/08.4-conditional-identification-experiment/08.4-05-PLAN.md)。


## 2026-09-13：规模依据与批准后的执行说明

这组数值适合作为本轮受控实验，不是统计功效计算得到的充分样本量，也不是外部强制规定。8构型来自项目现有公开目录，检验参数与拓扑变化；72条来自8×3激励×3角色，各角色每种激励只有一个种子，种子与激励族尚未完全交叉。因此bootstrap只作探索性描述，不能宣称广泛平台的统计显著性。

512控制区间约8.53秒，扩展了pilot的128区间，但不能等同长航程可靠性。3小时采集、1小时CPU分析、4GiB是停止预算；不是预计必须花完的配额。实际8条短预检的native采集总耗时104.80秒，另有源码/环境准备时间。磁盘是病例边界检查而非硬配额。

实际分段为8条预检→48条fit/validation→验证门及真实模型冻结→至多24条test。验证失败就不采test；72条是本次完整正式矩阵的上限。D-23用于记录本次具体范围和防止结果出来后改规则；用户2026-09-13的确认已提供本次授权，不再重复询问同一许可。

在首次正式拟合/验证结果打开前明确分析口径：nonlinear_fixed全部local/pooled/heldout算子都须完整且512步稳定；heldout迁移及拟交接pooled模型分别接受相同的20/60/128逐项精度门。local精度保留作诊断，不替代pooled交接。数值阈值和候选空间保持原策略。

证据：[具体批准记录](evidence/phase8_4/formal-approval-20260913/decision.json)、[预检拉回验收](evidence/phase8_4/server-formal-20260912-r8/preflight/acceptance.json)。

正式评价源码e2为`3bdde17883158d085bddda97d50a65deef4d6366`，源工作区/独立克隆各266项相关测试通过；与r8共享的385文件全部不变。冻结发生在首次正式模型拟合前。e1仅在本地反例测试中发现零误差平手处理问题，未用于正式拟合，已保留并由e2取代。见[评价源码冻结](evidence/phase8_4/evaluator-package-20260913-e2/pre-fit-freeze.json)。

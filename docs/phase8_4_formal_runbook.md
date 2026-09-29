# Phase 8.4 v25 正式运行入口

**最新执行结论（2026-09-13）：正式验证NO_GO／NO_SELECTION，68模型及2280评分已独立核对；24test未采，无handoff。见[正式结果与失败定位](phase8_4_formal_validation_results.md)。下方运行步骤保留供复现，不能据此重启已停止实验。**

状态：2026-09-13具体D-23已批准，8条预检及48条fit/validation已通过真实GPU采集和本地逐文件、逐子步验收；冻结e2评价正在运行，test保持关闭。命令按已批准 [提案](phase8_4_formal_d23_proposal.md) 分阶段执行。一般服务器/训练授权已经存在，不重复请求；协议、分析策略、采集源码或预算若改变，须在实施前处理对应的新具体决定。

## 1. 本地检查和身份

源码包位于 `.pytest-tmp/phase84-runtime-20260912-r8/EasyUUV-phase8-4-formal.bundle`，独立clone位于同目录`verified-clone/`。当前精确SHA与测试结果以 [package.json](evidence/phase8_4/runtime-package-20260912-r8/package.json)、[test-results.json](evidence/phase8_4/runtime-package-20260912-r8/test-results.json)、[proposal-checks.json](evidence/phase8_4/runtime-package-20260912-r8/proposal-checks.json) 为准；root和clone测试均为Isaac-free相关检查，不能替代第3节真实预检。

重新准备时从EasyUUV根运行`.venv/Scripts/python.exe -X utf8 -B -m pytest -q -p no:cacheprovider`，测试范围用test-results.json中的明确列表及新的仓库内basetemp；不要跑旧正式实验。不得修改已冻结r8包；若确需改采集实现，创建新r号并重新测试/绑定，不复用既有SHA。

批准前保持`protocols/phase8_4/d23_approval_pending.json`为pending。收到明确批准后另建`d23_approval_approved.json`，仅把decision改为approved，保留精确role/policy/source字段；记录实际用户决定来源，不伪称身份认证。批准记录及协议复制到远端传输目录中的`d23_approval.json`、`role_protocol.json`、`analysis_policy.json`。

## 2. 远端独立克隆与安装

SSH为`agentic-AUV`；不改现有r7运行目录，不重启/杀死其他作业。先确认GPU可用。本次唯一源码根为`/root/EASYkoopman-phase8-4-formal-20260912-r8`，传输根为`/root/phase84-transfer-20260912/formal-r8`。两个新根若已存在，先读取失败/运行记录，不覆盖、不自动重新执行。

把经SHA确认的bundle、expected-source-commit.txt和三份批准后JSON传到传输根。`git bundle verify`后clone到上述源码根，验证HEAD、385源文件SHA及`git status --porcelain`为空。外部协议文件不进入源码Git树。

锁定运行时：RTX4090；IsaacSim5.0 / IsaacLab2.2.1，conda`isaaclab`、Python3.11。`scripts/phase6_server_preflight.sh`负责真实release/dirty-patch核验，`scripts/phase6_offline_install.sh`负责已知离线依赖/当前源码editable绑定；精确运行时commit及patchSHA写在新服务器脚本中。任意不一致停止，不能通过放宽版本检查继续。

## 3. 三个显式阶段

在远端源码根执行；每个阶段必须前一个验收完成，不能把三个命令接成无条件整批任务：

```bash
bash scripts/phase8_4_formal_server.sh preflight
```

它先验证新批准、协议/策略、干净源码及文件哈希，再激活conda/安装并启动仿真。8个预检实际native exit全0、语义/时钟/初始化/质量惯量/因果执行器重建全过后，程序才产生`preflight-gate.json`。任何case失败立即终止，保留日志、原生exit、原始trace；SimApp的close可能掩盖Python异常，必须同时核验trace状态。

预检归档/拉回通过后：

```bash
bash scripts/phase8_4_formal_server.sh fit-validation
```

只采24fit+24validation。分析实现按08.4-05先完成测试和独立源码冻结；验收数据后进行68固定拟合及validation门。未通过则NO_SELECTION并保留test未访问。通过后生成包含真实模型内容、完整验证结果和所有依赖哈希的`pre-test-freeze.json`，另行重算其内容和门，禁止手写success来满足入口。

只有freeze已验收后：

```bash
bash scripts/phase8_4_formal_server.sh test
```

只采24test；使用冻结模型一次性评估，bootstrap/closeout也遵守固定策略。测试采集器验证68模型身份、验证报告、预检trace和hash绑定；这不替代模型数值、评分算术和完整性独立核验。

## 4. 预算、失败和拉回

每例native进程由timeout限制在至多10分钟（其中15秒为强制退出窗口）；累计采集进程预算180分钟由`collection-budget.json`跨阶段记账。意外中断保留该例完整时间预留，不归零预算。CPU分析60分钟由后续正式分析驱动器设置外部超时。磁盘在病例开始检查，达到4GiB即停；该限制是病例边界检查，非文件系统硬配额。

已开始的stage不能自动重跑；runtime预检输出和阶段目录也排他创建。需要修复时先检查真实失败与已用预算，保留证据，另行修订源包/计划，不往旧成功根续写来掩盖失败。

各阶段结束后把原始trace、native exit/log、source/runtime预检、协议/批准/策略、脚本/真实加载源码、验收结果逐文件SHA和相对路径写入新的inventory，再创建独立tar.gz及归档SHA。打包文件本身不纳入自身inventory；拒绝绝对/逃逸路径、符号链接、重复成员。传到本地新的`docs/evidence/phase8_4/server-formal-20260912-r8/<stage>/`后，独立重算归档SHA、完整文件集和逐文件SHA，并调用`validate_formal_trace_v25.validate_trace`逐条验收。不得手工预建canonical通过状态，未验收数据不进入拟合。

新canonical结果根仅为`source/results/phase8.4-structured-formal-v25-20260912`；旧Phase8/8.1/8.2与pilot不可覆盖。运行status、raw语义通过、inventory/pullback通过、预测selection和模型handoff分别报告。正式驱动器为`workflows/evaluate_formal_v25.py`，执行源码冻结于e2，见[首次拟合前冻结](evidence/phase8_4/evaluator-package-20260913-e2/pre-fit-freeze.json)。首次验证用已存在的`.pytest-tmp/phase84-formal-transfer-r8/run-validation-e2.py`启动；已有运行须读取STATE/HANDOFF及实际终止状态，不重复执行。独立closeout在实际验证结果产生后完成，GO仍需真实freeze导出/导入、条件test与合格handoff，不能把采集成功描述为全流程完成。

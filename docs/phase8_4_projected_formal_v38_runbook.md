# v38冻结投影预测：正式执行手册

## 当前执行补充：r23资源修订（2026-09-20）

用户明确批准“批准，仅增加15分钟分析额度”（call_sJQJ3xtYoXpGOmGFLbdYj1Hn question0）。r23仅将累计分析上限3600增至4500秒；原72笔账本、2290.438407秒分析与1510.428232秒采集全部继承，原两个native1及其修复证据保留。8条预检和24条validation已完成，后续只运行原定24条test（seed9500–9523），18冻结模型零拟合。原协议JSON及科学门保持原字节，资源修订另由resource-approval、resource-parent-budget、resource-amendment及新freeze绑定。以下r20/r21/r22步骤是对应历史版本的程序，不覆盖此修订。

使用`workflows.package_projected_resource_v38 build/freeze`。先build，再分别从原树和r23源码运行本文件规定的local_preflight全部测试，再freeze。r23读取r21 validation数据和r22 validation评分，分别保留其原source/freeze身份；独立复核GO凭证逐字节继承。test收集、评分与复核使用r23。新远程目录为`/root/EASYkoopman-phase8-4-projected-formal-v38-r23`及`/root/phase84-projected-formal-v38-r23`。不得在r22原目录改源码或重跑validation。

新源码的两份未改动USD物理资产通过硬链接共享r22的同一文件内容；其余源码独立复制。只在新且不存在的路径建立链接，禁止写入共享资产，制作前后逐项验证原r22清单。两端4GiB上限保持；存储记录同时报告路径大小总和与按同一主机(device,inode)去重的实际文件内容字节。仅真实硬链接计一次，内容相同的独立副本仍分别计数；两台机器之间不去重。保留32MiB元数据/增长余量，磁盘检查禁止符号链接。源包和旧证据均不删除。测试原始归档/解压仍按完整独立文件大小预留。

服务器安装采用共享Git对象的`clone --no-checkout`和明确的源文件清单；两资产校验后链接，其余文件从已验证delta提交取出。运行前对照新freeze及继承账本、原r22静止状态、原24组validation GO及两端磁盘实测；先release-test再由原server.sh监督24条test。各操作继续串行预留和结算，超过4500秒或任一精度/证据门失败即停止后续阶段。


## 当前修订：r22验证数据的数值复核

原24条validation已经采集完成。r21首次Windows验收native1及688.434756秒累计分析账本保留；随后219.391秒有界诊断确认24条全部通过原物理门，只有uuv6_angled/chirp的转速最大残差摘要两端相差1.16793e-5。转速摘要容差统一采用既有缓存转速检查的1e-4；wrench仍1e-5，原物理限值仍1e-3。最大残差的变化不大于逐点重算值的最大变化，故两项检查应使用同一界。

使用`workflows.package_projected_validation_repair_v38`依次build、reaudit、freeze，包为新r22目录，父包为不可变r21。build后先用现有local_preflight运行原树和新源码的完整清单。冻结前若发现候选接线问题，保留先前Git提交、bundle和测试日志，通过明确的新候选提交修正；package中的test_suffix绑定随后完整重测输出，不能用旧测试充当新源码验证。reaudit从新源码检查现存`validation/raw`，参数`--diagnosis`为完整24条诊断目录，监督器最多600秒且始终受原3600秒余额约束。它只写新的复核凭证。freeze保留前69项尝试和两个native1，追加219.391秒诊断及完整复核实际耗时。无重采、重拟合、选种子、改变精度门或重置预算。

r22服务器根为`/root/EASYkoopman-phase8-4-projected-formal-v38-r22`与`/root/phase84-projected-formal-v38-r22`。旧r20/r21源、数据和账本完整保留。r22通过stage_directory直接读取原r21的validation目录和归档，正式复核凭证原样复制；不建立符号链接、不复制原轨迹、不修改旧采集身份。评分结果记录r22执行身份，而episode保留r21采集身份；`stage_identity`显式校验两者。新的test采用r22身份，仅在24条validation完整评分、原精度门和独立算术审计全部通过后开放。r22拒绝preflight/validation重采。

独立validation算术审计新增`--transfer <r22-inputs>`以验证执行源码与旧采集数据的映射；仍读取原raw、原命令和旧模型。评分模块只修改worker的数据身份接线，`score_episode`及其余函数的AST必须与r21一致。先量测所有r20/r21/r22两端文件的总量再上传或执行；保留旧失败，4GiB和3600秒累计上限持续生效。

以下r21/r20步骤均为历史记录，不可照旧重跑。

## 当前修订：r21数值验收修复（2026-09-14）

原56病例/18模型/5400秒采集/3600秒分析/4GiB范围已获用户批准；用户随后明确授权用小容差替换浮点完全相等。r20已有8条预检，首次拉回native1保留；不重复收集这些病例。以下原r20制作/执行步骤保留为历史说明，不能原地重跑。

修复仅改变审计/运行管理文件。`package_projected_repair_v38.build`验证父537文件，拒绝物理、控制、数据适配、预测器、模型或协议/科学门的任何变化；建立一个独立r21 checkout和依赖r20的delta bundle。r20源码、bundle、原数据和失败账本均保留。

1. 在原树用`python -B -m workflows.package_projected_repair_v38 build --root <root> --parent <r20-package> --directory <new-r21-package>`建立隔离包。按现有local_preflight分别运行原树与r21源码的完整测试清单，输出到新包的`preflight-root`/`preflight-clone`。
2. 从r21源码调用该模块的`reaudit`：输入现存r20的`preflight/raw`、失败live-budget、累计诊断账本及缓存差异报告。监督器最多120秒；原失败费用、已有诊断、缓存探针和本次复核全部相加。复核沿用原物理检查，通过显式审计源码修订比较派生摘要；只产生新的父预检审计凭证，不覆盖原失败输出。
3. `freeze --directory <r21-package>`只在两份完整测试和真实复核native0后生成修复freeze。新账本保留旧18条记录（含第18条失败native1），追加已计费用；新的失败仍阻止下一阶段。所有费用共享原上限，不重新获得预算。修复授权文件绑定原D-23批准、用户本轮容差指令和新freeze；不是新增科学实验授权。
4. 新远程源码为`/root/EASYkoopman-phase8-4-projected-formal-v38-r21`，transfer为`/root/phase84-projected-formal-v38-r21`。保留r20根，通过共享父Git对象建立新的checkout，再导入delta并核对新HEAD、全部文件和clean状态。不复制整套旧预检数据、不删除旧文件节约空间。
5. 复制修复inputs和生成的父预检审计凭证；父凭证在原transfer写为此前不存在的`preflight-pullback.json`。r21 release重新核对原8条trace/native/source身份及修复凭证。拒绝r21的preflight重采，只允许原已批准的24条validation及通过原门后的24条test。

摘要数值容差见[修复说明](phase8_4_v38_tolerance_repair.md)。评分缓存中状态/命令/时钟仍精确一致；转速比较绝对容差1e-4、加速度换算为wrench后比较绝对容差1e-5。完整物理检查仍先执行，条件预测复算使用已独立核验的同一份生产端缓存。角度指标重算绝对容差1e-7 rad，其余指标保持1e-11绝对/1e-9相对；聚合结果只允许1e-12绝对/1e-9相对浮点误差，GO布尔值、计数及所有科学门保持严格一致。这些容差在正式validation前冻结。

2026-09-14。承接[正式提案](phase8_4_projected_formal_v38_proposal.md)与[08计划](../.planning/phases/08.4-conditional-identification-experiment/08.4-08-PLAN.md)。本手册和本地包不构成新D-23批准。模型固定为18个旧v30文件，零新拟合；完整提升闭合、MPC与Agentic贡献均未获证明。

## 1. 本地源码包与准备门

在原工作树只创建新版本文件和独立包，不提交或清理原工作树。以下命令的`<package>`必须是EasyUUV下`.pytest-tmp/`内尚不存在的专用目录。失败目录保留，不能覆盖成功或部分输出重新冒充首次尝试。

```powershell
Set-Location -LiteralPath 'E:/code for project/Agentic AUV/EasyUUV'
& '.venv/Scripts/python.exe' -X utf8 -B -m workflows.package_projected_v38 build --root . --directory '<package>'
& './scripts/phase8_4_projected_v38_local_preflight.ps1' -Python 'E:/code for project/Agentic AUV/EasyUUV/.venv/Scripts/python.exe' -RepositoryRoot 'E:/code for project/Agentic AUV/EasyUUV' -OutputDirectory '<package>/preflight-root'
& '<package>/verified-clone/scripts/phase8_4_projected_v38_local_preflight.ps1' -Python 'E:/code for project/Agentic AUV/EasyUUV/.venv/Scripts/python.exe' -RepositoryRoot '<package>/verified-clone' -OutputDirectory '<package>/preflight-clone'
& '.venv/Scripts/python.exe' -X utf8 -B -m workflows.package_projected_v38 freeze --directory '<package>'
```

preflight运行`phase8_4_projected_v38_tests.json`的完整清单，保留原生退出、日志、时间、实际测试文件。源码快照包含运行依赖、18模型、历史锚点和实际使用列清单；bundle必须能离线克隆、哈希一致且clean。freeze只有在原树及clone测试成功且被测字节未改变后生成。`authorization-pending.json`不能用于采集；`verify_snapshot`只检查完整性，运行入口仍要求真实新批准的`authorization.json`。

将实际包清单、两份测试报告和freeze复制到新的`docs/evidence/phase8_4/projected-formal-package-v38-20260914-r20/`，保存真实路径和哈希；该目录只表示本地准备。源码包出现失败就先解决原因并建立新的包身份，不给失败包签就绪状态。

## 2. 新D-23与服务器准备

本地工作全部就绪后，按NID-02请求一次针对新freeze的决定：8预检＋24validation＋GO后24test，90分钟新采集、每例300秒；60分钟新分析墙钟、最多4个CPU进程；4GiB新实验文件总量。用户批准后才把该实际回复引用、`authorized_by=user`、`decision=approved`、freeze SHA和原resource_cap写入`authorization.json`。不得套用v25旧批准。

用户此前允许关闭服务器。正式准备好后告知需要开机；有已确认运行句柄时只观察原进程，不因观察超时重启。读取当前SSH配置后连接`agentic-AUV`，不要仅凭旧地址改网络。确认无本任务遗留进程、新目录均不存在、磁盘充足。

专用远程路径：

- 源码：`/root/EASYkoopman-phase8-4-projected-formal-v38`。
- 输入、账本、运行证据：`/root/phase84-projected-formal-v38`。
- Isaac：`/root/IsaacLab/isaaclab.sh`，conda Python `/opt/conda/envs/isaaclab/bin/python`。

上传已核验bundle和inputs；远程核对bundle SHA后离线clone到上述新源码根，HEAD必须等于freeze.source_commit、tracked/untracked均clean。只使用包内脚本；不覆盖r17/r18/r19/v25。`phase8_4_projected_v38_server.sh`在任何新采集之前验证新D-23、数据角色、预算、固定IsaacLab2.2.1父提交/HEAD/补丁及离线安装；不升级运行环境。

## 3. 预算与磁盘的具体口径

- `budget.json`是唯一新实验账本，所有操作串行预留与结算。native采集含启动、结束和失败等待，累计≤5400秒，每例≤300秒。监督器TERM后最多15秒KILL余量包含在该300秒内。
- 在线语义验收、归档、独立拉回验收、正式评分和独立分析复核均计入3600秒分析墙钟。四进程按监督器墙钟记账，不冒称各CPU核心秒数。不同操作与失败不因换编号免计。
- 本地source测试、源码制作及传输时间单列为准备/传输，不占采集或分析额度；记录实测时长。v36/v37等历史账本另存，重叠账本不可相加。
- 4GiB检查覆盖新远程源码/transfer和本地新包、拉回/分析副本。开始每个阶段、复制前及分析前实际测量两端总量；任何一步预计复制/解压后达到上限则停止，不删除旧证据腾挪。运行中的每病例/worker检查远程用量；阶段开始前给当前阶段预留本地固定用量及预计新增空间，不能仅看单机空闲容量。
- 本地拉回工具以`--remote-bytes`接收刚测得的远程用量，自动加入同一专用拉回根及将要解压的字节。运行者还须计入专用拉回根以外的新源码包和证据副本；把这些固定本地字节加入`--remote-bytes`保守核算，并在操作记录中分别记录真实remote_bytes与additional_local_bytes，不能把合计冒称纯服务器测量。
- 每次在本地审计前，从静止服务器复制最新账本并记原SHA。审计后仅在服务器账本仍等于该SHA且无运行任务时，把本地结算账本复制回去；不合并分叉账本，不使用归档中仍处于预留状态的旧budget作为live账本。

## 4. 每个数据阶段的实际执行与拉回

在远程源码根执行，首次role为`preflight`，通过下述拉回后才能用`validation`。`test`仅第6节批准开放后执行。

```bash
bash scripts/phase8_4_projected_v38_server.sh preflight
/opt/conda/envs/isaaclab/bin/python -B -m workflows.projected_archive_v38 archive --transfer /root/phase84-projected-formal-v38 --stage preflight
```

保留采集原生返回码、逐病例日志、collector-exit、完整trace、在线语义结果、stage-status、runtime目录。stage完成仍是`pending_pullback`。归档包含源码清单及字节、固定inputs、真实数据、运行时文本及IsaacLab补丁；不手工制造成功状态。

新本地拉回根例如`docs/evidence/phase8_4/server-projected-formal-v38-r20/`。每个role是新子目录，复制`<role>-evidence.tar.gz`、`<role>-archive.json`及最新live budget。对照远程SHA，确认两端磁盘口径后，**从verified-clone根**执行：

```powershell
& 'E:/code for project/Agentic AUV/EasyUUV/.venv/Scripts/python.exe' -X utf8 -B -m workflows.projected_archive_v38 accept --stage preflight --directory '<pullback>/preflight' --sha256 '<remote archive SHA>' --budget '<pullback>/live-budget.json' --remote-bytes <remote_plus_additional_local_bytes>
```

验收检查每个归档字节、固定源文件/模型/运行时、真实原生退出、完整病例集合，再重新加载全部trace验证物理、实际参数、命令/转速因果历史及子步时序；与在线语义结果逐项相同才写acceptance。将原字节`acceptance.json`复制为服务器`preflight-pullback.json`并同步结算账本，之后运行validation。role变更采用同一流程，不换种子、不增加病例。

native失败或语义拒绝时立即停止后续角色；允许在剩余资源内归档和审计失败档案，但只产生rejection，不提升可用前缀。若预算已耗尽，仅保留现有输出并报告，不重置账本。异常结束先查原进程是否仍活着，不重跑同名脚本。

## 5. 正式评分与独立复算

只有validation真实拉回被接收后，在远程clean源码根运行：

```bash
/opt/conda/envs/isaaclab/bin/python -B -m workflows.evaluate_projected_formal_v38 --stage validation --transfer /root/phase84-projected-formal-v38 --workers 4
```

加载18个冻结模型，不拟合。每role必须1152条：576条件预测＋144连续512全段＋432策略前缀。保存逐病例48条分数、六条路径的full/policy预测数组、实际输入缓存、全部子进程原生退出与文件哈希。512分块连续携带自身预测状态及命令/转子/时钟历史，无真实状态重置；策略未来命令来自自身预测状态。

结束并确认无worker后，记录服务器`validation-analysis/result.json` SHA、最新账本SHA和磁盘实测；把整个analysis目录复制到同一专用本地拉回根的`validation-analysis/`。从verified-clone运行：

```powershell
& 'E:/code for project/Agentic AUV/EasyUUV/.venv/Scripts/python.exe' -X utf8 -B -m workflows.audit_projected_v38 --raw '<pullback>/validation/raw' --analysis '<pullback>/validation-analysis' --budget '<pullback>/live-budget.json' --result-sha256 '<remote result SHA>' --remote-bytes <remote_plus_additional_local_bytes>
```

独立入口核对原数据与缓存、所有worker/模型/源文件绑定；576条条件预测由冻结预测器重新递推、独立累加误差；576条全段/策略指标由保存数组逐物理步重算，最后重算全部门和配对bootstrap。它不调用生产评分聚合例程，但复用冻结预测器数学实现；未完整重新生成全部策略命令序列，不能称为两个独立模型实现。任何部分输出/修改后的误差/错误角色均不产生通过凭证。

把原字节`validation-analysis-audit.json`复制回transfer同名文件，并按SHA同步最新结算账本。审计通过只证明算术/绑定一致；`evaluation_pass=false`仍是NO_GO，禁止test。

## 6. test开放和关闭

validation固定门GO且独立审核完成后：

```bash
/opt/conda/envs/isaaclab/bin/python -B -m workflows.projected_archive_v38 release-test --transfer /root/phase84-projected-formal-v38
bash scripts/phase8_4_projected_v38_server.sh test
```

release重新计算门，并绑定validation结果/分数/原数据验收/独立数组审计及模型清单，采集入口再次核对全部绑定。test沿用第4、5节采集、归档、独立拉回、评分和复算流程，role改为test；只评价一次，不调参。

最终同时报告validation与test全部构型和强基线，保留失败、未执行病例和bootstrap边界。通过正式门后仍须单独审查匹配输入/状态合同及科学主张，才可能交接Phase9；未通过则明确NO_SELECTION/有限关闭。与同D/Q参数方程等价、完整算子负证据、尚无MPC/Agentic结果必须保留。

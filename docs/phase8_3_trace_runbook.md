# Phase 8.3 有界trace：本地准备与待执行门

**当前状态以[初始化修复](phase8_3_initialization_repair.md)为准；以下首批准备命令/离线状态是历史执行记录。** 新修复模式需显式`--initialization authored_static_v1 --inertia-sync declared_v1 --reset-mode episode_local_v1`；新run-id和tested bundle仍必需，不能复用下方旧目录重复执行。

2026-09-12更新：用户已接受按控制器/控制区间方向继续；两次SSH均在握手阶段超时，用户确认服务器离线并要求需要时告知。未启动Isaac。当前原工作区仍有未提交修改；已另建独立源码快照bundle、重克隆并通过187项相关测试，原仓库HEAD/分支没有改变。服务器开机后先执行本文的64区间对照及实际环境预检；不复用Phase8.2的formal D-23或结果目录。

## 已有入口

- [本地失败诊断](../workflows/diagnose_koopman_v23.py)：只允许固定候选及35个source fit/validation episode，输出到新 `tmp/phase8_3/<run-id>/report.json`。本轮只拟合了一次；不要仅为换输出路径重复回放。
- [逐子步观察器](../workflows/control_trace_v23.py)：context内安装实例方法观察钩子，结束/异常时恢复。关闭时无子步钩子。`_get_dones`采样发生在自动reset之前；这一顺序需要与实际加载源码核对。
- [单case trace驱动](../workflows/trace_control_v23.py)：默认仅打印请求；`--execute`才进入clean-source检查与Isaac。当前只验证了准备入口、动作生成及记录器本地合同，未验证完整Isaac驱动。

在repo根用项目Python打印请求，不启动Isaac：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m workflows.trace_control_v23 --run-id trace-base-8201-on --trace on
.\.venv\Scripts\python.exe -X utf8 -B -m workflows.trace_control_v23 --run-id trace-base-8201-off --trace off
```

## 第一批具体请求：仅64个control interval

两次独立环境运行：base、seed8201、cold、恒定raw action `[0.1,0.1,0.1,0.1]`、legacy reset、各32步。physics dt=1/120、decimation=2、control dt=1/60。环境eval、无随机化/传感噪声/波浪，关闭episode时间上限但保留物理边界终止。

服务器目标目录固定为 `/root/EASYkoopman-phase8-3-trace-20260912`，尚未创建，若已存在则停止并保留。输出固定为该目录内 `tmp/phase8_3/trace-base-8201-on/` 与 `...-off/`，本地拉回使用新ID。包内提交是单独快照仓库的身份，不是原仓库历史提交。不能拿旧远端工作区直接执行。

当不可变tested bundle、适用的服务器依赖/离线预检、加载路径检查和具体启动授权具备后，命令为：

```bash
python -B -m workflows.trace_control_v23 --run-id trace-base-8201-on --trace on --execute
python -B -m workflows.trace_control_v23 --run-id trace-base-8201-off --trace off --execute
```

这不是后台任务，不自动调度下一批。不要调用会写 `source/results/koopman_phase8_2/` 的旧collect/evaluate脚本。失败输出也保留；源身份检查或建环境前失败时可能没有trace文件，运行终端错误同样须留存。

## Gate与尚未完成的运行检查

1. 比较两次 `initial_boundary` 与 `observed_start_boundary` 的实际物理、执行器、controller/RNG配置，不以相同seed代替状态匹配。要求两次动作序列相同；各32步边界状态及telemetry逐通道比较。名义容差1e-6、敏感性1e-5；若超限先检查可重复性，未匹配前不得进入矩阵。预算内没有自动追加重复运行。
2. 对照 `loaded_sources` 中真实EasyUUVEnv/DirectRLEnv路径及hash，确认pre一次→apply/scene update两次→dones→reset；读取的before/after不是两个reset混合出来的伪transition。
3. trace每interval必须有2条记录，token每次+1。对**每个子步**核对原始/裁剪PWM、mask、非线性速度命令、执行器state和dt；逐通道检查有限值与控制边界。驱动内已有末次快照、token和步数fail-closed检查；新增validate_interval已逐子步检查有限值、mask、clip、速度/状态、token与时间接缝，并接入on驱动；validate_pair检查初始/边界逐分量、有效配置、loaded-source hash和完整条数。它不代替独立的服务器provenance/pullback检查。
4. `telemetry.applied_wrench_6`是thruster-only；`_thrust/_moment`为传给PhysX的合力/矩，仍不等于包含PhysX重力等作用的总状态增量。状态布局：world z、wxyz、body线速度、body角速度。转速沿用执行器内部rad/s约定；须用加载的ConversionFunction与rotorConstant核实物理标定。
5. snapshots会同步GPU→CPU，不能只靠本地fixture声称真实仿真行为不变。on/off均记录control边界，只有on安装子步observer。
6. 当前trace已接入按顺序PWM驱动的N维速度估计器；初始化为已知零转速reset，truth仅作事后误差诊断、不回馈估计。另读回实际PhysX质量/惯量，缺失读回则失败。保存并验证inventory、文件hash、退出状态和拉回字节一致性后才写08.3-02-SUMMARY。

## 后续矩阵与修复对照

第一批通过后，按8.3-CONTEXT运行base/uuv6/uuv4 × seed8201/8202 × zero/constant/step/prbs × cold/warm。每case32 observed；warm先记录32步0.1恒定动作，再按同seed reset。step在index8由0变0.1；PRBS每4步改变一次，独立轴，幅值0.1；uuv4 raw yaw=0。按源码中的固定生成器执行，不根据输出换seed。

共1536 observed +768 preparation +64 on/off=2368 control intervals，暂估0.5–2 GPU小时。每case单独新run-id，**无自动矩阵循环**。trace驱动的 `--reset-mode episode_local_v1` 已可表达修复分支，但修复A/B的额外病例不在这个legacy测量矩阵内：先提交明确的替换病例/追加预算再运行。不能在同一矩阵混用reset模式后统称原plant。

## 本地验证

完整Isaac运行仍待执行。原工作区187项相关回归通过；独立包重克隆后同187项通过，覆盖Bridge、proxy、模型、指标、推进器、reset实际方法、observer、估计器、机械参数读回和源码隔离。原始构建与包身份见[package.json](evidence/phase8_3/runtime-package-20260912-r2/package.json)。脚本已通过bash语法检查；没有运行旧formal preflight，也没有声称实际服务器预检通过。

## 拉回后的自动成对验收（尚无真实trace可运行）

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m workflows.validate_control_trace_v23 --trace-on tmp/phase8_3/trace-base-8201-on/trace.json --trace-off tmp/phase8_3/trace-base-8201-off/trace.json
```

[验收实现](../workflows/validate_control_trace_v23.py)失败时退出1，成功只报告local_pair_checks_pass，不能自动授权矩阵或模型晋级。默认逐分量绝对阈值1e-6，不计算混合单位范数。若不匹配，停止查明；不得为了通过而把阈值调宽。

## 已准备的不可变源码包与首次运行

本地bundle：`E:/code for project/Agentic AUV/EasyUUV/.pytest-tmp/phase83-runtime-20260912-r2/EasyUUV-phase8-3-trace.bundle`，77,381,785字节；同目录有`bundle.sha256`和`expected-source-commit.txt`。归档索引及362文件清单在[包证据目录](evidence/phase8_3/runtime-package-20260912-r2/package.json)。目录虽在pytest隔离根中，本任务没有删除它；未来若清理，须先另存该运行包或按已记录manifest重新准备并使用新身份。

- bundle SHA256：`dfd09f314d1e20f2365277a081f8c567cab403ef8cd11c7e08aaad2c3c1c376f`
- snapshot commit：`7fd0f3cd28ca1340cef910a4b00f5e439cf69762`
- 原仓库HEAD：`782c15a68574bfd923707e499320e7b611e950bd`，分支`no-selection`。
- 包仅包含选定运行代码、资产、测试和脚本，没有旧数据集、结果、formal协议、凭据或原Git历史；不依赖原工作区未跟踪文件。

服务器开机后，先以只读SSH确认锁定环境仍在；新建独立传输目录`/root/phase83-transfer-20260912`，已存在则停止。通过scp传入上面三个文件。以下只针对这个已传输的包：

```bash
cd /root/phase83-transfer-20260912
test "$(sha256sum EasyUUV-phase8-3-trace.bundle | cut -d ' ' -f 1)" = dfd09f314d1e20f2365277a081f8c567cab403ef8cd11c7e08aaad2c3c1c376f
test ! -e /root/EASYkoopman-phase8-3-trace-20260912
git -c core.autocrlf=false clone --branch phase83-trace-snapshot EasyUUV-phase8-3-trace.bundle /root/EASYkoopman-phase8-3-trace-20260912
cd /root/EASYkoopman-phase8-3-trace-20260912
test "$(git rev-parse HEAD)" = 7fd0f3cd28ca1340cef910a4b00f5e439cf69762
timeout --signal=TERM --kill-after=30s 30m bash scripts/phase8_3_server_pair.sh
```

以上每条须在前条退出0后继续；不是可忽略错误的批处理。首次总上限30分钟（终止宽限最多30秒），每个Isaac进程上限10分钟；只观察64个control interval，相当于两次各0.533秒的仿真时间，墙钟时间主要用于启动。通过后也不会自动跑矩阵。重复运行必须新ID/保留失败目录，不能删旧文件再重试。

[首次成对脚本](../scripts/phase8_3_server_pair.sh)复用phase6的严格conda、IsaacLab版本/提交/补丁和离线安装检查；离线editable安装指向新目录，不安装/下载依赖。IsaacSim锁定5.0、IsaacLab2.2.1。脚本记录原生退出码，对输出做成对验收，并检查实际EasyUUVEnv/DirectRLEnv的路径和hash。任何环境差异、非有限值、边界终止、子步数/时钟异常、on/off不匹配立即停下。

脚本结束后（成功或失败均保留）：记录外层timeout退出码到传输目录，复制实际加载的`direct_rl_env.py`到传输证据并校验与trace所载hash一致；对`tmp/phase8_3/`现有文件生成排序SHA256 inventory，inventory放在传输目录以免自包含。将诊断结果打包到传输目录，保存archive SHA256；scp拉回新的`tmp/phase8_3/server-pair-pullback-20260912/`，先验证archive字节，再校验内部逐文件hash与精确病例集合。只有两份完整trace、各32边界、on64/off0子步、两次原生退出0、总脚本退出0、源码/加载/版本绑定全部通过，才可记录首次runtime gate通过。32步trace不能关闭整个08.3-02。


## 当前用户授权：服务器已开机，继续执行与训练

2026-09-12T17:43:01+08:00。用户明确报告服务器已开启，并授权本任务负责服务器GPU加速及后续训练。该授权覆盖必要的SSH、隔离包传输、既定有界trace、失败定位与范围内辨识修复；不需要再次询问是否开始或选择研究方向。首先执行64区间on/off gate，通过实际环境、数据与拉回验收后再推进既定矩阵和证据支持的训练。训练仍须整段fit/validation分离、保留persistence/简单线性基线与原NO_SELECTION；性能晋级不能由授权替代。GPU优先用于Isaac仿真，拟合是否上GPU取决于规模和实测收益；小矩阵回归不因有GPU就换算法。连接尚未成功：本轮首次SSH握手超时，正按现配置做一次30秒重试，尚未上传/启动仿真/训练。


## 2026-09-12实际GPU更新（优先于历史待执行状态）

见[初始化修复](phase8_3_initialization_repair.md)。固定构型初始化修复已通过真实GPU验收：原资产22.8kg造成冷启动首步响应异常，authored_static_v1在PhysX创建前写入质量/惯量；base/uuv4 seed8201及uuv6 seed8201/8202共四组冷/热对照，64个observed物理子步state11逐分量差0。新增576区间/13进程，累计1056区间/26进程；210本地及210独立克隆测试通过，105文件拉回核验通过。完成修复后覆盖审查，再用匹配轨迹比较有序子步输入与因果N维执行器状态；8.4 fresh pilot在接口决定后冻结。剩余46个旧plant病例保持未完成且不自动恢复。动态换构型/DR尚未验证，32步trace不支持60/512步性能结论。Phase8.3仍partial，8.4conditional，Phase9无handoff。

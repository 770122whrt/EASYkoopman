# v87：扩大运动场景，冻结物理基线

2026-09-29，用户授权扩大数据、检查并优化控制链、整理文档并提交PR合并。此次固定base与20%额外二次阻力，扩大运动激励范围；不新增模型家族、在线学习或Agent。

## 预定实验

- 16条训练：PRBS、多正弦、升/降扫频、平滑正反向脉冲，各4个幅值尺度0.5/1/1.5/2。幅值基准为角加速度2/1/0.5 rad/s²、升沉加速度0.25 m/s²。
- 4条验证：每种输入类型一个新种子、尺度1.25。4条新测试：每种一个新种子、尺度1.75。新种子使频率、相位、保持时间不同。只支持同类输入及其参数的轨迹泛化，不宣称未见输入家族泛化。
- 每条320个30Hz控制区间，含64区间共同启动与256区间激励；每区间4个120Hz物理子步。启动原始数据全部保留，训练只纳入第一条的256个启动转移，合计16640行。验证/测试不参与拟合或参数挑选。
- 升沉激励去均值，避免长采集持续单向加速；保留原运动/接触边界及0.6rad姿态坐标边界，失败不截断成成功。
- 物理基线仍用v81冻结文件SHA256 `82d7f0c1c20faa3299d5b3f9f81a64c5a66888c255a6ceb953bba5384c8cd0f3`，不学习任何v86/v87数据。
- Koopman与结合模型使用原38维提升，同一新拟合A/B；结合另拟合残差R。正则0.001固定，只拟合一次。每个真实控制时刻初始化；预测时域自主传播，无解码重提升、未来真值或隐藏扰动输入。

预测从384/640/896/1152物理步出发，各80步。每个模型分别记录16个验证及16个测试窗口；每窗深度RMSE≤2mm、姿态RMSE≤4mrad。报告全部窗口及实际速度范围，不删掉外推或失败窗口。旧v86扫频保持已查看的历史负结果，不改称新盲测试。

离线求解固定选新验证的PRBS和扫频两条，各384/896步，共4个不同运动状态×3模型。相同历史重建推进器、相同任务/代价/约束/CPU预算。核对NumPy/CasADi，独立复核原始候选及最终计划；保留超时、不可行与回退来源，禁止仅凭候选存在准入。四个起点若重复则拒绝多工况结论。

三臂全部通过预测与求解后，运行相同初态、任务、扰动的pitch_pos/pitch_neg各2秒闭环，共6例。模型参数冻结，保留原depth4_h20、PWM/变化率/支持域/接触限制和同步非实时执行。失败先保留、讨论，不能看新测试重调。未完成2秒配对前不扩大构型或控制时长。

## 控制链检查与本轮修复

独立检查确认完整提升传播、因果推进器历史、反馈预演与执行时钟合理。本轮修复求解准入对坏候选的误判，独立验收绑定源码清单并复核原始候选；改变求解检查起点，避免重复启动状态。现有支持域属于共同控制限制，不等于物理参数重校准；不因扩大训练而自动放宽安全约束。

v86/v87共用采集与原始验收实现，通过显式协议参数区分；旧v86默认语义保持。共享代码修改后复算旧证据须使用其保存的release-r2源码包，不能声称新源码符合旧清单哈希。版本文件说明协议差异，不把旧模型作为当前有效模型。

## 执行

先本地定向测试与打包，主服务器新隔离目录部署并复测。先最大幅值扫频训练pilot，再采集其余固定病例。数据采集可最多两个独立进程组并行，单例600秒硬上限；不与离线求解或闭环并行。模型拟合、预测和求解按顺序运行，退出回执保留。

```text
python -B -m workflows.prepare_disturbance_v87 --output RELEASE
python -B -m workflows.collect_disturbance_data_v87 --case CASE --manifest v87-manifest.json --output DATA/CASE
python -B -m workflows.fit_disturbance_v87 train --data DATA --manifest v87-manifest.json --output model.json
python -B -m workflows.fit_disturbance_v87 validation --data DATA --manifest v87-manifest.json --model model.json --output validation.json
python -B -m workflows.fit_disturbance_v87 test --data DATA --manifest v87-manifest.json --model model.json --output test.json
python -B -m workflows.solve_disturbance_v87 --data DATA --manifest v87-manifest.json --model model.json --model-sha SHA --assets ASSETS --output solver.json
```

闭环入口`workflows.collect_disturbance_control_v87`要求完整新验证、测试和求解报告；验收入口`workflows.validate_disturbance_control_v87`额外要求`--manifest`。沿用v86其余参数，native exit必须从外部监督器读取。原始数据、日志、模型、指标、源码清单按逐文件哈希回传。本轮结果写入[v87报告](phase9_diverse_v87_report.md)，无论正负均保留。

## 本轮执行收尾

24条全部采集并验收。所有训练轨迹验收后开始一次拟合，此时最后一条测试仍在独立采集；训练只读取训练角色。模型冻结后评估验证/测试，之后离线求解，未依据测试再次训练。

用户确认保留预定三臂全部通过门限。预测和求解总门限未通过，本轮不运行闭环，完成结果整理与PR合并。后续若研究更大范围控制支持域，需要另行明确协议；本次不放宽约束。实际数字见结果报告。


运行位置更新：上文路径与分支是原实验时点信息。当前入口见 [运行说明](../../../docs/runbook.md)，原始材料集中于本地 `results/history/`，参数、门限与采集身份保持原值。

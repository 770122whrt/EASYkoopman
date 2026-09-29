# 加扰动与物理结合：v86

2026-09-29。只执行用户确定的两步，Phase9 / 09-04 保持开放。旧负结果和原始轨迹不改写。执行结果见[结果报告](phase9_disturbance_v86_report.md)：8条真实数据验收通过，但学习两臂扫频预测门失败，停在2秒闭环之前；本文件保留预定协议。

## 固定方法

基础构型 `base`，静水环境的原二次阻力额外增加20%：`tau_extra = -0.2 Dq |nu| nu`。固定偏差不按测试表现扩大。零速度时附加阻力为零，因此短任务可能没有明显收益，结果如实记录。

物理基线为旧 v81 的 `pooled__physical.json`，它曾用旧数据校准，本轮不重校准。文件 SHA256 为 `82d7f0c1c20faa3299d5b3f9f81a64c5a66888c255a6ceb953bba5384c8cd0f3`。三臂使用相同 MPC、反馈启动、执行器、目标、代价、约束、初态和求解预算：

- 物理：`x[k+1] = F_phys(x[k], a[k])`。
- 完整提升：`z[0] = psi(x_observed)`，`z[k+1] = A z[k] + B [a[k], a[k]^2]`，`x[k+1] = decode(z[k+1][:10])`。
- 结合：使用同一 A/B，另拟合残差读出 R；`xi[k+1] = coordinates(F_phys(x[k],a[k])) + R z[k]`，`x[k+1] = decode(xi[k+1])`。完整 z 仍按 A/B 自行传播，不接收解码状态或物理预测的回灌。

沿用38维非线性字典；xi为高度偏移、局部姿态和机体系速度。R的高度输入列固定为零，保留高度平移等变性。每个真实控制时刻只用当前观测初始化一次；推进器状态由已执行控制因果重建。实际扰动力只进入原始诊断记录，由验收器读取，不作为模型输入或补偿。

a由已知机械参数、计划pre-TAM控制与推进器递推计算。输入平方、执行器、姿态解码及物理支路仍非线性，不宣称整个MPC为线性QP。测试所有参数固定，无自进化、Agent或额外模型家族。

## 数据与停止规则

`workflows/protocol_v86.py` 固定4条训练（PRBS/多正弦各2）、2条验证（新种子PRBS/多正弦）、2条测试（独立扫频）。每条160个30Hz控制区间、640个120Hz物理步；前64个控制区间启动。整条轨迹隔离，种子86010–86017，扰动恒为20%。正则固定0.001，不搜索候选或根据测试调参。

训练只打开四条训练轨迹；验证、测试命令只读冻结模型，不拟合。原始记录核对native exit、源码、清理、机械参数、状态/backend、接触、运动界限、控制/推进器重放及实际附加阻力。缺失或失败不填补、不改成功。

预测从物理步256/384/512开始，各80步；沿用2mm高度RMSE、4mrad姿态RMSE门，记录速度误差和失败。输入是过去执行控制及预先给定的未来控制序列，不读取未来状态或转子真值。这是给定输入下的预测检查。

随后在两条验证轨迹的第256步，对三臂分别运行隔离进程NLP，核对NumPy/CasADi、原单位约束残差与父进程可行性。超时仍标记未收敛，保留最后有限候选和复核结果；无返回候选不伪造，保留旧计划不算新求解收益。

三臂预测与求解通过后，运行`pitch_pos`、`pitch_neg`两个2秒任务，各三臂，共六例。初始高度5.5m、单位姿态、零速度/转子、种子86030；沿用`depth4_h20`、preview on、30秒求解CPU上限。预测门失败或闭环安全/接口失败时保留证据并讨论，不扩大构型、扰动或时长。

比较深度/姿态RMSE、原综合跟踪指标、控制量、约束、求解状态和回退。扫频留出只支持相同构型和扰动下的轨迹泛化，两秒结果只支持短任务控制；未见扰动、未见构型、长时间、实时性和硬件泛化均未覆盖。

## 运行入口

主服务器`suanliyun-agentic-AUV`。先完成本地工作再确认可用。使用新目录与既有合格runtime、Isaac启动及进程组supervisor，不复用旧输出目录或重启旧队列。数据child外部600秒封顶，闭环沿用v82外部预算；保留非零退出与清理记录。

本地打包，拒绝覆盖已有目录：

```powershell
& ./.venv/Scripts/python.exe -B -m workflows.prepare_disturbance_v86 --output docs/evidence/phase9/disturbance-v86-20260929/release
```

在服务器新目录先运行本地同组定向测试，再运行一条训练pilot并独立验收，通过后收集余下七条。包内`v86-manifest.json`绑定源码、协议及旧物理文件。

```text
python -B -m workflows.collect_disturbance_data_v86 --case v86-base-train-86010-prbs --manifest v86-manifest.json --output DATA/v86-base-train-86010-prbs
python -B -m workflows.fit_disturbance_v86 train --data DATA --manifest v86-manifest.json --output model.json
python -B -m workflows.fit_disturbance_v86 validation --data DATA --manifest v86-manifest.json --model model.json --output validation.json
python -B -m workflows.fit_disturbance_v86 test --data DATA --manifest v86-manifest.json --model model.json --output test.json
python -B -m workflows.solve_disturbance_v86 --data DATA --manifest v86-manifest.json --model model.json --model-sha MODEL_SHA --assets ASSETS --output solver.json
```

MODEL_SHA是现场冻结模型文件的SHA256；ASSETS是核验后的旧合格v38资产根。三臂预测与求解门通过后，每个任务/模型用独立新目录：

```text
python -B -m workflows.collect_disturbance_control_v86 --configuration base --controller physics --learned-model model.json --learned-sha256 MODEL_SHA --assets ASSETS --output CONTROL/base-physics-pitch_pos --manifest v86-manifest.json --preview on --task pitch_pos --validation-report validation.json --test-report test.json --solver-report solver.json
python -B -m workflows.validate_disturbance_control_v86 --trace CONTROL/base-physics-pitch_pos/trace.json.gz --learned-model model.json --learned-sha256 MODEL_SHA --assets ASSETS --native-exit ACTUAL_NATIVE_EXIT --output CONTROL/base-physics-pitch_pos/acceptance.json
```

其余臂为`koopman`、`hybrid`。ACTUAL_NATIVE_EXIT必须来自supervisor回执，不能预写0。输出按既有清单/哈希拉回，本地独立复核；成功采集不自动等于完整验收。现有冻结模型及逐窗口效果数字见结果报告；上述闭环命令因预测门失败尚未执行，不应绕过门限直接运行。


运行位置更新：上文路径与分支是原实验时点信息。当前入口见 [运行说明](../../../docs/runbook.md)，原始材料集中于本地 `results/history/`，参数、门限与采集身份保持原值。

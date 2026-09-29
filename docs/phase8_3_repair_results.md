> **当前方向更新：** 固定pooled/分构型/运动学对照已完成，位姿单步有收益、动力学泛化和长递推仍失败；当前入口为[方向对照结果](phase8_3_direction_assay.md)。以下为前次调查记录。

# 失败定位后的第一轮修复：稳定了，但模型仍不可用

2026-09-12。用户明确要求进入下一步修复。本轮完成一个固定源案例的机制核验、一次有界稳定性约束修复对照，以及3处控制链trace验收缺口修复。没有启动Isaac/SSH，没有改变原控制计算或Phase8.2证据。

**结论：原候选20/21个源验证episode发散，修复候选0/21发散；但六项full-horizon误差的等构型宏平均全部差于persistence。** 因此数值发散问题在此案例上得到缓解，预测模型修复仍未完成。该候选被拒绝用于控制，没有model handoff，不进入Phase9。

## 1. 这次查到的机制

重复拟合了上轮同一候选，模型hash与上轮精确一致：`d54c12e93819131258d47156df581ebb6f6bd335fad02f8595e5d94fbd0a6c2e`。仅使用原来的14个source fit和21个source validation episode，均不含base或test轨迹。

用独立SVD公式求解**同一个ridge目标**：系数相对差异1.1856e-11，训练预测最大绝对差异3.8521e-13。没有证据把原发散归咎于normal-equation求解错误、target排列错误或SO(3)增量应用顺序错误。本次没有更换原求解器。

固定构型context后，identity conditional模型可以精确拆成：

```text
s = [z, vx, vy, vz, wx, wy, wz]
s_next = A7(context) s + bounded-feature terms(R6, memory, control, bias)
```

| 源构型 | 原A7最大特征值模 |
|---|---:|
| long_body | 1.01558 |
| heavy_moderate | 1.00941 |
| asymmetric | 1.05727 |
| uuv6 | 1.40036 |
| uuv6_angled | 1.39310 |
| uuv4 | 2.00039 |
| uuv4_angled | 1.96554 |

这是模型中深度/速度递推块的放大模态，结合上轮实际full rollout发散，支持“拟合模型含不稳定递推方向”的机制解释。它**不是完整SO(3)耦合系统或真实艇体的特征谱**，也不能据此声称任何初值都会发散、推进器数决定发散，或者跨构型泛化已经被证明不可能。

## 2. 实施了什么修复

新增 [stability_repair_v23.py](../koopman/stability_repair_v23.py)，是一份有明确范围的诊断性约束重拟合实现，没有正式model loader/selection/handoff接口。

保持conditional identity字典、PCA scores、prefix2、ridge1e-8、原始输入与源数据不变。只重拟合前7个增量输出，姿态增量的3行系数保持原样。使用14个fit episode计算的状态标准差D（下限1e-6），对7个源context施加：

```text
|| D^-1 A7(context) D ||_2 <= 0.999
```

目标是在按D缩放的输出误差上做ridge回归。没有约束时，各输出行的最优解与原ridge一致；加上约束后，这是一个保守的新拟合先验。预测阶段不裁剪状态，不改变100 rad/s门限，也不偷偷重置递推。

约束以NumPy实现的ADMM求解，无新依赖。第一次固定数值penalty在5000次迭代内没有达到最优性残差阈值，程序拒绝返回模型；失败报告及源码版本均保留。随后仅补充残差平衡的数值penalty更新，目标、radius、数据、5000次上限及1e-7残差阈值保持不变。第二次数值求解1108次迭代收敛，primal=2.6380e-8，relative dual=9.9536e-8，独立重算的最大operator norm约0.999000026，处于预设1e-6浮点容差内且严格小于1。

稳定性约束作为模型学习先验有研究依据，但不自动带来精度保证；本实现并非DISKO复现，采用的是更保守的固定D范数约束。[Learning Stable Models for Prediction and Control](https://arxiv.org/abs/2005.04291)。ADMM是把凸优化拆成易解子问题的方法；本实现的具体目标、投影与数值残差由代码和测试约束。[Boyd的ADMM资料](https://web.stanford.edu/~boyd/admm.html)。

**方法限制：** 深度本来可能含积分/漂移模式，严格收缩并不是艇体物理定律；同一个D的范数约束也比特征值稳定性更强。它适合检验“仅去掉不稳定递推是否足够”，不宜未经对照就作为正式动力学先验。证书只覆盖这7个固定source context；不保证未见context、真实闭环安全或预测准确。

## 3. 同21个source validation episode的结果

都从episode初始真实状态和初始memory开始，之后使用预测状态递推512步；输入/memory逻辑和原生产SO(3)/rollout gate一致。不是每一步喂真实状态来伪造稳定预测。

| 检查 | 原固定候选 | 修复候选 |
|---|---:|---:|
| full rollout数值门存活 | 1/21 | 21/21 |
| full rollout发散 | 20/21 | 0/21 |

下表是等构型、等episode的宏平均（7构型，每构型3个episode）；不是正式test/LOCO选择结果。原模型20个episode没有合法full指标，因此不将其失败值填0后比较精度。

| full指标 | 修复候选 | persistence | 候选/基线 |
|---|---:|---:|---:|
| 深度RMSE，m | 5.57837 | 0.50876 | 10.96 |
| 线速度RMSE，m/s | 0.63693 | 0.09226 | 6.90 |
| 角速度RMSE，rad/s | 8.56949 | 0.75746 | 11.31 |
| 姿态测地角均值，rad | 1.37023 | 0.99584 | 1.38 |
| 姿态测地角RMSE，rad | 1.56696 | 1.06054 | 1.48 |
| 姿态最大测地角的episode宏平均，rad | 2.65912 | 1.57739 | 1.69 |

这回答了本轮的一个重要问题：**仅把递推变稳定，远不足以把该候选变成合格预测模型。** 一步角速度增量误差在各源构型有所降低，仍未转化为合格full预测。输入时间语义、执行器状态充分性、字典/条件化表达、激励与状态覆盖等问题，仍可能影响模型；本轮不能从这些结果唯一锁定其中一项。

## 4. 同步修复的控制链验收问题

[validate_control_trace_v23.py](../workflows/validate_control_trace_v23.py)原先主要检查每个interval内部，可能让以下错误通过：

1. 上一control interval结束状态与下一interval开始状态跳变。
2. trace-on与trace-off的boundary记录互相一致，但与实际子步记录不一致。
3. cold episode中reset generation异常跳变。

三项均先用失败测试复现，再补跨interval状态、执行器状态、token/clock连续性，boundary↔substep绑定及预期reset generation检查。这是本地代码缺口修复，仍待真实Isaac输入验证。

## 5. 当前决定和下一步

- **保留修复实现及失败/成功数值求解证据，拒绝将本候选用于模型或控制。** “稳定性现象修复”与“模型可用”分别记录，Phase8.2仍为NO_SELECTION。
- 不继续对这21段validation盲调radius、字典或ridge。这些数据已经用于探索，不再充当新方案的独立成功证明。
- 下一步优先完成8.3-02：按旧plant记录完整子步控制、PWM非线性和执行器状态；先通过64区间trace-on/off门，再量化控制历史reset的影响。当前尚无clean tested runtime bundle或Isaac trace。
- 8.3-03用同轨迹、可部署的输入/状态比较检验信息是否充分；若要改模型结构，应先明确pose运动学、速度动力学、控制器内部状态的边界。新的模型精度结论需要fresh pilot，不能复用本轮旧源validation作独立验收。
- 8.4保持条件性；Phase9无模型入口。不能把本次局部修复称为Phase8.3完成。

## 6. 复核入口

[修复证据目录](evidence/phase8_3/repair-20260912/)含机制报告、第一次未收敛报告、第二次完整assay、fit-only数值数组、诊断系数、运行源码快照及 [summary.json](evidence/phase8_3/repair-20260912/summary.json)。数组不是正式模型；`.py.txt`是运行源码快照，保留原路径约定，不是从当前位置直接执行的入口。失败求解器和第一次脚本快照的SHA与原失败报告逐项匹配。

原始运行目录分别为 `tmp/phase8_3/mechanism-audit-20260912/`、`tmp/phase8_3/stability-repair-20260912/`、`tmp/phase8_3/stability-repair-adaptive-20260912/`；未覆盖上轮 `fixed-source-20260912`。

本轮最终本地回归：**167 passed in9.25s**，包含新增稳定性约束、闭式最优解对照、feature-based导数核对、未收敛拒绝与trace接缝测试；不是全仓/Isaac测试。

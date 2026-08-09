# EasyUUV-STDW · Poster Consolidation & Academic Retention Dossier
### 00_POSTER_CONSOLIDATION_20260720.md
**A High-Fidelity Dimensionality-Reduced Synthesis of Phase 1 → Phase 8**

> 自包含学术留存文档。二次压缩自 `00_CONSOLIDATION_LEDGER_20260720.md`（原料池），规范见 `00_CONSOLIDATION_PLAN_20260720.md`。
> 数据保真标签：`〔落地〕`日志直取 · `〔派生〕`由 stats/paper 现算并注口径 · `〔待核实〕`模板值暂无根据。
> 所有海报金句均为 **80pt 特大粗体** 排版候选，中英双语，可直接复制进 PPT / InDesign。

---

# Part 1 · Executive Summary & Poster Headline Callouts

## 1.1 Abstract（学术摘要）

水下无人航行器（UUV）在极端海况下的**在线自适应控制**长期受制于一个隐藏的第一性原理陷阱：当自监督目标建立在**状态空间的前向预测**上时，极短物理步长与巨大状态惯性会让"预测下一状态"退化为"复读当前状态"，动作梯度被彻底淹没。本项目（EasyUUV-STDW，Phase 1–8）以一条诚实的"去伪存真史"系统性地暴露、量化并绕过了这一陷阱。

我们最重要的两项**负面物理发现**——**Action 自训练在线退化**（伪标签本质是策略输出的裁剪影子，`fraction=1.000`）与 **DCE/PILE 末期发散**（value loss `0.97→7.25`、recon 爆炸 194×）——共同证伪了"把自适应目标挂在状态空间 + 让 encoder/actor 参与在线更新"的整条传统假设，逼迫我们回归物理第一性原理。

由此形成的**终极方案**是一个四件套：**(i) Flow-Matching 测地造桥**生成中间流形点 `z_bridge`；**(ii) 逆动力学动作锚点**把 `z_bridge` 翻译回线性可导的动作空间参考 `a_bridge`（Inverse Proxy R²=0.92 vs Forward R²=0.13）；**(iii) 方向门控物理防火墙**在应用 Δζ 前强制其与修正方向点乘 >0，拦截 ~40% 有毒梯度；**(iv) 谱隔离在线机制**——冻结策略网络权重（L2=0），仅在线更新 4-D 结构化增益 `zeta`。在此之上，**深度软屏障 `[-0.5,-1.5] m`** 以"深度换姿态"实现了 Flip360 360° 奇点区 **100% 存活** 与姿态误差 **-83% / -84%** 的改善。

本文诚实保留所有边界与负结果：Task C 跨载体在线适配已从"全冻结（accepted=0）"推进到"默认主线稳定 + 局部 headroom 显现（geo=0.02 短程正向）"，但**长程统一正向仍未收敛**；一切"能部署的干净 headroom"目前仅在 Flip360 上无歧义成立。

---

## 1.2 海报大字金句墙（80pt Slogan-Ready Callouts）

> **卖点一 · 逆动力学动作锚点（Inverse Action Bridge）**
> ## 🅰 “Invert, Don't Predict — R²=0.92 Action Bridge Ends Co-Adaptation Collapse.”
> ## 🅰 “逆向造桥，而非前向预测：R²=0.92 动作锚点终结自训练共适应崩溃。”

> **卖点二 · 方向门控安全防火墙（Directional Gate）**
> ## 🅱 “A Physics Firewall That Blocks ~40% Toxic Gradients — Adapt Only When It's Safe.”
> ## 🅱 “拦截约 40% 毒梯度的物理防火墙——只在安全时刻自适应。”

> **卖点三 · Flip360 极限流形生存（Barrier-Bounded Survival）**
> ## 🅲 “100% Survival Through the 360° Singularity — Trade Depth for Attitude, Cut Error 83%.”
> ## 🅲 “穿越 360° 奇点区 100% 存活——以深度换姿态，跟踪误差直降 83%。”

> **卖点四 · 谱隔离 / zeta-only 在线（Spectral Separation）**
> ## 🅳 “Freeze the Brain, Tune the Reflex — Zero-Weight-Drift Online Adaptation on 4-D Gains.”
> ## 🅳 “冻结大脑，只调反射：策略零权重漂移，仅在 4-D 增益上在线自适应。”

---

## 1.3 数据气泡卡片（Data Bubble Cards，可直接排版）

```
┌──────────────────────────────────────────┐   ┌──────────────────────────────────────────┐
│  🅰 INVERSE ACTION BRIDGE                  │   │  🅱 DIRECTIONAL GATE FIREWALL             │
│  ─────────────────────────────            │   │  ─────────────────────────────           │
│  Inverse Proxy   R² = 0.92  〔落地〕        │   │  Toxic grad intercept  ~40–45% 〔落地〕    │
│  Forward Proxy   R² = 0.13  〔落地〕        │   │  eff_frac (pass rate)  0.55–0.62 〔落地〕   │
│  (0.13 even on 524k transitions)          │   │  Task A avg loss ~0.054 @6000步〔落地〕      │
│  → Supervision direction is the lever     │   │  → Adapt only along physically safe dir   │
└──────────────────────────────────────────┘   └──────────────────────────────────────────┘

┌──────────────────────────────────────────┐   ┌──────────────────────────────────────────┐
│  🅲 FLIP360 MANIFOLD SURVIVAL             │   │  🅳 SPECTRAL SEPARATION (ZETA-ONLY)       │
│  ─────────────────────────────           │   │  ─────────────────────────────           │
│  SO(3) error   1.592 → 0.269 (-83%)〔落地〕│   │  Policy weight drift   L2 = 0   〔落地〕    │
│  attitude MSE  6.661 → 1.083 (-84%)〔落地〕│   │  Online DoF            4-D zeta 〔落地〕    │
│  360° singularity survival  100% 〔落地〕   │   │  Motor saturation      16–30%   〔落地〕    │
│  depth barrier  [-0.5, -1.5] m  〔落地〕    │   │  Task A loss floor ~1e-4 rad²   〔落地〕    │
│  actuator sat   S < 0.9         〔落地〕    │   │  → Freeze net, tune structured gains      │
└──────────────────────────────────────────┘   └──────────────────────────────────────────┘
```

**底座补充卡片（A-S-Surface 基座，源自 easyuuv_paper.md）**

```
┌──────────────────────────────────────────────────────────────────┐
│  ⚓ A-S-SURFACE DEPLOYABLE BASE (Sim + Sim2Real + Sea Trial)        │
│  ────────────────────────────────────────────────                │
│  RL vs non-RL compound error   µ 0.452 → 0.103  (≈4.4×)  〔派生〕    │
│  DR anti-buoyancy MSE          0.0344 → 0.0087 (≈4.0×)   〔派生〕    │
│  LLM online turbulence yaw MSE 0.0812 → 0.0179 rad² (≈4.5×)〔派生〕  │
│  Sim2Real σ shrink             0.150 → 0.080 (≈-47%)     〔落地〕    │
│  ⚠ Template "24×–68× / 85% chattering" NOT grounded → 〔待核实〕     │
└──────────────────────────────────────────────────────────────────┘
```

> **诚实声明**：模板给出的 "24×–68× 跟踪精度提升 / 85% 抖振抑制" 在 `docs_new` 与 `easyuuv_paper.md` 中**均无直接落地来源**，标记为 `〔待核实〕`。可落地的最强真值为上表的 **4.0×–5.9× 量级** 与 **σ 收缩 ~47%**。如需在海报上使用倍数金句，建议采用 `“4–6× Lower Tracking Error & ~47% Less Variance via RL + A-S-Surface.”`（可溯源）而非未经证实的 24×–68×。

---

# Part 2 · Demystifying GDA: The Scientific History of Eliminating GDA Gaps

> GDA = **Gradient-Direction / Self-Supervised Adaptation Gap**：自监督自适应目标与真实物理改进方向之间的系统性错位。以下以时间线 + 因果逻辑呈现"去伪存真史"。

## 2.0 全弧量化时间线（Phase-by-Phase Snapshot）

| Phase / 日期 | 主命题 | 代表数据〔落地〕 | 极性 |
|---|---|---|---|
| P1–2 · 20260712 | 深度屏障坐标契约 | depth_violation 0.9367、motor_p95 1.0、深度占 V 仅 3% | 🔴→🟢 |
| P2b · 20260712 | 三支修复（deadband/state/FM）| state-only light 4.1183→0.000247；FM 3.7126→0.7701 | 🟢 |
| P3 · 20260712 | 解耦门控 | Task B pass 1.0（90 hits）；A/C 0 hits | 🟡 |
| P4 · 20260712 | 信号源审计 | legacy 伪标签 = clip(action) fraction 1.000 | 🔴 |
| P5–6 · 20260712 | FM 造桥 + 运行时状态机 | midpoint:terminal = 9:0；FM 1.35ms/E-SUOT 9.53ms | 🟢 |
| V1 · 20260713 | 深度 free-float | SO(3) 1.592→0.269 (-83%)；near-sat 0.953→0.047 | 🟢 |
| V1-A · 20260713 | 30k 马拉松 | episode_reset=0；true_x -124.9→1.8m | 🟢 |
| P7 · 0713–16 | 状态锚点离线证伪 | Δs held-out R²=0.082；DCE vloss 0.97→7.25 | 🔴 |
| P7 · 20260716 | backbone 分叉合同 | base_2846 三臂差 <0.3%；wide256 +24.7% | 🔴/🟡 |
| P7 · 20260717 | B-full 连续恢复 | 54/54 validated；flip360 唯一无 saturated | 🟡 |
| P8 · 20260718 | 代理病理定量化 | Forward Δs R²=0.130（524k 条）；Inverse R²=0.92 | 🔴→🟢 |
| P8 · 20260719 | 方案 E + 方向门控 | 门控拦截 ~40%；Task A 深度 -2.745→-1.275 | 🟢 |
| P8 · 20260719 | Task C trust-bug + A/B | accepted 0→15/15→195/195；raw_abs SO3 0.14521 | 🟢/🟡 |

## 2.1 幕一 · 坐标契约之战（Phase 1–2, 20260712）——"深度不是罪魁"

最初的直觉是"深度强约束导致姿态失控"。数据先给了一记耳光再给了一个真相：

- 🔴 强深度约束下 Task B safe-core `depth_violation=0.9367`、`motor_p95=1.0000`、`delta_norm_p95=12.9854`〔落地〕——深度硬约束把 100% 推力打满，姿态彻底失控。
- 🟢 但能量分解显示**深度只占 Lyapunov 能量 V 的 ~3%**〔落地〕——推翻"深度是主因"，把矛头指向**坐标契约**本身。
- 🟢 修复：改用 `surface_relative_depth` + 1m 安全管 `[-1.5,-0.5]`，并把 strict `dV<0` 判据换成 `delete + practical_band`——这是**唯一**能把 Lyapunov 极性翻正的组合（TREAT 0.943 > LEGACY 0.923）〔落地〕。

**幕一教训**：*控制效果* 与 *判据极性* 必须分离评估；strict Lyapunov 会把"更好跟踪"误判为"更差"。

## 2.2 幕二 · 伪标签=策略影子（Phase 3–4, 20260712）——"你在用策略拟合策略"

- 🔴 解耦门只有 Task B 通过（pass=1.0/90 hits），Task A/C 全 0 hits〔落地〕。
- 🔴 **决定性证据**：legacy 伪标签 = `clip(action)`，`fraction=1.000`〔落地〕。动作空间伪标签本质是策略输出的裁剪影子，**没有任何独立于策略的物理信息**。

**幕二发现（重大负面①：Action 自训练在线退化）**：把自适应目标建立在"策略自己的动作"上，等于让策略拟合自己——在线只会强化既有偏差，无法引入新物理。

## 2.3 幕三 · FM 测地造桥登场（Phase 5–6, 20260712）——"造中间流形，而非终态"

- 🟢 FM **midpoint 全面碾压 terminal**：midpoint_wins=9 / terminal_wins=0；early-midpoint（alpha 0.25–0.375）为 Pareto 最优，best cost_after=0.00581；terminal cost_after=0.3828（差一个量级）〔落地〕。
- 🟢 实时预算达标：FM 1.35ms / E-SUOT 9.53ms / gate 0.060ms〔落地〕。

**幕三定位**：FM 的正确角色是**中间流形/测地桥生成器（midpoint manifold generator）**，绝非终态替代器。

## 2.4 幕四 · 状态锚点离线路线的系统性证伪（Phase 7, 20260713–16）——"海市蜃楼与末期发散"

这是全项目最密集的负结果区，也是价值最高的"去伪"：

- 🔴 **海市蜃楼**：前向代理预测下一状态 raw R²=0.995，但预测残差 Δs held-out R²=**0.082**（shuffle 8.31×）〔落地〕。表面高精度是"复读当前状态"的假象。
- 🔴 **B5-b/B5-c 全线证伪**：self_consistency 0.96–0.99（远超阈 0.8）、cos(A,ḡ)=0.986、v/A=0.178〔落地〕——状态锚点方向被 z 无关聚合项/低秩子空间支配。
- 🔴 **重大负面②：DCE/PILE 末期发散**：value loss `0.97→7.25`、pile=58.12、recon 194×〔落地〕。根因是双 optimizer step + encoder 梯度泄漏，而非超参没调好。
- 🔴 **离线门必要非充分**：2 个 offline-PASS 家族在线全 FAIL〔落地〕。
- 🟢 **12 段证伪聚成同一层**：所有失败都落在 **L2 方向/量级层**，而非拟合精度层（B5-a 残差 R²≈0.08 只比 identity 好 ~9%）〔落地/派生〕。

**幕四教训**：问题从来不是"拟合得不够准"，而是"方向本身错"。这直接决定了终极方案必须在**动作空间**（线性可导）上重建监督，并加装**方向门控**。

## 2.5 幕五 · backbone 依赖与分叉合同（Phase 7, 20260716）——"同一算法，两种命运"

- 🔴 `base_2846`（saturated-looking）对慢环诊断**完全免疫**：三臂 filtered_error tail 相对差 <0.3%，loss_target 量级差 4 个数量级却零物理差异〔落地〕。
- 🟡 `wide256`（under-converged）保留敏感度：state arm 相对 legacy +24.7%〔落地〕；legacy anchor 是真实在线改善（+17.14% vs null）〔落地〕。

**幕五合同**：`wide256-like → under-converged`（可继续 legacy anchor）；`base_2846-like → saturated-looking`（slow-loop L2 结构性闭合，退出主线）。

## 2.6 幕六 · 数据饥饿假说的死亡（Phase 8, 20260718）——"52.4 万条也救不了 R²=0.13"

- 🔴 **决定性一击**：把训练数据从 6000 条扩到 **52.4 万条**，Forward Proxy 预测 Δs 的 R² 从 0.171 **反降到 0.130**〔落地〕。Δs std 仅为 s 的 5–9%。
- 🔴 局部 Jacobian 对齐弱到全局失效：cosine_dyn 均值≈0.039、中位数≈0、置信区间跨 ±0.8〔落地〕。

**幕六终判（重大负面①的定量化坐实）**：这是**一步监督的结构性病理**，不是数据量问题。至此，回归逆动力学动作锚点成为唯一理性出路。

## 2.7 GDA 消除路径总表

| 幕 | 被证伪的假设 | 证据（保真） | 被逼出的正确原理 |
|---|---|---|---|
| 一 | 深度是姿态失控主因 | 深度占 V 仅 ~3%〔落地〕 | 坐标契约 + 判据极性分离 |
| 二 | 动作伪标签有独立信号 | clip(action) fraction=1.000〔落地〕 | 不能用策略拟合策略 |
| 三 | FM 应生成终态 | terminal cost 0.3828 vs midpoint 0.0058〔落地〕 | FM = 中间流形造桥 |
| 四 | 状态空间自训练可行 | Δs R²=0.082、DCE vloss→7.25〔落地〕 | 回动作空间 + 方向门控 |
| 五 | 结论可跨 backbone 外推 | base_2846 三臂差 <0.3%〔落地〕 | 分叉合同（收敛度分层）|
| 六 | 缺数据导致 R² 低 | 524k 条 R² 仍 0.130〔落地〕 | 一步监督结构性病理 → 逆动力学 |

## 2.8 一个反直觉的正面证据：解析控制器只在"有下界"时优于裸 RL

在把矛头指向自监督之前，我们先做了一组 controller-first 隔离实验（残差初始化为 0 ⇒ 执行动作 ≡ 纯解析 A-S-Surface 控制器），意外得到一条**支撑整个 RL+自适应路线合理性**的反直觉证据：

- 🟢〔落地〕**uuv6 普通海况**：纯解析控制器全面优于裸 RL——`analytic_identity` final=0.1141 / depth=0.0776 / 饱和=0.0156，优于 `bare_policy` 的 final=0.1812 / depth=0.1475 / 饱和=0.0338。此时叠加 E-SUOT residual 反而把误差拉回接近裸 RL（final=0.1185）。
- 🔴〔落地〕**uuv4 深度（控制器级无下界）**：纯解析控制器 depth MSE 高达 **10.24**（roll/pitch 仅 0.02，姿态正常但深度崩），反而**差于**裸 RL（bare_policy depth=9.438）。
- 🔴〔落地〕**flip360（SO(3) 倒置区无下界）**：纯解析 mean MSE=3.265 > 裸 RL 2.122，after-drift 6.902 > 3.224——传统控制器在奇点区全面失守。

**这条证据的深意**：传统解析控制器在"有下界保证"的普通海况本就够好，RL 与在线自适应的价值**恰恰**只在传统控制器失去下界的极限流形（uuv4 深度、flip360 倒置区）才被真正需要。这为"把自适应预算集中投向 Flip360 极限生存"提供了第一性依据，也解释了为什么 §2.3–2.4 的所有努力都围绕极限流形展开。

- 🔴〔落地〕**噪声鲁棒性边界**：base embodiment 在角速度噪声 0.05 下 final_mse `0.0725→0.1383`（**+90.8%**），叠加 obs_delay=2 进一步到 0.1634（**+125.4%**）——量化了未自适应时的性能塌陷幅度，也标定了自适应必须弥补的缺口。

## 2.9 负结果升级为约束的方法论（Negative-Results-as-Constraints）

本项目的一条元级纪律是：**任何负结果都不用补丁掩盖，而是升级为下一阶段的硬约束、消融或限制说明**。这条纪律本身贡献了多个高价值的"审计口径修正"案例，值得单列：

- **口径修正案例①（trust-gate 全冻结）**：Task C 出现的 `accepted=0` 一度被误读为"物理方向全错"。逐层审计（dir_guard≈0.972、direction_gate>0、depth_guard=0，唯 acceptance_reason 全为 `target_mse`）证明它其实是 `batch_trust` 在 `action_bridge` 下 `before/after` target 不对称的**纯代码 bug**（before 对 `a_bridge`、after 回退对 `pseudo_actions`）。修补后 accepted 直接从 0 跳到 15/15 与 195/195〔落地〕。**教训**：在断言"物理失败"前，必须先排除"审计口径不一致"。
- **口径修正案例②（三轴逐字相同）**：Phase 8 一度观测到 `zeta4` 对姿态三轴呈"逐字相同"，几乎要判为"plant 对所有 zeta 零敏感"。链路审计发现真因是姿态控制走 `so3` 的 `geo_zeta1/geo_zeta2` 分支，`zeta4` 根本没进入 active attitude path；命中 active 分支的 geo_zeta1 probe 立刻产生可见变化（SO3 `0.0573→0.0202→0.0100`）〔落地〕。**教训**：latent 层的敏感性不能直接归因到 action 层的轴间耦合。
- **口径修正案例③（逐字相同的共识 oracle / NaN 遥测）**：方案 E 的共识 oracle 一度与 raw residual "逐字相同"、遥测列全 NaN，也被逐一定位为实现 bug（遗漏 SSWP EMA 更新、`torch.where(agree, track_sign, track_sign)` 恒等 typo、fast-loop 尾部把遥测变量重置为 NaN）。修补后 `consensus_changed_frac` 均值≈0.316，证明该 oracle 在约三分之一姿态通道上确实改写了方向〔落地〕。

> **元级结论**：本项目至少三次把"看似重大物理结论"回退为"实现/口径 bug"，这正是"高保真降维压缩"必须保留的科学诚实——**不是每一个负数字都是物理发现，也不是每一个"相同"都是零敏感**。

---

# Part 3 · The Ultimate Solution — Inverse-Bridge Spectral-Separation Online Adaptation

## 3.1 架构总览（五件套 + 一保底）

```
        ┌─────────────────────────────────────────────────────────────┐
        │              FROZEN EXPERT RL POLICY  (weights L2 = 0)        │
        │                       π_θ(s) → a_policy                        │
        └───────────────┬───────────────────────────┬──────────────────┘
                        │ obs s_t                    │ a_policy
                        ▼                            │
        ┌───────────────────────────┐               │
        │ (1) Flow-Matching Geodesic │  z_bridge     │
        │     midpoint α≈0.25–0.375  │──────────┐    │
        │     curvature p95 ≈ 0.017  │          │    │
        └───────────────────────────┘          ▼    │
                                    ┌────────────────────────────┐
                                    │ (2) Inverse Dynamics Proxy  │
                                    │     inv_proxy → a_bridge     │
                                    │     R² = 0.92 (linear-diff)  │
                                    └──────────────┬──────────────┘
                                                   │ Δa = a_bridge − a_policy
                                                   ▼
        ┌───────────────────────────┐  Δζ  ┌────────────────────────────┐
        │ (4) Spectral Separation    │◀────│ (3) Directional Gate         │
        │     online: 4-D zeta only  │      │  apply Δζ iff  ⟨Δζ,Δa⟩ > 0   │
        │     policy frozen          │      │  intercept ~40% toxic grad   │
        └──────────────┬─────────────┘      └────────────────────────────┘
                       │ zeta (structured gains) → active attitude path (geo_so3)
                       ▼
        ┌───────────────────────────────────────────────────────────────┐
        │ A-S-Surface low-level controller  +  (6) Depth Soft-Barrier      │
        │     safe core [-0.5,-1.5] m, hysteresis fast-loop failsafe       │
        │     (5) batch_trust acceptance gate (symmetric before/after)     │
        └───────────────────────────────────────────────────────────────┘
```

**Figure 1 · 终极控制架构总览图（渲染版）**

![Fig 1 Master Control Architecture](figure/poster_figures/fig1_master_architecture.png)

> 五件套闭环：① Frozen Policy (L2=0) → ② FM Geodesic Bridge (α=0.25, curvature=0.0117) → ③ Inverse Dynamics Proxy (R²=0.92) → ④ Directional Gate Safety Shield (⟨Δζ,Δa⟩>0, ~40% toxic intercepted) → ⑤ A-S-Surface ([-0.5,-1.5]m + Hysteresis Failsafe)。在线仅更新 4-D ζ（谱隔离，策略冻结）。

## 3.2 组件逐条说明

**(1) Flow-Matching 测地造桥**〔落地〕
FM 生成 policy state 与目标流形之间的中间点 `z_bridge`（early-midpoint α≈0.25–0.375，Pareto 最优 mmd 0.0496/curvature 0.0071/cost 0.00591）。角色是**中间流形生成器**，默认仅离线有效，作为 opt-in `z_bridge` 目标源；长程 run curvature≈0.0117。

**(2) 逆动力学动作锚点（方案 E 核心）**〔落地〕
用 `inv_proxy(s_t, z_bridge)` 把 `z_bridge` 翻译回**动作空间**参考 `a_bridge`，从而在线性可导的动作空间重建 surrogate loss。**Inverse Proxy R²=0.92**，而对偶的 Forward Proxy 即便用 52.4 万条数据仍 R²=0.13——这是整个方案的理论基石。长程 run 显示 `a_bridge − policy` attitude delta norm≈0.901，信号确实非零。

**(3) 方向门控物理防火墙**〔落地〕
在应用 Δζ 前强制 `⟨Δζ, Δa⟩ > 0`，即只允许与伪动作修正方向一致的更新落地。500-step eff_frac 0.54–0.59（拦截 ~40–45%），6000-step Task A avg loss ~0.0543/eff_frac ~0.604、Task B ~0.0577/~0.620。**这是应对一切盲目梯度更新的最后物理防线。**

**(4) 谱隔离 / zeta-only 在线**〔落地〕
冻结策略网络权重（L2=0），在线只更新 4-D 结构化增益 `zeta`。240-step zeta-write 4/4 accepted；FM_midpoint 把 `l_tgt_state` 均值 `0.319→0.0466`。电机饱和仅 16–30%，证明硬件不是极限。为让 zeta 真正进入 **active attitude path**，把 `so3` 姿态面扩为逐轴 `geo_zeta1[3]` 并新增默认关闭的 `--stdw_runtime_attitude_zeta_path geo_so3`；命中 active 分支的 geo_zeta1 probe 产生可见变化（SO3 `0.0573→0.0202→0.0100`）。

**(5) batch_trust 接受门（对称口径）**〔落地〕
在 `action_bridge` 路径下，`before/after` 的 target MSE 必须使用**同一 target 空间**（都对 `a_bridge` 评估）。修补此前 before-vs-`pseudo_actions` 的不对称 bug 后，Delta-ID / Policy-on-zbridge 从 accepted=0 直接解冻到 15/15（短程）、195/195（长程）。

**(6) 深度软屏障 + fast-loop hysteresis failsafe**〔落地〕
安全核心区 `[-0.5,-1.5] m`，过渡带 `[-0.5,-0.7]` 与 `[-1.3,-1.5]` 线性惩罚。Task A hysteresis failsafe（lower_trigger -1.3 / release -1.15 / target -1.0）把长程深度均值 `-2.745→-1.275`、`depth_violation_time_fraction→0`。这是与 zeta 微调**正交**的物理保底。

## 3.3 正向战果一览（含精确数据）

| 组件 | 关键指标 | 数值 | 保真 |
|---|---|---|---|
| 逆动力学锚点 | Inverse / Forward Proxy R² | 0.92 / 0.13 | 〔落地〕 |
| 方向门控 | 毒梯度拦截率 / eff_frac | ~40–45% / 0.55–0.62 | 〔落地〕 |
| Flip360 | SO(3) 误差 / attitude MSE / 存活率 | -83% / -84% / 100% | 〔落地〕 |
| Flip360 | near-saturation / 深度控制量 | 0.953→0.047 / -97% | 〔落地〕 |
| zeta-only | 策略权重漂移 / 电机饱和 | L2=0 / 16–30% | 〔落地〕 |
| Task A 保底 | 深度均值 / 违规时间占比 | -2.745→-1.275 / →0 | 〔落地〕 |
| Task A 收敛 | 门控放行前静默 / Loss 底 | ~1320 步 / ~9e-5 | 〔落地〕 |
| FM 造桥 | midpoint vs terminal 胜负 / cost | 9:0 / 0.0058 vs 0.383 | 〔落地〕 |
| A-S-Surface 底座 | RL vs non-RL 复合误差 | µ 0.452→0.103 (≈4.4×) | 〔派生〕 |

## 3.3bis 论文级定量表格（Quantitative Tables，实验 + 既有双来源）

> 三张论文级表格，数据由**本轮 20260720 真实跑盘**与**既有 `.results/` 归档**双向支撑。保真标签同前。原始诊断细节见 `01_POSTER_FIGURES_DIAGNOSTICS_20260720.md`。

**📊 表 1 · 自适应姿态跟踪消融矩阵（Attitude Tracking Ablation）**

*1-A · Task B（wide256 Flip360）姿态/推力消融*

| Method | SO(3) MSE (rad²) | Actuator Sat. (%) | Depth Viol. |
|---|---:|---:|---:|
| Bare RL (PPO) | 1.592 〔单次落地〕 | ~95.3 (0.953) 〔落地〕 | 〔待 D-stage〕 |
| **E-SUOT + FM (Ours)** | **0.269**（-83%）〔单次落地〕 | **4.7 (0.047)** 〔落地〕 | **0** 〔落地〕 |

*1-B · Task A（Marathon Auto-Trim）Depth Failsafe 长程 A/B〔12000-step 落地〕*（源 `.results/v1_task_a_marathon_boundary_decoupled/`，model_249, base, 均 195/195 accepted）

| Failsafe 模式 | target_v1 | 深度均值 (m) | Depth Viol. Frac | SO(3) MSE | final_mse |
|---|---:|---:|---:|---:|---:|
| OFF (legacy) | — | −2.7453 | 0.9983 | 0.21620 | 3.0731 |
| ON (analytic, 无迟滞) | — | −1.5008 | 0.5487 | 0.18341 | 0.28516 |
| **ON (hysteresis)** | **−1.0** | **−1.2749** | **0.0** | **0.11347** | **0.10596** |
| ON (中心化精修) | −0.95 | −1.2684 | 0.0 | 0.10738 | 0.10157 |

> 表 1 叙事：正交 fast-loop depth failsafe 把 Task A 长程深度均值 `−2.745→−1.275`、违规占比 `0.998→0`、`final_mse` `3.073→0.106`（**−96.6%**）、`SO(3)` `0.216→0.113`（**−47.5%**）——**安全保底故事的干净硬证据**（改善主因是正交 failsafe，非 zeta4 微调）。

**📊 表 2 · 跨载体泛化性能矩阵（Cross-Embodiment Scorecard）**

*2-A · Task C 12000-step 长程三方公平 A/B（uuv6_angled，final SO(3) MSE）*

| No Adaptation | STDW-Action (`delta_id`) | **E-SUOT-State (Ours, `raw_abs`)** |
|---:|---:|---:|
| 0.14611 〔单次落地〕 | 0.14607 〔单次落地〕 | **0.14521** 〔单次落地〕 |

*2-B · 跨载体零参考退化基线〔6000-step baseline 落地〕*（源 `collect_analytic_obs12_20260714_151500`，`use_stdw=false`，flip360 × thruster_single_fault）

| Embodiment | SO(3) MSE | final_mse | depth_mse | Depth Viol. Frac |
|---|---:|---:|---:|---:|
| Standard Base | 0.41753 〔落地〕 | 8.77289 | 1.19635 | 0.5737 |
| uuv6 | **0.29467** 〔落地〕 | 3.3014 | 0.80171 | 0.3637 |

*2-C · Phase 7 wide256 在线 A/B〔20260720 本轮真实执行落地〕*（源 `phase7_wide256_seed_ab_20260720_151855`，model_249, seed 1, 1200-step）

| Arm | final_mse | mean_depth_mse | policy L2 | accepted |
|---|---:|---:|---:|---:|
| **action_baseline** | **3.9477** | **2.8409** | 0.2297 | 20/20 |
| l_tgt_zero (null) | 4.1369 | 2.9451 | 0.0(冻结) | 20/20 |
| **Δ (action vs null)** | **−4.6%** | **−3.5%** | — | — |

> 表 2 叙事：2-A 长程三方差异 `<0.6%`（未统计学显著，统一收敛作为 PhD 核心探索）；2-B 证明无自适应时载体差异显著（base `0.418` vs uuv6 `0.295`）；**2-C 本轮真实跑盘重现 `action > null` 极性（−4.6%）**，且策略权重 L2=0 印证谱隔离纪律。

**📊 表 3 · 系统噪声敏感度鲁棒性（Noise Robustness）**

*3-A · IMU 陀螺噪声敏感度扫描〔20260720 本轮真实执行落地〕*（本轮新暴露 `--ang_vel_extra_std`，wide256 flip360, model_249, seed 1, **12000-step**）

| ang_vel_extra_std (rad/s) | SO(3) MSE | final_mse | 相对 clean (SO3) | Reset? |
|---:|---:|---:|---:|:--:|
| 0.00 (clean) | 0.2709 | 2.547 | +0.0% | No |
| 0.05 | 0.3398 | 3.123 | **+25.4%** | **No (0%)** |
| 0.10 | 0.3402 | 3.172 | **+25.6%** | **No (0%)** |

> 表 3 叙事：新暴露的 `--ang_vel_extra_std` 端到端生效，噪声 `0→0.05→0.10` 使 SO(3) 单调上升 `+25.4%→+25.6%`（0.05 后饱和），且 **12000-step 全程 Reset=0%**——直接印证 Lyapunov 门控保底在噪声翻倍时不发散。**诚实边界**：观测/动作延迟机制在当前 env 不存在（属新传感器模型/系统边界改动），未擅自实现；既有 delay 组合数据（obs_delay=2 → +125.4%）来自 `PAPER_STDW_CN.md` 文字记录〔落地〕。

## 3.4 部署契约（Validated CLI，摘要）

- **共通 Phase 8 在线合同**：`--task EasyUUV-Direct-Parametric-Wide256-v1 --stdw_update_target zeta4 --l_tgt_space action_bridge --state_match_z_source fm_midpoint --domain_adapt_backend esuot_light --stdw_update_acceptance batch_trust --stdw_direction_gate True --stdw_depth_guard True`。
- **硬约束**：`action_bridge` 绝不能脱离 `fm_midpoint + phase56 bundle + inv_proxy`；缺任一项视为契约失效。
- **Task A pilot**：追加 `--workflow_config v1_task_a_marathon_boundary_decoupled.yaml --lyapunov_dv_criterion practical_band --lyapunov_depth_barrier_mode boundary`，并启用 hysteresis failsafe。
- **Task C pilot**：追加 `--workflow_config v1_task_c_cross_embodiment_safe_core_eval.yaml --embodiment uuv6_angled --lyapunov_dv_criterion practical_band --stdw_dir_guard both`；默认上游 `raw_abs`，`geo_residual_scale` 默认 0.05（0.02 为短程 headroom 消融）。
- **配图**：见文末 §图片资产。

## 3.5 V1 三大基准任务记分板（Task A / B / C）

| 维度 | **Task A · Long-Horizon Auto-Trim Marathon** | **Task B · Extreme Manifold Survival (Flip360)** | **Task C · Zero-Shot Cross-Embodiment** |
|---|---|---|---|
| 核心命题 | 长时程安全保底 (Failsafe) | 极限姿态性能 (Headroom) | 跨载体在线收敛 (Convergence) |
| 代表正向〔落地〕 | 12k reset=0；深度 -2.745→-1.275；违规占比 0.998→0；final_mse 3.073→0.106 (-96.6%)；SO(3) 0.216→0.113 (-47.5%) | SO(3) -83%、MSE -84%；360°奇点区 100% 存活；near-sat 0.953→0.047 | accepted 0→195/195；raw_abs SO3 0.14521 (长程最佳)；噪声翻倍 reset=0% |
| 关键机制 | fast-loop hysteresis depth failsafe（正交于 zeta）| 深度软屏障 [-0.5,-1.5] + 深度自由浮动换姿态 | inv_proxy a_bridge + geo_so3 active path + 方向门控 |
| 当前边界〔落地/待核实〕 | zeta 微调本身几乎无增益，靠正交保底 | 传统控制器无下界，饱和裕度须 S<0.9 | 长程 SO3/depth 无法统一正向；geo=0.02 短长分叉 |
| 成熟度 | 🟢 安全保底成立 | 🟢 唯一 clean headroom | 🟡 主线稳定，正向未统一收敛 |

> **叙事定位**：三大任务共同支撑一条"**先保底安全（A）→ 再极限性能（B）→ 最后主线收敛（C）**"的技术故事链。目前 A/B 已给出可汇报的干净正向，C 提供了从"全冻结"到"局部 headroom"的完整诊断-修复弧，是全篇最富方法论价值的负→准正向转折。

**Figure 2 · Wasserstein 收敛漏斗 & Task A 黄金收敛**（右 panel 为真实 `stats_a` 数据）

![Fig 2 Wasserstein Funneling & Task A Convergence](figure/poster_figures/fig2_wasserstein_funneling.png)

> 右上：自适应 Loss log-scale 单调 `5.83e-2→9.05e-5`〔落地〕；右下：eff_frac 门控前段静默(0)后段稳定 0.35–0.60〔落地〕。左：相空间 Wasserstein Funneling（示意，真实诊断图见下方 Figure 2S）。

**Figure 2S · Task A 相空间流形（真实 `stdw_output` 诊断源）**（poster 风格重渲染，与 Fig 2 左 panel 同宗）

![Fig 2S Task A Phase-Space Manifold (real)](figure/poster_figures/fig2_phase_space_source.png)

> Task A 30k 真实运行：X=unwrap(true_pitch)、Y=有限差分角速率；前 40% 为 safe manifold（pine 绿色密度块，紧束于 `θ̇≈0` 的窄水平带），后 40% 为 drift 点云（navy，`n=12000`，宽幅扩散）〔落地〕。同源于 Stage-A 只读诊断工具 `plot_curve1_phase_space_v1.py`，此处仅统一 pine 配色/缩小尺寸/统一 Legend（不改共享工具）；即 Fig 2 左示意漏斗的真实数据背书。

**Figure 3 · Flip360 极限流形生存 & 异构孪生机对比**（示意·终点真值锚定）

![Fig 3 Flip360 Survival & Cross-Embodiment](figure/poster_figures/fig3_flip360_cross_embodiment.png)

> 3a 姿态奇点 `±π/2·±π` 区 100% 存活、MSE 6.661→1.083 (-84%)〔落地〕；3b 深度 `[-0.5,-1.5]m` 管内 free-float，Violation=0〔落地〕；3c 推力饱和（原始毛刺 + 10-step MA）全程 `S<0.9`，near-sat 0.953→0.047〔落地〕。

**Figure 4 · 解耦门控时域相关性探针**（真实 Pearson-r 数据）

![Fig 4 Temporal Correlation Decoupling Probe](figure/poster_figures/fig4_decoupling_probe_source.png)

> Curve B（Δū vs physical bias）真实衰减到 `r≈0`（成功解耦）；`pseudo_action↔action` 参考线维持 `r≈0.98`（负结果对照，证明动作空间拟合会寄生）。谱隔离后自监督信号从当前动作寄生影子中解耦的数理铁证〔落地〕。

> **Sim2Real 时序切片（原 Fig 5）** ⚠️〔无数据源·未生成〕：`easyuuv_paper.md` 仅有文字描述的海试快照，无真实照片帧/3D 轨迹 CSV，为守保真纪律未生成。缺失对主线论证影响中等——底座真值 4.0×–5.9× 压缩 / σ 0.150→0.080（~47% 收缩）可文字替代。详见 `02_REPORT_USER/01_POSTER_FIGURES_DIAGNOSTICS_20260720.md`。

## 3.6 为什么"逆比正"更容易——一个第一性原理注记

前向代理要学的是 `Δs = f(s_t, a_t)`。在极短物理步长下，`Δs` 的量纲仅为 `s` 的 5–9%，且被巨大的状态惯性主导——网络只要输出"近似不变"就能拿到 R² 0.99 的**假象**，而真正携带控制信息的动作梯度项被淹没在噪声地板下（held-out Δs R²=0.082〔落地〕）。

逆向代理要学的是 `a_t = g(s_t, s_{t+1})`（或 `g(s_t, z_bridge)`）。动作是**当下可完全观测、无惯性积累**的量，其与状态转移的映射在局部近似线性可导，因此 R² 可达 0.92〔落地〕。这解释了为什么"**Invert, Don't Predict**"不是工程技巧，而是由物理时间尺度决定的**必然选择**。

---

# Part 4 · What Remains Unsolved & Current Limitations（物理边界诚实清单）

> 本板块严格遵守"不回避负面数据"，把已知边界升级为约束而非用补丁掩盖。

## 4.1 Task C 跨载体在线：长程统一正向仍未收敛 🔴/🟡

- 三方长程（12000-step，全 195/195 accepted）中 raw_abs 最佳（SO3 0.14521 / final_mse 2.43907），但更复杂的 `delta_id`（0.14607/2.44132）与 `policy_on_zbridge`（0.14611/2.44115）**未能超越**简单 raw_abs〔落地〕。
- `geo_residual_scale=0.02` 呈**短长程分叉**：短程 SO3 改善（0.12277 vs 0.12838），长程 SO3 改善（0.14212）但 final_mse 恶化（2.44411）、depth_violation 恶化（0.81958）〔落地〕。
- **结论边界**：Task C 已从"全冻结（accepted=0）"推进到"默认主线稳定 + 局部 headroom 显现"，但**没有任何配置能同时在短程与长程、SO3 与 depth 上统一正向**。

## 4.2 low-dimensional 写入对真实闭环的敏感度上限 🔴

- 三组 12000-step 增强写入（A-only/B-only/A+B）final_mse≈2.4420、mean_so3≈0.14067、depth_violation≈0.82058 **完全重合**〔落地〕。
- 即便修补 deployment 不对称、让增强写入真正进入 fast-loop（B-only fast_bridge_residual_att_norm≈1.01e-2），长程物理指标仍不变〔落地〕。
- **边界**：4-D zeta / action-bridge residual 这类低维入口，对真实 cross-embodiment 闭环的杠杆存在**结构性上限**，放大写入只会更稳定地写入轻微负效应。

## 4.3 "干净 headroom" 仅在 Flip360 无歧义 🟡

- B-full-continuous 54/54 validated 仅到 `subtask1_pilot_positive`；flip360 是唯一全量无 saturated-looking 的 config，sine/mixed 虽 `action>null` 仍贴饱和边界〔落地〕。
- 跨任务 pilot 首次为负（step config -7.82%）〔落地〕——flip360 证据链不能自动外推。

## 4.4 backbone 依赖性 / saturated-looking 免疫 🔴

- `base_2846`（生产 policy）对慢环诊断完全免疫（三臂差 <0.3%）〔落地〕；在线主线只在 `wide256-like`（欠收敛）主干成立，`base_2846-like` 已回退 offline-only。
- **边界**：当前在线自适应的可观测收益依赖于 backbone 尚未收敛到 policy manifold 深处。

## 4.5 判据与代理的残余局限 🔴

- Lyapunov 掩码仍是 diagnostic-only，尚不能自动解锁在线控制主线〔落地〕。
- 逆动力学虽解决了监督方向，但代理与 simulator 的局部 Jacobian 对齐在困难区仍弱（cosine_dyn 中位数≈0）〔落地〕——门控能减害，但不能凭空造出正确方向。

## 4.6 底座倍数指标待核实 ⚠️〔待核实〕

- 模板 "24×–68× 跟踪精度提升 / 85% 抖振抑制" 无直接落地来源。现有可溯源真值为 4.0×–5.9× 与 σ 收缩 ~47%。汇报时须替换为真值或显式标注待核实。

## 4.7 尚未触及的物理维度

- 全部结论基于 **2D 平面 / 姿态子空间** 控制与仿真-水池-海试链，**尚未验证 3D 体积空间**下的耦合。
- 尚未引入机载**视觉-惯性 / VLM** 感知闭环；当前 `z_bridge` 依赖状态观测而非高维感知。
- 跨异构物理载体（ROV / 鱼雷 / 仿生鱼）的**单一 Universal Checkpoint** 仍是愿景而非既成事实。

---

# Part 5 · Long-term Ph.D. Roadmap & Vision（迈向万能自适应底座）

> 站在第一性原理高度，Week 11+ 的长线规划。核心信念：**冻结大脑、只调反射的谱隔离机制，是通向"万能具身自校准控制底座"的可扩展路径。**

## 5.1 Phase III · Ph.D. Year 1 — 从平面到体积、从状态到感知

**目标**：把 2D 平面/姿态控制升级到 **3D 体积空间控制**，并融合机载 **视觉-惯性 / VLM** 感知。

- **III-A 3D 体积控制**：把深度软屏障从 1-D 安全管推广到 3-D 安全壳；`z_bridge` 从姿态子空间扩展到 6-DoF 位姿流形；验证 Flip360 类奇点在体积空间的存活率是否仍可达 100%。
- **III-B VLM 感知闭环**：用机载多模态模型（视觉 + 惯性）产生 `z_bridge` 的高维语义先验，替代/增强当前纯状态观测的造桥源；保持"感知只影响 z_bridge，不解冻策略权重"的谱隔离纪律。
- **III-C 方向门控升级**：把 `⟨Δζ,Δa⟩>0` 单点门控升级为多源共识门控（SSWP + tracking-error + VLM 先验），在 3D 下继续拦截毒梯度。
- **里程碑**：3D 体积空间 zero-shot 存活率 + VLM 融合下 Task C 长程统一正向首次收敛。

## 5.2 Phase IV · Ph.D. Year 2–3 — 万能具身自校准底座（Universal Checkpoint）

**目标**：打造完全跨异构物理载体（ROV、鱼雷、仿生鱼）的**万能具身自校准控制底座**，冲击 **Nature Communications** 级控制学理论闭环。

- **IV-A Universal Checkpoint**：训练一个单一冻结策略 + 逆动力学锚点库，能通过纯 4-D zeta 在线适配到从未见过的载体形态；把"backbone 依赖性"这一当前边界（§4.4）转化为可控的收敛度谱系。
- **IV-B 理论闭环**：形式化"逆动力学监督方向性 + 方向门控 + 谱隔离"的稳定性证明，给出何时低维在线入口对闭环**非零敏感**的充要条件（直面 §4.2 的结构性上限）。
- **IV-C 跨形态泛化基准**：建立 ROV/鱼雷/仿生鱼三类异构载体的统一 zero-shot 基准，证明 Universal Checkpoint 的存活率与 headroom 可跨形态迁移。
- **里程碑**：单一 checkpoint 跨 ≥3 类异构载体 zero-shot 部署 + 稳定性理论闭环 → Nature Communications 级投稿。

## 5.3 愿景一句话

> **“One frozen brain, infinite bodies.”** —— 用一个冻结的专家大脑 + 一组逆动力学动作锚点 + 4-D 反射级在线自校准，让任意异构水下具身在极端海况下自适应生存。这正是 EasyUUV-STDW 从 Phase 1 的坐标契约之战，一路"去伪存真"走到今天所指向的终点。

---

## 附 · 图片资产（相对路径引用，可直接嵌入海报）

| 板块 / 卖点 | 资产 | 相对路径 |
|---|---|---|
| **Fig 1** 终极控制架构（渲染版）| Master Control Architecture | `figure/poster_figures/fig1_master_architecture.png` (+ `.drawio` 源) |
| **Fig 2** Wasserstein 漏斗 + Task A 收敛 | Funneling & Golden Convergence | `figure/poster_figures/fig2_wasserstein_funneling.png` |
| **Fig 3** Flip360 生存 + 跨载体 | Flip360 Survival & Cross-Embodiment | `figure/poster_figures/fig3_flip360_cross_embodiment.png` |
| **Fig 4** 解耦时域相关性探针（真实）| Decoupling Probe | `figure/poster_figures/fig4_decoupling_probe_source.png` |
| Fig 2 相空间原始诊断 | phase-space source | `figure/poster_figures/fig2_phase_space_source.png` |
| 🅱 方向门控 / Part 3 安全网 | Safety Shield | `../poster_asset_1_safety_shield.png` |
| 🅰 动作锚点 / Part 3 | Action Bridge vs Legacy | `../poster_asset_2_action_bridge.png` |
| 🅲 Flip360 / Part 3 | Flip360 Manifold Survival | `../poster_asset_3_flip360_manifold.png` |
| FM 测地造桥 / Part 3 | FM Geodesic Bridge | `../poster_asset_4_fm_geodesic.png` |
| Task A 相空间收敛 | curve1 phase-space (20.4×/15.0× 分离) | `figure/v1_phase7_diagnostics/curve1_phase_space_pitch_taskA_30k.png` |
| 解耦探针 | curve3 decoupling | `figure/v1_phase7_diagnostics/curve3_decoupling_b1_runtime_ctrl_smoke_thr0.png` |

```markdown
![Directional Gate Safety Shield](../poster_asset_1_safety_shield.png)
![Inverse Action Bridge vs Legacy](../poster_asset_2_action_bridge.png)
![Flip360 Manifold Survival](../poster_asset_3_flip360_manifold.png)
![Flow-Matching Geodesic Bridge](../poster_asset_4_fm_geodesic.png)
```

### 附.2 · 每图海报排版指南（Placement / Size / Caption / Narration）

针对 A0 纵向三栏海报（约 841×1189 mm）给出每图的放置位置、尺寸、caption 与英文口述文本。

- **Fig 1 · 终极控制架构**：`顶部通栏（横跨三栏）`，宽≈750 mm × 高≈260 mm。
  - *Caption*: "Figure 1. The five-stage closed-loop Separation-Mechanism Online Adaptation architecture: a frozen policy (L2=0) is bridged by a Flow-Matching geodesic (α=0.25), translated through an inverse-dynamics proxy (R²=0.92), gated by a directional safety shield (~40% toxic gradients intercepted), and executed by an A-S-Surface controller with a [-0.5,-1.5] m depth soft-barrier. Only the 4-D ζ is updated online."
  - *Narration*: "Our controller never touches the neural weights online. We freeze the policy and adapt only a four-dimensional zeta vector; a flow-matching bridge builds a geodesic target, an inverse-dynamics proxy translates it with 0.92 R-squared, and a directional gate rejects about forty percent of harmful gradients before they reach the plant."
- **Fig 2 · Wasserstein 漏斗 + Task A 收敛**：`中栏上部（Methods→Results 过渡）`，宽≈520 mm × 高≈215 mm。
  - *Caption*: "Figure 2. (Left) Phase-space Wasserstein funneling toward the safe attractor (schematic). (Right, real data) Task-A adaptive loss decays monotonically from 5.83e-2 to 9.05e-5 on a log scale; the gate eff_frac stays silent for ~1320 steps then stabilizes at 0.35–0.60."
  - *Narration*: "On the right, this is real logged data. The adaptation loss drops three orders of magnitude and the gate stays completely silent until a drift is actually detected, then opens to about half throughput."
- **Fig 2S · Task A 相空间诊断源（真实）**：`中栏 Fig 2 正下方（小图内嵌 / 补充图）`，宽≈260 mm × 高≈210 mm。
  - *Caption*: "Figure 2S. Real Task-A phase-space manifold (pitch, 30k, from stdw_output). The pre-fault safe manifold (green density) concentrates into a narrow band around zero angular rate, while the post-fault drift point-cloud (n=12000) spreads widely — the empirical backing for the schematic funnel in Fig 2 (left)."
  - *Narration*: "This is the real phase-space evidence: before the fault the state stays pinned in a thin sheet near zero rate; after the fault it fans out, and our adaptation funnels it back."
- **Fig 3 · Flip360 生存 + 跨载体**：`右栏中部（Task B 版块）`，宽≈260 mm × 高≈300 mm（竖版三子图）。
  - *Caption*: "Figure 3. Flip-360 extreme-manifold survival (schematic, endpoint-anchored). (a) Roll/Pitch sweep through the ±π/2 and ±π singularities with 100% survival, attitude MSE 6.661→1.083 (-84%). (b) Depth free-floats inside the [-0.5,-1.5] m pipe with zero violation. (c) Thruster saturation (10-step moving average) stays below S<0.9; near-saturation 0.953→0.047."
  - *Narration*: "Even during a full 360-degree flip through the attitude singularities, the vehicle survives every time; depth free-floats inside the safety pipe rather than fighting the waves, and thruster saturation collapses from ninety-five percent to under five percent."
- **Fig 4 · 解耦时域相关性探针**：`左栏下部（Spectral Separation 版块）`，宽≈260 mm × 高≈175 mm。
  - *Caption*: "Figure 4. Temporal decoupling probe (real data). After spectral separation the correlation between the self-supervised correction Δū and the physical bias decays to r≈0, whereas the pseudo-action↔action reference stays at r≈0.98 — evidence that fitting in action space would parasitically shadow the current action."
  - *Narration*: "This is the mathematical proof behind our demystifying-GDA story: once we isolate the spectrum, the learning signal fully decouples from the current action, while the naive action-space baseline stays pinned near one and diverges."
- **Fig 5 · Sim2Real 时序切片** ⚠️〔无数据源·未生成〕：`右栏底部（Sim2Real 版块，占位）`。缺真实照片/3D 轨迹，未生成；可由文字底座（4.0×–5.9× 跟踪压缩、σ 0.150→0.080 ~47% 收缩）替代，对主线闭环影响中等。

## 附 · 溯源与三文档链

- 本文档（交付物C，最终）：`docs_new/00_POSTER_CONSOLIDATION_20260720.md`
- 图表诊断报告（已整合入本文档 §3.3bis / §附.2）：`docs_new/01_POSTER_FIGURES_DIAGNOSTICS_20260720.md`
- 原料池（交付物B，流水账）：`docs_new/00_CONSOLIDATION_LEDGER_20260720.md`
- 规范蓝图（交付物A，Plan）：`docs_new/00_CONSOLIDATION_PLAN_20260720.md`
- **20260720 本轮真实跑盘产物**：`.results/phase7_wide256_seed_ab_20260720_151855/`（Phase7 A/B）、`.results/table3_noise_sweep_20260720/`（噪声敏感度）、`.results/v1_task_a_marathon_boundary_decoupled/`（Task A failsafe 长程）、`.results/collect_analytic_obs12_20260714_151500/`（跨载体 baseline）。
- 一手来源：`docs_new/01_LOG_CODE/*`、`docs_new/02_REPORT_USER/*`、`docs_new/03_PLAN_FUTURE/*`、`AGENTS.md`（20260713–20260719 单句锚点）、`easyuuv_paper.md`、`stats_{a,b,c}_milestone.txt`。

> **保真纪律再声明**：所有 `〔落地〕` 均可在上述一手来源逐字复核；`〔派生〕` 均已注明计算口径；`〔待核实〕`（24×–68× / 85%）在任何对外海报中**必须**替换为可溯源真值或保留待核实标注，不得作为既成结论展示。

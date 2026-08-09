# 00 · Consolidation Plan — docs_new 学术级降维压缩规范（20260720）

> **本文件是三文档流水线的施工蓝图（中间文档①）**。目的：把用户散落在 prompt 里的整合规则、5 板块结构、保真策略、卖点清单、数字台账，固化成一份自洽、抗上下文压缩的规范。后续两份文档（Ledger 原料池、最终 Poster 文档）严格以本文件为准。

---

## 1. 三文档流水线定义

```
交付物A：00_CONSOLIDATION_PLAN_20260720.md   ← 本文件（规范/蓝图）
        │
        ▼  （逐个读日志，负面/边界一句话，正向留数据+分析）
交付物B：00_CONSOLIDATION_LEDGER_20260720.md  ← 原料池（流水账，按 Phase 时间线三档）
        │
        ▼  （二次压缩，只从 Ledger 取料，不回翻原始日志）
交付物C：00_POSTER_CONSOLIDATION_20260720.md  ← 最终自包含文档（5 板块，~50KB）
```

**三份文档全部留存**。A 定规范；B 建原料池（承担最重的"读+一句话概括"工作）；C 只从 B 二次压缩，保证口径一致、前后严密。

---

## 2. Consolidation Guidelines（整合与加工规则）

### 2.1 结构化大局观（Macro-level Perspective）
- **不罗列**零碎调试代码、某天具体 Traceback、临时探针输出。
- **要提炼**"走过的弯路、踩过的雷、重构的理论"为有理有据、环环相扣的**学术探索史**。
- **不回避负面数据**：诚实把"Action 自训练在线退化"和"DCE 末期发散"作为**重大物理发现**论述——说明它们如何推翻传统算法假设，逼迫回归物理第一性原理。

### 2.2 金句提炼规则（Headline Callouts）
- 每个正向/准正向结果**必须给出精确实验数据**。
- 自动提炼 **3–4 句** 可在海报上以 **80pt 特大粗体**展示的"口号式金句（Slogan-ready Callouts）"。
- 金句中英双语（英文便于直接排版进 PPT/InDesign）。

### 2.3 数据保真三档标签（用户授权）
| 标签 | 含义 | 处理 |
|---|---|---|
| `〔落地〕` | 日志 / stats / AGENTS.md 直取 | 直接写，带来源脚注 |
| `〔派生〕` | 由 stats 原始曲线现算 | 写入 + 注明**计算口径与来源** |
| `〔待核实〕` | 模板值（24×–68×、85%），暂无根据 | 显式标注，**不伪造精确值**；找到根据后回填 |

> 用户明确："可使用已落地数字，并从以往实验数据派生关键数据，二者并行；日志可能有信息丢失，剩下的无根据数据除非找不到再推测，并明确标注。"

---

## 3. 四大硬核卖点骨架表（用户已锁定）

| # | 卖点 | 数据支撑（含保真标签） | 海报金句(80pt, 中英) | 主来源 |
|---|---|---|---|---|
| ① | **逆动力学动作锚点** | Inverse Proxy `R²=0.92` vs Forward Proxy `R²=0.13`〔落地〕；52.4 万条数据 Forward 仍 `0.13`〔落地〕 | "Invert, Don't Predict: R²=0.92 Action Bridge Ends Co-Adaptation Collapse." / "逆向动作造桥，R²=0.92 终结共适应崩溃。" | REPORT_SYSTEMATIC_LESSONS、AGENTS 20260718 |
| ② | **方向门控安全防火墙** | 拦截 ~40% 有毒梯度〔落地〕；放行率 `eff_frac` 稳定 0.55–0.60、Loss ~0.05（6000 步）〔落地〕 | "A Physics Firewall Blocking 40% Toxic Gradients — Adapt Only When Safe." / "物理防火墙拦截 40% 毒梯度，只在安全时自适应。" | PLAN_MILESTONE_POSTER §4 |
| ③ | **Flip360 极限流形生存** | 深度软屏障 `[-0.5,-1.5] m`〔落地〕；奇点区 100% 存活〔落地〕；饱和 `S_actuator<0.9`〔落地〕 | "100% Survival Through 360° Singularity by Trading Depth for Attitude." / "以深度换姿态，360°奇点区 100% 存活。" | prompt.md Task B、REPORT_SYSTEMATIC_LESSONS |
| ④ | **谱隔离 / zeta-only 在线** | 冻结策略权重 `L2=0`〔落地〕；仅在线更新 4-D zeta〔落地〕；Task A Loss `~1e-4 rad²`〔落地〕 | "Freeze the Brain, Tune the Reflex: Zero-Weight-Drift Online Adaptation." / "冻结大脑，只调反射：策略零漂移在线自适应。" | AGENTS 20260718、stats_a_milestone |

> 最终 Part 1 取全部四条为「数据气泡卡片 + 80pt 金句」。

---

## 4. 落地真数字总台账

### 4.1 架构级（去伪存真）
- **Forward Proxy 雅可比崩溃**：52.4 万条数据下预测 Δs 的 `R²=0.13`（比 6000 条更低）→ 推翻"数据饥饿"，坐实一步监督结构性病理。〔落地〕AGENTS 20260718
- **Inverse Proxy 反转**：预测动作，`R²=0.92`（动作空间无状态惯性干扰）。〔落地〕REPORT_SYSTEMATIC_LESSONS
- **Proxy 局部 Jacobian 对齐弱**：`cosine_dyn` 16-probe 均值 `≈0.039`、中位数 `≈0`、`p05≈-0.764`、`p95≈0.787`；64-probe 全维度中位数 0。〔落地〕AGENTS 20260718

### 4.2 Task A（Long-Horizon Auto-Trim Marathon）
- 跟踪 Loss：`5.835e-2 → 9.05e-5`（stats_a_milestone step 1380→11940 单调收敛）。〔落地〕
- 门控放行率（eff_frac）：稳态 0.50–0.68，长期均值 ~0.55–0.60。〔落地〕stats_a_milestone
- 前 ~1320 步慢环静默（Loss=0.0）：门控完全阻断，不被波浪带偏。〔落地〕stats_a_milestone
- depth_guard_eps 修复后 baseline 回到 `195/195 accepted`。〔落地〕AGENTS 20260719
- hysteresis failsafe：深度均值 `-2.745 → -1.275`，`depth_violation_time_fraction → 0`。〔落地〕AGENTS 20260719

### 4.3 Task B（Extreme Manifold Survival - Flip360）
- 深度软屏障 `[-0.5,-1.5] m`，过渡带 `[-0.5,-0.7]`、`[-1.3,-1.5]`。〔落地〕AGENTS Stable Constants
- 奇点区 100% 存活（uuv6）；uuv4 欠驱动目标 ≥85% 存活。〔落地〕prompt.md Task B
- 执行器饱和 `S_actuator<0.9`（保留 ≥10% 推力裕度）。〔落地〕prompt.md §7
- B-full-continuous recovery 收敛到 `54/54` validated CSV，`subtask1_pilot_positive`（连续家族受限成立，flip360 唯一全量无 saturated-looking）。〔落地〕AGENTS 20260717
- stats_b_milestone：Loss 在 flip 注入后从 ~1e-4 跳到 2.3e-1 峰值再回落到 ~2–5e-2（翻转扰动响应）。〔落地〕stats_b_milestone

### 4.4 Task C（Zero-Shot Cross-Embodiment）
- accepted 解冻链：`0/195`(strict+off+both) → `33/195`(practical_band+boundary) → `195/195`(depth_guard_eps 修复 / grad_mask)。〔落地〕AGENTS 20260719
- trust-bug 修补：`accepted=0 → 15/15`(短程) → `195/195`(长程)。〔落地〕AGENTS 20260719
- 三方公平 A/B（1200-step，全 15/15）：raw_abs SO3 `0.12838` < delta_id `0.12888` < policy_on_zbridge `0.12891`；final_mse delta_id `2.42858` 微弱最佳。〔落地〕AGENTS 20260719
- 三方长程（12000-step，全 195/195）：raw_abs SO3 `0.14521`/final_mse `2.43907` 最佳；delta_id `0.14607`/`2.44132`；policy_on_zbridge `0.14611`/`2.44115`。〔落地〕AGENTS 20260719
- raw_abs+geo=0.02：短程 `0.12277`/`2.42791`（优于 geo=0.05 的 `0.12838`/`2.42874`）；长程 SO3 `0.14521→0.14212` 改善，但 final_mse `2.43907→2.44411`、depth_violation `0.81800→0.81958` 恶化（短长程分叉）。〔落地〕AGENTS 20260719
- geo_zeta1 active-path probe：SO3 `0.0573→0.0202→0.0100`，电机 raw 均值 `0.0843→0.1030→0.1619`（geo_zeta1=0.25/1.0/4.0）。〔落地〕AGENTS 20260719
- write 增强 A/B：write_progress_att_ratio `1.16e-4→1.17e-3`(A-only)；bridge_residual_att_norm `≈7.15e-4`(B-only)；但 12000-step final_mse/SO3/depth 三组完全重合。〔落地〕AGENTS 20260719

### 4.5 可视化资产
- 根目录 4 张海报 PNG：`poster_asset_1_safety_shield.png`、`poster_asset_2_action_bridge.png`、`poster_asset_3_flip360_manifold.png`、`poster_asset_4_fm_geodesic.png`。〔落地〕ls 核实
- `docs_new/figure/` 下 107 张诊断图（含 curve1 相空间、curve3 解耦、flow_matching_* 系列、stdw_saturation_authority 等）。〔落地〕ls 核实

---

## 5. 待派生 / 待核实数字清单

| 目标 | 模板值 | 派生尝试来源 | 状态 |
|---|---|---|---|
| Bare-RL vs S-Surface 跟踪精度倍数 | 24×–68× | `easyuuv_paper.md`、`REPORT_V1_TASK_EFFECT_DEPTH_FREEFLOAT`、`stats_*.txt` | 待 r3 派生；否则 `〔待核实〕` |
| 执行器抖振/纹波抑制 | 85% | 同上（RMS 纹波对比曲线） | 待 r3 派生；否则 `〔待核实〕` |

---

## 6. 最终文档（交付物C）目标结构与字数配额

| 板块 | 标题 | 内容 | 占比 |
|---|---|---|---|
| Part 1 | Executive Summary & Poster Headline Callouts (40pt 大字墙) | 学术冲击 Abstract + 4 张数据气泡卡片 + 4 句 80pt 金句 | ~20% |
| Part 2 | Demystifying GDA: The Scientific History of Eliminating GDA Gaps | 去伪存真时间线+因果链（4 大坑→反转） | ~25% |
| Part 3 | The Ultimate Solution | 最终架构五件套 + 4 张资产图 + 命令契约摘要 | ~25% |
| Part 4 | What remains Unsolved & Current Limitations | 物理边界诚实清单 | ~15% |
| Part 5 | Long-term Ph.D. Roadmap & Vision | Phase III (Y1) / Phase IV (Y2-3) | ~15% |

- 总目标 ~50 KB，信息不足可上探 60–80 KB。
- 所有数字带保真标签与来源脚注；图片用相对路径 markdown 引用。

---

## 7. 图片资产映射表

| 卖点/板块 | 首选图 | 相对路径 |
|---|---|---|
| 卖点② 方向门控 / Part 3 安全网 | Safety Shield | `../poster_asset_1_safety_shield.png` |
| 卖点① 动作锚点 / Part 3 | Action Bridge | `../poster_asset_2_action_bridge.png` |
| 卖点③ Flip360 / Part 3 | Flip360 Manifold | `../poster_asset_3_flip360_manifold.png` |
| FM 测地造桥 / Part 3 | FM Geodesic | `../poster_asset_4_fm_geodesic.png` |
| Task A 相空间收敛(补充) | curve1 phase-space | `figure/v1_phase7_diagnostics/curve1_phase_space_pitch_taskA_30k.png` |
| 解耦探针(补充) | curve3 decoupling | `figure/v1_phase7_diagnostics/curve3_decoupling_b1_runtime_ctrl_smoke_thr0.png` |

> 最终文档在 `docs_new/` 下，故根 PNG 用 `../`，figure/ 用相对路径。

---

## 8. 施工纪律

1. 只读原料（`01/02/03/04`、`AGENTS.md`、`prompt.md`），只新增 A/B/C 三文件，不改任何既有文件。
2. 超大日志（177KB/131KB/88KB）不逐行读，`rg` 定位结论/数字/负面词后精读片段。
3. AGENTS.md 20260713–20260719 单句锚点=压缩主脉络。
4. Ledger 完成后，Final 只从 Ledger 取料，不回翻原始日志。
5. 叙事因果闭合：负面发现 → 被逼回第一性原理 → 最终方案 → 边界 → 展望。

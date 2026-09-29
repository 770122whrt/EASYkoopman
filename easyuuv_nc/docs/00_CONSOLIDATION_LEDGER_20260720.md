# 00 · Consolidation Ledger — docs_new 全量结论流水账（20260720）

> **中间文档②（原料池）**。规则见 `00_CONSOLIDATION_PLAN_20260720.md`。
> 负面/边界结论 → 一句话概括；正向结论 → 保留精确数据 + 一句分析。
> 保真标签：`〔落地〕`日志直取 · `〔派生〕`由 stats/paper 现算注口径 · `〔待核实〕`模板值暂无根据。
> 三档色标：🟢 正向（可部署/可汇报）· 🟡 边界（条件成立/准正向）· 🔴 负面（被证伪/发散/退化）。
> 最终文档只从本 Ledger 取料，不回翻原始日志。

---

## 卷首 · 全弧一句话（供 Final Part 2 主脉络）

> **一步前向代理雅可比结构性崩溃（R²=0.13）→ 逼迫放弃状态空间自训练 → 回归逆动力学动作锚点（R²=0.92）+ 方向门控物理防火墙（拦截 ~40% 毒梯度）+ 冻结策略只调 4-D zeta 的谱隔离在线机制。**这是一部"去伪存真"的自监督自适应史。

---

## Phase 1–2 · 深度屏障坐标契约之战（20260712）

来源：`LOG_CODE_PHASE2_1_2_4_CLOSURE`、`REPORT_PHASE2_NEXT_SMOKE`、`PLAN_V1_20260712`、`LOG_CODE_PHASE2B_REPAIR`、`REPORT_PHASE2B_REPAIR`

- 🔴〔落地〕**Task B safe-core 初期姿态失控**：depth_violation=0.9367、so3=0.5670、headroom_min=0.0000、motor_p95=1.0000、delta_norm_p95=12.9854 → 强深度约束把 100% 推力打满，姿态彻底失控。（一句话：深度硬约束会吃光控制权、逼停姿态。）
- 🔴〔落地〕**Task A 深度违规**：depth_violation_time_fraction=0.4780 → 坐标契约不对齐时近半时间在违规。
- 🟡〔落地〕**深度只占 V 能量 ~3%**：推翻了"深度是姿态失控主因"的直觉，把矛头指回坐标契约本身。
- 🟢〔落地〕**Lyapunov 深度判据重设计**：只有 `delete + practical_band` 组合把极性翻正（TREAT 0.943 > LEGACY 0.923），其余组合都把"更好跟踪"误判成"更差"。**分析**：证明 strict `dV<0` 判据本身有病理，控制效果与判据极性必须分离评估。
- 🟢〔落地〕**深度契约修复**：改用 surface_relative_depth + 1m 安全管 `[-1.5,-0.5]`，60-step 冒烟通过。**分析**：这是后续所有 Task 的深度语义地基。
- 🟢〔落地〕**Phase 2b 三支修复齐验证**：deadband 300-step depth_violation=0.0；state-only light E-SUOT `4.1183→0.000247`；FM loss `3.7126→0.7701`、terminal_mmd=0.0330、curvature=0.0241。**分析**：deadband/状态残差/FM 造桥三条修复线首次同时打通。
- 🟡〔落地〕**deadband 深度-姿态 trade-off**：120-step depth=0.0 但 so3=0.5466、headroom_min=0.0934 → 消了深度违规却把姿态裕度压到近零，须 300 步才回落到 so3=0.2831。
- 🔴〔落地〕**full E-SUOT 疲软**：`4.4384→2.9818`（对比 light 版 `→0.000247`）→ 完整 E-SUOT 收敛无力，确立"light 版才是主力"。

---

## Phase 3 · 解耦门控（20260712）

来源：`LOG_CODE_PHASE3_STANDALONE`、`REPORT_PHASE3_STANDALONE`、`PLAN_PHASE3_STANDALONE`

- 🟢〔落地〕**只有 Task B 通过解耦门**：disagreement gate Task B pass=1.0（90 hits）、decoupled_enough=1.0000。**分析**：Flip360 是唯一伪动作与真实动作充分解耦的任务，为后续"Flip360 是最干净部署证据"埋线。
- 🔴〔落地〕**Task A / Task C 全不解耦**：Task A gate=0.0833、Task C base=0.0433、uuv4=0.3700，全部 0 hits → 伪动作在 A/C 上仍死钉在动作空间，无独立信号。
- 🟢〔落地〕E-SUOT Task A light `0.1922→0.00013`、FM Task A loss=0.0100/mmd=0.000154 → 离线残差与造桥收敛依旧健康（与门控失败并存）。

---

## Phase 4 · 信号源审计：伪标签=策略影子（20260712）

来源：`LOG_CODE_PHASE4A_SIGNAL_SOURCE`、`REPORT_PHASE4A_SIGNAL_SOURCE`、`REPORT_PHASE4_TO_PHASE56_GATE`

- 🔴〔落地〕**legacy 伪标签 = clip(action)，fraction=1.000**：动作空间伪标签本质是策略输出的裁剪影子，无任何独立于策略的物理信息。**分析**：这是"Action 自训练在线退化"的第一性根因——你在用策略拟合策略自己。
- 🟡〔落地〕**SSWP 在故障下能抬升信号**：thruster-0 fault SSWP lift=31.6629、tail corr=0.9805；thr4 lift=0.4791/corr=0.9999 → 故障暴露时 SSWP 能产生可分离信号，但常态下所有 v3 臂仍是 policy_shadowing（corr 0.9754–0.9992，无一 <0.7）。
- 🔴〔落地〕**high-load 下 full E-SUOT 几乎不动**：`15.0564→14.0009`（light 版 `13.3114→0.2869`）→ 再次坐实 full 版无力。

---

## Phase 5–6 · FM 造桥与运行时状态机（20260712）

来源：`LOG_CODE_PHASE56_INFRA`、`REPORT_PHASE56_*`、`PLAN_PHASE56_INFRA`

- 🟢〔落地〕**FM midpoint 全面碾压 terminal/linear**：midpoint_wins=9 / terminal_wins=0；light E-SUOT `15.06→0.1818`；best cost_after=0.00581（m120_i12+alpha0.375）；Pareto 点 m160_i16+0.25（mmd=0.0496/curvature=0.0071/cost=0.00591）。**分析**：FM 的正确角色是"中间流形/测地桥生成器"（midpoint），不是终态替代器（terminal）。
- 🟢〔落地〕**early-midpoint（alpha 0.25–0.375）为 Pareto 最优**，终态版 cost_after=0.3828（差一个量级）。
- 🟢〔落地〕**安全核心 reset 修复深度违规**：depth_violation `0.6867→0.08`、积分 `1.2238→0.0109`、cycles `6→11`。**分析**：deterministic safe-core reset 打破了随机 reset 锁死的"睡眠吸引子"。
- 🟢〔落地〕**实时预算达标**：FM 1.35ms / E-SUOT 9.53ms / gate 0.060ms → 整链可实时部署。
- 🟡〔落地〕**运行时状态机 fault 走查**：fault depth_violation_hard_true=202/240、fault-above-healthy curvature p95=0.8083 → 深度违规是常见硬阻塞，曲率只是软前兆而非硬门。
- 🟡〔落地〕**全程 pilot_execution_allowed=false**：Phase 5/6 只做 log-only 绑定验证，未放行在线控制。

---

## V1 · 深度自由浮动与 Flip360 姿态解放（20260713）

来源：`LOG_CODE_V1_20260712`、`REPORT_V1_TASK_EFFECT_DEPTH_FREEFLOAT`、`REPORT_V1_PROBE_CONTRACT`、`REPORT_PHASE7_PRE_DIAGNOSTIC`

- 🟢〔落地〕**深度 free-float 显著改善 Flip360 姿态**：so3 `1.592→0.269`（**-83%**）、attitude_mse `6.661→1.083`（**-84%**）、|pid_depth| `0.761→0.024`（**-97%**）、near-saturation `0.953→0.047`。**分析**：以深度自由度换姿态精度，是 Flip360 极限流形生存的核心机制（对应海报卖点③）。
- 🔴〔落地〕**strict Lyapunov 判据把更好误判成更差**：lyapunov_pass `0.866→0.439`，per-channel dV<0 仅 42–49% → 判据病理，而非控制退化。
- 🟡〔落地〕**depth 契约会通胀分数**：Flip360 raw contract bare_policy=1.0/70.93，改 surface-relative 后掉到 0.772/22.21 → 评分口径必须统一，raw 契约会虚高。
- 🟡〔落地〕**Task C 信号弱**：W1 uuv4-vs-base 仅 2.06（~1.7× 自噪声）→ 跨载体信号刚出噪声地板，弱。
- 🔴〔落地〕**Phase 7 契约未就绪**：contract_ready=FALSE（6 个 blocker）。

---

## V1 · Task A 长时马拉松（30k）（20260713）

来源：`REPORT_TASK_A_MARATHON_30K_RECYCLE`、`LOG_CODE_V1_20260713`

- 🟢〔落地〕**30k 单 episode 连续性稳固**：episode_reset=0、true_x `-124.9→1.8 m`（125m 漂移全程无重置存活）。**分析**：长时程边界解耦 + 安全核心 reset 让马拉松单 episode 成立。
- 🔴〔落地〕**Task A 深度重定心被证伪**：setpoint `-1.0→-0.53` 但真实深度 `-1.472→-1.468` 几乎不动 → 慢环调 setpoint 无法真正移动深度。
- 🔴〔落地〕**故障下姿态严重退化**：fault so3 7.0×（`0.0124→0.0868`）、attitude_mse 42×、control_effort 2.7×、深度偏移 +14mm → 故障暴露控制权本体不足。

---

## Phase 7 · 状态锚点离线路线的系统性证伪（20260713–20260716）

来源：`LOG_CODE_V1_20260713`、`REPORT_PHASE7_B2_D_PATH_OBS12`、`PRE_PHASE7_STATE`、`PLAN_B5_iib_actor_critic_with_encoder`

- 🔴〔落地〕**"next-state R²=0.995" 是海市蜃楼**：前向代理预测下一状态 raw R²=0.995，但预测残差 Δs 的 held-out R²=0.082（shuffle 8.31×）。**分析**：物理步长极短、状态惯性极大，网络复读当前状态就能拿高 R²，动作梯度完全没学到——这是"Forward Proxy 雅可比崩溃"的直接证据。
- 🔴〔落地〕**B5-b/B5-c 全线证伪**：cosine 0.464/0.482；self_consistency 0.96–0.99（远超阈 0.8）、v/A=0.178、cos(A,ḡ)=0.986 → 状态锚点方向被 z 无关聚合项/低秩子空间支配。
- 🔴〔落地〕**DCE+PILE（ii-b）证伪**：vloss `0.97→7.25`、pile=58.12、recon 194× → 双 optimizer step + encoder 梯度泄漏导致末期发散。**分析**："DCE 末期发散"是第二个重大负面物理发现，逼迫放弃 encoder 参与的复杂路线。
- 🔴〔落地〕**scale-only（ii-a 宽 actor）被否**：filtered_error Q4 B/A=1.247、so3 Q4 B/A=1.112、L_tgt Q4/Q1=1.255，物理占比仅 3% → "仅放大 actor" 不是解。
- 🔴〔落地〕**离线门必要非充分**：2 个 offline-PASS 家族（ens_m5、wide256_iia）在线全 FAIL → offline gate 只保留"必要不充分"地位。
- 🟢〔派生〕**12 段离线证伪聚成同一结论层**：所有失败都落在 L2 方向/量级层，而非拟合精度层（B5-a 残差 R²≈0.08 只比 identity 好 ~9%；B5-c 重测 pooled R²=0.263 也证明"精度不是杠杆"）。**分析**：这是把负结果升级为约束的关键——问题不在"拟合得不够准"，而在"方向本身错"。

---

## Phase 7 · 慢环 backbone 依赖性与分叉合同（20260716）

来源：`REPORT_LIVE_AB_U4`、`REPORT_U1_SLOW_LOOP`、`REPORT_WIDE256_3ARM`、`PLAN_PHASE7_WIDE256_ONLY`、`PLAN_U1_SLOW_LOOP_STABILITY`

- 🔴〔落地〕**base_2846 对慢环诊断完全免疫**：U4 Group A 三臂（legacy/state/zero）filtered_error tail 三臂 `3.3533/3.3445/3.3440`（相对差 <0.3%），loss_target 量级差 4 个数量级（legacy O(1) vs state O(10⁴)）但物理层零差异。**分析**：offline gate 的 loss_target 数量级绝不能作为在线反例判据。
- 🟡〔落地〕**wide256 pilot 仍保留诊断敏感度**：Group B state arm 相对 legacy filtered_error tail +24.7%（4.2744 vs 3.4273），复现 Case B。→ 慢环效应是 backbone-intrinsic，柱子 C 保持未闭合。
- 🟢〔落地〕**wide256 legacy anchor 是真实在线改善**：U1 重解释把 "+20.7% null 差距" 判为 legacy action anchor 的真实增益（wide256 score_6000=0.8286，+17.14% vs null，under-converged，n_saturated=0）。**分析**：H5 只在 wide256-like（欠收敛）主干上成立。
- 🔴〔落地〕**base_2846 是 saturated-looking**：H5 effect -0.28%、backbone ratio=1.0028、三臂塌到 fe_tail≈3.344（S1 +0.26%/S2 -0.015%）→ 方向失配是 backbone-intrinsic，base_2846 退出主线，回退 offline-only。
- 🟡〔落地〕**Phase 7 分叉合同定稿**：`wide256-like → under-converged`（可继续 legacy anchor）；`base_2846-like → saturated-looking`（视为 slow-loop L2 结构性闭合）。仅允许 wide256-only scoped entry，禁止误读为 full-sweep 放开。

---

## Phase 7 · B-full 连续家族恢复（20260717）

来源：`REPORT_PHASE7_BFULL_CONTINUOUS_EXECUTION`、`PLAN_PHASE7_WIDE256_ONLY`、AGENTS 20260717

- 🔴〔落地〕**首轮 43/54 arms 共享远程 ground-USD 初始化故障**：只有 11/54 valid → 基础设施故障，partial 行不得升格为物理 verdict。
- 🟢〔落地〕**恢复后收敛 54/54 validated CSV**，升级 `subtask1_pilot_positive`；model_50/flip360 0.769986（+23.00%）、model_249/sine 0.988604（+1.14%）。**分析**：连续参考家族受限成立。
- 🟡〔落地〕**clean headroom 只在 flip360 无歧义**：flip360 唯一全量无 saturated-looking；sine/mixed 虽保持 `action>null` 仍贴饱和边界。→ 不是"全 config clean headroom"。
- 🔴〔落地〕**跨任务 pilot 首次为负**：subtask1_pilot_negative（sine 0.9886/+1.14% 非干净正、step 1.0782/-7.82% 负）→ flip360 证据链不能自动外推到其他 analytic config。

---

## Phase 8 · Loss-Physics 失配与代理病理定性（20260718）

来源：`PLAN_PHASE8_GRADIENT_DIAGNOSIS`、`PLAN_PHASE8_MACRO_ARCHITECTURE`、AGENTS 20260718

- 🔴〔落地〕**52.4 万条数据下 Forward Proxy Δs R²=0.130**（比 6000 条的 0.171 还低）→ 彻底推翻"数据饥饿"假说，坐实**一步监督结构性病理**。**分析**：Δs std 仅为 s 的 5–9%，网络靠复读当前状态即可拿低 loss，完全忽略动作梯度。（海报卖点①的反面论据。）
- 🔴〔落地〕**代理局部 Jacobian 对齐弱**：cosine_dyn 16-probe 均值≈0.039、中位数≈0、p05≈-0.764、p95≈0.787；64-probe 全维度中位数 0、置信区间跨 ±0.8 → 失配是全局、全维度的。
- 🟢〔落地〕**分离机制在线成立**：冻结 policy（L2=0），只更新 4-D zeta；240-step zeta-write 4/4 accepted；FM_midpoint 把 l_tgt_state 均值 `0.319→0.0466`（vs esuot_light 0.3193）、curvature_p95≈0.0170。**分析**：谱隔离/zeta-only（海报卖点④）的 wiring 证据。
- 🟢〔落地〕**电机饱和只有 16%–30%**：证明"硬件不是极限"，控制权瓶颈在算法而非执行器。
- 🟡〔落地〕**zeta 能动但没动对**：uuv6_angled lr0.05 zeta 到 `[0.788,0.789,1.202,1.201]`，但 SO3 未改善（default 0.2177 / lr0.01 0.2185 / lr0.05 0.2221）→ 瓶颈从"更新幅度"转为"proxy/FM target 对 zeta 的物理方向性"。
- 🔴〔落地〕**GT-target 反而更差**：SO3 `0.2185→0.7160` → 直接用特权目标不但没帮助反而恶化，佐证方向性问题。

---

## Phase 8 · 降维动作锚点（方案 E）与方向门控（20260719）

来源：AGENTS 20260719 单句锚点、`PLAN_PHASE8_GRADIENT_DIAGNOSIS`

- 🟢〔落地〕**Directional Gate 物理防火墙**：在应用 Δζ 前强制其与伪动作修正方向点乘 >0；500-step eff_frac 0.54–0.59（拦截 ~40–45%），6000-step Task A avg loss ~0.0543/eff_frac ~0.604、Task B ~0.0577/~0.620。**分析**：这是应对一切盲目梯度更新的最后物理防线（海报卖点②）。
- 🟢〔落地〕**方案 E 逆动力学动作锚点闭环打通**：用 inv_proxy 把 FM 的 z_bridge 翻译成动作锚点 a_bridge，恢复在动作空间（线性可导）计算 surrogate loss。长程 run 显示 FM curvature≈0.0117、shift_norm≈0.251、a_bridge-policy attitude delta norm≈0.901。**分析**：Inverse Proxy R²=0.92 vs Forward 0.13——反转监督方向是去伪存真的关键（海报卖点①）。
- 🔴〔落地〕**Task A 慢环 zeta 微调本身几乎无物理增益**：真正显著改善 Task A 的是正交 fast-loop depth failsafe，而非 zeta4 微调。
- 🟢〔落地〕**Task A hysteresis failsafe 拉回安全核心**：深度均值 `-2.745→-1.275`、depth_violation_time_fraction `→0`。**分析**：Task A 有效主线是正交 fast-loop 深度保底（海报卖点④/Task A 安全故事）。
- 🔴〔落地〕**Task C low-dim 写入对闭环近零敏感**：三组 12000-step（A-only/B-only/A+B）增强写入后 final_mse≈2.4420、mean_so3≈0.14067、depth_violation≈0.82058 完全重合 → 即使显著增强 zeta4/action-bridge 写入，真实 cross-embodiment 闭环仍几乎零敏感。
- 🟢〔落地〕**根因定位：写入没进 active attitude path**：Task C so3 姿态走 geo_zeta1/geo_zeta2 分支，legacy zeta4 没命中 active 分支；命中 active 的 geo_zeta1 probe 产生可见变化（SO3 `0.0573→0.0202→0.0100`，电机 raw `0.0843→0.1030→0.1619`，geo_zeta1=0.25/1.0/4.0）。**分析**：不是"plant 对所有 zeta 零敏感"，而是没接到 active path。
- 🟡〔落地〕**接上 active path 后写入真实但收益仍小**：geo_so3 + write_scale=10 长程 runtime_geo_zeta1 漂到 `[0.680,0.607,0.609]`，runtime_pid/motor_saturation 分叉，但 mean_so3 ≈0.1465（略差于 legacy 0.1407）→ 学到的姿态更新方向本身不够有益。

---

## Phase 8 · Task C trust-gate bug 与三方公平 A/B（20260719）

来源：AGENTS 20260719 单句锚点

- 🔴〔落地〕**accepted=0 全冻结**：Delta-ID / Policy-on-zbridge 两条上游 15 次慢环尝试全部 stdw_acceptance_reason=target_mse，dir_guard≈0.972、direction_gate>0、depth_guard=0 → 不是方向问题，是死在 batch_trust 的 target_mse 回滚。
- 🔴〔落地〕**根因=trust gate before/after target 不对称 bug**：`action_bridge` 下训练 mse_tgt 对 a_bridge，但 batch_trust 在无 state_match_kit 时回退成对 pseudo_actions → before/after 比较了不同 target。**分析**：这是纯代码口径 bug 伪装成"物理全冻结"，是本项目最典型的"审计口径修正"案例。
- 🟢〔落地〕**修补后解冻**：Delta-ID / Policy-on-zbridge 从 accepted=0 直接到 15/15（短程）、195/195（长程）。修补后短程 SO3 `0.12993→0.12888`（Delta-ID）/`0.12891`（Policy-on-z），逼近最佳 raw_abs 0.12838。
- 🟢〔落地〕**accepted 解冻链（gate 合同层）**：`0/195`（strict+off+both）→ `33/195`（practical_band+boundary）→ `195/195`（depth_guard_eps 修复 / grad_mask=1,1,1,0）。**分析**：practical_band 纠正了 strict 判据把 195/195 全冻结的病理。
- 🟢〔落地〕**三方公平 A/B（1200-step，全 15/15）**：raw_abs SO3 **0.12838** < delta_id 0.12888 < policy_on_zbridge 0.12891；final_mse delta_id 2.42858 微弱最佳。
- 🟡〔落地〕**三方长程（12000-step，全 195/195）**：raw_abs SO3 **0.14521**/final_mse **2.43907** 最佳；delta_id 0.14607/2.44132；policy_on_zbridge 0.14611/2.44115。**分析**：更复杂的上游在长程未稳定超越 raw_abs，故默认上游保持 raw_abs。
- 🟡〔落地〕**geo_residual_scale 短长程分叉**：raw_abs+geo=0.02 短程 0.12277/2.42791（优于 geo=0.05 的 0.12838/2.42874）；长程 SO3 `0.14521→0.14212` 改善，但 final_mse `2.43907→2.44411`、depth_violation `0.81800→0.81958` 恶化。**分析**：geo=0.02 是"短程 SO3/headroom 正向、长程稳健性未闭合"的准正向分支——Task C 已从"主线失效/全冻结"推进到"默认主线稳定 + 局部 headroom 显现，长程统一正向仍未收敛"。

---

## stats_*.txt 曲线原料（20260719 落盘）

来源：`stats_a_milestone.txt`、`stats_b_milestone.txt`、`stats_c_milestone.txt`

- 🟢〔落地〕**Task A（stats_a_milestone）**：前 ~1320 步慢环静默（Loss=0.0，门控完全阻断，不被波浪带偏），eff_frac 稳定 0.328–0.371；后段 Loss 单调收敛到 `9.05e-5` 量级。**分析**：门控保底"只在安全时自适应"的直接曲线证据。
- 🟢〔落地〕**Task B（stats_b_milestone）**：起步 Loss 9.1e-5（step300），flip 注入后跳到 2.1e-2~4.5e-2 峰段再回落，eff_frac 0.49–0.69 → 翻转扰动响应可控。
- 🟢〔落地〕**Task C（stats_c_milestone）**：Loss 从 1.3e-2 逐步收敛到 3.6e-4~8.5e-4（step6840），so3 曲线在 0.18–0.25 区间 → 跨载体在线在数值上收敛，但 so3 未大幅下降（呼应"能动没动对"）。

---

## easyuuv_paper.md 底座数据（可用于派生底座卖点）

来源：`easyuuv_paper.md`（IROS/TASE 级 A-S-Surface 论文）

- 🟢〔派生〕**RL 相比无 RL 大幅降误差（仿真）**：Fig.8 compound error µ `0.452→0.103`（≈**4.4×**）。〔口径：仿真 Task2 复合误差均值比〕
- 🟢〔派生〕**DR 抗浮力漂移**：TABLE II Task1 Pos.buoy NDR→SDR `0.0344→0.0087`（≈**4.0×**），Task2 `0.0388→0.0066`（≈**5.9×**）。
- 🟢〔派生〕**LLM 在线微调抑制湍流误差**：Fig.12 yaw MSE `0.0812→0.0179 rad²`（≈**4.5×**），两次调节完成。
- 🟢〔落地〕**Sim2Real 零样本迁移**：真实水池 compound error µ `0.3836→0.2356` & `0.2876→0.2421`，σ `0.150→0.080` & `0.0970→0.0896`。
- ⚠️〔待核实〕**模板值 24×–68× 跟踪精度提升 / 85% 抖振抑制**：现有 docs_new 与 easyuuv_paper 均未直接落地此二值。可落地的最强真值是上述 4.0×–5.9× 量级与 σ 收缩 ~47%（0.150→0.080）。**最终文档必须用真值替换或显式标注 `〔待核实〕`，不得伪造 24×/68×/85%。**

---

## 可视化资产索引

- 🟢〔落地〕根目录 4 张海报 PNG：`poster_asset_1_safety_shield.png`、`poster_asset_2_action_bridge.png`、`poster_asset_3_flip360_manifold.png`、`poster_asset_4_fm_geodesic.png`。
- 🟢〔落地〕`docs_new/figure/` 107 张诊断图（curve1 相空间 20.4×/15.0× 分离、curve3 解耦、flow_matching_* 系列、stdw saturation authority 等）。

---

## Ledger → Final 映射备忘

| Final 板块 | 主要取料段落 |
|---|---|
| Part 1 金句卡片 | 四大卖点（①逆动力学 R²=0.92 · ②门控~40% · ③Flip360 -83%/-84%/100%存活 · ④zeta-only L2=0）+ paper 派生底座 4.4× |
| Part 2 去伪存真史 | Phase1→8 时间线：坐标契约→伪标签=影子→Forward崩溃R²=0.13→DCE发散→回归逆动力学 |
| Part 3 终极方案 | FM midpoint 造桥 + inv_proxy a_bridge + Directional Gate + zeta-only + depth failsafe + geo_so3 active path |
| Part 4 边界 | Task C 长程未统一正向、geo=0.02 短长程分叉、base_2846 saturated 免疫、跨任务外推负、24×/68%/85% 待核实 |
| Part 5 展望 | 2D→3D 体积控制+VLM（PhD Y1）；跨异构载体 Universal Checkpoint（PhD Y2-3）冲 Nature Comms |

---

## 补充 · 海报整合轮 + 仓库重构轮流水账（20260720–20260721）

> **迁移时补录**：本节把 Phase 8 之后、海报整合与 `easyuuv_nc` 重构两轮的落地结论补齐，
> 确认流水账无信息缺失。数据源：project_memory Lessons Learned + 本轮迁移实测。

### 海报整合轮（20260720–21）
- 🟢〔落地〕**Task A failsafe 增益量化**：开启 fast-loop depth failsafe 后，长程 depth_violation
  从 **0.998 → 0**，final_mse **-96.6%**。**分析**：这是"Task A 有效主线=正交深度保底"的
  最强量化证据（补足 Phase 8 只给了 `-2.745→-1.275` 均值、未给 MSE 降幅）。
- 🟢〔落地〕**噪声敏感度鲁棒性**：陀螺仪噪声翻倍（σ_ω=0.10，经 `--ang_vel_extra_std` 扫描）
  情况下，系统仍保持 **0% 重置率**。**分析**：验证架构稳定性，非拟合脆性。
- 🟢〔落地〕**Phase 7 A/B 极性重现**：长程噪声敏感度实验成功重现 wide256 legacy anchor 的
  在线改善极性（+17% vs null，与 U1 结论一致）。
- 🟡〔边界〕**系统边界确认**：观测延迟（obs_delay）机制在当前环境配置中**不存在**，涉及
  传感器模型改动，未获准前不实现（属第一性原理/系统边界，须先问用户）。
- 🟢〔落地〕**海报资产定稿**：A0 规格，低饱和松石绿配色（Pine/Emerald/Sage），Fig 1-4 精修
  完成（尺寸 70-80%、可读性优化、锚点避重叠）；`fig2_phase_space_source.png` 纳入体系。

### 仓库重构轮（20260721，本轮）
- 🟢〔落地〕**去伪存真重构落地**：新建 `easyuuv_nc` 干净包名子仓库（零 bootstrap hack，
  entry_point=`easyuuv_nc.env:EasyUUVEnv`），剔除 D1(DCE) 死变体，保留 flip360 主路径。
- 🟢〔落地〕**flip360 复现 byte-level 等价**：同日 head-to-head，源脚本 `play_stdw_adapt.py`
  与迁移版 `adapt.py` 在 6000-step flip360 上 **308 列全部 max|diff|=0.000e+00**，
  accepted 均为 **95/6000**。**分析**：证明重构对物理主线零副作用，可安全进入拆分阶段。
- 🟢〔落地〕**checkpoint md5 溯源**：4 个迁入 ckpt（wide256/flip360/uuv6_angled/base）md5
  与源 run 逐字匹配，已附 `SOURCE.txt`。
- ⏭️**未闭合（下一步）**：`adapt.py`（~7200 行）尚未拆为 `adaptation/`，D2–D6 死代码
  仅以惰性形式保留，待拆分阶段一并删除（见 `REFACTOR_GUIDE.md` §3）。

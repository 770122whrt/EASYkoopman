# AGENT_HANDOFF — easyuuv_nc 仓库接手指南（20260721）

> 面向"下一个接手本仓库的 agent / 研究者"。目标：**5 分钟内跑通 flip360 复现，
> 30 分钟内理解为什么代码长这样、哪些分支是死的、下一步该往哪走。**

---

## 0. 一句话背景

这是一部**"去伪存真"的自监督在线自适应史**：
> 一步前向代理雅可比结构性崩溃（R²=0.13）→ 逼迫放弃状态空间自训练 →
> 回归逆动力学动作锚点（R²=0.92）+ 方向门控物理防火墙（拦截 ~40% 毒梯度）+
> 冻结策略只调 4-D zeta 的谱隔离在线机制。

`easyuuv_nc` 是主仓库 `easyuuv_stdw` 被大量探针污染后的**去伪存真重构版**：
干净包名、零 bootstrap hack、剔除死变体（DCE），保留经验证的 flip360 主路径。

---

## 1. 先跑起来（Smoke → Repro）

```bash
cd <...>/easyuuv_stdw/easyuuv_nc
export PYTHONPATH=$(pwd):$PYTHONPATH

# 200 步冒烟（~1 分钟）：确认 action_bridge 全链路激活
bash workflows/tools/run_flip360_repro.sh 200

# 6000 步复现（~5 分钟）：坐实 accepted=95 基准
bash workflows/tools/run_flip360_repro.sh 6000
```
产物在 `.results/v1_task_b_flip360_barrier/easyuuv_parametric/.../stdw_output.csv`。
通过标准与基准值见 `docs/COMMAND_CONTRACT.md` §2。

---

## 2. 仓库结构导览

```
easyuuv_nc/
├── __init__.py                 # import 即注册 4 个 gym task（零 bootstrap）
├── env/                        # 环境本体（零 lab_tasks 依赖的自洽闭包）
│   ├── easyuuv_env.py          # EasyUUVEnv（entry_point 指向此）
│   ├── agents/rsl_rl_ppo_cfg.py   # PPO cfg（DCE runner cfg 已删）
│   └── assets/warpauv.py           # USD 资产路径
├── workflows/
│   ├── train.py                # 训练入口（去 bootstrap + 删 DCE）
│   ├── adapt.py                # 在线自适应主脚本（原 play_stdw_adapt.py, ~7200 行）
│   ├── configs/{train,tasks}/  # 训练 & Task A/B/C 配置
│   └── tools/run_flip360_repro.sh  # 一键复现
├── stdw_integration/           # FM/phase56/metrics/plots/signals/scheduler...
├── esuot/                      # light/full E-SUOT + semidual + transport
├── custom_workflows/           # cli_args / workflow_config / workflow_paths
├── utils/stdw_buffer.py        # StdwReplayBuffer
├── easyuuv_stdw_wrapper.py     # EasyUUVStdwWrapper
├── stdw_dir_guard.py           # 方向门控物理防火墙
├── checkpoints/{flip360,wide256,uuv6_angled,base}/model_*.pt
├── artifacts/{fm_bundle/, dynamics_proxy/inv_proxy_12_v1_large.pt}
└── docs/                       # 本目录：诊断结论 + 契约 + 指南
```

---

## 3. 死分支索引（**已判定绝对用不上，禁止复活**）

来源：`docs/00_CONSOLIDATION_LEDGER_20260720.md` + 主仓库 `AGENTS.md`。
迁移时 D1 已物理删除；**拆分 adapt.py 时又物理删除 D5**（micro-probe / auto-drift-router）。
D2–D4/D6 因位于 `action_bridge` 不可达/懒加载分支内，仍保留为"惰性死代码"，
**待后续拆解 `main()` 时一并删除**。

| 编号 | 死分支 | 证伪结论（一句话） |
| --- | --- | --- |
| **D1** | DCE / PILE（encoder+双 optimizer） | 末期发散（vloss 0.97→7.25，recon 194×）。**已物理删除**（argparse/helpers/branch/register 变体全清）。 |
| **D2** | B5 state-match（`state_match_kit_v1`） | 状态锚点方向被 z 无关聚合项/低秩子空间支配（cosine 0.46–0.48，self_consistency>0.96）。**仅剩懒加载 import，拆 main() 时删。** |
| **D3** | `l_tgt_space=zero` | 慢环 zero-target 与 legacy 在 base_2846 上物理零差异（fe_tail 相对差<0.3%）。 |
| **D4** | consensus oracle / SSWP-sign 方向修正 | 只有"减害"价值（SO3 0.12902→0.12838），未把方案 E 拉入正收益区。 |
| **D5** | micro-probe / auto-drift-router | 诊断脚手架，非在线主线。**已物理删除**（20260721 拆分 adapt.py 时清除 argparse 15 参数 / 构造 / in-loop 调用 / CSV 6 列 / `probe_deprecated.py`；302 列 byte-level 等价 PASS）。 |
| **D6** | delta_id / policy_on_zbridge 上游 | 修 trust-gate bug 后可解冻，但长程未稳定超越 raw_abs（0.14607/0.14611 vs 0.14521）。 |

> **default 上游 = `raw_abs`**（不是 delta_id / policy_on_zbridge）。

---

## 4. 活线（当前唯一可部署/可汇报的成果）

- 🟢 **flip360 深度 free-float**：so3 -83%、attitude_mse -84%、|pid_depth| -97%、100% 存活。
- 🟢 **逆动力学动作锚点（方案 E）**：inv_proxy R²=0.92，FM midpoint→z_bridge→a_bridge。
- 🟢 **方向门控物理防火墙**（`stdw_dir_guard.py`）：拦截 ~40% 毒梯度。
- 🟢 **谱隔离 zeta-only**：冻结 policy（L2=0），只更新 4-D zeta。
- 🟢 **Task A fast-loop depth failsafe**：深度均值 -2.745→-1.275，depth_violation→0。

---

## 5. 边界 / 未闭合（下一步空间）

- 🟡 **Task C 长程未统一正向**：`raw_abs+geo=0.02` 短程 SO3 正向（0.12277）但长程
  final_mse/depth 恶化 → "短程 headroom 显现，长程稳健性未闭合"。
- 🟡 **base_2846-like saturated 免疫**：慢环诊断对饱和 backbone 无效，回退 offline-only。
- ⚠️ **待核实数据**：24×/68% 跟踪精度、85% 抖振抑制 **在现有 docs 无落地根据**，
  可用真值为 paper 派生 4.0×–5.9× 与 σ 收缩 ~47%。**禁止伪造。**

---

## 6. 进一步实验验证思路（验收③，落地不实跑）

> 因子仓库验证成立（Plan A），本轮只实跑到验收②。以下为后续接手者的 checklist：

1. **Task A 长时马拉松**：用 `configs/tasks/v1_task_a_marathon_boundary_decoupled.yaml`
   + fast-loop depth failsafe（hysteresis 版），验证 30k 单 episode depth_violation→0。
2. **Task C 跨载体**：`configs/tasks/v1_task_c_cross_embodiment_safe_core_eval.yaml`
   + `--embodiment uuv6_angled` + `--stdw_runtime_attitude_zeta_path geo_so3`，
   对比 `geo_residual_scale=0.02/0.05` 的短长程分叉。
3. **上游 A/B**：`raw_abs`（默认）vs `delta_id` vs `policy_on_zbridge`——但已知长程
   raw_abs 最佳，除非有新机制，否则不必重跑。

---

## 7. 铁律（继承自主仓库 AGENTS.md）

- 做实质规划/实现前先对齐 `docs/00_CONSOLIDATION_*` 与 `COMMAND_CONTRACT.md`。
- 第一性原理改动（重训练、模型结构、控制裁剪、任务/指标定义、V 定义、部署假设、
  系统边界）**必须先问用户**。
- 新能力模块化且默认关闭，可 config/CLI 独立开关。
- 自适应结论只能用可部署信号，禁止用仿真特权信息偷渡。
- 负结果保留并升级为约束，不靠补丁掩盖。
- 除非明确放行，`online_allowed=false`。
- 不伪造数据；每生成图须亲自看图校验。

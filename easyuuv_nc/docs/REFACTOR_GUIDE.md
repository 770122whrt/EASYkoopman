# REFACTOR_GUIDE — 文件结构重构指南（20260721）

> 本文件规定 `easyuuv_nc` 的**结构原则、拆分流程、配置文件制定原则**。
> 目标：为后续诊断留出空间，避免二次重构。

---

## 1. 核心原则

1. **干净包名，零 bootstrap**：`import easyuuv_nc` 即触发 gym 注册，
   entry_point 用普通模块路径 `easyuuv_nc.env:EasyUUVEnv`。**禁止**再引入
   `_bootstrap_local_lab_tasks_package()` 一类把物理伪装成 `omni.isaac.lab_tasks.*`
   命名空间的 hack——env 本体对 lab_tasks 零依赖。
2. **先搬后删**：先把 flip360 主路径完整搬到新结构跑通（验收②ok），再删死分支。
   删之前必须有等价性证据（本轮 = 308 列 byte-level 等价）。
3. **死分支不复活**：D1–D6 见 `AGENT_HANDOFF.md` §3。新实验分支一律**默认关闭 +
   config/CLI 独立开关**，不得改变现有主线的 byte 行为。
4. **只改路径与包名，不改物理**：迁移契约时物理参数逐字不变。
5. **不改动主仓库其他文件**：`easyuuv_nc` 是自洽子树，迁移=拷贝+改 import，
   源文件保持只读。

---

## 2. 目录职责边界

| 目录 | 职责 | 禁止放入 |
| --- | --- | --- |
| `env/` | 环境本体（物理/观测/奖励/资产） | 任何 workflow/adaptation 逻辑 |
| `workflows/` | 训练与在线自适应入口脚本 + 配置 | 可复用算法组件（应下沉到下面各包） |
| `stdw_integration/` | FM、phase56、metrics、plots、signals | CLI 解析 |
| `esuot/` | E-SUOT（light/full）、半对偶、传输 | — |
| `custom_workflows/` | CLI args、workflow_config/paths | 物理逻辑 |
| `utils/` | 通用工具（replay buffer 等） | 任务专属逻辑 |
| `checkpoints/` | 纯权重 `.pt`（附 `SOURCE.txt` 溯源） | 训练日志 |
| `artifacts/` | FM bundle、inv_proxy 等离线产物 | — |
| `docs/` | 诊断结论 + 契约 + 指南 | — |

---

## 3. adapt.py 拆分实录（**已完成 20260721**）

`workflows/adapt.py`（原 ~7070 行）曾是本轮唯一未拆的巨石。本轮按**用户批准的
"提取 helpers + 物理删除 D5 死分支"**口径完成拆分：把 76–3239 行的 ~40 个 omni-free
独立 helper 逐字节迁至 `workflows/adaptation/` 包，并物理删除 D5（micro-probe /
auto-drift-router）死分支。**未拆解 `main()` 本体**（~3800 行运行时编排循环，用户
未选该选项）。拆分后 `adapt.py` 从 7070 → 5052 行（−2018），顶层仅剩 `def main()`。

**实际模块层（按"函数聚类 + omni 依赖边界"切分，以此为准）**：

```
workflows/adaptation/          # omni-free，可在 AppLauncher 之前 import
├── __init__.py         # re-export 全部 60 符号 + __all__ + 模块职责边界表
├── cli_parsers.py      # _bool_arg / _parse_axes / _parse_p_diag / _parse_zeta_grad_mask / …
├── policy.py           # policy forward(eval/train) / param_l2 / rng capture-restore / safe_corr
├── zeta.py             # 4-D zeta4 乘子 / 深度地板 / surrogate & runtime 写入
├── pose.py             # 四元数 / true & desired pose / 跟踪误差方向 / direction-gate
├── action_bridge.py    # action_bridge residual write / 部署侧 reduced-action-anchor
├── failsafe.py         # 解析式 s-surface / Task A fast-loop depth failsafe（hysteresis）
├── pseudo_action.py    # 低层修正读取 / 逆动力学对角 / pseudo-action 目标构造
├── phase56.py          # PHASE56 常量 + FM 桥接 runtime 监控 / 曲率诊断 / phase8 midpoint anchor
└── env_io.py           # drift router / 初始扰动 / reset / 快照 / checkpoint 保存 / phase4a 契约
```

拆分纪律（已执行）：
1. **两阶段**：Phase1 纯搬迁（byte-identical 提取器）→ 跑 200-step 验证 308 列全
   byte-level 等价；Phase2 物理删 D5（有意改 schema）→ 跑 200-step 验证"仅 6 个
   `micro_probe_*` 列被移除、其余 302 列 byte-level 等价"。**两阶段均 PASS**。
2. **借拆分删死分支**：本轮删除 **D5**（`MicroProbeController` + `_force_probe_offset` +
   auto-drift-router 分支 + argparse `--enable_micro_probe` 等 15 参数 + CSV 6 列）。
   **D2–D4/D6 暂留**为惰性死代码（位于 `action_bridge` 不可达/懒加载分支内），待后续
   拆解 `main()` 时一并删除（见 `AGENT_HANDOFF.md` §3）。
3. adapt.py 已退化为薄入口：仅 argparse/AppLauncher 编排 + `main()`，全部 helper 从
   `easyuuv_nc.workflows.adaptation` import。
4. **omni 依赖边界**：`pose.py` 的 `euler_xyz_from_quat`、`failsafe.py` 的 `convert_depth_to_v1`
   等 omni-gated 名走**函数体内 lazy import**（因这些 helper 在 AppLauncher 前被 import）；
   `from __future__ import annotations` 使 annotation-only 的 omni 类型无需运行时 import。

---

## 4. 配置文件制定原则

1. **task 配置放 `configs/tasks/`，训练配置放 `configs/train/`**，命名前缀 `v1_task_{a,b,c}_`。
2. **一个 config = 一个可复现的语义契约**：config 内只放"任务定义 + 安全边界 +
   评估口径"，不放实验开关（实验开关走 CLI）。
3. **新任务/新载体 = 新 config 文件**，不在旧 config 里塞 if-else 分支。
4. **深度语义固定**：安全核心 `[-0.5, -1.5]`，`[-0.5,-0.7]`/`[-1.3,-1.5]` 为线性惩罚
   过渡带——任何 config 不得偏离此常量（属系统边界，改动须问用户）。
5. **路径用子仓库相对路径**（`checkpoints/...`、`artifacts/...`），不写绝对路径、
   不引用主仓库旧路径。

---

## 5. checkpoint / artifact 迁移原则

1. **`cp -L`**（解软链，取实体权重），避免子仓库依赖主仓库软链失效。
2. 每个 checkpoint 目录附 `SOURCE.txt`：记录原 run 名、训练 config、关键指标，保可追溯。
3. checkpoint 是**纯权重**，不受包名重构影响（本轮已验证）。
4. artifact（FM bundle / inv_proxy）迁移后**目录名以子仓库实际为准**
   （`artifacts/fm_bundle/`、`artifacts/dynamics_proxy/`），文档路径同步更新，
   避免出现"计划初稿路径 vs 实际路径"偏差（本轮已踩，见 COMMAND_CONTRACT §3）。

---

## 6. 迁移完成自检清单

- [x] `import easyuuv_nc` 触发注册，`gym.make` + `step` OK（探针 `probe/probe_clean_package.py`）
- [x] 训练冒烟①：`train.py` 3 iter 写出 model_*.pt
- [x] flip360 复现②：`run_flip360_repro.sh 6000` accepted=95，308 列 byte-level 等价
- [x] 五类文档齐备（3 诊断文本 + LEDGER 流水账 + COMMAND_CONTRACT + AGENT_HANDOFF + 本指南）
- [x] adapt.py 拆分为 `adaptation/`（10 模块，7070→5052 行，200-step byte-level PASS）
- [x] D5 死代码物理删除（micro-probe / auto-drift-router；302 列 byte-level 等价 PASS）
- [ ] D2–D4/D6 死代码物理删除（惰性死代码，待拆解 `main()` 时一并删）

# COMMAND_CONTRACT — easyuuv_nc 重构后命令契约（20260721）

> 本文件是 `easyuuv_nc` 子仓库**重构后的权威命令契约**。所有命令均在
> **本子仓库根目录**（`.../easyuuv_stdw/easyuuv_nc/`）下执行。
> 契约来源：主仓库 `AGENTS.md` 的 "Current Validated CLI Contracts" 段，
> 迁移时仅改**路径与包名**，物理参数逐字不变（已由 flip360 6000-step
> 308 列 byte-level 等价验证，见 `docs/../../docs_new/00_REPO_REFACTOR_MIGRATION_PLAN_20260721.md` §7.4）。
>
> **⚠️ CSV schema 更新（20260721 拆分 adapt.py）**：物理删除 D5（micro-probe）后，
> `stdw_output.csv` 从 **308 列降为 302 列**（移除 6 个 `micro_probe_*` 列）。其余 302 列
> 与拆分前逐字节等价（200-step head-to-head PASS）。命令参数与物理行为**完全不变**，
> 仅诊断列数变化。

---

## 0. 通用执行前置（务必先做）

```bash
cd <...>/easyuuv_stdw/easyuuv_nc
export PYTHONPATH=$(pwd):$PYTHONPATH          # 让 `import easyuuv_nc` 触发 gym 注册
# 或（父目录法，run_flip360_repro.sh 用的就是这个）：
#   export PYTHONPATH="$(dirname $(pwd)):$PYTHONPATH"
```

### 两个已知坑（迁移时踩过，务必遵守）
1. **不要用 `run_with_isaac_env.sh` 直接 `exec python "$@"`**：它会误解析相对路径。
   正确姿势是显式 `conda run -n isaaclab python -u <脚本>`。
2. **必须加 `-u`（无缓冲）**：`conda run` 会缓冲 stdout，不加 `-u` 时
   实时 print 标记（FM midpoint active / inv_proxy loaded 等）无法被日志实时捕获。

---

## 1. 训练契约（验收①）— flip360 curriculum-B

```bash
conda run -n isaaclab python -u workflows/train.py \
  --task EasyUUV-Direct-Parametric-v1 --num_envs 64 --headless \
  --max_iterations 3 \
  --workflow_config workflows/configs/train/train_flip360_curric_b.yaml
```
- **冒烟通过标准**：3 learning iterations 无异常，写出 `model_0.pt`/`model_2.pt`，
  `compact_log.jsonl` 记录 vloss/ploss/noise_std。
- **正式训练**：把 `--max_iterations` 提到完整轮数（curriculum-B 分阶段梯度隔离：
  Stage1 冻结增益头 `[4:8]`，Stage2 冻结控制头 `[0:4]` + 主干）。
- `workflows/train.py` 已去 bootstrap、删 DCE runner cfg。

---

## 2. flip360 免训练复现契约（验收②，**主验收**）

**一键脚本**（推荐，路径全部内聚在子仓库）：
```bash
bash workflows/tools/run_flip360_repro.sh 6000    # 参数 = total_steps，默认 6000
bash workflows/tools/run_flip360_repro.sh 200     # 200 步冒烟
```

**等价展开**（若需手改参数）：
```bash
conda run -n isaaclab python -u workflows/adapt.py \
  --task EasyUUV-Direct-Parametric-Wide256-v1 \
  --experiment_name easyuuv_parametric --num_envs 1 \
  --workflow_config workflows/configs/tasks/v1_task_b_flip360_barrier.yaml \
  --total_steps 6000 --headless \
  --checkpoint checkpoints/wide256/model_249.pt \
  --stdw_update_target zeta4 \
  --l_tgt_space action_bridge \
  --state_match_z_source fm_midpoint \
  --phase56_runtime_bundle_dir artifacts/fm_bundle \
  --stdw_inv_proxy artifacts/dynamics_proxy/inv_proxy_12_v1_large.pt \
  --domain_adapt_backend esuot_light \
  --stdw_target_domain_mode mixed_all \
  --stdw_update_acceptance batch_trust \
  --stdw_direction_gate True \
  --stdw_direction_gate_source target_anchor \
  --stdw_depth_guard True \
  --stdw_zeta_depth_min_multiplier 0.9 \
  --lyapunov_dv_criterion practical_band \
  --lyapunov_depth_barrier_mode delete \
  --stdw_dir_guard both \
  --stdw_dir_guard_min_pass_rate 0.5
```

### 硬约束记忆点（迁移不变，违反即契约失效）
- `action_bridge` **绝不能脱离** `fm_midpoint + phase56 bundle + inv_proxy` 三件套；缺任一项视为契约失效而非可解释实验。
- Task B / flip360 若复跑 Lyapunov，应沿 `practical_band + depth_barrier_mode=delete + dir_guard=both`，**不得**把 Task A/C 的 `boundary` 深度合同机械套入 Flip360。

### 通过标准（20260721 实测基准，同日 head-to-head byte-level 等价）
| 指标 | 6000-step 参考值 |
| --- | --- |
| `stdw_update_accepted` 总数 | **95 / 6000** |
| `so3_attitude_error` mean | 0.5095 |
| `attitude_tracking_mse` mean | 1.643 |
| `depth_violation` mean | 0.4167 |
| `true_depth_v1` mean | -1.295 |
| `stdw_fm_bridge_curvature` mean | 0.0533（**非 NaN**，NaN 表示 action_bridge 分支未激活） |

> ⚠️ 若 `stdw_fm_bridge_curvature` 全为 NaN → action_bridge 路径被 legacy fallback
> 吞掉，属实现级 bug（见 AGENTS 20260719 锚点），**不是** FM/inv_proxy 无信号。

---

## 3. 路径速查（迁移后实际目录，勿沿用旧计划初稿路径）

| 资源 | easyuuv_nc 内路径 | 旧仓库对应（勿用） |
| --- | --- | --- |
| wide256 checkpoint | `checkpoints/wide256/model_249.pt` | logs/.../model_249.pt |
| flip360 checkpoint | `checkpoints/flip360/model_2846.pt` | — |
| FM bundle | `artifacts/fm_bundle/`（bundle.pt + 6 json） | `artifacts/phase56_fm_bundle_obs12_v1` |
| inv_proxy | `artifacts/dynamics_proxy/inv_proxy_12_v1_large.pt` | `artifacts/inv_proxy_12_v1_large.pt` |
| Task A cfg | `workflows/configs/tasks/v1_task_a_marathon_boundary_decoupled.yaml` | — |
| Task B cfg | `workflows/configs/tasks/v1_task_b_flip360_barrier.yaml` | — |
| Task C cfg | `workflows/configs/tasks/v1_task_c_cross_embodiment_safe_core_eval.yaml` | — |
| 训练 cfg | `workflows/configs/train/train_flip360_curric_b.yaml` | — |

---

## 4. 已注册 gym task（4 个 clean register，DCE 变体已剔除）

| task id | 说明 |
| --- | --- |
| `EasyUUV-Direct-v1` | 基础直接任务 |
| `EasyUUV-Direct-Parametric-v1` | 参数化（训练默认） |
| `EasyUUV-Direct-Parametric-SatObs-v1` | 饱和观测变体 |
| `EasyUUV-Direct-Parametric-Wide256-v1` | wide256 backbone（flip360 复现用） |

所有 entry_point 均为 `easyuuv_nc.env:EasyUUVEnv`（普通模块路径，无 bootstrap hack）。
`import easyuuv_nc` 即触发注册。

---

## 5. Task A / Task C 契约（后续实验用，本轮不实跑）

> 迁移已保留 config，但物理结论未变（见 `docs/00_CONSOLIDATION_LEDGER_20260720.md`）：
> Task A 有效主线是**正交 fast-loop depth failsafe**（非 zeta4 微调）；
> Task C 默认上游保持 `raw_abs`，`geo=0.02` 是"短程正向、长程未闭合"准正向分支。
> 完整 CLI 见主仓库 `AGENTS.md` "Task A/C 当前 pilot 合同"，迁移时同样只改路径。

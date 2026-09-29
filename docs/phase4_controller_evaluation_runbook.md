# Phase 4 Controller Evaluation Runbook

**目的:** 在重新接入 PPO 之前，先完成 controller-only 的 Isaac 对比实验。

Phase 4 只比较低层控制器：

```text
scripted trajectory/reference -> controller -> 8D PWM -> AUV
```

本阶段不接入：

- PPO/RL policy；
- LLM 调参；
- 在线 Kalman/RLS 更新；
- 新的推进器或水动力模型。

## 1. 评估矩阵

目标是同一套 scripted reference 下比较：

| Controller label | Mode | Manifest | Trajectories |
|---|---|---|---|
| `legacy` | `legacy` | none | `step`, `sine`, `irregular` |
| `direct_state_mpc` | `koopman_mpc` | Phase 2.5 selected manifest | `step`, `sine`, `irregular` |
| `paper_lifted_mpc` | `koopman_mpc` | Phase 3.5 paper manifest | `step`, `sine`, `irregular` |

默认每条命令使用：

```text
num_envs = 1
headless = true
trajectory_cycles = 2
steps_per_action = 100
mpc_horizon = 5
mpc_timeout_ms = 12
mpc_delta_pwm_limit = 0.35
```

如果服务器时间紧张，可以先把 `trajectory_cycles` 改成 `1`，或者加 `--max_goals 2` 做 smoke。正式 Phase 4 summary 应记录实际参数。

## 2. 服务器准备

在服务器上：

```bash
source /opt/conda/etc/profile.d/conda.sh
conda activate isaaclab
mkdir -p /root/EASYkoopman/source/results/koopman_phase4/data
cd /root/IsaacLab
```

确认代码在服务器上是当前分支内容。如果 GitHub/TLS 不稳定，优先用本地打包上传：

```powershell
git archive --format=tar -o "$env:TEMP\easykoopman_phase4.tar" HEAD
scp -F "$env:USERPROFILE\.ssh\config" "$env:TEMP\easykoopman_phase4.tar" agentic-AUV:/tmp/easykoopman_phase4.tar
```

服务器解包：

```bash
cd /root/EASYkoopman
tar -xf /tmp/easykoopman_phase4.tar
```

然后在服务器上做轻量检查：

```bash
cd /root/EASYkoopman
/opt/conda/envs/isaaclab/bin/python -m pytest -q tests/test_phase4_log_metrics.py tests/test_phase4_summary_workflow.py
/opt/conda/envs/isaaclab/bin/python -m compileall __init__.py easyuuv_env.py koopman workflows tests
```

## 3. Manifest 路径

在 `/root/IsaacLab` 里设置：

```bash
DIRECT_MANIFEST=/root/EASYkoopman/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json
PAPER_MANIFEST=/root/EASYkoopman/source/results/koopman_phase3_5/paper_lifted_manifest.json
```

检查文件存在：

```bash
test -f "$DIRECT_MANIFEST" && echo "direct manifest OK"
test -f "$PAPER_MANIFEST" && echo "paper manifest OK"
```

如果 `PAPER_MANIFEST` 不存在或 gate 不通过，本轮仍然跑 `legacy` 和 `direct_state_mpc`，并在 summary 中把 paper-lifted 标记为 skipped。

## 4. Legacy Runs

```bash
cd /root/IsaacLab
for TRAJ in step sine irregular; do
  WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_controller.py \
    --task EasyUUV-Direct-v1 \
    --num_envs 1 \
    --headless \
    --controller_mode legacy \
    --trajectory_type "$TRAJ" \
    --trajectory_cycles 2 \
    --steps_per_action 100 \
    --koopman_log_path "/root/EASYkoopman/source/results/koopman_phase4/data/legacy_${TRAJ}_run01.jsonl"
done
```

## 5. Direct-State Koopman+MPC Runs

```bash
cd /root/IsaacLab
for TRAJ in step sine irregular; do
  WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_controller.py \
    --task EasyUUV-Direct-v1 \
    --num_envs 1 \
    --headless \
    --controller_mode koopman_mpc \
    --koopman_manifest_path "$DIRECT_MANIFEST" \
    --mpc_horizon 5 \
    --mpc_timeout_ms 12 \
    --mpc_delta_pwm_limit 0.35 \
    --trajectory_type "$TRAJ" \
    --trajectory_cycles 2 \
    --steps_per_action 100 \
    --koopman_log_path "/root/EASYkoopman/source/results/koopman_phase4/data/direct_state_mpc_${TRAJ}_run01.jsonl"
done
```

## 6. Paper-Lifted Koopman+MPC Runs

只有当 `PAPER_MANIFEST` 存在且可以加载时执行：

```bash
cd /root/IsaacLab
for TRAJ in step sine irregular; do
  WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_controller.py \
    --task EasyUUV-Direct-v1 \
    --num_envs 1 \
    --headless \
    --controller_mode koopman_mpc \
    --koopman_manifest_path "$PAPER_MANIFEST" \
    --mpc_horizon 5 \
    --mpc_timeout_ms 12 \
    --mpc_delta_pwm_limit 0.35 \
    --trajectory_type "$TRAJ" \
    --trajectory_cycles 2 \
    --steps_per_action 100 \
    --koopman_log_path "/root/EASYkoopman/source/results/koopman_phase4/data/paper_lifted_mpc_${TRAJ}_run01.jsonl"
done
```

## 7. 验证日志

所有生成的 JSONL 都需要验证：

```bash
cd /root/EASYkoopman
for f in source/results/koopman_phase4/data/*.jsonl; do
  python workflows/validate_koopman_log.py "$f" || exit 1
done
```

预期每个文件输出类似：

```text
OK: N samples
state_dim=11 reference_dim=5 action_dim=4 pwm_dim=8
trajectory_types=step
controller_modes=koopman_mpc/Ssurface
```

## 8. 服务器上生成 metrics summary

服务器可以直接生成一次 summary：

```bash
cd /root/EASYkoopman
mkdir -p source/results/koopman_phase4/reports
python workflows/summarize_phase4_evaluation.py \
  --glob "source/results/koopman_phase4/data/*.jsonl" \
  --output-json source/results/koopman_phase4/reports/metrics_summary.json \
  --output-md source/results/koopman_phase4/reports/metrics_summary.md
```

## 9. 拉回本地

本地 PowerShell：

```powershell
New-Item -ItemType Directory -Force "E:\code for project\Agentic AUV\EasyUUV\source\results\koopman_phase4\data"
New-Item -ItemType Directory -Force "E:\code for project\Agentic AUV\EasyUUV\source\results\koopman_phase4\reports"

scp -F "$env:USERPROFILE\.ssh\config" agentic-AUV:/root/EASYkoopman/source/results/koopman_phase4/data/*.jsonl `
  "E:\code for project\Agentic AUV\EasyUUV\source\results\koopman_phase4\data"

scp -F "$env:USERPROFILE\.ssh\config" agentic-AUV:/root/EASYkoopman/source/results/koopman_phase4/reports/* `
  "E:\code for project\Agentic AUV\EasyUUV\source\results\koopman_phase4\reports"
```

注意：Windows `scp` 目标路径包含空格时，目标目录不要写尾部反斜杠，否则 OpenSSH 可能把结尾引号解析进路径。

本地也可以重新生成 summary：

```powershell
cd "E:\code for project\Agentic AUV\EasyUUV"
python workflows\summarize_phase4_evaluation.py `
  --glob "source/results/koopman_phase4/data/*.jsonl" `
  --output-json source/results/koopman_phase4/reports/metrics_summary.json `
  --output-md source/results/koopman_phase4/reports/metrics_summary.md
```

## 10. Phase 4 Summary 要写清楚的内容

完成服务器实验后，Phase 4 summary 至少包含：

- 实际跑了哪些 controller/trajectory；
- 哪些 JSONL 通过验证；
- 每个 controller 的 tracking、control effort、smoothness、fallback、latency；
- paper-lifted 是否进入三方比较；
- direct-state 是否仍然是更稳的工程 baseline；
- 哪些结果只能说明 Isaac 仿真表现，不能说明真实硬件表现；
- Phase 4.5 PPO 接入应该拿哪组 controller-only log 作为 baseline。

## 11. 2026-07-02 已完成的一次基线结果

本项目已经在 `agentic-AUV` 服务器完成一轮 Phase 4 基线评估：

```text
legacy, direct_state Koopman+MPC, paper_lifted Koopman+MPC
step, sine, irregular
9/9 logs validated
1400 samples per log
all PWM bounded
```

结果摘要位于：

```text
.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-SUMMARY.md
.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-VERIFICATION.md
.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-PHASE45-HANDOFF.md
source/results/koopman_phase4/reports/metrics_summary.md
```

当前结论是：`legacy/Ssurface` 仍是最稳的 controller-only baseline；`direct_state` Koopman+MPC 已闭环可用但 fallback/latency 需要优化；`paper_lifted_edmd` 已进入论文风格对比，但暂不适合作为 Phase 4.5 PPO 的默认底层控制器。

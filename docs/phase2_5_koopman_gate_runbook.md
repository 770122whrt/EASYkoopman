# Phase 2.5 Koopman 模型准入 Gate 运行手册

本文档用于你把本地代码打包到服务器后，完成 Koopman 模型的离线准入验证。Phase 2.5 不启动 MPC，也不改 Isaac 闭环控制；它只回答一个问题：

```text
当前 Koopman 模型是否足够稳定、可泛化、可复现，能够作为 Phase 3 MPC 的预测模型？
```

如果 gate report 的结果是 `fail`，这不是程序错误，而是说明当前数据或模型还不适合进入 MPC。

## 0. 推荐目录

以下命令默认代码目录是：

```bash
export EASYKOOPMAN_DIR=/root/EASYkoopman
export ISAACLAB_PATH=/root/IsaacLab
```

如果你的路径不同，先改成自己的真实路径。

Phase 2.5 的推荐输出目录：

```bash
export PHASE25_DIR="$EASYKOOPMAN_DIR/source/results/koopman_phase2_5"
mkdir -p "$PHASE25_DIR"
```

## 1. 先收集三类日志

最终 gate 至少需要 train、validation、test 三组日志。推荐先准备：

```text
source/results/koopman_phase1/koopman_step_long.jsonl
source/results/koopman_phase1/koopman_sine_long.jsonl
source/results/koopman_phase1/koopman_irregular_long.jsonl
```

### 1.1 step 日志，已知 direct-controller 路径

```bash
cd "$ISAACLAB_PATH"
export WANDB_MODE=disabled

./isaaclab.sh -p "$EASYKOOPMAN_DIR/workflows/play_controller.py" \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --steps_per_action 200 \
  --koopman_log_path "$EASYKOOPMAN_DIR/source/results/koopman_phase1/koopman_step_long.jsonl"
```

如果只想先 smoke test：

```bash
./isaaclab.sh -p "$EASYKOOPMAN_DIR/workflows/play_controller.py" \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --steps_per_action 2 \
  --max_goals 1 \
  --koopman_log_path "$EASYKOOPMAN_DIR/source/results/koopman_phase1/smoke_step.jsonl"
```

### 1.2 sine / irregular 日志

当前 `play_eval.py` 和 `play_eval_task2.py` 是 legacy eval workflow，通常需要 PPO policy checkpoint。如果你已有 checkpoint：

```bash
export POLICY_PATH=/absolute/path/to/model_800.pt
```

sine：

```bash
cd "$ISAACLAB_PATH"
export WANDB_MODE=disabled

./isaaclab.sh -p "$EASYKOOPMAN_DIR/workflows/play_eval.py" \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --custom_weights "$POLICY_PATH" \
  --koopman_log_path "$EASYKOOPMAN_DIR/source/results/koopman_phase1/koopman_sine_long.jsonl"
```

irregular：

```bash
cd "$ISAACLAB_PATH"
export WANDB_MODE=disabled

./isaaclab.sh -p "$EASYKOOPMAN_DIR/workflows/play_eval_task2.py" \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --custom_weights "$POLICY_PATH" \
  --koopman_log_path "$EASYKOOPMAN_DIR/source/results/koopman_phase1/koopman_irregular_long.jsonl"
```

如果 sine / irregular workflow 在 Isaac Lab 2.2.1 上报错，先不要硬改模型 gate。把完整报错发回来；Phase 2.5 的离线代码已经准备好，缺的是对应轨迹日志。

## 2. 验证每个 JSONL

```bash
cd "$EASYKOOPMAN_DIR"

python workflows/validate_koopman_log.py source/results/koopman_phase1/koopman_step_long.jsonl
python workflows/validate_koopman_log.py source/results/koopman_phase1/koopman_sine_long.jsonl
python workflows/validate_koopman_log.py source/results/koopman_phase1/koopman_irregular_long.jsonl
```

每个命令都应该输出类似：

```text
OK: 1400 samples
state_dim=11 reference_dim=5 action_dim=4 pwm_dim=8
trajectory_types=step
```

## 3. 创建 log-level split manifest

最小版本是一份 train、一份 validation、一份 test：

```bash
cd "$EASYKOOPMAN_DIR"
mkdir -p "$PHASE25_DIR"

python workflows/split_koopman_logs.py \
  --train-log source/results/koopman_phase1/koopman_step_long.jsonl \
  --validation-log source/results/koopman_phase1/koopman_sine_long.jsonl \
  --test-log source/results/koopman_phase1/koopman_irregular_long.jsonl \
  --output "$PHASE25_DIR/split_manifest.json" \
  --seed 7 \
  --notes "phase2.5 first gate: step train, sine validation, irregular test"
```

注意：这里是 log-level split，不允许把同一个连续日志按行随机拆分。连续轨迹的相邻行高度相关，row-level random split 会让验证误差虚假变好。

如果你有多次运行，可以这样追加多个 train log：

```bash
python workflows/split_koopman_logs.py \
  --train-log source/results/koopman_phase1/koopman_step_long_run1.jsonl \
  --train-log source/results/koopman_phase1/koopman_step_long_run2.jsonl \
  --validation-log source/results/koopman_phase1/koopman_sine_long.jsonl \
  --test-log source/results/koopman_phase1/koopman_irregular_long.jsonl \
  --output "$PHASE25_DIR/split_manifest.json" \
  --seed 7 \
  --notes "multi-run train split"
```

## 4. 跑候选模型 sweep

```bash
cd "$EASYKOOPMAN_DIR"

python workflows/sweep_koopman_models.py \
  --split-manifest "$PHASE25_DIR/split_manifest.json" \
  --output-dir "$PHASE25_DIR/sweep"
```

默认会比较：

- direct-state Koopman candidate
- paper-style lifted EDMD candidate
- ridge: `1e-8, 1e-6, 1e-4, 1e-2`
- lifting: `linear, selected_quadratic`
- normalization: `off, standard`
- baselines: `persistence, simple_linear`

输出核心文件：

```text
$PHASE25_DIR/sweep/sweep_results.json
$PHASE25_DIR/sweep/models/*.json
$PHASE25_DIR/sweep/metrics/*.json
$PHASE25_DIR/sweep/normalizers/*.json
```

## 5. 选择模型并生成 selected manifest

```bash
cd "$EASYKOOPMAN_DIR"

python workflows/select_koopman_model.py \
  --sweep-results "$PHASE25_DIR/sweep/sweep_results.json" \
  --output "$PHASE25_DIR/selected_model_manifest.json"
```

这个步骤会检查：

- 最优 candidate 是否在 validation multi-step rollout 中发散。
- candidate 是否优于 persistence baseline。
- candidate 是否优于 simple linear baseline。
- candidate 是否能在 held-out test logs 上保持稳定。

如果不满足，`selected_model_manifest.json` 仍然会生成，但 `gate_status` 会是 `fail`。

## 6. 写 gate report

```bash
cd "$EASYKOOPMAN_DIR"

python workflows/write_koopman_gate_report.py \
  --manifest "$PHASE25_DIR/selected_model_manifest.json" \
  --sweep-results "$PHASE25_DIR/sweep/sweep_results.json" \
  --output "$PHASE25_DIR/gate_report.md"
```

查看结果：

```bash
cat "$PHASE25_DIR/gate_report.md"
```

只有当报告写明：

```text
Gate Status: pass
```

我们才进入 Phase 3，把 `selected_model_manifest.json` 作为 MPC 预测模型输入。

## 7. 你需要回传给我的内容

服务器跑完后，把这些结果发我：

```bash
cd "$EASYKOOPMAN_DIR"

git log -1 --oneline
ls -lh "$PHASE25_DIR"
cat "$PHASE25_DIR/selected_model_manifest.json"
cat "$PHASE25_DIR/gate_report.md"
```

如果失败，也请发：

```bash
cat "$PHASE25_DIR/sweep/sweep_results.json"
```

失败信息本身很有价值，它会告诉我们是数据不够、baseline 太强、模型发散，还是某类轨迹分布和训练集差别太大。

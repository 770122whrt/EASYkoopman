# EasyUUV Phase 1 Isaac 服务器运行手册

本文档用于在服务器上的 Isaac Sim / Isaac Lab 环境中运行 EASYkoopman 的 Phase 1 验证与数据采集。目标是生成第一批 Koopman 训练日志，验证本地已经完成的 controller boundary、PWM 缓存和 JSONL 数据 schema 能在真实 Isaac rollout 中工作。

本文默认你已经有一台能运行 Isaac Sim / Isaac Lab 的 Linux 服务器。Isaac 本体安装不在本文范围内，但本文会覆盖 Isaac 之外需要准备的系统工具、Python 依赖、Git 拉取、任务部署、运行命令、结果验证和日志拷回本地。

## 0. 你最终要得到什么

Phase 1 的必需产物是一个 JSONL 日志文件：

```text
<EasyUUV任务目录>/source/results/koopman_phase1/koopman_step.jsonl
```

每一行应该包含：

```text
t
state
reference
action_4d
pwm_8d
next_state
trajectory_type
controller_mode
```

其中最关键的是 `pwm_8d`，它是进入推进器死区和推力多项式之前的 8D PWM。Phase 2 的 EDMD / Koopman 训练会用它作为控制输入 `u_k`。

## 1. 路径约定

后续命令统一使用这几个变量。请先按你的服务器实际路径修改：

```bash
export ISAACLAB_PATH=/path/to/IsaacLab
export EASYUUV_TASK_NAME=EasyUUV-Isaac-Simulation
export EASYUUV_TASK_DIR="$ISAACLAB_PATH/source/extensions/omni.isaac.lab_tasks/omni/isaac/lab_tasks/direct/$EASYUUV_TASK_NAME"
export EASYKOOPMAN_REMOTE=https://github.com/770122whrt/EASYkoopman.git
```

注意：当前代码里的 Gym 注册入口仍使用原 EasyUUV 任务名，因此推荐服务器上的任务目录名保持为：

```text
EasyUUV-Isaac-Simulation
```

也就是说，虽然 GitHub 仓库叫 `EASYkoopman`，服务器上的目录名最好仍然 clone 成 `EasyUUV-Isaac-Simulation`。

## 2. 一次性安装 Isaac 之外的系统工具

Ubuntu 服务器建议先装这些工具：

```bash
sudo apt update
sudo apt install -y git git-lfs curl wget unzip tmux rsync tree python3 python3-pip
git lfs install
```

用途：

- `git` / `git-lfs`：拉取代码和可能的大文件。
- `tmux`：长时间运行 Isaac 命令时防止 SSH 断开影响进程。
- `rsync` / `scp`：把服务器日志拷回本地。
- `tree`：检查输出目录结构。
- `python3`：离线验证 JSONL schema，不依赖 Isaac。

## 3. 确认 Isaac Lab 基础环境

进入 Isaac Lab 根目录：

```bash
cd "$ISAACLAB_PATH"
```

确认 Isaac Lab wrapper 可用：

```bash
./isaaclab.sh -p -c "print('Isaac Lab Python OK')"
```

确认 GPU 可见：

```bash
nvidia-smi
```

如果这些命令失败，先修 Isaac / NVIDIA / CUDA / driver 环境，暂时不要继续 EasyUUV。

## 4. 安装 Python 依赖

EasyUUV workflow 里会用到 `pandas`、`wandb`、`pytest`、`tensorboard`。推荐安装到 Isaac Lab 的 Python 环境中：

```bash
cd "$ISAACLAB_PATH"
./isaaclab.sh -p -m pip install --upgrade pip
./isaaclab.sh -p -m pip install pandas wandb pytest tensorboard
```

通常不要手动安装 `torch`、`gymnasium`、`omni.*`，这些应该由 Isaac Sim / Isaac Lab 管理。

如果后面遇到：

```text
ModuleNotFoundError: No module named 'rsl_rl'
```

说明 Isaac Lab 的 RSL-RL 相关依赖没有装好。优先回到 Isaac Lab 的安装流程，运行它自己的安装命令。常见形式是：

```bash
cd "$ISAACLAB_PATH"
./isaaclab.sh --install
```

如果你的 Isaac Lab 版本使用不同安装命令，以服务器上 Isaac Lab 仓库的 README 为准。

## 5. 配置 wandb

当前 workflow 会 import 并调用 `wandb`。如果你不想登录 wandb，建议直接使用离线模式：

```bash
export WANDB_MODE=offline
```

如果你要在线记录：

```bash
wandb login
```

Phase 1 建议先用离线模式，减少变量。

## 6. 拉取 EASYkoopman 代码

### 6.1 如果服务器还没有 EasyUUV 任务目录

```bash
mkdir -p "$(dirname "$EASYUUV_TASK_DIR")"
cd "$(dirname "$EASYUUV_TASK_DIR")"
git clone "$EASYKOOPMAN_REMOTE" "$EASYUUV_TASK_NAME"
cd "$EASYUUV_TASK_DIR"
git checkout main
git pull --ff-only origin main
git log -1 --oneline
```

期望最后能看到类似：

```text
a096c71 feat(01-01): add Koopman data logging seam
```

commit 不一定永远是这个，但至少应该包含 Phase 1 的 Koopman data logging seam。

### 6.2 如果服务器已经有旧的 EasyUUV 任务目录

先进入目录并确认 remote：

```bash
cd "$EASYUUV_TASK_DIR"
git remote -v
```

如果 remote 不是 `770122whrt/EASYkoopman`，改成新的：

```bash
git remote set-url origin "$EASYKOOPMAN_REMOTE"
```

更新代码：

```bash
git fetch origin main
git checkout main
git pull --ff-only origin main
git log -1 --oneline
```

如果本地有未提交改动导致 pull 失败，先不要强行 reset。把报错和 `git status --short` 发回来，我再判断是否需要保留或清理。

## 7. 检查任务注册

当前 `__init__.py` 注册的任务名是：

```text
EasyUUV-Direct-v1
```

在 Isaac Lab 根目录运行一次短检查：

```bash
cd "$ISAACLAB_PATH"
export WANDB_MODE=offline
./isaaclab.sh -p "$EASYUUV_TASK_DIR/workflows/play_controller.py" \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --koopman_log_path "$EASYUUV_TASK_DIR/source/results/koopman_phase1/smoke_koopman_step.jsonl"
```

如果这个命令能跑完，并生成 `smoke_koopman_step.jsonl`，说明任务注册、direct controller 和 Koopman 日志入口都打通了。

如果报 `Task EasyUUV-Direct-v1 not found` 或 import 失败，优先检查：

```bash
echo "$EASYUUV_TASK_DIR"
ls "$EASYUUV_TASK_DIR"
grep -n "EasyUUV-Direct-v1" "$EASYUUV_TASK_DIR/__init__.py"
```

并确认目录位于：

```text
$ISAACLAB_PATH/source/extensions/omni.isaac.lab_tasks/omni/isaac/lab_tasks/direct/
```

## 8. Phase 1 必跑：direct controller 数据采集

这是当前最重要的一步。它不依赖 PPO checkpoint。

```bash
cd "$ISAACLAB_PATH"
export WANDB_MODE=offline
mkdir -p "$EASYUUV_TASK_DIR/source/results/koopman_phase1"

./isaaclab.sh -p "$EASYUUV_TASK_DIR/workflows/play_controller.py" \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --koopman_log_path "$EASYUUV_TASK_DIR/source/results/koopman_phase1/koopman_step.jsonl"
```

预期输出：

```text
[INFO]: Saving Koopman data into: .../source/results/koopman_phase1/koopman_step.jsonl
```

运行完成后检查文件：

```bash
ls -lh "$EASYUUV_TASK_DIR/source/results/koopman_phase1/koopman_step.jsonl"
head -n 1 "$EASYUUV_TASK_DIR/source/results/koopman_phase1/koopman_step.jsonl"
```

## 9. 验证 JSONL 是否可用于 Koopman 训练

这个验证不需要 Isaac，只需要普通 Python：

```bash
cd "$EASYUUV_TASK_DIR"
python3 - <<'PY'
from koopman_data import load_koopman_samples, reconstruct_training_tuples

path = "source/results/koopman_phase1/koopman_step.jsonl"
samples = load_koopman_samples(path)
tuples = reconstruct_training_tuples(samples)

print("samples:", len(samples))
print("first keys:", sorted(samples[0].keys()))
print("state length:", len(samples[0]["state"]))
print("reference length:", len(samples[0]["reference"]))
print("action_4d length:", len(samples[0]["action_4d"]))
print("pwm_8d length:", len(samples[0]["pwm_8d"]))
print("next_state length:", len(samples[0]["next_state"]))
print("first tuple lengths:", [len(x) for x in tuples[0]])

assert len(samples) > 0
assert len(samples[0]["action_4d"]) == 4
assert len(samples[0]["pwm_8d"]) == 8
assert len(samples[0]["state"]) == len(samples[0]["next_state"])
print("OK: Koopman JSONL schema is valid.")
PY
```

看到 `OK: Koopman JSONL schema is valid.` 就说明 Phase 1 的核心 Isaac Gate 通过。

## 10. 可选：运行 Isaac 环境最小训练 smoke test

这一步不是生成 Koopman 数据的必要条件，但可以验证 legacy 训练入口仍然没坏：

```bash
cd "$ISAACLAB_PATH"
./isaaclab.sh -p source/standalone/workflows/rsl_rl/train.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 4 \
  --headless \
  --max_iterations 1
```

如果显存很小，继续降低：

```bash
--num_envs 1
```

## 11. 可选：采集 sine / step / irregular 三类轨迹

这三条 workflow 目前仍然依赖 PPO policy checkpoint。如果你已经有可用 checkpoint，可以运行它们来生成更丰富的数据。

先设置一个 checkpoint。二选一：

```bash
export POLICY_PATH=/absolute/path/to/model_800.pt
```

或者使用 Isaac Lab / RSL-RL 默认的 `--load_run` 和 `--checkpoint`：

```bash
export LOAD_RUN=<run_folder_name>
export CHECKPOINT=model_800.pt
```

### 11.1 step 轨迹

使用自定义 checkpoint：

```bash
cd "$ISAACLAB_PATH"
export WANDB_MODE=offline

./isaaclab.sh -p "$EASYUUV_TASK_DIR/workflows/play_eval_step.py" \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --custom_weights "$POLICY_PATH" \
  --koopman_log_path "$EASYUUV_TASK_DIR/source/results/koopman_phase1/koopman_eval_step.jsonl"
```

或使用默认 RSL-RL checkpoint 参数：

```bash
./isaaclab.sh -p "$EASYUUV_TASK_DIR/workflows/play_eval_step.py" \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --load_run "$LOAD_RUN" \
  --checkpoint "$CHECKPOINT" \
  --koopman_log_path "$EASYUUV_TASK_DIR/source/results/koopman_phase1/koopman_eval_step.jsonl"
```

### 11.2 sine 轨迹

```bash
cd "$ISAACLAB_PATH"
export WANDB_MODE=offline

./isaaclab.sh -p "$EASYUUV_TASK_DIR/workflows/play_eval.py" \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --custom_weights "$POLICY_PATH" \
  --koopman_log_path "$EASYUUV_TASK_DIR/source/results/koopman_phase1/koopman_eval_sine.jsonl"
```

### 11.3 irregular 轨迹

```bash
cd "$ISAACLAB_PATH"
export WANDB_MODE=offline

./isaaclab.sh -p "$EASYUUV_TASK_DIR/workflows/play_eval_task2.py" \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --custom_weights "$POLICY_PATH" \
  --koopman_log_path "$EASYUUV_TASK_DIR/source/results/koopman_phase1/koopman_eval_irregular.jsonl"
```

检查所有日志：

```bash
ls -lh "$EASYUUV_TASK_DIR/source/results/koopman_phase1/"*.jsonl
```

## 12. 把服务器日志拷回本地

在本地 Windows PowerShell 中运行：

```powershell
scp -r user@server:/absolute/path/to/IsaacLab/source/extensions/omni.isaac.lab_tasks/omni/isaac/lab_tasks/direct/EasyUUV-Isaac-Simulation/source/results/koopman_phase1 "E:\code for project\Agentic AUV\EasyUUV\server_results\phase1"
```

把 `user@server` 和服务器路径换成真实值。

建议不要把大日志提交进 Git。日志用于 Phase 2 训练，可以保存在：

```text
E:\code for project\Agentic AUV\EasyUUV\server_results\phase1
```

如果你希望我后续直接读取这些日志，拷回来后告诉我实际路径。

## 13. 推荐完整执行顺序

第一次在服务器上跑，按这个顺序：

```bash
# 1. 设置路径
export ISAACLAB_PATH=/path/to/IsaacLab
export EASYUUV_TASK_NAME=EasyUUV-Isaac-Simulation
export EASYUUV_TASK_DIR="$ISAACLAB_PATH/source/extensions/omni.isaac.lab_tasks/omni/isaac/lab_tasks/direct/$EASYUUV_TASK_NAME"
export EASYKOOPMAN_REMOTE=https://github.com/770122whrt/EASYkoopman.git
export WANDB_MODE=offline

# 2. 安装基础依赖
sudo apt update
sudo apt install -y git git-lfs curl wget unzip tmux rsync tree python3 python3-pip
git lfs install

# 3. 安装 Python 依赖到 Isaac Lab Python
cd "$ISAACLAB_PATH"
./isaaclab.sh -p -m pip install pandas wandb pytest tensorboard

# 4. 拉代码
mkdir -p "$(dirname "$EASYUUV_TASK_DIR")"
cd "$(dirname "$EASYUUV_TASK_DIR")"
git clone "$EASYKOOPMAN_REMOTE" "$EASYUUV_TASK_NAME" || true
cd "$EASYUUV_TASK_DIR"
git remote set-url origin "$EASYKOOPMAN_REMOTE"
git fetch origin main
git checkout main
git pull --ff-only origin main
git log -1 --oneline

# 5. 跑 Phase 1 direct-controller 数据采集
cd "$ISAACLAB_PATH"
mkdir -p "$EASYUUV_TASK_DIR/source/results/koopman_phase1"
./isaaclab.sh -p "$EASYUUV_TASK_DIR/workflows/play_controller.py" \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --koopman_log_path "$EASYUUV_TASK_DIR/source/results/koopman_phase1/koopman_step.jsonl"

# 6. 验证 JSONL
cd "$EASYUUV_TASK_DIR"
python3 - <<'PY'
from koopman_data import load_koopman_samples
path = "source/results/koopman_phase1/koopman_step.jsonl"
samples = load_koopman_samples(path)
print("samples:", len(samples))
print("pwm_8d length:", len(samples[0]["pwm_8d"]))
assert len(samples) > 0
assert len(samples[0]["pwm_8d"]) == 8
print("OK")
PY
```

## 14. 常见问题

### `No module named wandb`

```bash
cd "$ISAACLAB_PATH"
./isaaclab.sh -p -m pip install wandb
export WANDB_MODE=offline
```

### `No module named pandas`

```bash
cd "$ISAACLAB_PATH"
./isaaclab.sh -p -m pip install pandas
```

### `No module named rsl_rl`

先跑 Isaac Lab 自己的安装流程：

```bash
cd "$ISAACLAB_PATH"
./isaaclab.sh --install
```

如果仍失败，把完整报错发回来。

### `Task EasyUUV-Direct-v1 not found`

检查任务目录：

```bash
echo "$EASYUUV_TASK_DIR"
ls "$EASYUUV_TASK_DIR"
grep -n "EasyUUV-Direct-v1" "$EASYUUV_TASK_DIR/__init__.py"
```

任务目录必须在 Isaac Lab 的 direct tasks 目录下：

```text
$ISAACLAB_PATH/source/extensions/omni.isaac.lab_tasks/omni/isaac/lab_tasks/direct/EasyUUV-Isaac-Simulation
```

### 显存不足或运行很慢

优先使用：

```bash
--num_envs 1 --headless
```

不要一开始就跑 1024 或 2048 env。

### wandb 要求登录

先用离线模式：

```bash
export WANDB_MODE=offline
```

### 生成了 CSV 但没有 JSONL

确认你传了：

```bash
--koopman_log_path "$EASYUUV_TASK_DIR/source/results/koopman_phase1/koopman_step.jsonl"
```

并检查运行输出中是否出现：

```text
[INFO]: Saving Koopman data into:
```

## 15. 给我回传什么信息

你在服务器跑完后，把下面这些信息发给我：

```bash
cd "$EASYUUV_TASK_DIR"
git log -1 --oneline
ls -lh source/results/koopman_phase1/
python3 - <<'PY'
from koopman_data import load_koopman_samples
p = "source/results/koopman_phase1/koopman_step.jsonl"
s = load_koopman_samples(p)
print("samples:", len(s))
print("first sample:", s[0])
PY
```

如果运行失败，发：

```bash
cd "$EASYUUV_TASK_DIR"
git status --short
git log -1 --oneline
```

以及 Isaac 命令的完整报错。这样我就能继续判断是环境问题、任务注册问题、依赖问题，还是代码路径问题。

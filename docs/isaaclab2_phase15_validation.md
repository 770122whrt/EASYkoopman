# Isaac Lab 2 Phase 1.5 服务器验证流程

本文档用于验证 `isaaclab2-migration` 分支是否能在服务器 Isaac Sim 5.0 + Isaac Lab 2.2.1 环境中跑通 EasyUUV direct controller，并生成 Koopman Phase 1 JSONL 数据。

## 目标

本阶段只验证：

- Isaac Lab 2.x namespace 兼容层可用。
- `EasyUUV-Direct-v1` 可以从普通 Git clone 目录注册。
- `workflows/play_controller.py` 不依赖 PPO/RSL-RL wrapper。
- legacy controller 能跑一段 rollout。
- Koopman JSONL 能写出至少一条记录。

本阶段不验证：

- PPO 训练。
- Koopman EDMD 训练。
- Koopman+MPC 闭环控制。

## 1. 拉取分支

如果服务器上还没有仓库：

```bash
cd /root
git clone -b isaaclab2-migration https://github.com/770122whrt/EASYkoopman.git EASYkoopman
```

如果服务器上已经有 `/root/EASYkoopman`：

```bash
cd /root/EASYkoopman
git fetch origin
git checkout isaaclab2-migration
git pull --ff-only origin isaaclab2-migration
```

确认分支和最新提交：

```bash
cd /root/EASYkoopman
git branch --show-current
git log --oneline -3
```

应该看到当前分支为：

```text
isaaclab2-migration
```

## 2. 确认 Isaac Lab 启动方式

不要用裸 `python` 直接 import Isaac Lab。必须从 `/root/IsaacLab` 使用 `isaaclab.sh` 启动。

可先跑一次 app startup 测试：

```bash
cd /root/IsaacLab
./isaaclab.sh -p -c '
import argparse
from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args(["--headless"])

app_launcher = AppLauncher(args)
simulation_app = app_launcher.app

import omni.log
import isaaclab
import isaaclab_tasks
import isaaclab_rl

print("Isaac Sim + Isaac Lab app startup OK")

simulation_app.close()
'
```

如果输出里有 `Warp CUDA error`，但最后出现：

```text
Isaac Sim + Isaac Lab app startup OK
```

则本阶段可以继续。这类 warning 之前已经出现过，不等同于环境不可用。

## 3. 运行 EasyUUV direct controller

先创建日志目录：

```bash
mkdir -p /root/EASYkoopman/source/results/koopman_phase1
```

运行 headless rollout：

```bash
cd /root/IsaacLab
WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_controller.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --koopman_log_path /root/EASYkoopman/source/results/koopman_phase1/koopman_step.jsonl
```

说明：

- `WANDB_MODE=disabled` 是为了避免服务器没有 wandb 登录时卡住。
- 第一次启动 Isaac 可能较慢，先等它完成 app startup。
- 当前 workflow 会跑 step trajectory，完成后会保存 CSV 和 JSONL。

## 4. 检查 JSONL

运行结束后检查：

```bash
ls -lh /root/EASYkoopman/source/results/koopman_phase1/koopman_step.jsonl
wc -l /root/EASYkoopman/source/results/koopman_phase1/koopman_step.jsonl
head -n 1 /root/EASYkoopman/source/results/koopman_phase1/koopman_step.jsonl
```

通过标准：

- 文件存在。
- 行数大于 0。
- 每行是 JSON，包含 `state`、`reference`、`action_4d`、`pwm_8d`、`next_state`、`trajectory_type`、`controller_mode`。

快速检查 key：

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("/root/EASYkoopman/source/results/koopman_phase1/koopman_step.jsonl")
first = json.loads(path.read_text().splitlines()[0])
print(sorted(first.keys()))
print("controller_mode =", first["controller_mode"])
print("trajectory_type =", first["trajectory_type"])
print("state_dim =", len(first["state"]))
print("pwm_dim =", len(first["pwm_8d"]))
PY
```

期望：

```text
controller_mode = legacy/Ssurface
trajectory_type = step
pwm_dim = 8
```

## 5. 常见错误判断

### `ModuleNotFoundError: No module named 'omni.log'`

通常说明没有先启动 Isaac app，或者用了裸 Python。请确认命令是：

```bash
cd /root/IsaacLab
./isaaclab.sh -p /root/EASYkoopman/workflows/play_controller.py ...
```

### `ModuleNotFoundError: No module named 'easyuuv_task_registration'`

通常说明没有拉到 `isaaclab2-migration` 分支，或者脚本路径不是 `/root/EASYkoopman/workflows/play_controller.py`。检查：

```bash
cd /root/EASYkoopman
git branch --show-current
ls easyuuv_task_registration.py isaaclab_compat.py isaaclab_app.py
```

### `No registered env with id: EasyUUV-Direct-v1`

说明任务注册没有执行成功。请确认 `play_controller.py` 中存在：

```text
register_easyuuv_task()
```

并把完整 traceback 发回本地继续修。

### Isaac API import 失败

如果错误指向 `isaaclab_compat.py`，说明 Isaac Lab 2.2.1 的具体 API 路径和我们预期有差异。把 traceback 复制回来，我们只需要修兼容层，不需要大改控制器。

## 6. 完成本阶段后的下一步

如果 JSONL 生成成功：

1. 把 `koopman_step.jsonl` 拿回本地或保留在服务器。
2. Phase 1.5 可以视为通过。
3. 下一阶段进入 Phase 2：离线 EDMD / Koopman identification。

如果 JSONL 未生成：

1. 保存完整 terminal 输出。
2. 优先定位错误在 `isaaclab_compat.py`、task registration 还是 `play_controller.py`。
3. 不要先改 Koopman/MPC；本阶段目标只是让 baseline 数据链路在 Isaac Lab 2 上跑通。

# IsaacLab 2 服务器环境记录

本文档记录当前服务器镜像的实际 Isaac Sim / Isaac Lab 环境状态，用于后续将 EasyUUV / EASYkoopman 从 Isaac Lab v1 代码迁移到 Isaac Lab 2.x。

## 结论

当前服务器环境可用，但它不是旧版二进制安装结构。

实际环境是：

```text
Isaac Sim 5.0 pip/conda 版
Isaac Lab 2.x API 结构
Python: /opt/conda/envs/isaaclab/bin/python
IsaacLab root: /root/IsaacLab
```

因此后续不要再按旧路径查找：

```text
/root/isaacsim/python.sh
/root/isaacsim/isaac-sim.sh
```

这个镜像的 Isaac Sim 是装进 conda 环境里的，入口在：

```text
/opt/conda/envs/isaaclab/bin/python
/opt/conda/envs/isaaclab/bin/isaacsim
```

## 已确认路径

```text
/root/IsaacLab
/root/IsaacLab/isaaclab.sh
/root/IsaacLab/source/isaaclab
/root/IsaacLab/source/isaaclab_tasks
/root/IsaacLab/source/isaaclab_rl
/root/IsaacLab/apps/isaaclab.python.headless.kit
/opt/conda/envs/isaaclab/bin/python
/opt/conda/envs/isaaclab/bin/isaacsim
```

## 已确认 Python 包

服务器 `pip list | grep -i isaac` 显示：

```text
isaaclab                   0.45.9               /root/IsaacLab/source/isaaclab
isaaclab_assets            0.2.2                /root/IsaacLab/source/isaaclab_assets
isaaclab_mimic             1.0.13               /root/IsaacLab/source/isaaclab_mimic
isaaclab_rl                0.2.4                /root/IsaacLab/source/isaaclab_rl
isaaclab_tasks             0.10.47              /root/IsaacLab/source/isaaclab_tasks
isaacsim                   5.0.0.0
isaacsim-app               5.0.0.0
isaacsim-core              5.0.0.0
isaacsim-rl                5.0.0.0
isaacsim-robot             5.0.0.0
isaacsim-ros1              5.0.0.0
isaacsim-ros2              5.0.0.0
omniverse-kit              107.3.1.206797
```

说明服务器确实包含 Isaac Sim 5.0 和 Isaac Lab 相关源码包。

## 通过的测试

### 1. AppLauncher 启动测试

命令：

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

结果：

```text
Isaac Sim + Isaac Lab app startup OK
```

结论：`omni.log`、`isaaclab`、`isaaclab_tasks`、`isaaclab_rl` 都能在 AppLauncher 启动后正常导入。

### 2. Isaac Lab 内置任务列表测试

命令：

```bash
cd /root/IsaacLab
./isaaclab.sh -p scripts/environments/list_envs.py
```

结果：命令成功列出 Isaac Lab 内置任务，包括：

```text
Isaac-Ant-Direct-v0
Isaac-Cartpole-Direct-v0
Isaac-Quadcopter-Direct-v0
Isaac-Humanoid-Direct-v0
Isaac-Velocity-Flat-Anymal-C-Direct-v0
...
```

结论：Isaac Lab 的 app 启动、任务注册和内置 direct / manager-based 环境枚举正常。

## 需要注意的警告

测试输出中出现了：

```text
Warp CUDA error: Failed to get driver entry point 'cuDeviceGetUuid'
Warp CUDA error 36: API call is not supported in the installed CUDA driver
```

但两个测试都继续完成，并且 `list_envs.py` 成功列出任务。因此当前判断为：

```text
非阻塞警告
```

后续运行 EasyUUV rollout 时仍需要观察它是否影响真实仿真 step。如果出现物理仿真无法运行、CUDA kernel 失败或程序中断，再单独处理驱动 / Warp 兼容问题。

测试输出也出现：

```text
Modules: ['omni.kit_app'] were loaded before SimulationApp was started
```

当前不阻塞环境验证。后续迁移代码时需要遵守规则：

```text
先 AppLauncher / SimulationApp
再导入 omni、isaaclab_tasks、gymnasium task 等依赖 Kit 的模块
```

## 之前失败的原因

直接运行：

```bash
./isaaclab.sh -p -c "import isaaclab; import isaaclab_tasks; import isaaclab_rl"
```

曾经报错：

```text
ModuleNotFoundError: No module named 'omni.log'
```

这不是缺少 Isaac Sim，而是因为没有先启动 Isaac / Kit app。Isaac Lab 2 中部分 `omni.*` 模块需要在 `AppLauncher` 拉起后才可用。

因此后续不要用裸 Python import 判断 Isaac Lab 是否可用，应使用 AppLauncher 测试。

## 对 EasyUUV 代码迁移的影响

当前 EasyUUV 代码是 Isaac Lab v1 风格，典型 import 是：

```python
import omni.isaac.lab.sim as sim_utils
from omni.isaac.lab.assets import RigidObject, RigidObjectCfg
from omni.isaac.lab.envs import DirectRLEnv, DirectRLEnvCfg
from omni.isaac.lab_tasks.utils import parse_env_cfg
from omni.isaac.lab_tasks.utils.wrappers.rsl_rl import RslRlVecEnvWrapper
```

服务器环境需要迁移到 Isaac Lab 2 风格：

```python
import isaaclab.sim as sim_utils
from isaaclab.assets import RigidObject, RigidObjectCfg
from isaaclab.envs import DirectRLEnv, DirectRLEnvCfg
from isaaclab_tasks.utils import parse_env_cfg
from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
```

迁移时必须优先保证：

```text
play_controller.py direct-controller 数据采集
```

因为 Phase 1 的目标只是跑通：

```text
EasyUUV env -> legacy controller -> _last_pwm_8d -> koopman_step.jsonl
```

PPO 训练、PPO eval、checkpoint 加载可以后置。

## 推荐下一阶段

新增一个迁移阶段：

```text
Phase 1.5: Isaac Lab 2.x Compatibility Migration
```

第一目标：

```text
在 Isaac Sim 5.0 + Isaac Lab 2.x 服务器上跑通 play_controller.py，并生成 koopman_step.jsonl。
```

范围：

- 迁移 import namespace。
- 调整 task registration。
- 调整 asset / config 引用。
- 调整 workflow 中 AppLauncher 之后的导入顺序。
- 优先适配 direct-controller 路径。
- 本阶段不实现 EDMD、MPC、Kalman。

暂不优先处理：

- PPO 训练稳定性。
- PPO checkpoint eval。
- 三类 PPO 轨迹采集。
- Isaac Lab v1 向后兼容。

## 服务器基准命令

后续每次登录服务器，可先运行：

```bash
cd /root/IsaacLab
./isaaclab.sh -p scripts/environments/list_envs.py
```

如果能列出内置任务，说明 Isaac Lab 基础环境仍然正常。

若要测试 AppLauncher：

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

## 当前环境判断

```text
环境可用：是
需要代码迁移：是
可直接运行当前 EASYkoopman main：否
下一步：编写 Isaac Lab 2.x compatibility migration
```

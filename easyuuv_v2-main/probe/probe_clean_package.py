"""干净包名验证探针（无 bootstrap hack）。

验证 easyuuv_nc 作为独立包名时，能否：
Isaac 启动 -> import easyuuv_nc (触发 gym.register, 普通 entry_point)
-> gym.spec -> parse_env_cfg -> gym.make -> reset -> step -> 干净关闭。

与 probe_subfolder_bootstrap.py 的关键区别：
- 完全不调用 _bootstrap_local_lab_tasks_package()。
- entry_point 是普通模块路径 easyuuv_nc.env:EasyUUVEnv（不含 '-'，无命名空间冲突）。

用法（须让 easyuuv_stdw 的父目录在 sys.path，以便 import easyuuv_nc）：
  export PYTHONPATH=$(pwd):$PYTHONPATH   # pwd = easyuuv_stdw
  conda run -n isaaclab python -u easyuuv_nc/probe/probe_clean_package.py --headless
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from omni.isaac.lab.app import AppLauncher

# easyuuv_nc 的父目录（= easyuuv_stdw）必须在 sys.path，才能 import easyuuv_nc。
PROBE_DIR = Path(__file__).resolve().parent          # .../easyuuv_nc/probe
EASYUUV_NC_DIR = PROBE_DIR.parent                     # .../easyuuv_nc
PARENT_OF_NC = EASYUUV_NC_DIR.parent                  # .../easyuuv_stdw
if str(PARENT_OF_NC) not in sys.path:
    sys.path.insert(0, str(PARENT_OF_NC))


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean-package (no-bootstrap) probe.")
    parser.add_argument("--task", type=str, default="EasyUUV-Direct-Parametric-Wide256-v1")
    AppLauncher.add_app_launcher_args(parser)
    args_cli = parser.parse_args()

    print(f"[NCPROBE] PARENT_OF_NC = {PARENT_OF_NC}")
    print(f"[NCPROBE] task         = {args_cli.task}")

    app_launcher = AppLauncher(args_cli)
    simulation_app = app_launcher.app

    # 关键：仅普通 import，触发 easyuuv_nc/__init__.py 里的 gym.register，无任何 hack。
    import easyuuv_nc  # noqa: F401
    print(f"[NCPROBE] import easyuuv_nc ok: {easyuuv_nc.__file__}")

    import gymnasium as gym  # noqa: E402
    import torch  # noqa: E402
    from omni.isaac.lab_tasks.utils import parse_env_cfg  # noqa: E402

    spec = gym.spec(args_cli.task)
    print(f"[NCPROBE] gym.spec ok: id={spec.id} entry_point={spec.entry_point}")

    env_cfg = parse_env_cfg(args_cli.task, use_gpu=True, num_envs=1)
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode=None)
    print(f"[NCPROBE] gym.make ok: {type(env).__name__}")

    obs, _ = env.reset()
    act_dim = env.action_space.shape[-1]
    env.step(torch.zeros((1, act_dim), device="cuda"))
    print(f"[NCPROBE] step ok: action_dim={act_dim}")

    env.close()
    simulation_app.close()
    print("[NCPROBE][RESULT] CLEAN_PACKAGE_RUNTIME_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

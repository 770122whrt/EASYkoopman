"""Plan A/B 决策探针：验证【嵌套子文件夹】里的脚本能否正确完成
Isaac 启动 -> 本地 lab_tasks 包 bootstrap -> gym 注册解析 -> flip360 环境创建。

设计要点（与 workflows/play_stdw_adapt.py 的脆弱路径完全对齐）：
- 本脚本物理位置在 easyuuv_stdw/easyuuv_nc/probe/ 下（比 workflows/ 深一层）。
- REPO_ROOT 指向父级现有包 easyuuv_stdw/（复用其 __init__.py 里的 gym.register），
  以此回答"子文件夹脚本能否解析到含 '-' 的 gym entry_point"这一 Plan A 关键问题。
- 只做最小 gym.make + 一步 step 冒烟，不加载策略、不做自适应循环。

用法：
  custom_workflows/run_with_isaac_env.sh python \
      easyuuv_nc/probe/probe_subfolder_bootstrap.py --headless
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from omni.isaac.lab.app import AppLauncher

# ---------------------------------------------------------------------------
# 路径推导：本脚本在 easyuuv_nc/probe/ 下，父级现有包根为其上两级。
# ---------------------------------------------------------------------------
PROBE_DIR = Path(__file__).resolve().parent            # .../easyuuv_nc/probe
EASYUUV_NC_DIR = PROBE_DIR.parent                       # .../easyuuv_nc
REPO_ROOT = EASYUUV_NC_DIR.parent                       # .../easyuuv_stdw (现有父级包根)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
CUSTOM_WORKFLOWS_DIR = REPO_ROOT / "custom_workflows"
if str(CUSTOM_WORKFLOWS_DIR) not in sys.path:
    sys.path.insert(0, str(CUSTOM_WORKFLOWS_DIR))


def _bootstrap_local_lab_tasks_package() -> None:
    """与 play_stdw_adapt.py 同名函数逐字等价（详见其脚注）。"""
    package_name = "omni.isaac.lab_tasks"
    if package_name in sys.modules and getattr(
        sys.modules[package_name], "__file__", None
    ) == str(REPO_ROOT / "__init__.py"):
        return

    try:
        import omni.isaac.lab_tasks  # noqa: F401
        import omni.isaac.lab_tasks.utils  # noqa: F401
        import omni.isaac.lab_tasks.utils.wrappers  # noqa: F401
        import omni.isaac.lab_tasks.utils.wrappers.rsl_rl  # noqa: F401
    except Exception:
        pass

    package_init = REPO_ROOT / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        package_name,
        package_init,
        submodule_search_locations=[str(REPO_ROOT)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to bootstrap {package_name} from {package_init}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)


def main() -> int:
    parser = argparse.ArgumentParser(description="Subfolder bootstrap probe.")
    parser.add_argument("--task", type=str, default="EasyUUV-Direct-Parametric-v1")
    AppLauncher.add_app_launcher_args(parser)
    args_cli = parser.parse_args()

    print(f"[PROBE] PROBE_DIR    = {PROBE_DIR}")
    print(f"[PROBE] REPO_ROOT    = {REPO_ROOT}")
    print(f"[PROBE] task         = {args_cli.task}")

    app_launcher = AppLauncher(args_cli)
    simulation_app = app_launcher.app

    _bootstrap_local_lab_tasks_package()
    from easyuuv_task_registration import register_gym_tasks

    register_gym_tasks()

    injected = sys.modules.get("omni.isaac.lab_tasks")
    print(f"[PROBE] injected omni.isaac.lab_tasks.__file__ = "
          f"{getattr(injected, '__file__', None)}")

    import gymnasium as gym  # noqa: E402
    import torch  # noqa: E402
    from omni.isaac.lab_tasks.utils import parse_env_cfg  # noqa: E402

    # 1) gym 注册解析：能否拿到 spec（含 '-' 的 id + entry_point）
    spec = gym.spec(args_cli.task)
    print(f"[PROBE] gym.spec ok: id={spec.id} entry_point={spec.entry_point}")

    # 2) env cfg 解析 + gym.make（最小 1 env / headless）
    env_cfg = parse_env_cfg(args_cli.task, use_gpu=True, num_envs=1)
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode=None)
    print(f"[PROBE] gym.make ok: {type(env).__name__}")

    # 3) reset + 一步随机动作 step
    obs, _ = env.reset()
    act_dim = env.action_space.shape[-1]
    action = torch.zeros((1, act_dim), device="cuda")
    env.step(action)
    print(f"[PROBE] step ok: action_dim={act_dim}")

    env.close()
    simulation_app.close()
    print("[PROBE][RESULT] PLAN_A_SUBFOLDER_RUNTIME_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

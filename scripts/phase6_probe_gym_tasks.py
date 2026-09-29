"""Server-only probe for the four public EasyUUV Gym registrations."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from isaaclab_app import AppLauncher


TASK_IDS = (
    "EasyUUV-Direct-v1",
    "EasyUUV-Direct-Parametric-v1",
    "EasyUUV-Direct-Parametric-SatObs-v1",
    "EasyUUV-Direct-Parametric-Wide256-v1",
)


app_launcher = AppLauncher({"headless": True})
simulation_app = app_launcher.app
probe_error: BaseException | None = None
try:
    import gymnasium as gym

    from easyuuv_nc import register_gym_tasks
    from easyuuv_nc.package_paths import EMBODIMENT_USD_PATH

    register_gym_tasks()

    assert EMBODIMENT_USD_PATH.is_file()
    print(f"embodiment_usd={EMBODIMENT_USD_PATH}", flush=True)

    for task_id in TASK_IDS:
        specification = gym.spec(task_id)
        print(
            f"gym_task_id={task_id};entry_point={specification.entry_point}",
            flush=True,
        )
except BaseException as exc:
    probe_error = exc
    print(f"ERROR: gym_probe_failed:{type(exc).__name__}:{exc}", flush=True)
finally:
    simulation_app.close()

if probe_error is not None:
    raise probe_error

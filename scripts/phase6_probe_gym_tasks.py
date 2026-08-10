"""Server-only probe for the four public EasyUUV Gym registrations."""

from isaaclab_app import AppLauncher


TASK_IDS = (
    "EasyUUV-Direct-v1",
    "EasyUUV-Direct-Parametric-v1",
    "EasyUUV-Direct-Parametric-SatObs-v1",
    "EasyUUV-Direct-Parametric-Wide256-v1",
)


app_launcher = AppLauncher({"headless": True})
simulation_app = app_launcher.app
try:
    import gymnasium as gym

    import easyuuv_nc  # noqa: F401

    for task_id in TASK_IDS:
        specification = gym.spec(task_id)
        print(f"gym_task_id={task_id};entry_point={specification.entry_point}")
finally:
    simulation_app.close()

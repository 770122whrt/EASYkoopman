"""EasyUUV task package."""


def register_gym_tasks() -> None:
    """Register the Gym task after Isaac's app launcher has started."""
    try:
        from .easyuuv_task_registration import register_gym_tasks as _register_gym_tasks
    except ImportError:
        from easyuuv_task_registration import register_gym_tasks as _register_gym_tasks

    _register_gym_tasks()


def register_easyuuv_task() -> None:
    """Backward-compatible alias for older callers."""
    register_gym_tasks()

"""EasyUUV task package."""


def register_easyuuv_task() -> None:
    """Register the Gym task after Isaac's app launcher has started."""
    try:
        from .easyuuv_task_registration import register_easyuuv_task as _register_easyuuv_task
    except ImportError:
        from easyuuv_task_registration import register_easyuuv_task as _register_easyuuv_task

    _register_easyuuv_task()

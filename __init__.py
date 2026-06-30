"""EasyUUV task package."""

try:
    from .easyuuv_task_registration import register_easyuuv_task
except ImportError:
    from easyuuv_task_registration import register_easyuuv_task


register_easyuuv_task()

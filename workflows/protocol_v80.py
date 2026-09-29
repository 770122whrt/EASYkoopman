"""Frozen two-second development tasks for causal preview attribution."""
import math
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS

KINDS=('feedback','nominal_physics','identified_physics','structured_projected')
TASKS=('pitch_pos','pitch_neg')


def case_spec(configuration,controller,preview_enabled,task):
    if configuration not in SUPPORTED_EMBODIMENTS or controller not in KINDS or task not in TASKS:
        raise ValueError('case_spec')
    if type(preview_enabled) is not bool:raise ValueError('preview_flag')
    if controller=='feedback' and preview_enabled:raise ValueError('feedback_preview')
    angle=.04 if task=='pitch_pos' else -.04
    return dict(configuration=configuration,controller=controller,profile='depth4_h20',
                preview_enabled=preview_enabled,controls=60,seed=19760,
                reference=[5.5,math.cos(angle/2),0.,math.sin(angle/2),0.],task=task)

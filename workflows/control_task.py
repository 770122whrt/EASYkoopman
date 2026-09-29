"""The common task reference used unchanged by all three frozen controllers."""
import math

TASKS=("pitch_pos","pitch_neg")


def reference(task="pitch_pos"):
    if task not in TASKS:
        raise ValueError("case_spec")
    angle=.04 if task=="pitch_pos" else -.04
    return [5.5,math.cos(angle/2),0.,math.sin(angle/2),0.]

"""Plant-only extra quadratic drag. Never exported as model mechanical context."""
import math


def extra_quadratic_drag(density_force, density_torque, fraction):
    if isinstance(fraction, bool) or not math.isfinite(fraction) or not 0 <= fraction <= .5:
        raise ValueError('hidden_quadratic_drag_fraction')
    return fraction*density_force, fraction*density_torque

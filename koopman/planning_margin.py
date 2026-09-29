"""Numerical PWM interior shared by the optimizer and independent admission.

Observed execution keeps its 2e-6 gate. Exact CPU plans require 3e-6, while
the float64 NLP targets 4e-6. These buffers do not establish CPU/GPU parity;
execution still requires actual backend allocation and receipt checks.
"""
import numpy as np

PLANNING_MARGIN = 3e-6
OPTIMIZER_MARGIN = 4e-6


def enforce_interior(result, allocator, commands):
    """Reject an otherwise feasible plan too close to a PWM deadzone edge."""
    if result['feasible']:
        raw = np.asarray([allocator.command(u, pre_tam=True)['pwm_raw'] for u in commands],
                         dtype=float)
        if np.min(np.abs(np.abs(raw)-float(np.float32(.02)))) <= PLANNING_MARGIN:
            return dict(feasible=False, reason='planning_pwm_interior', cost=None, predictions=None)
    return result


def tighten_deadzone_bounds(lower, horizon, num_thrusters):
    """Tighten only deadzone constraints; reject any constraint-layout drift.

    Each physics step has 11 state features and four scalar hard constraints;
    each macro step has four slew, N raw PWM and N deadzone constraints.
    """
    low = np.asarray(lower, dtype=float).copy()
    h, n = horizon, num_thrusters
    if low.shape != (60*h+h*(4+2*n),):
        raise ValueError('constraint_layout')
    for k in range(h):
        part = slice(60*h+k*(4+2*n)+4+n, 60*h+(k+1)*(4+2*n))
        if not np.all(low[part] == 2e-6):
            raise ValueError('constraint_layout')
        low[part] = OPTIMIZER_MARGIN
    return low

"""Shared controllability-aware optimization and evaluation objective.

The reduced attitude is the world vertical expressed in body coordinates. It
is invariant to left multiplication by any world-Z yaw, including at nonzero
roll/pitch. Passive yaw rate remains a physical support constraint elsewhere.
"""
from dataclasses import dataclass
import numbers

import numpy as np

from easyuuv_nc.embodiments import qualification_record
from koopman.physical_terms_v26 import validate_states
from koopman.projected_edmd_v24 import rotation


def control_mask(configuration):
    return np.asarray(qualification_record(configuration)['control_mask'], dtype=float)


def checked_mask(mask):
    m = np.asarray(mask, dtype=float)
    if m.shape != (4,) or not any(np.array_equal(m, v) for v in ([1, 1, 1, 1], [1, 1, 0, 1])):
        raise ValueError('control_objective_mask')
    return m


def checked_reference(reference):
    r = np.array(reference, dtype=float, copy=True)
    if r.shape != (5,) or not np.isfinite(r).all() or abs(np.linalg.norm(r[1:])-1) > 1e-3:
        raise ValueError('control_reference_invalid')
    r[1:] /= np.linalg.norm(r[1:])
    return r


def state_features(states, mask):
    x, m = validate_states(states), checked_mask(mask)
    q = x[:, 1:5]/np.linalg.norm(x[:, 1:5], axis=1, keepdims=True)
    angle = 2*np.arctan2(np.linalg.norm(q[:, 1:], axis=1), np.abs(q[:, 0])) if m[2] else np.zeros(len(x))
    return np.column_stack((x[:, 0], rotation(q)[:, 2, :], x[:, 5:], angle))


def tracking_terms(states, reference, mask):
    x, ref, m = validate_states(states), checked_reference(reference), checked_mask(mask)
    q = x[:, 1:5]/np.linalg.norm(x[:, 1:5], axis=1, keepdims=True)
    r = rotation(q)
    if m[2]:
        angle = 2*np.arccos(np.clip(np.abs(q@ref[1:]), 0, 1))
    else:
        up = r[:, 2, :]; desired = rotation(ref[1:])[2]
        angle = np.arctan2(np.linalg.norm(np.cross(up, desired), axis=1), np.clip(up@desired, -1, 1))
    return dict(depth=(x[:, 0]-ref[0])**2, attitude=angle**2,
                vertical_speed=np.einsum('ni,ni->n', r[:, 2, :], x[:, 5:8])**2,
                angular_speed=np.sum((x[:, 8:]*m[:3])**2, axis=1))


@dataclass(frozen=True)
class ObjectiveWeights:
    depth: float = 1.
    attitude: float = 1.
    vertical_speed: float = .1
    angular_speed: float = .1
    effort: float = .01
    slew: float = .05
    terminal: float = 1.

    def __post_init__(self):
        values = tuple(vars(self).values())
        if (any(isinstance(v, bool) or not isinstance(v, numbers.Real) for v in values)
                or not np.isfinite(values).all() or min(values) < 0 or self.depth+self.attitude <= 0):
            raise ValueError('control_weights_invalid')


def trajectory_cost(states, commands, previous, reference, mask, weights):
    x, m = validate_states(states), checked_mask(mask)
    u, old = np.asarray(commands, dtype=float), np.asarray(previous, dtype=float)
    if (not isinstance(weights, ObjectiveWeights) or u.ndim != 2 or u.shape[1] != 4
            or not len(u) or len(x) != 2*len(u) or old.shape != (4,)
            or not np.isfinite(u).all() or not np.isfinite(old).all()):
        raise ValueError('control_cost_shape')
    terms = tracking_terms(x, reference, m)
    tracking = sum(getattr(weights, name)*values for name, values in terms.items())
    applied = u*m
    changes = np.diff(np.vstack([old*m, applied]), axis=0)
    cost = (tracking.sum()/120+weights.terminal*tracking[-1]
            +weights.effort*np.sum(applied**2)/60+weights.slew*np.sum(changes**2)/60)
    if not np.isfinite(cost): raise ValueError('control_cost_nonfinite')
    return float(cost)

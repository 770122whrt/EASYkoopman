"""Fixed, non-promoting linear-increment representation diagnostics.

No fitted artifact loader or controller handoff: this module compares information
on exploratory traces and does not implement a qualified Koopman model.
"""
from dataclasses import dataclass
import numpy as np
from koopman.so3_v21 import quaternion_to_r6_v21, apply_increment_target_v21

VARIANTS = ('last_proxy', 'ordered_proxy', 'last_speed', 'ordered_speed')


def features(state, memory, controls, *, variant, mask):
    x, m, u = (np.asarray(v, dtype=float) for v in (state, memory, controls))
    mask = np.asarray(mask)
    if (variant not in VARIANTS or x.shape != (11,) or m.ndim != 1 or not len(m)
            or u.shape != (2, 4) or mask.shape != (4,) or not np.isin(mask, [0, 1]).all()
            or not all(np.isfinite(v).all() for v in (x, m, u))):
        raise ValueError('representation_features_invalid')
    active = mask.astype(bool)
    if np.any(u[:, ~active] != 0):
        raise ValueError('representation_masked_control')
    if variant.endswith('proxy'):
        if m.shape != (4,) or np.any(m[~active] != 0):
            raise ValueError('representation_masked_memory')
        m = m[active]
    commands = u[:, active].ravel() if variant.startswith('ordered') else u[-1, active]
    return np.concatenate(([x[0]], quaternion_to_r6_v21(x[1:5]), x[5:], m, commands))


@dataclass(frozen=True)
class Fit:
    mean: np.ndarray
    scale: np.ndarray
    intercept: np.ndarray
    coefficient: np.ndarray
    audit: dict

    def predict(self, design):
        x = np.asarray(design, dtype=float)
        if x.ndim not in (1, 2) or x.shape[-1:] != self.mean.shape or not np.isfinite(x).all():
            raise ValueError('representation_predict_invalid')
        return self.intercept + ((x - self.mean) / self.scale) @ self.coefficient


def fit(design, targets):
    x, y = np.asarray(design, dtype=float), np.asarray(targets, dtype=float)
    if (x.ndim != 2 or len(x) < 2 or not x.shape[1] or y.shape != (len(x), 10)
            or not np.isfinite(x).all() or not np.isfinite(y).all()):
        raise ValueError('representation_fit_invalid')
    mean, scale, intercept = x.mean(0), np.maximum(x.std(0), 1e-6), y.mean(0)
    z = (x - mean) / scale
    u, s, vt = np.linalg.svd(z / np.sqrt(len(z)), full_matrices=False)
    coefficient = vt.T @ ((s / (s*s + .001))[:, None] * (u.T @ ((y-intercept) / np.sqrt(len(z)))))
    rank = int(np.linalg.matrix_rank(z))
    # Include null feature directions in the regularized design spectrum.
    smallest = 0.0 if rank < x.shape[1] else float(s[-1]**2)
    audit = {'rows': len(x), 'nonbias_columns': x.shape[1], 'centered_rank': rank,
             'singular_values_mean_design': s.tolist(), 'ridge_mean_objective': .001,
             'regularized_condition': float((s[0]**2+.001)/(smallest+.001)),
             'feature_std_below_floor': np.flatnonzero(x.std(0) < 1e-6).tolist()}
    for a in (mean, scale, intercept, coefficient):
        a.setflags(write=False)
    return Fit(mean, scale, intercept, coefficient, audit)


def rollout(model, initial_state, memories, controls, *, variant, mask):
    """Causal recursion accepts no future measured states, including in failures."""
    x = np.array(initial_state, dtype=float, copy=True)
    if len(memories) != len(controls) or not len(controls):
        raise ValueError('representation_rollout_invalid')
    predictions = []
    for index, (memory, commands) in enumerate(zip(memories, controls, strict=True)):
        try:
            delta = model.predict(features(x, memory, commands, variant=variant, mask=mask))
            x = apply_increment_target_v21(x, delta)
            if not np.isfinite(x).all() or abs(x[0]) > 100 or np.any(np.abs(x[5:]) > 100):
                raise ValueError('representation_state_bound')
        except (ValueError, FloatingPointError, OverflowError) as exc:
            return {'status': 'failed', 'failed_step': index+1, 'reason': str(exc), 'predictions': None}
        predictions.append(x.copy())
    return {'status': 'success', 'failed_step': None, 'reason': None, 'predictions': np.asarray(predictions)}

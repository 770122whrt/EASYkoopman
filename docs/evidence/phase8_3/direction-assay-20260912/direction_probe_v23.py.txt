"""Fixed local research probes. No selection, serialization or MPC handoff API."""
import numpy as np

from koopman.model_v21 import build_observable_features_v21, diagnose_solve_design_v21
from koopman.so3_v21 import quaternion_to_rotation_matrix_v21


def fit_probe_coefficients(design, targets, *, ridge=1e-8):
    x, y = np.asarray(design, dtype=float), np.asarray(targets, dtype=float)
    if (x.ndim != 2 or x.shape[1] != 22 or y.shape != (len(x), 10)
            or not np.isfinite(x).all() or not np.isfinite(y).all()
            or not np.isfinite(ridge) or ridge <= 0):
        raise ValueError('probe_fit_invalid')
    audit = diagnose_solve_design_v21(x, ridge=ridge)
    u, s, vt = np.linalg.svd(x, full_matrices=False)
    coefficient = (vt.T @ ((s/(s*s+ridge))[:, None]*(u.T@y))).T
    return coefficient, audit.to_dict()


class DirectionProbe:
    def __init__(self, coefficient, *, dt, kinematic_pose=False):
        if isinstance(dt, bool) or not np.isfinite(dt) or dt <= 0:
            raise ValueError('probe_dt_invalid')
        self.coefficient = np.array(coefficient, dtype=float, copy=True)
        if self.coefficient.shape != (10,22) or not np.isfinite(self.coefficient).all():
            raise ValueError('probe_coefficient_invalid')
        self.coefficient.setflags(write=False)
        self.dt, self.kinematic_pose = float(dt), bool(kinematic_pose)

    def predict_increment(self, state, memory, control, *, platform_score=None):
        if platform_score is not None:
            raise ValueError('platform_features_forbidden')
        phi = build_observable_features_v21(state, memory, control, 'so3_identity_v1')
        prediction = phi @ self.coefficient.T
        if self.kinematic_pose:
            states = np.asarray(state, dtype=float)
            single = states.ndim == 1
            rows = states[None, :] if single else states
            pred_rows = prediction[None, :] if single else prediction
            for x, dx in zip(rows, pred_rows, strict=True):
                # State[0] is root_pos_w.z; body velocities must be rotated.
                dx[0] = self.dt * (quaternion_to_rotation_matrix_v21(x[1:5]) @ x[5:8])[2]
                dx[7:10] = self.dt * x[8:11]
        return prediction


def complete_macro(entries):
    """Equal episode macro only when every requested episode succeeded."""
    successes = [e for e in entries if e['status'] == 'success']
    macro = None
    if entries and len(successes) == len(entries):
        macro = {k: float(np.mean([e['metrics'][k] for e in entries])) for k in entries[0]['metrics']}
    return {'episode_count':len(entries), 'success_count':len(successes), 'macro_metrics':macro}

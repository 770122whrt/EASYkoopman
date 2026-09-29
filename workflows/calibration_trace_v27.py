"""Calibration motion limits, in addition to the qualified contact contract."""
import numpy as np
from koopman.projected_edmd_v24 import rotation
from workflows.free_water_trace_v26 import FreeWaterTraceSession
from workflows.validate_free_water_v26 import contact_screen

LIMITS = {'linear_speed_m_s': 1.5, 'angular_speed_rad_s': 3., 'tilt_rad': np.pi/3,
          'horizontal_displacement_m': 2., 'vertical_displacement_m': 2.}
TAIL_LIMITS = {'linear_speed_m_s': .5, 'angular_speed_rad_s': .5, 'tilt_rad': np.pi/6}


def state_metrics(x):
    x = np.asarray(x, dtype=float)
    if x.shape != (11,) or not np.isfinite(x).all() or abs(np.linalg.norm(x[1:5])-1) > 1e-3:
        raise ValueError('calibration_state_invalid')
    return {'linear_speed_m_s': float(np.linalg.norm(x[5:8])),
            'angular_speed_rad_s': float(np.linalg.norm(x[8:])),
            'tilt_rad': float(np.arccos(np.clip(rotation(x[1:5])[2, 2], -1, 1)))}


def domain_screen(row, geometry, starting_z):
    result = contact_screen(row, geometry)
    metrics = state_metrics(np.asarray(row['state_after_physics_11'])[0])
    pose = np.asarray(row['backend_after_physics']['transform_actor_world_xyzw'])[0]
    metrics.update(horizontal_displacement_m=float(np.linalg.norm(pose[:2])),
                   vertical_displacement_m=float(abs(pose[2]-starting_z)))
    labels = ('linear_speed_limit', 'angular_speed_limit', 'tilt_limit',
              'horizontal_displacement_limit', 'vertical_displacement_limit')
    for name, label in zip(LIMITS, labels):
        if metrics[name] > LIMITS[name]: result['reasons'].append(label)
    result['screen_pass'] = not result['reasons']; result['motion_metrics'] = metrics
    return result


def tail_gate(rows):
    if len(rows) < 64: raise ValueError('calibration_tail_incomplete')
    metrics = [state_metrics(np.asarray(r['state_after_physics_11'])[0]) for r in rows[-64:]]
    maximum = {k: max(m[k] for m in metrics) for k in TAIL_LIMITS}
    return {'eligible_for_excitation': all(maximum[k] <= TAIL_LIMITS[k] for k in maximum),
            'tail_physics_ticks': 64, 'maximum': maximum,
            'limits': dict(TAIL_LIMITS), 'claim': 'bounded motion only, not exact hovering'}


class CalibrationTraceSession(FreeWaterTraceSession):
    def __init__(self, env, *, starting_z, **kwargs):
        super().__init__(env, stop_on_rejection=True, **kwargs)
        self.starting_z = starting_z

    def _finish_physics(self):
        row = self.pending
        super()._finish_physics()
        if row is None: return
        result = domain_screen(row, self.geometry, self.starting_z)
        row['calibration_screen_v27'] = result
        if not result['screen_pass']:
            raise ValueError('calibration_motion_rejected:'+','.join(result['reasons']))

"""Necessary free-water screens using measured backend forces and velocities.

This is not a contact sensor or a geometry-clearance certificate. A passing
screen does not establish absence of contact (e.g. a purely angular impulse).
The altitude floor is an explicit operating restriction on actor world z.
It is not water depth or an inferred lower hull surface. Existing v25 evidence
and acceptance rules are never modified by this additive diagnostic.
"""
import numpy as np
from koopman.projected_edmd_v24 import rotation

MINIMUM_ACTOR_Z_M = 1.0
RESIDUAL_LIMIT_M_S = 1e-3


def _array(value, shape):
    a = np.asarray(value, dtype=float)
    if a.shape != shape or not np.isfinite(a).all():
        raise ValueError('free_water_contract: shape or finite value')
    return a


def screen_step(row, *, minimum_actor_z_m=MINIMUM_ACTOR_Z_M,
                residual_limit_m_s=RESIDUAL_LIMIT_M_S):
    """Evaluate one no-reset, single-body, body-frame-wrench physics step.

    Residual is measured dv minus dt*(R F_external/m + gravity), in world axes.
    It includes unrecorded solver forces, numerical discrepancies or logging
    faults; it must not be labelled measured contact force.
    """
    try:
        floor = float(minimum_actor_z_m); limit = float(residual_limit_m_s)
        dt = float(row['physics_dt_s'])
        if not np.isfinite([floor, limit, dt]).all() or limit <= 0 or dt <= 0:
            raise ValueError('invalid thresholds or dt')
        b = row['before']['backend']; c = row['command']['backend']
        a = row['backend_after_physics']
        mass = float(_array(b['mass_kg'], (1, 1))[0, 0])
        gravity = _array(b['gravity_world_m_s2'], (3,))
        if mass <= 0:
            raise ValueError('nonpositive mass')
        for part in (b, c, a):
            if (not np.array_equal(_array(part['mass_kg'], (1, 1)), [[mass]])
                    or not np.array_equal(_array(part['gravity_world_m_s2'], (3,)), gravity)
                    or np.any(_array(part['gravity_disabled'], (1, 1)))):
                raise ValueError('mechanics changed or gravity disabled')
        if c['_use_global_wrench_frame'] is not False or c['uses_external_wrench_positions'] is not False:
            raise ValueError('unsupported wrench frame or application position')
        force = _array(c['_external_force_b'], (1, 1, 3))[0, 0]
        if not isinstance(c['has_external_wrench'], bool) or (not c['has_external_wrench'] and np.any(force)):
            raise ValueError('inactive nonzero wrench')
        poses = [_array(p['transform_actor_world_xyzw'], (1, 7))[0] for p in (b, a)]
        if any(abs(np.linalg.norm(p[3:])-1) > 1e-3 for p in poses):
            raise ValueError('invalid actor quaternion')
        q = poses[0][[6, 3, 4, 5]]
        r = rotation(q.reshape(1, 4))[0]
        old_v = _array(b['velocity_com_world_6'], (1, 6))[0, :3]
        new_v = _array(a['velocity_com_world_6'], (1, 6))[0, :3]
        predicted_dv = dt*(r @ force/mass + gravity)
        residual = new_v-old_v-predicted_dv
        if not np.isfinite(residual).all():
            raise ValueError('nonfinite balance')
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError(f'free_water_contract: {exc}') from exc
    minimum_z = min(p[2] for p in poses)
    max_abs = float(np.max(np.abs(residual)))
    reasons = []
    if minimum_z < floor: reasons.append('actor_altitude_below_operating_floor')
    if max_abs > limit: reasons.append('unexplained_linear_impulse')
    return {'screen_pass': not reasons, 'reasons': reasons,
            'minimum_actor_z_m': float(minimum_z),
            'operating_floor_world_z_m': floor, 'residual_limit_m_s': limit,
            'velocity_residual_world_3_m_s': residual.tolist(),
            'max_abs_velocity_residual_m_s': max_abs,
            'estimated_unexplained_impulse_norm_n_s': float(mass*np.linalg.norm(residual)),
            'direct_contact_observed': None}


def require_admissible_step(row, **kwargs):
    """Reject an unsuitable step; never certify a full dataset from one step."""
    result = screen_step(row, **kwargs)
    if not result['screen_pass']:
        raise ValueError('free_water_screen_rejected: '+','.join(result['reasons']))
    return result

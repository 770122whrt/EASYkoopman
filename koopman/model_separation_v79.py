"""Explicit model identities and a non-admitted full lifted operator probe.

The frozen projected readout remains a structured physical baseline. The probe
propagates the whole latent vector without relifting/resetting it each step;
its output is decoded, never silently replaced by a physical integration step.
No fitting, frozen artifact changes, or control promotion happen here.
"""
import numpy as np
from workflows.sparse_evaluation_v32 import decode_lift
from koopman.physical_terms_v26 import validate_states
from koopman.physical_control_v76 import PhysicalPredictor
from koopman.prepared_projected_v40 import prepare_projected
from koopman.sparse_world_edmd_v30 import lift, input_effect
from workflows.identify_sparse_world_v30 import validate_matrix


def make_predictor(kind, fitted, context):
    if kind == 'structured_projected': return prepare_projected(fitted, context)
    if kind in ('nominal_physics', 'identified_physics'):
        return PhysicalPredictor(fitted, context, identified=kind == 'identified_physics')
    if kind == 'frozen_full_lift_probe':
        raise ValueError('full_lift_not_admitted_to_control')
    raise ValueError('ambiguous_or_unknown_model_kind')


def full_lift_probe(fitted, context, initial_state, accelerations, *, rotation_tolerance=.05):
    """Offline controlled-lift diagnostic, not a promoted Koopman-MPC model.

    Input remains the historical known state-dependent lift kick. Geometry is
    decoded by nearest proper rotation only within the declared residual bound.
    Record projection residuals; do not conceal invalid/nonphysical operators.
    """
    x = validate_states(np.asarray(initial_state, dtype=float)[None])[0].copy()
    a = np.asarray(accelerations, dtype=float)
    if (a.ndim != 2 or a.shape[1] != 6 or not 1 <= len(a) <= 256
            or not np.isfinite(a).all() or not np.isfinite(rotation_tolerance)
            or not 0 < rotation_tolerance <= .1):
        raise ValueError('full_lift_probe_input')
    matrix = validate_matrix(fitted.matrix, fitted.family, fitted.damping,
                             fitted.quadratic, fitted.angular_damping)
    latent = lift(x[None], context, fitted.family)[0]
    result = dict(kind='frozen_full_lift_probe', complete=False, reason=None,
                  predictions=[], rotation_residuals=[], runtime_eligible=False,
                  model_fits=0, propagation='full_latent_no_relift',
                  input_map='frozen_known_state_dependent_lift_kick',
                  rotation_tolerance=rotation_tolerance)
    for u in a:
        with np.errstate(over='ignore', invalid='ignore'):
            latent = latent @ matrix + input_effect(x[None], u[None], context,
                                        fitted.family, fitted.angular_damping)[0]
        if not np.isfinite(latent).all(): result['reason'] = 'nonfinite_lift'; break
        if abs(latent[-1]-1) > 1e-8: result['reason'] = 'constant_observable'; break
        raw = latent[1:10].reshape(3, 3)
        left, singular, right = np.linalg.svd(raw)
        if singular[-1] < 1e-8: result['reason'] = 'rotation_rank_deficient'; break
        correction = np.diag([1., 1., np.linalg.det(left @ right)])
        rotation = left @ correction @ right
        residual = float(np.linalg.norm(raw-rotation, ord='fro'))
        result['rotation_residuals'].append(residual)
        if residual > rotation_tolerance: result['reason'] = 'rotation_projection_limit'; break
        # Reuse the established SO(3) readout, after checking its correction.
        following = decode_lift(latent[None])[0]
        if following[1:5] @ x[1:5] < 0: following[1:5] *= -1
        x = following
        result['predictions'].append(x.copy())
    result['predictions'] = np.asarray(result['predictions']).reshape(-1, 11)
    result['complete'] = len(result['predictions']) == len(a)
    return result

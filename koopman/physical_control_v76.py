"""Direct equations comparator; no fitting and no lifted matrix in prediction.

The identified variant reuses the frozen D/Q parameters. Its equivalence to
the projected velocity readout is intentional and must not be called an
independent Koopman representation gain. Nominal uses D=0, Q=1.
"""
import numpy as np
from koopman.physical_terms_v26 import state_terms, validate_states
from koopman.physical_prediction_v29 import advance_old_frame_velocity
from koopman.prepared_projected_v40 import prepare_projected, _context_key, _immutable
from koopman.sparse_world_edmd_v30 import core_matrix
from workflows.identify_sparse_world_v30 import SparseModel


class PhysicalPredictor:
    def __init__(self, frozen, context, *, identified=False):
        if type(identified) is not bool:
            raise ValueError('physical_comparator_kind')
        self.damping = _immutable(frozen.damping if identified else np.zeros(6))
        self.quadratic = _immutable(frozen.quadratic if identified else np.ones(6))
        self.angular_damping = frozen.angular_damping
        self._key = _context_key(context)
        family = frozen.family if identified else 'nonlinear'
        m = SparseModel(family, core_matrix(family, self.damping, self.quadratic,
                        self.angular_damping), self.damping, self.quadratic, self.angular_damping, {})
        # Same algebra for the differentiable proxy, independently tested below
        # against direct equations in the exact admission path.
        self._symbolic_base = prepare_projected(m, context)
        self.kind = 'identified_physics' if identified else 'nominal_physics'

    def __call__(self, states, acceleration, context):
        if _context_key(context) != self._key:
            raise ValueError('physical_comparator_context')
        x = validate_states(states); u = np.asarray(acceleration, dtype=float)
        if u.shape != (len(x), 6) or not np.isfinite(u).all():
            raise ValueError('physical_comparator_input')
        terms = state_terms(x, context)
        rate = u + np.c_[terms['net_buoyancy'], terms['restoring']]
        rate += terms['linear_drag'] + self.quadratic*terms['quadratic_drag']
        rate -= self.damping*x[:, 5:]
        rate[:, 3:] += terms['gyro']
        nu = x[:, 5:] + rate/120
        nu[:, 3:] *= 1-self.angular_damping/120
        return advance_old_frame_velocity(x, nu)

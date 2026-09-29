"""Shared offline model/control fixtures; no test-module imports."""
import numpy as np
from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS
from koopman.projected_edmd_v24 import PhysicalContext
from koopman.sparse_world_edmd_v30 import core_matrix
from workflows.identify_sparse_world_v30 import SparseModel
from workflows.workpoint_v27 import mechanics


def context(name='base'):
    m = mechanics(name)
    return PhysicalContext(m['mass_kg'], m['inertia_kg_m2'], m['cob_m'], m['volume_m3'],
                           EMBODIMENT_CONFIGS[name]['drag_multiplier'])

def model(family='nonlinear'):
    d = np.linspace(.01, .12, 6)
    q = np.linspace(.03, .08, 6) if family == 'nonlinear' else np.zeros(6)
    angular = float(np.float32(.05))
    return SparseModel(family, core_matrix(family, d, q, angular), d, q, angular, {})

def states(count=7):
    rng = np.random.default_rng(405)
    x = rng.normal(size=(count, 11))
    x[:, 0] += 5.5
    x[:, 1:5] /= np.linalg.norm(x[:, 1:5], axis=1, keepdims=True)
    # Include half-turn attitude and norm just inside the original admission.
    x[0, 1:5] = [0, 1.0009, 0, 0]
    return x

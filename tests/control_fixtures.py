"""Shared offline model/control fixtures; no test-module imports."""
import numpy as np
from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS
from koopman.physics_context import PhysicalContext
from koopman.sparse_physics import core_matrix
from workflows.frozen_physics import SparseModel
from workflows.mechanics import mechanics


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


def state(n=1):
    x = np.zeros((n, 11))
    x[:, 0] = 5.5
    x[:, 1] = 1
    return x


def oracle(name='frozen_contract_7bbbbef.json'):
    import json
    from pathlib import Path
    return json.loads((Path(__file__).parent / 'fixtures' / name).read_text(encoding='utf8'))


def assert_frozen(actual, expected, *, atol=1e-12):
    """Compare frozen numeric behavior; omit only measured wall-clock durations."""
    import pytest
    if isinstance(actual, dict):
        actual = {k: v for k, v in actual.items() if k not in ('elapsed_seconds', 'elapsed_ms', 'prepare_ms')}
        assert actual.keys() == expected.keys()
        for key in actual:
            assert_frozen(actual[key], expected[key], atol=atol)
    elif isinstance(actual, np.ndarray):
        np.testing.assert_allclose(actual, np.asarray(expected, dtype=actual.dtype), rtol=1e-12, atol=atol)
    elif isinstance(actual, (list, tuple)):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected):
            assert_frozen(a, b, atol=atol)
    elif isinstance(actual, (float, np.floating)):
        if not np.isfinite(actual):
            assert str(actual) == expected
        else:
            assert actual == pytest.approx(expected, rel=1e-12, abs=atol)
    else:
        assert actual == expected

import numpy as np
import pytest
pytest.importorskip('casadi', reason='v76 symbolic comparator tests require isolated CasADi')
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from test_prepared_projected_v40 import context, model, states


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
@pytest.mark.parametrize('identified', [False, True])
def test_direct_physics_matches_independent_reference_and_symbolic(name, identified):
    from koopman.physical_control_v76 import PhysicalPredictor
    from koopman.continuous_prediction_v76 import SymbolicPlant
    from koopman.prepared_projected_v40 import prepare_projected
    from koopman.physical_prediction_v29 import known_step
    c = context(name); fitted = model()
    predictor = PhysicalPredictor(fitted, c, identified=identified)
    x = states(8); u = np.random.default_rng(7601).uniform(-.3, .3, (8, 6))
    actual = predictor(x, u, c)
    expected = (prepare_projected(fitted, c)(x, u, c) if identified else
                known_step(x, u, c, angular_damping=fitted.angular_damping, gyroscopic=True))
    np.testing.assert_allclose(actual, expected, rtol=1e-11, atol=1e-11)
    plant = SymbolicPlant(predictor, name)
    for a, b, e in zip(x, u, expected):
        np.testing.assert_allclose(np.asarray(plant.step(a, b)).ravel(), e, rtol=1e-11, atol=1e-11)

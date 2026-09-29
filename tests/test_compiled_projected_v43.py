"""Optional compiled execution must preserve the admitted model and its guards."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip('numba', reason='v43 compiler is an isolated optional dependency')

from koopman.prepared_projected_v40 import prepare_projected
from test_prepared_projected_v40 import context, model, states
from test_command_batch_v41 import setup, same


@pytest.mark.parametrize('name', ['base', 'uuv6_angled'])
@pytest.mark.parametrize('family', ['linear', 'nonlinear'])
@pytest.mark.parametrize('count', [0, 1, 8, 64])
def test_compiled_matches_prepared_and_original_single_step(name, family, count):
    from koopman.compiled_projected_v43 import prepare_compiled
    c, m = context(name), model(family)
    x = states(count) if count else np.empty((0, 11))
    u = np.random.default_rng(431).uniform(-.5, .5, (count, 6))
    before_x, before_u = x.copy(), u.copy()
    compiled = prepare_compiled(m, c)
    expected = prepare_projected(m, c)(x, u, c)
    np.testing.assert_allclose(compiled(x, u, c), expected, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(compiled(x, u, c), m(x, u, c), rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(x, before_x); np.testing.assert_array_equal(u, before_u)


@pytest.mark.parametrize('name', ['base', 'uuv6_angled'])
@pytest.mark.parametrize('family', ['linear', 'nonlinear'])
def test_long_recurrence_both_directions_and_parallel_are_equivalent(name, family):
    from koopman.compiled_projected_v43 import prepare_compiled
    c, m = context(name), model(family)
    reference, compiled = prepare_projected(m, c), prepare_compiled(m, c)
    x = np.array([[5.5, 1., 0, 0, 0, .01, -.02, .01, .01, 0, -.01]])
    inputs = np.random.default_rng(432).uniform(-.15, .15, (256, 6))
    def run(predict, sign):
        result, y = [], x.copy()
        for u in inputs:
            y = predict(y, sign*u[None], c); result.append(y.copy())
        return np.asarray(result)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(run, compiled, 1), pool.submit(run, compiled, -1)
        np.testing.assert_allclose(a.result(), run(reference, 1), rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(b.result(), run(reference, -1), rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize('case', ['nan_state', 'inf_state', 'quaternion', 'shape', 'nan_input', 'input_shape'])
def test_runtime_validation_is_preserved(case):
    from koopman.compiled_projected_v43 import prepare_compiled
    c, m, x, u = context(), model(), states(1), np.zeros((1, 6))
    if case == 'nan_state': x[0, 0] = np.nan
    if case == 'inf_state': x[0, 5] = np.inf
    if case == 'quaternion': x[0, 1:5] = 0
    if case == 'shape': x = x[0]
    if case == 'nan_input': u[0, 0] = np.nan
    if case == 'input_shape': u = u[:, :4]
    with pytest.raises(ValueError): prepare_projected(m, c)(x, u, c)
    with pytest.raises(ValueError): prepare_compiled(m, c)(x, u, c)


@pytest.mark.parametrize('key,value', [('mass', 30.), ('volume', .02), ('rho', 1000.),
    ('beta', .002), ('gravity', 9.8), ('drag_multiplier', .7),
    ('inertia', np.array([.6, .7, .8])), ('cob', np.array([.01, .02, .03]))])
def test_context_is_bound_and_cannot_silently_change(key, value):
    from koopman.compiled_projected_v43 import prepare_compiled
    c = context()
    compiled = prepare_compiled(model(), c)
    with pytest.raises(ValueError, match='context'):
        compiled(states(1), np.zeros((1, 6)), replace(c, **{key:value}))


def test_source_model_mutation_and_input_layout_do_not_recompile_or_leak():
    from koopman.compiled_projected_v43 import prepare_compiled, _step
    c, m = context(), model()
    compiled = prepare_compiled(m, c)
    x, u = states(8), np.zeros((8, 6))
    expected = m(x, u, c)
    signatures = tuple(_step.signatures)
    m.matrix[:] = np.nan; m.damping[:] = 99
    for a, b, ref in [(x, u, expected), (x[::2], u[::2], expected[::2])]:
        a.setflags(write=False); b.setflags(write=False)
        np.testing.assert_allclose(compiled(a, b, replace(c)), ref, rtol=1e-12, atol=1e-12)
    assert tuple(_step.signatures) == signatures
    assert _step.nopython_signatures and _step.targetoptions['fastmath'] is False


def test_invalid_model_is_rejected_before_forecasting():
    from koopman.compiled_projected_v43 import prepare_compiled
    m = model(); m.matrix[0, 10] = 1
    with pytest.raises(ValueError): prepare_compiled(m, context())


@pytest.mark.parametrize('name', ['base', 'uuv6_angled'])
def test_batch_integration_has_same_outputs_and_no_live_commit(name):
    from koopman.compiled_projected_v43 import prepare_compiled
    from koopman.command_batch_v42 import forecast_batch
    live, saved, x, reference = setup(name, 64)
    c = context(name)
    compiled = prepare_compiled(model(), c)
    drive = np.random.default_rng(433).uniform(-.03, .03, (8, 20, 4)); drive[:, :, 3] += .12
    for a,b in zip(forecast_batch(saved, x, drive, compiled), forecast_batch(saved, x, drive, reference)):
        same(a,b)
    assert live.physics_index == 128

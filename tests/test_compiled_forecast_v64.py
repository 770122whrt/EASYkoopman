"""All-field numerical equivalence to the frozen forecast, not physics evidence."""
from copy import deepcopy
from dataclasses import replace
import time

import numpy as np
import pytest

pytest.importorskip('numba')
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.command_batch_v45 import forecast_prepared as reference
from koopman.compiled_projected_v43 import prepare_compiled
from koopman.prepared_commands_v45 import PreparedCommands
from test_command_batch_v41 import setup, same
from test_prepared_projected_v40 import model


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
@pytest.mark.parametrize('origin,horizon', [(0, 20), (128, 128)])
@pytest.mark.parametrize('share', [False, True])
def test_all_fields_all_configurations_history_and_shared_prefix(name, origin, horizon, share):
    from koopman.compiled_forecast_v64 import forecast_compiled, warm_forecast
    live, saved, x, _ = setup(name, origin)
    predict = prepare_compiled(model(), saved._context)
    warm_forecast(predict)
    drive = np.random.default_rng(641).uniform(-.015, .015, (3, horizon, 4))
    drive[:, :, 3] += .12
    drive[:, :8] = drive[0, :8]
    prepared = PreparedCommands(saved, drive)
    original_speed = saved._actuator.current()
    expected = reference(saved, x, prepared, predict)
    actual = forecast_compiled(saved, x, prepared, predict, share_prefix=share)
    for a, b in zip(actual, expected): same(a, b)
    np.testing.assert_array_equal(saved._actuator.current(), original_speed)
    assert live.physics_index == 2*origin
    actual[0]['predictions'][:] = 999
    assert not np.any(actual[1]['predictions'] == 999)


@pytest.mark.parametrize('mode', ['nan', 'raise'])
def test_generic_predictor_keeps_scalar_failure_isolation(mode):
    from koopman.compiled_forecast_v64 import forecast_compiled
    _, saved, x, _ = setup(origin=0)
    drive = np.zeros((3, 4, 4)); drive[1, :, 3] = .4
    def predict(states, u, c):
        bad = np.abs(u[:, 2]) > .02
        if mode == 'raise' and bad.any(): raise ValueError('branch_domain')
        y = states.copy(); y[:, 5:] += 1e-5*u
        if mode == 'nan': y[bad] = np.nan
        return y
    prepared = PreparedCommands(saved, drive)
    for a, b in zip(forecast_compiled(saved, x, prepared, predict), reference(saved, x, prepared, predict)):
        same(a, b)


def test_indices_boundaries_clock_deadline_and_kernel_signature():
    from koopman.compiled_forecast_v64 import forecast_compiled, warm_forecast, _chunk
    _, saved, x, _ = setup('uuv6_angled', 128)
    predict = prepare_compiled(model(), saved._context); warm_forecast(predict)
    signature = tuple(_chunk.signatures)
    drive = np.zeros((3, 5, 4))
    drive[0, :, 3] = np.float32(.02)
    drive[1, :, 3] = np.nextafter(np.float32(.02), np.float32(0))
    drive[2, :, 3] = -.12
    p = PreparedCommands(saved, drive)
    for share in (False, True):
        for a, b in zip(forecast_compiled(saved, x, p, predict, indices=[2, 0, 2], share_prefix=share),
                        reference(saved, x, p, predict, indices=[2, 0, 2])): same(a, b)
    assert tuple(_chunk.signatures) == signature
    assert _chunk.nopython_signatures and _chunk.targetoptions['fastmath'] is False
    with pytest.raises(TimeoutError): forecast_compiled(saved, x, p, predict, deadline=time.perf_counter()-1)
    changed = deepcopy(saved)
    object.__setattr__(changed, '_context', replace(changed._context, gravity=9.7))
    with pytest.raises(ValueError): forecast_compiled(changed, x, p, predict)
    for indices in ([], [3], [True], [-1]):
        with pytest.raises(ValueError): forecast_compiled(saved, x, p, predict, indices=indices)


def test_compiled_numerical_failure_preserves_reference_partial_results():
    from koopman.compiled_forecast_v64 import forecast_compiled, warm_forecast
    _, saved, x, _ = setup(origin=0)
    predict = prepare_compiled(model(), saved._context); warm_forecast(predict)
    x[5] = 99.
    p = PreparedCommands(saved, np.zeros((3, 8, 4)))
    for a, b in zip(forecast_compiled(saved, x, p, predict, share_prefix=True), reference(saved, x, p, predict)):
        same(a, b)


def test_shared_prefix_reduces_actual_kernel_work_without_reference_fallback(monkeypatch):
    import koopman.compiled_forecast_v64 as module
    _, saved, x, _ = setup(origin=3)
    predict = prepare_compiled(model(), saved._context); module.warm_forecast(predict)
    drive = np.zeros((9, 20, 4)); drive[:, :, 3] = .12
    drive[:, 8:, 3] += np.arange(9)[:, None]*.001
    p = PreparedCommands(saved, drive)
    original = module._chunk; work = []
    def counted(*args):
        work.append(2*args[3].shape[0]*args[3].shape[1])
        return original(*args)
    counted.signatures = original.signatures
    monkeypatch.setattr(module, '_chunk', counted)
    def forbidden(): raise AssertionError('valid input fell back to Python')
    monkeypatch.setattr(module, 'reference_forecast', lambda *a, **kw: forbidden())
    a = module.forecast_compiled(saved, x, p, predict)
    assert sum(work) == 360
    work.clear()
    b = module.forecast_compiled(saved, x, p, predict, share_prefix=True)
    assert sum(work) == 232
    for first, second in zip(a, b): same(first, second)


def test_chunk_deadline_failure_is_not_retried(monkeypatch):
    import koopman.compiled_forecast_v64 as module
    _, saved, x, _ = setup(origin=3)
    predict = prepare_compiled(model(), saved._context); module.warm_forecast(predict)
    p = PreparedCommands(saved, np.zeros((2, 20, 4)))
    original = module._chunk
    def slow(*args):
        value = original(*args)
        time.sleep(.03)
        return value
    slow.signatures = original.signatures
    monkeypatch.setattr(module, '_chunk', slow)
    def forbidden(*a, **kw): raise AssertionError('timeout must not retry reference')
    monkeypatch.setattr(module, 'reference_forecast', forbidden)
    with pytest.raises(TimeoutError):
        module.forecast_compiled(saved, x, p, predict, deadline=time.perf_counter()+.02)

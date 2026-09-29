"""The search, constraints and selected controls survive rollout acceleration."""
from dataclasses import replace
import numpy as np
import pytest

pytest.importorskip('numba')
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.compiled_projected_v43 import prepare_compiled
from koopman.bounded_mpc_v51 import BoundedMPC as Reference
from test_bounded_mpc_v44 import fixtures
from test_prepared_projected_v40 import model


def compare(a, b):
    for key in ('status', 'reason', 'selected_index', 'candidate_count'):
        assert a[key] == b[key], key
    for x, y in zip(a['candidates'], b['candidates']):
        for key in ('index', 'feasible', 'rejection'): assert x[key] == y[key]
        if x['cost'] is not None: assert x['cost'] == pytest.approx(y['cost'], rel=1e-12, abs=1e-12)
    for key in ('commands', 'predictions', 'cost', 'baseline_cost'):
        if a[key] is None: assert b[key] is None
        else: np.testing.assert_allclose(a[key], b[key], rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
@pytest.mark.parametrize('share', [False, True])
def test_same_candidates_selection_cost_prefix_and_predictions(name, share):
    from koopman.bounded_mpc_v64 import BoundedMPC
    live, domain, old, args = fixtures(name)
    predictor = prepare_compiled(model(), args['origin']._context)
    kw = dict(model_id=domain.model_id, config=old.config, weights=old.weights, allow_diagnostic=True)
    reference = Reference(domain, predictor, **kw)
    actual = BoundedMPC(domain, predictor, share_prefix=share, **kw)
    args['committed_prefix'] = 3
    compare(actual.solve(**args), reference.solve(**args))
    assert live.physics_index == 0


@pytest.mark.parametrize('kind', ['state', 'command', 'slew', 'deadzone', 'prediction', 'timeout'])
def test_rejection_and_generic_predictor_contracts(kind):
    from koopman.bounded_mpc_v64 import BoundedMPC
    _, domain, old, args = fixtures()
    kw = dict(model_id=domain.model_id, config=old.config, allow_diagnostic=True)
    ref = Reference(domain, old.predictor, **kw)
    got = BoundedMPC(domain, old.predictor, share_prefix=True, **kw)
    if kind == 'state': args['initial_state'][0] = 1.
    if kind == 'command': args['baseline'][:, 3] = .96
    if kind == 'slew': args['baseline'][:, 3] = .2
    if kind == 'deadzone': args['baseline'][:, 3] = .02; args['previous'][3] = .02
    if kind == 'prediction': ref.predictor = got.predictor = lambda x, u, c: np.full_like(x, np.nan)
    if kind == 'timeout': ref.config = got.config = replace(old.config, timeout_ms=1e-6)
    compare(got.solve(**args), ref.solve(**args))

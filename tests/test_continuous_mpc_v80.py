"""Server-only check of the actual symbolic constraint layout, not a mock."""
import numpy as np
import pytest
pytest.importorskip('casadi', reason='requires isolated server CasADi environment')
from test_prepared_projected_v40 import context, model


@pytest.mark.parametrize('cfg', ['base', 'uuv4', 'uuv6'])
def test_real_nlp_changes_only_deadzone_lower_bounds(cfg):
    from koopman.continuous_mpc_v76 import ContinuousMPC as Old
    from koopman.continuous_mpc_v80 import ContinuousMPC as New
    from koopman.prepared_projected_v40 import prepare_projected
    from koopman.bounded_mpc_v44 import SupportDomain
    c=context(cfg); predictor=prepare_projected(model(),c)
    d=SupportDomain.diagnostic(cfg,c,'8'*64)
    a=Old(d,predictor,horizon=2,allow_diagnostic=True)
    b=New(d,predictor,horizon=2,allow_diagnostic=True)
    n=b.plant.allocator.wrench_matrix.shape[1]
    ids=np.concatenate([np.arange(120+k*(4+2*n)+4+n,120+(k+1)*(4+2*n)) for k in range(2)])
    np.testing.assert_array_equal(np.flatnonzero(a._lower_g!=b._lower_g),ids)
    np.testing.assert_array_equal(b._lower_g[ids],np.full(2*n,4e-6))
    np.testing.assert_array_equal(a._upper_g,b._upper_g)
    assert a._evaluate.serialize()==b._evaluate.serialize()

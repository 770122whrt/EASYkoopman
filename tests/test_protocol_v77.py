import importlib
import pytest
from dataclasses import asdict


def test_profile_changes_one_factor_at_each_step():
    assert importlib.util.find_spec('workflows.protocol_v77'), 'v77 protocol missing'
    from workflows.protocol_v77 import settings
    from koopman.control_objective_v44 import ObjectiveWeights
    a,b,c=(settings(x) for x in ('repair','depth4','depth4_h20'))
    assert a['horizon']==b['horizon']==10 and c['horizon']==20
    assert asdict(a['weights'])==asdict(ObjectiveWeights())
    assert asdict(b['weights'])==dict(asdict(a['weights']),depth=4.)
    assert c['weights']==b['weights']
    with pytest.raises(ValueError):settings('unknown')

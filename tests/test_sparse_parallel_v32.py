import json,hashlib
import numpy as np
import pytest
from workflows.evaluate_sparse_parallel_v32 import cached_forecast
from workflows.identification_protocol_v32 import cases

def test_cache_miss_and_hash_failure_are_not_predictions(tmp_path):
    q=cases()[0];assert cached_forecast(tmp_path,q,'known_physics','none',128) is None
    p=tmp_path/(q['run_id']+'__known_physics__none__128.npz');np.savez_compressed(p,predictions=np.zeros((256,11)),commands=np.zeros((128,4)))
    meta=dict(q,family='known_physics',scope='none',origin_control=128,forecast_sha256='a'*64)
    p.with_suffix('.json').write_text(json.dumps(meta))
    with pytest.raises(ValueError,match='checkpoint_identity'):cached_forecast(tmp_path,q,'known_physics','none',128)

def test_complete_cache_cannot_hide_missing_prefix(tmp_path):
    q=cases()[0];p=tmp_path/(q['run_id']+'__known_physics__none__128.npz')
    np.savez_compressed(p,predictions=np.zeros((1,11)),commands=np.zeros((1,4)))
    meta=dict(q,family='known_physics',scope='none',origin_control=128,forecast_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),complete=True,failure=None,origin_actuator_time_s=1.,future_inputs='generated_from_own_predicted_state_and_fixed_external_drive')
    p.with_suffix('.json').write_text(json.dumps(meta))
    with pytest.raises(ValueError,match='checkpoint_shape'):cached_forecast(tmp_path,q,'known_physics','none',128)

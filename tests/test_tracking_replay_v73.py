import copy
import gzip
import json
from pathlib import Path

import pytest


@pytest.fixture(scope='module')
def trace():
    from workflows.runtime_assets_v56 import AssetLocation, load_assets
    from workflows.collect_runtime_v59 import HANDOFF_SHA
    root = Path(__file__).resolve().parents[1]
    assets = load_assets(AssetLocation(str(root/'.pytest-tmp/phase9-runtime-v59-20260920'),
        '.', 'assets/v38/inputs', HANDOFF_SHA), model_key='nonlinear__pooled')
    p = root/'docs/evidence/phase9/remaining-coverage-v73-20260921/results/uuv6-depth-feedback/output/diagnostic.json.gz'
    return json.loads(gzip.decompress(p.read_bytes())), assets.domains['uuv6'], assets.context('uuv6')


def test_float32_dot_order_does_not_change_physical_decision(trace):
    from workflows.validate_tracking_v73 import validate_tracking_audit
    data, domain, context = trace
    assert validate_tracking_audit(data, domain, context)['decisions'] == 60


@pytest.mark.parametrize('field', ['pwm_raw', 'steady_wrench', 'acceleration_error', 'physical_residual_accepted'])
def test_numerical_bound_does_not_admit_corruption(trace, field):
    from workflows.validate_tracking_v73 import validate_tracking_audit
    data, domain, context = trace
    data = copy.deepcopy(data)
    record = data['inexact_feedback_audit'][0]['result']['inspection']
    if field == 'physical_residual_accepted':
        record[field] = not record[field]
    else:
        record[field][2] += 1e-4
    with pytest.raises(ValueError):
        validate_tracking_audit(data, domain, context)

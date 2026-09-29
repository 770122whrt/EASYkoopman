import copy,gzip,json
from pathlib import Path
import pytest

@pytest.fixture(scope='module')
def real_trace():
    from workflows.runtime_assets_v56 import AssetLocation,load_assets
    from workflows.collect_runtime_v59 import HANDOFF_SHA
    root=Path(__file__).resolve().parents[1]
    release=root/'.pytest-tmp/phase9-runtime-v59-20260920'
    p=root/'docs/evidence/phase9/lifecycle-fix-v70-20260921/results/uuv4-pitch-feedback/output/diagnostic.json.gz'
    a=load_assets(AssetLocation(str(release),'.','assets/v38/inputs',HANDOFF_SHA),model_key='nonlinear__pooled')
    return json.loads(gzip.decompress(p.read_bytes())),a.domains['uuv4'],a.context('uuv4')

def test_real_linux_trace_replays_logged_float32_pwm(real_trace):
    from workflows.validate_tracking_v70 import validate_tracking_audit
    d,domain,c=real_trace
    assert validate_tracking_audit(d,domain,c)['decisions']==60

@pytest.mark.parametrize('field',['pwm_raw','acceleration_error','steady_wrench','physical_residual_accepted'])
def test_replay_cannot_hide_corrupted_evidence(real_trace,field):
    from workflows.validate_tracking_v70 import validate_tracking_audit
    d,domain,c=real_trace;d=copy.deepcopy(d);r=d['inexact_feedback_audit'][0]['result']['inspection']
    if field=='physical_residual_accepted':r[field]=not r[field]
    else:r[field][0]+=1e-4
    with pytest.raises(ValueError):validate_tracking_audit(d,domain,c)

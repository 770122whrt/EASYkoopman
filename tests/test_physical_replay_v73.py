import gzip,json,copy
from pathlib import Path
import pytest

@pytest.fixture(scope='module')
def actual_feedback():
    from workflows.runtime_assets_v56 import AssetLocation,load_assets
    from workflows.collect_runtime_v59 import HANDOFF_SHA
    root=Path(__file__).resolve().parents[1];release=root/'.pytest-tmp/phase9-runtime-v59-20260920'
    p=root/'docs/evidence/phase9/lifecycle-fix-v70-20260921/results/uuv4-pitch-feedback/output/diagnostic.json.gz'
    a=load_assets(AssetLocation(str(release),'.','assets/v38/inputs',HANDOFF_SHA),model_key='nonlinear__pooled')
    return json.loads(gzip.decompress(p.read_bytes())),a.domains['uuv4'],a.context('uuv4')

def test_physical_scope_does_not_claim_arbitration(actual_feedback):
    from workflows.validate_effects_v73 import validate_execution
    d,domain,c=actual_feedback;r=validate_execution(d,d['case'],domain,c,physical_only=True)
    assert r['physics_steps']==240 and not r['arbitration_verified'] and not r['history_digest_replay_verified']

def test_physical_scope_still_checks_applied_actuator(actual_feedback):
    from workflows.validate_effects_v73 import validate_execution
    d,domain,c=actual_feedback;d=copy.deepcopy(d)
    d['substeps'][30]['command']['actuator_speed_n'][0][0]+=1
    with pytest.raises(ValueError):validate_execution(d,d['case'],domain,c,physical_only=True)

"""Only a reconstructed support-only failure may isolate a configuration."""
import copy
import gzip
import json
from pathlib import Path
import pytest

@pytest.fixture(scope='module')
def recorded_failure():
    from workflows.runtime_assets_v56 import AssetLocation, load_assets
    from workflows.collect_runtime_v59 import HANDOFF_SHA
    root=Path(__file__).resolve().parents[1]
    release=root/'.pytest-tmp/phase9-runtime-v59-20260920'
    trace=root/'docs/evidence/phase9/rate30-primary-v67-20260921/r3/results/asymmetric-pitch-feedback/output/diagnostic.json.gz'
    if not trace.exists() or not release.exists():pytest.skip('requires preserved real failure and frozen assets')
    assets=load_assets(AssetLocation(str(release),'.','assets/v38/inputs',HANDOFF_SHA),model_key='nonlinear__pooled')
    with gzip.open(trace,'rt') as f:data=json.load(f)
    return data,assets.domains['asymmetric'],assets.context('asymmetric')

def test_real_failure_is_isolated_without_success_promotion(recorded_failure):
    from workflows.validate_support_failure_v68 import validate_failure
    data,domain,context=recorded_failure
    result=validate_failure(data,data['case'],domain,context)
    assert result['status']=='configuration_support_no_go'
    assert result['physical_steps']==10
    assert result['control_benefit_claim'] is False

@pytest.mark.parametrize('mutation',['command','rotor','contact','cleanup','exception','early_state','controller'])
def test_unsafe_or_ambiguous_failure_stops_whole_queue(recorded_failure,mutation):
    from workflows.validate_support_failure_v68 import validate_failure
    original,domain,context=recorded_failure;data=copy.deepcopy(original)
    if mutation=='command':data['substeps'][3]['execution_command_v55']['command'][0]+=.01
    if mutation=='rotor':data['substeps'][-1]['command']['actuator_speed_n'][0][0]+=10
    if mutation=='contact':data['substeps'][-1]['free_water_screen_v26']['screen_pass']=False
    if mutation=='cleanup':data['cleanup_errors']=['failed']
    if mutation=='exception':data['exception']='RuntimeError:unknown'
    if mutation=='early_state':data['substeps'][2]['state_after_physics_11'][0][8]=2.9
    if mutation=='controller':data['case']['controller']='mpc'
    with pytest.raises(ValueError):validate_failure(data,data['case'],domain,context)

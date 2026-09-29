import copy,gzip,json,sys
from pathlib import Path
import pytest

@pytest.fixture(scope='module')
def actual_mpc_failure():
    from workflows.runtime_assets_v56 import AssetLocation,load_assets
    from workflows.collect_runtime_v59 import HANDOFF_SHA
    root=Path(__file__).resolve().parents[1];release=root/'.pytest-tmp/phase9-runtime-v59-20260920'
    p=root/'docs/evidence/phase9/uuv4-pairs-v71-20260921/results/uuv4-pitch-mpc/output/diagnostic.json.gz'
    a=load_assets(AssetLocation(str(release),'.','assets/v38/inputs',HANDOFF_SHA),model_key='nonlinear__pooled')
    return json.loads(gzip.decompress(p.read_bytes())),a.domains['uuv4'],a.context('uuv4')

@pytest.mark.skipif(sys.platform!='linux',reason='Exact float32 allocator/1e-12 rotor arbitration checked in original Linux runtime')
def test_actual_mpc_prefix_including_terminal_partial_interval(actual_mpc_failure):
    from workflows.validate_support_failure_v72 import validate_failure
    d,domain,c=actual_mpc_failure;r=validate_failure(d,d['case'],domain,c)
    assert r['physical_steps']==209 and r['arbitration']['activations']==11
    assert r['status']=='configuration_support_no_go' and not r['complete_episode']
    assert r['arbitration']['confirmed_controls']==52 and not r['control_benefit_claim']

def test_physical_only_check_cannot_authorize_configuration_isolation(actual_mpc_failure):
    from workflows.validate_support_failure_v72 import validate_failure
    d,domain,c=actual_mpc_failure;r=validate_failure(d,d['case'],domain,c,physical_only=True)
    assert r['physical_steps']==209 and r['status']=='physical_support_failure_prefix_replayed'
    assert not r['arbitration_verified'] and not r['configuration_isolation_authorized_by_this_check']

@pytest.mark.parametrize('mutation',['worker','command','receipt','arbitration','activation','terminal','early_state','contact'])
def test_no_go_classification_requires_intact_mpc_history(actual_mpc_failure,mutation):
    from workflows.validate_support_failure_v72 import validate_failure
    d,domain,c=actual_mpc_failure;d=copy.deepcopy(d)
    if mutation=='worker':d['worker_closed']['process_stopped']=False
    if mutation=='command':d['intervals'][10]['decision']['packet']['command'][1]+=.01
    if mutation=='receipt':d['substeps'][10]['execution_ack_v55']['receipt']['history_digest']='0'*64
    if mutation=='arbitration':d['arbitration_audit'][0]['capture']['history_digest']='0'*64
    if mutation=='activation':d['runtime_final']['stats']['mpc_activations']-=1
    if mutation=='terminal':d['arbitration_audit'][-1]['reason']='other'
    if mutation=='early_state':d['substeps'][1]['state_after_physics_11'][0][0]=9
    if mutation=='contact':d['substeps'][-1]['free_water_screen_v26']['screen_pass']=False
    if sys.platform!='linux' and mutation in ('arbitration','activation','terminal'):
        pytest.skip('Strict arbiter mutation checks run separately in the frozen Linux environment')
    with pytest.raises((ValueError,AssertionError)):validate_failure(d,d['case'],domain,c,physical_only=sys.platform!='linux')

"""Mutate copies of pulled-back real evidence; never rewrite the source trace."""
import gzip,json
from copy import deepcopy
from pathlib import Path
import pytest
from workflows.validate_continuous_v76 import validate
from workflows.runtime_assets_v56 import AssetLocation,load_assets


@pytest.fixture(scope='module')
def evidence():
    root=Path(__file__).resolve().parents[1]
    trace=root/'docs/evidence/phase9/continuous-v76-20260924/base-pitch-feedback-r1/trace.json.gz'
    assets=root/'.pytest-tmp/phase9-runtime-v59-20260920'
    if not trace.exists() or not assets.exists():pytest.skip('requires pulled-back v76 evidence and frozen local assets')
    loaded=load_assets(AssetLocation(str(assets),'.','assets/v38/inputs',
        '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    return json.loads(gzip.decompress(trace.read_bytes())),loaded


def test_pulled_back_baseline_passes_independent_replay(evidence):
    data,assets=evidence
    assert validate(data,assets,0)['physics_steps']==240


@pytest.mark.parametrize('fault',['native','source','history','contact'])
def test_tampered_evidence_cannot_be_accepted(evidence,fault):
    original,assets=evidence;data=deepcopy(original)
    if fault=='source':data['intervals'][3]['decision']['packet']['source']='mpc'
    if fault=='history':data['substeps'][3]['execution_ack_v55']['receipt']['history_digest']='0'*64
    if fault=='contact':data['substeps'][3]['contact_after_physics_v26']['normal_force_world_n']=[[0,0,1.]]
    with pytest.raises(ValueError):validate(data,assets,1 if fault=='native' else 0)

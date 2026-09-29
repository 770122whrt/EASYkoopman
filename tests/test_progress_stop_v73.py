import copy
import gzip
import json
from pathlib import Path
import pytest


@pytest.fixture(scope='module')
def trace():
    from workflows.runtime_assets_v56 import AssetLocation,load_assets
    from workflows.collect_runtime_v59 import HANDOFF_SHA
    root=Path(__file__).resolve().parents[1]
    a=load_assets(AssetLocation(str(root/'.pytest-tmp/phase9-runtime-v59-20260920'),'.','assets/v38/inputs',HANDOFF_SHA),model_key='nonlinear__pooled')
    p=root/'docs/evidence/phase9/remaining-coverage-v73-20260921/results/heavy_moderate-pitch-feedback/output/diagnostic.json.gz'
    return json.loads(gzip.decompress(p.read_bytes())),a.domains['heavy_moderate'],a.context('heavy_moderate')


def test_real_progress_stop_is_reconstructed_without_qualifying_run(trace):
    from workflows.diagnose_progress_stop_v73 import diagnose
    d,domain,c=trace;r=diagnose(d,domain,c)
    assert r['physical_steps']==80 and not r['configuration_isolation_authorized']
    assert not r['complete_episode'] and r['mpc_activations']==0


@pytest.mark.parametrize('field',['command','stop_reason','zero_progress'])
def test_diagnostic_rejects_inconsistent_evidence(trace,field):
    from workflows.diagnose_progress_stop_v73 import diagnose
    d,domain,c=trace;d=copy.deepcopy(d)
    if field=='command':d['substeps'][12]['command']['telemetry']['virtual_control_4'][0][1]+=.01
    elif field=='stop_reason':d['exception']='ValueError:timeout'
    else:d['inexact_feedback_audit'][-1]['result']['zero_progress']=False
    with pytest.raises(ValueError):diagnose(d,domain,c)

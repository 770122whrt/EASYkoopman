"""Small portability drift is allowed; command/physical/identity gates are not."""
import copy
import gzip
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/evidence/phase9/preview-v80-20260926'


@pytest.fixture(scope='module')
def inputs():
    from workflows.diagnose_separation_v79 import prepare
    data=json.loads(gzip.decompress((EVIDENCE/'uuv4-partial-return/uuv4-identified-off-r1/trace.json.gz').read_bytes()))
    return data,prepare(ROOT)[1],json.loads((EVIDENCE/'source-manifest-r3.json').read_text())


@pytest.mark.parametrize('field,label',[
    ('cost','^recorded_cost$'),('prediction','^recorded_predictions$'),
    ('command','^runtime_validation_first_plan_action$'),('source','^portable_frozen_source:')])
def test_portability_does_not_hide_material_corruption(inputs,field,label):
    from workflows.validate_portable_v82 import validate
    original,assets,manifest=inputs;data=copy.deepcopy(original);manifest=copy.deepcopy(manifest)
    if field=='cost':data['solve_audit'][0]['cost']+=1e-6
    elif field=='prediction':data['solve_audit'][0]['predictions'][0][0]+=1e-4
    elif field=='command':data['solve_audit'][0]['commands'][0][0]+=.01
    elif field=='source':manifest['files']['workflows/validate_preview_decision_v79.py']='0'*64
    with pytest.raises(ValueError,match=label):validate(data,assets,0,manifest=manifest)


def test_full_portable_replay_keeps_frozen_validator_untouched(inputs):
    import workflows.validate_preview_decision_v79 as frozen
    from workflows.validate_portable_v82 import validate
    data,assets,manifest=inputs;original=frozen._same
    result=validate(data,assets,0,manifest=manifest)
    assert result['physics_steps']==240 and result['decision_audits']==59
    assert result['actual_pwm_checks']==240 and result['backend_allocation_checks']==60
    assert len(result['portable_comparisons'])==59*4
    assert result['physical_and_selection_gates_unchanged']
    assert frozen._same is original

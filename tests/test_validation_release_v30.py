import copy
import pytest
from workflows.validation_release_v30 import validate_freeze,validate_prior_budget
from workflows.identification_protocol_v29 import cases,digest,protocol
from workflows.sparse_evaluation_v30 import policy

def frozen():
    from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
    scopes=['pooled']+['local-'+c for c in SUPPORTED_EMBODIMENTS]+['heldout-'+c for c in SUPPORTED_EMBODIMENTS]
    return {'schema':'v30-before-validation-freeze','frozen_before_validation':True,
        'models':{f+'__'+s:'a'*64 for f in ('linear','nonlinear') for s in scopes},
        'analysis_source_sha256':'4ccf666b9b7b28e3128317e356adc623613d40c2edb14d0f9cb87d481d2bc10f',
        'evaluation_policy':policy(),'protocol_sha256':digest(protocol()),
        'validation_cases':[q['run_id'] for q in cases() if q['role']=='validation'],
        'fit_source_commit':'1fbfed1d85051845fcd28d9d799ebe364450c8b6',
        'fit_archive_sha256':'d226d559b0ca349ee060d00bf5cd0b581a0013ceff3f2680ae6835915fdf62cf',
        'preflight_archive_sha256':'6fa2c01e6b1dbadb63e964b6b28fa287c601219c453147b521ef611abb03e768',
        'model_handoff':False,'test_access':False}

def test_freeze_requires_exact_models_and_policy():
    f=frozen();validate_freeze(f)
    for key,value in [('frozen_before_validation',False),('test_access',True),('models',{}),('evaluation_policy',{})]:
        bad=copy.deepcopy(f);bad[key]=value
        with pytest.raises(ValueError):validate_freeze(bad)

def test_budget_cannot_reset_or_include_validation():
    qs=[q for q in cases() if q['role']!='validation']
    budget={'charged_seconds':32.,'attempts':[{'case':q['run_id'],'status':'exited','native_exit':0,'charged_seconds':1.} for q in qs]}
    validate_prior_budget(budget)
    for bad in ({'attempts':[],'charged_seconds':0.},dict(budget,charged_seconds=0.)):
        with pytest.raises(ValueError):validate_prior_budget(bad)

def test_original_validation_entry_stays_closed(tmp_path):
    from workflows.run_identification_v29 import prepare
    with pytest.raises(ValueError,match='validation_not_released'):prepare(tmp_path,tmp_path,'validation')

def test_new_collector_changes_admission_only():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    old=(root/'workflows/collect_identification_v29.py').read_text()
    new=(root/'workflows/collect_validation_v30.py').read_text()
    new=new.replace("if q['role']!='validation':raise ValueError('validation_role_required')\n    from workflows.validation_release_v30 import verify_release,REMOTE_ROOT,TRANSFER_ROOT\n    verify_release(REMOTE_ROOT,TRANSFER_ROOT,expected_source)","if q['role']=='validation':raise ValueError('identification_validation_not_released')")
    new=new.replace("'workflows.collect_validation_v30'","'workflows.collect_identification_v29'")
    assert old==new

def test_new_entry_rejects_before_simulation_or_output(tmp_path):
    from workflows.collect_validation_v30 import run_case
    from workflows.feedback_v28 import parameters
    q=next(q for q in cases() if q['role']=='fit')
    with pytest.raises(ValueError,match='validation_role_required'):run_case(q,tmp_path/'output','a'*40,parameters())
    assert not (tmp_path/'output').exists()

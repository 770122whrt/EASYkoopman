import json
from pathlib import Path
import pytest


def test_new_budget_counts_failed_reserved_attempts():
    from workflows.run_identification_v29 import reservation_seconds
    assert reservation_seconds({'attempts':[],'charged_seconds':0})==300
    assert reservation_seconds({'attempts':[{'status':'reserved'}]*47,'charged_seconds':5355})==45
    with pytest.raises(ValueError,match='identification_process_budget'):
        reservation_seconds({'attempts':[{}]*48,'charged_seconds':0})
    with pytest.raises(ValueError,match='identification_time_budget'):
        reservation_seconds({'attempts':[],'charged_seconds':5380})


def test_validation_collection_cannot_start_before_model_release(tmp_path):
    from workflows.run_identification_v29 import prepare
    from workflows.collect_identification_v29 import run_case
    from workflows.identification_protocol_v29 import cases
    from workflows.feedback_v28 import parameters
    with pytest.raises(ValueError,match='identification_validation_not_released'):
        prepare(tmp_path,tmp_path/'transfer','validation')
    q=next(q for q in cases() if q['role']=='validation')
    with pytest.raises(ValueError,match='identification_validation_not_released'):
        run_case(q,tmp_path/'out','a'*40,parameters())
    assert not (tmp_path/'out').exists()


def test_prior_success_labels_without_raw_evidence_do_not_admit_fit(tmp_path):
    from workflows.run_identification_v29 import verify_preflight
    from workflows.identification_protocol_v29 import cases
    ids=[q['run_id'] for q in cases() if q['role']=='preflight']
    tmp_path.mkdir(exist_ok=True)
    (tmp_path/'stage-status.json').write_text(json.dumps({'status':'identification_stage_completed_pending_pullback',
        'source_commit':'a'*40,'accepted':ids,'rejected':[],'trace_sha256':{key:'b'*64 for key in ids}}))
    with pytest.raises(ValueError,match='identification_prior_missing'):
        verify_preflight(tmp_path,'a'*40,tmp_path)


def test_any_rejected_preflight_blocks_training_collection(tmp_path):
    from workflows.run_identification_v29 import verify_preflight
    (tmp_path/'stage-status.json').write_text(json.dumps({'status':'identification_stage_completed_pending_pullback',
        'source_commit':'a'*40,'accepted':[],'rejected':['failed-case'],'trace_sha256':{}}))
    with pytest.raises(ValueError,match='identification_prior_inventory'):
        verify_preflight(tmp_path,'a'*40,tmp_path)

"""New experiment admission is independent of frozen v38 authorizations."""
import hashlib
import json
from pathlib import Path
import pytest


def test_preflight_has_fixed_base_first_cases_and_no_training_or_comparison_claim():
    from workflows.phase9_preflight_v57 import proposal, cases
    p=proposal();q=cases()
    assert len(q)==8 and q[0]['configuration']=='base'
    assert {c['controls'] for c in q}=={32}
    assert p['new_fits']==0 and p['maximum_wall_seconds']==1800
    assert p['require_at_least_one_mpc_activation'] and p['full_cycle_budget_s']==1/60
    assert p['control_benefit_claim'] is False


def release(root):
    from workflows.phase9_preflight_v57 import proposal,digest,REQUIRED_RUNTIME_FILES
    files={}
    for name in REQUIRED_RUNTIME_FILES:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('source fixture')
        files[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    record=dict(schema='phase9-executable-release-v57',protocol_sha256=digest(proposal()),files_sha256=files)
    path=root/'PHASE9_RELEASE.json';path.write_text(json.dumps(record))
    return dict(schema='phase9-runtime-preflight-approval-v57',approved=True,
                release_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),protocol_sha256=digest(proposal()))


def test_missing_or_v38_approval_cannot_launch_new_collector(tmp_path):
    from workflows.phase9_preflight_v57 import authorize_case,cases
    release(tmp_path)
    for approval in (None,{'schema':'projected-formal-v38-new-D23','approved':True},{}):
        with pytest.raises(ValueError,match='approval'):
            authorize_case(tmp_path,cases()[0],approval)


@pytest.mark.parametrize('bad',['source','release_sha','protocol_sha','approved','case','missing_source'])
def test_tampered_scope_or_source_rejected_before_simulator_import(tmp_path,bad):
    from workflows.phase9_preflight_v57 import authorize_case,cases,REQUIRED_RUNTIME_FILES
    approval=release(tmp_path);q=cases()[0]
    if bad=='source':(tmp_path/REQUIRED_RUNTIME_FILES[0]).write_text('changed')
    if bad=='missing_source':
        p=tmp_path/'PHASE9_RELEASE.json';d=json.loads(p.read_text());d['files_sha256'].pop(REQUIRED_RUNTIME_FILES[0]);p.write_text(json.dumps(d));approval['release_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    if bad=='release_sha':approval['release_sha256']='0'*64
    if bad=='protocol_sha':approval['protocol_sha256']='0'*64
    if bad=='approved':approval['approved']=1
    if bad=='case':q['controls']=64
    with pytest.raises(ValueError):authorize_case(tmp_path,q,approval)


def test_exact_approval_and_manifest_release_only_fixed_case(tmp_path):
    from workflows.phase9_preflight_v57 import authorize_case,cases
    approval=release(tmp_path)
    result=authorize_case(tmp_path,cases()[0],approval)
    assert result['release_sha256']==approval['release_sha256']
    assert result['case']==cases()[0]

"""Release only the sixteen prespecified validation cases after the fit freeze."""
import hashlib,json,math,re
from pathlib import Path
from workflows.identification_protocol_v29 import cases,protocol,digest
from workflows.sparse_evaluation_v30 import policy
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS

REMOTE_ROOT='/root/EASYkoopman-phase8-4-validation-20260913-r18'
TRANSFER_ROOT='/root/phase84-transfer-20260913/validation-r18'
FIT_SOURCE='1fbfed1d85051845fcd28d9d799ebe364450c8b6'
ANALYSIS_SHA='4ccf666b9b7b28e3128317e356adc623613d40c2edb14d0f9cb87d481d2bc10f'
FIT_ARCHIVE='d226d559b0ca349ee060d00bf5cd0b581a0013ceff3f2680ae6835915fdf62cf'
PREFLIGHT_ARCHIVE='6fa2c01e6b1dbadb63e964b6b28fa287c601219c453147b521ef611abb03e768'
read=lambda p:json.loads(Path(p).read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def validate_freeze(f):
    scopes=['pooled']+['local-'+c for c in SUPPORTED_EMBODIMENTS]+['heldout-'+c for c in SUPPORTED_EMBODIMENTS]
    expected={a+'__'+s for a in ('linear','nonlinear') for s in scopes}
    if (f.get('schema')!='v30-before-validation-freeze' or f.get('frozen_before_validation') is not True
        or f.get('analysis_source_sha256')!=ANALYSIS_SHA or f.get('evaluation_policy')!=policy()
        or f.get('protocol_sha256')!=digest(protocol()) or f.get('fit_source_commit')!=FIT_SOURCE
        or f.get('fit_archive_sha256')!=FIT_ARCHIVE or f.get('preflight_archive_sha256')!=PREFLIGHT_ARCHIVE
        or f.get('validation_cases')!=[q['run_id'] for q in cases() if q['role']=='validation']
        or set(f.get('models',{}))!=expected or any(not re.fullmatch('[a-f0-9]{64}',h) for h in f['models'].values())
        or f.get('model_handoff') is not False or f.get('test_access') is not False):
        raise ValueError('validation_freeze_binding')

def validate_prior_budget(b):
    expected={q['run_id'] for q in cases() if q['role']!='validation'}
    attempts=b.get('attempts',[]);charged=b.get('charged_seconds',-1)
    if (len(attempts)!=32 or {a['case'] for a in attempts}!=expected
        or any(a['status']!='exited' or a['native_exit']!=0 or not math.isfinite(a['charged_seconds']) or a['charged_seconds']<=0 for a in attempts)
        or not math.isfinite(charged) or charged<=0 or charged>=protocol()['resource_cap']['collector_seconds']
        or not math.isclose(sum(a['charged_seconds'] for a in attempts),charged,abs_tol=1e-6)):
        raise ValueError('validation_prior_budget_binding')

def verify_release(root,transfer,source):
    root=Path(root);transfer=Path(transfer)
    if str(root)!=REMOTE_ROOT or str(transfer)!=TRANSFER_ROOT:raise ValueError('validation_release_root')
    request=read(transfer/'request.json');f=read(transfer/'validation-freeze.json');validate_freeze(f)
    if (request['source_commit']!=source or request['protocol_sha256']!=digest(protocol())
        or request['authorization']!='user_resume_goal_fresh_data_and_koopman_route_20260913'
        or request['validation_freeze_sha256']!=sha(transfer/'validation-freeze.json')
        or request['prior_budget_sha256']!=sha(transfer/'prior-budget.json')
        or request['policy_sha256']!=sha(transfer/'policy.json')
        or read(transfer/'protocol.json')!=protocol()):raise ValueError('validation_release_request')
    from workflows.feedback_v28 import parameters
    if read(transfer/'policy.json')!=parameters():raise ValueError('validation_controller_changed')
    validate_prior_budget(read(transfer/'prior-budget.json'))
    for stage,archive in [('preflight',PREFLIGHT_ARCHIVE),('fit',FIT_ARCHIVE)]:
        path=transfer/(stage+'-pullback.json');p=read(path)
        if (p['status']!='identification_source_runtime_inventory_pullback_accepted' or p['stage']!=stage
            or p['source_commit']!=FIT_SOURCE or p['archive_sha256']!=archive
            or set(p['trace_sha256'])!={q['run_id'] for q in cases() if q['role']==stage}
            or sha(path)!=f[stage+'_acceptance_sha256']):raise ValueError('validation_prior_pullback')
    for name,h in read(root/'SOURCE_MANIFEST.json')['files_sha256'].items():
        if sha(root/name)!=h:raise ValueError('validation_source_hash:'+name)
    for model,h in f['models'].items():
        if sha(transfer/'models'/(model+'.json'))!=h:raise ValueError('validation_model_hash:'+model)
    return f

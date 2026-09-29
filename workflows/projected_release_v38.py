"""Fail-closed formal admissions; a score file alone never releases test data."""
import json
import math
import re
from pathlib import Path, PurePosixPath

from workflows.feedback_v31 import parameters
from workflows.projected_evaluation_v38 import evaluate, policy
from workflows.projected_models_v38 import sha, validate_manifest
from workflows.projected_protocol_v38 import cases, digest, protocol
from workflows.projected_resource_v38 import SCHEMA as RESOURCE_SCHEMA, amended_limits

REMOTE_ROOT = '/root/EASYkoopman-phase8-4-projected-formal-v38-r23'
TRANSFER_ROOT = '/root/phase84-projected-formal-v38-r23'
PARENT_ROOT = '/root/EASYkoopman-phase8-4-projected-formal-v38'
PARENT_TRANSFER = '/root/phase84-projected-formal-v38'
VALIDATION_TRANSFER_ROOT = '/root/phase84-projected-formal-v38-r21'
VALIDATION_ANALYSIS_TRANSFER_ROOT = '/root/phase84-projected-formal-v38-r22'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def _sha_string(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def stage_identity(frozen, role, freeze_sha256):
    """Keep preserved validation's collector identity; new test uses new source."""
    if 'validation_numeric_recovery_sha256' in frozen and role=='validation':
        source=frozen.get('validation_source_commit'); prior=frozen.get('parent_freeze_sha256')
        if (frozen.get('schema') not in ('projected-formal-v38-numeric-repair-before-scoring', RESOURCE_SCHEMA)
                or not isinstance(source,str) or re.fullmatch('[a-f0-9]{40}',source) is None
                or not _sha_string(prior) or prior==freeze_sha256):
            raise ValueError('formal_validation_recovery_stage_identity')
        return source,prior
    return frozen['source_commit'],freeze_sha256


def analysis_identity(frozen, role, freeze_sha256):
    if frozen.get('schema') == RESOURCE_SCHEMA and role == 'validation':
        source = frozen.get('resource_parent_source_commit'); prior = frozen.get('resource_parent_freeze_sha256')
        if (not isinstance(source, str) or re.fullmatch('[a-f0-9]{40}', source) is None
                or not _sha_string(prior) or prior == freeze_sha256):
            raise ValueError('formal_resource_analysis_identity')
        return source, prior
    return frozen['source_commit'], freeze_sha256


def analysis_directory(transfer, role):
    transfer = Path(transfer)
    if (role == 'validation' and (transfer/'freeze.json').is_file()
            and read(transfer/'freeze.json').get('schema') == RESOURCE_SCHEMA):
        return Path(VALIDATION_ANALYSIS_TRANSFER_ROOT)/(role+'-analysis')
    return transfer/(role+'-analysis')


def stage_directory(transfer,role):
    """Read inherited validation in place; no symlinks or duplicate raw files."""
    transfer=Path(transfer)
    if role=='validation' and (transfer/'freeze.json').is_file():
        frozen=read(transfer/'freeze.json')
        if frozen.get('validation_numeric_recovery_sha256'):
            stage_identity(frozen,role,sha(transfer/'freeze.json'))
            return Path(VALIDATION_TRANSFER_ROOT)/role
    return transfer/role


def verify_validation_recovery(transfer, frozen):
    transfer=Path(transfer);budget=read(transfer/'budget.json')
    expected=frozen.get('validation_numeric_recovery_sha256')
    if 'validation_numeric_recovery' not in budget and expected is None:
        return None
    if (frozen.get('schema') not in ('projected-formal-v38-numeric-repair-before-scoring', RESOURCE_SCHEMA)
            or not _sha_string(expected) or sha(transfer/'validation-numeric-recovery.json')!=expected):
        raise ValueError('formal_validation_recovery_unamended_freeze')
    recovery=read(transfer/'validation-numeric-recovery.json')
    from workflows.projected_budget_v38 import validate_budget
    validate_budget(budget,sha(transfer/'freeze.json'),allow_failed_evidence=True)
    prior=read(transfer/'validation-parent-budget.json')
    validate_budget(prior,recovery['parent_freeze_sha256'],allow_failed_evidence=True)
    parent_freeze=read(transfer/'parent-freeze.json')
    if (budget.get('validation_numeric_recovery')!=recovery
            or sha(transfer/'parent-freeze.json')!=frozen.get('parent_freeze_sha256')
            or prior['freeze_sha256']!=frozen['parent_freeze_sha256']
            or prior['attempts']!=budget['attempts'][:69]
            or prior.get('numeric_recovery')!=budget.get('numeric_recovery')
            or parent_freeze.get('source_commit')!=frozen.get('validation_source_commit')
            or parent_freeze.get('numeric_recovery_sha256')!=frozen.get('numeric_recovery_sha256')):
        raise ValueError('formal_validation_recovery_parent')
    path=transfer/'parent-validation-audit.json';audit=read(path)
    revision=audit.get('auditor_revision',{})
    auditor_freeze = read(transfer/'resource-parent-freeze.json') if frozen.get('schema') == RESOURCE_SCHEMA else frozen
    if (sha(path)!=recovery['validation_audit_sha256']
            or audit.get('status')!='projected_formal_source_runtime_inventory_pullback_accepted'
            or audit.get('role')!='validation' or audit.get('physics_ticks')!=24576
            or audit.get('source_commit')!=frozen['validation_source_commit']
            or audit.get('freeze_sha256')!=frozen['parent_freeze_sha256']
            or audit.get('model_handoff') is not False
            or set(audit.get('trace_sha256',{}))!={q['run_id'] for q in cases('validation')}
            or revision.get('auditor_source_commit')!=auditor_freeze.get('source_commit')
            or revision.get('auditor_source_manifest_sha256')!=auditor_freeze.get('source_manifest_sha256')
            or revision.get('parent_source_commit')!=parent_freeze['source_commit']
            or revision.get('parent_source_manifest_sha256')!=parent_freeze['source_manifest_sha256']
            or revision.get('parent_freeze_sha256')!=frozen['parent_freeze_sha256']):
        raise ValueError('formal_validation_recovery_audit')
    if (sha(transfer/'validation-numeric-diagnostics.json')!=frozen.get('validation_numeric_diagnostics_sha256')
            or read(transfer/'validation-numeric-diagnostics.json').get('charged_seconds')!=recovery['diagnostic_seconds']):
        raise ValueError('formal_validation_recovery_charges')
    return audit


def require_evaluation_agreement(actual, expected):
    """Same scores, same decisions and counts; only reduction roundoff may vary."""
    if type(actual) is not type(expected):
        raise ValueError('formal_evaluation_recomputation')
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError('formal_evaluation_recomputation')
        for key in expected:
            require_evaluation_agreement(actual[key], expected[key])
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError('formal_evaluation_recomputation')
        for left, right in zip(actual, expected):
            require_evaluation_agreement(left, right)
    elif type(expected) is float:
        if not (math.isfinite(actual) and math.isfinite(expected)
                and abs(actual-expected) <= 1e-12+1e-9*max(abs(actual), abs(expected))):
            raise ValueError('formal_evaluation_recomputation')
    elif actual != expected:
        raise ValueError('formal_evaluation_recomputation')


def verify_numeric_recovery(transfer, frozen):
    """A repaired ledger cannot grant itself permission under the old freeze."""
    transfer = Path(transfer)
    budget = read(transfer/'budget.json')
    expected = frozen.get('numeric_recovery_sha256')
    if 'numeric_recovery' not in budget and expected is None:
        return None
    if not _sha_string(expected):
        raise ValueError('formal_numeric_recovery_unamended_freeze')
    if sha(transfer/'numeric-recovery.json') != expected:
        raise ValueError('formal_numeric_recovery_binding')
    recovery = read(transfer/'numeric-recovery.json')
    if budget.get('numeric_recovery') != recovery:
        raise ValueError('formal_numeric_recovery_ledger')
    from workflows.projected_budget_v38 import validate_budget
    validate_budget(budget, sha(transfer/'freeze.json'), allow_failed_evidence=True)
    parent = read(transfer/'parent-budget.json')
    validate_budget(parent, recovery['parent_freeze_sha256'], allow_failed_evidence=True)
    if parent['attempts'] != budget['attempts'][:18]:
        raise ValueError('formal_numeric_recovery_parent')
    audit_path = transfer/'parent-preflight-audit.json'
    if sha(audit_path) != recovery['preflight_audit_sha256']:
        raise ValueError('formal_numeric_recovery_audit_hash')
    audit = read(audit_path)
    if (audit.get('status') != 'projected_formal_source_runtime_inventory_pullback_accepted'
            or audit.get('role') != 'preflight' or audit.get('freeze_sha256') != recovery['parent_freeze_sha256']
            or audit.get('physics_ticks') != 4096 or audit.get('model_handoff') is not False
            or set(audit.get('trace_sha256', {})) != {q['run_id'] for q in cases('preflight')}
            or not isinstance(audit.get('auditor_revision'), dict)):
        raise ValueError('formal_numeric_recovery_audit')
    revision = audit['auditor_revision']
    auditor_freeze=frozen
    if frozen.get('validation_numeric_recovery_sha256'):
        if sha(transfer/'parent-freeze.json')!=frozen.get('parent_freeze_sha256'):
            raise ValueError('formal_numeric_recovery_parent_freeze')
        auditor_freeze=read(transfer/'parent-freeze.json')
    if (revision.get('auditor_source_commit') != auditor_freeze.get('source_commit')
            or revision.get('auditor_source_manifest_sha256') != auditor_freeze.get('source_manifest_sha256')
            or revision.get('parent_source_commit') != audit.get('source_commit')
            or revision.get('parent_freeze_sha256') != audit.get('freeze_sha256')):
        raise ValueError('formal_numeric_recovery_auditor')
    if (sha(transfer/'numeric-diagnostics.json') != frozen.get('numeric_diagnostics_sha256')
            or read(transfer/'numeric-diagnostics.json').get('charged_seconds') != recovery['diagnostic_seconds']):
        raise ValueError('formal_numeric_recovery_diagnostic_charges')
    return audit


def validate_authorization(record, freeze_sha256):
    schema = record.get('schema') if isinstance(record, dict) else None
    resource = schema == 'projected-formal-v38-resource-amendment'
    if schema not in ('projected-formal-v38-new-D23', 'projected-formal-v38-numeric-amendment',
                      'projected-formal-v38-resource-amendment'):
        raise ValueError('formal_new_D23_required')
    expected = dict(schema=schema, decision='approved', authorized_by='user',
                    freeze_sha256=freeze_sha256, resource_cap=amended_limits() if resource else protocol()['resource_cap'])
    if (not isinstance(record, dict) or not _sha_string(freeze_sha256)
            or any(record.get(k) != v for k, v in expected.items())
            or not isinstance(record.get('approval_reference'), str) or not record['approval_reference'].strip()):
        raise ValueError('formal_new_D23_required')
    if (resource or schema == 'projected-formal-v38-numeric-amendment') and (
            not _sha_string(record.get('parent_freeze_sha256')) or record['parent_freeze_sha256'] == freeze_sha256
            or not _sha_string(record.get('parent_authorization_sha256'))):
        raise ValueError('formal_numeric_amendment_authorization')
    if resource and not _sha_string(record.get('approval_sha256')):
        raise ValueError('formal_resource_authorization_approval')


def predictor_binding(manifest, family, scope, configuration):
    if family in ('nonlinear', 'linear') and scope in ('pooled', 'heldout'):
        key = family+'__'+('pooled' if scope == 'pooled' else 'heldout-'+configuration)
        model = dict(key=key, sha256=manifest['models'][key]['sha256'], active_output_columns=list(range(10, 16)))
    elif (family, scope) in (('known_physics', 'none'), ('persistence', 'none')):
        model = dict(key=family, rule='fixed_known_step_v29' if family == 'known_physics' else 'identity_state')
    else:
        raise ValueError('formal_predictor_binding')
    return digest(dict(model=model, execution_sha256=manifest['execution_sha256']))


def validate_validation_result(result, scores, manifest, acceptance, source, freeze_sha256, *, data_identity=None):
    ids = {q['run_id'] for q in cases('validation')}
    data_source,data_freeze=data_identity or (source,freeze_sha256)
    if (acceptance.get('status') != 'projected_formal_source_runtime_inventory_pullback_accepted'
            or acceptance.get('role') != 'validation' or acceptance.get('source_commit') != data_source
            or acceptance.get('freeze_sha256') != data_freeze
            or set(acceptance.get('trace_sha256', {})) != ids
            or any(not _sha_string(h) for h in acceptance['trace_sha256'].values())):
        raise ValueError('formal_validation_acceptance')
    expected = dict(status='completed_projected_formal_evaluation', role='validation', source_commit=source,
        freeze_sha256=freeze_sha256, model_manifest_digest=digest(manifest), acceptance_digest=digest(acceptance),
        scores_digest=digest(scores), model_fits=0, model_handoff=False)
    if any(result.get(k) != v or type(result.get(k)) is not type(v) for k, v in expected.items()):
        raise ValueError('formal_validation_evaluation_binding')
    recalculated = evaluate(scores, 'validation', bootstrap=True)
    for row in scores:
        if (row.get('trace_sha256') != acceptance['trace_sha256'][row['run_id']]
                or row.get('predictor_binding_sha256') != predictor_binding(
                    manifest, row['family'], row['scope'], row['configuration'])):
            raise ValueError('formal_score_data_model_binding')
    require_evaluation_agreement(result.get('evaluation'), recalculated)
    if not recalculated['pass']:
        raise ValueError('formal_validation_not_GO')
    return recalculated


def verify_bundle(root, transfer, source):
    """Verify the approved snapshot and local files; no simulator is imported."""
    root, transfer = Path(root), Path(transfer)
    freeze_sha = sha(transfer/'freeze.json')
    authorization = read(transfer/'authorization.json')
    validate_authorization(authorization, freeze_sha)
    if authorization['schema'] == 'projected-formal-v38-resource-amendment':
        parent = read(transfer/'resource-parent-authorization.json')
        frozen = read(transfer/'freeze.json')
        if (frozen.get('schema') != RESOURCE_SCHEMA
                or sha(transfer/'resource-parent-authorization.json') != authorization['parent_authorization_sha256']
                or frozen.get('resource_parent_freeze_sha256') != authorization['parent_freeze_sha256']
                or sha(transfer/'resource-approval.json') != authorization['approval_sha256']):
            raise ValueError('formal_resource_authorization_binding')
        validate_authorization(parent, authorization['parent_freeze_sha256'])
        authorization = parent
    if authorization['schema'] == 'projected-formal-v38-numeric-amendment':
        parent = read(transfer/'authorization-parent.json')
        if (parent.get('schema') != 'projected-formal-v38-new-D23'
                or sha(transfer/'authorization-parent.json') != authorization['parent_authorization_sha256']
                or read(transfer/'freeze.json').get('authorization_parent_freeze_sha256',
                    read(transfer/'freeze.json').get('parent_freeze_sha256')) != authorization['parent_freeze_sha256']):
            raise ValueError('formal_numeric_amendment_parent_authorization')
        validate_authorization(parent, authorization['parent_freeze_sha256'])
    return verify_snapshot(root, transfer, source)


def verify_resource_amendment(transfer, frozen):
    """Bind the single approved cap change to immutable, settled r22 evidence."""
    from workflows.projected_resource_v38 import validate_approval, resource_limits
    from workflows.projected_budget_v38 import validate_budget
    transfer = Path(transfer); budget = read(transfer/'budget.json')
    if frozen.get('schema') != RESOURCE_SCHEMA:
        if 'resource_amendment' in budget or 'resource_amendment_sha256' in frozen:
            raise ValueError('formal_resource_unamended_freeze')
        return
    parent = read(transfer/'resource-parent-freeze.json')
    prior = read(transfer/'resource-parent-budget.json')
    approval = read(transfer/'resource-approval.json'); validate_approval(approval)
    amendment = read(transfer/'resource-amendment.json')
    audit = read(transfer/'validation-analysis-audit.json')
    if (sha(transfer/'resource-amendment.json') != frozen.get('resource_amendment_sha256')
            or budget.get('resource_amendment') != amendment
            or sha(transfer/'resource-parent-freeze.json') != frozen.get('resource_parent_freeze_sha256')
            or parent.get('schema') != 'projected-formal-v38-numeric-repair-before-scoring'
            or parent.get('source_commit') != frozen.get('resource_parent_source_commit')
            or amendment['parent_freeze_sha256'] != frozen['resource_parent_freeze_sha256']
            or prior.get('freeze_sha256') != frozen['resource_parent_freeze_sha256']
            or sha(transfer/'resource-parent-budget.json') != amendment['parent_budget_sha256']
            or sha(transfer/'resource-approval.json') != amendment['approval_sha256']
            or sha(transfer/'validation-analysis-audit.json') != amendment['validation_audit_sha256']
            or approval['parent_freeze_sha256'] != prior['freeze_sha256']
            or approval['parent_settled_budget_sha256'] != amendment['parent_budget_sha256']
            or approval['independent_validation_audit_sha256'] != amendment['validation_audit_sha256']
            or prior['attempts'] != budget['attempts'][:72]
            or any(prior.get(k) != budget.get(k) for k in ('numeric_recovery', 'validation_numeric_recovery'))):
        raise ValueError('formal_resource_parent_or_approval_binding')
    mutable = {'schema', 'source_commit', 'source_manifest_sha256', 'local_readiness_sha256'}
    if any(frozen.get(k) != v for k, v in parent.items() if k not in mutable):
        raise ValueError('formal_resource_changes_frozen_science')
    expected = dict(status='independent_projected_analysis_accepted', role='validation',
        source_commit=parent['source_commit'], freeze_sha256=prior['freeze_sha256'],
        raw_acceptance_sha256=sha(transfer/'validation-pullback.json'), rows_checked=1152,
        conditional_replayed=576, full_and_policy_array_metrics=576, independent_arithmetic=True,
        evaluation_pass=True, model_fits=0, model_handoff=False)
    if any(audit.get(k) != v or type(audit.get(k)) is not type(v) for k, v in expected.items()):
        raise ValueError('formal_resource_independent_validation_GO')
    validate_budget(prior, prior['freeze_sha256'])
    validate_budget(budget, sha(transfer/'freeze.json'), allow_failed_evidence=True)
    resource_limits(budget)


def verify_snapshot(root, transfer, source):
    """Read-only package integrity check, usable before approval; releases no role."""
    root, transfer = Path(root), Path(transfer)
    frozen = read(transfer/'freeze.json')
    if (frozen.get('schema') not in ('projected-formal-v38-before-any-new-data',
                                    'projected-formal-v38-numeric-repair-before-validation',
                                    'projected-formal-v38-numeric-repair-before-scoring', RESOURCE_SCHEMA)
            or not isinstance(source, str) or re.fullmatch('[a-f0-9]{40}', source) is None
            or frozen.get('source_commit') != source or type(frozen.get('model_fits')) is not int or frozen['model_fits'] != 0
            or frozen.get('model_handoff') is not False):
        raise ValueError('formal_freeze_identity')
    if (frozen['schema'] in ('projected-formal-v38-numeric-repair-before-validation',
                            'projected-formal-v38-numeric-repair-before-scoring', RESOURCE_SCHEMA)) != ('numeric_recovery_sha256' in frozen):
        raise ValueError('formal_numeric_amendment_freeze')
    if (frozen['schema'] in ('projected-formal-v38-numeric-repair-before-scoring', RESOURCE_SCHEMA)) != ('validation_numeric_recovery_sha256' in frozen):
        raise ValueError('formal_validation_recovery_freeze')
    expected_files = {
        'protocol.json': ('protocol_sha256', protocol()),
        'evaluation-policy.json': ('evaluation_policy_sha256', policy()),
        'policy.json': ('feedback_policy_sha256', parameters()),
    }
    for name, (key, expected) in expected_files.items():
        if sha(transfer/name) != frozen.get(key) or read(transfer/name) != expected:
            raise ValueError('formal_freeze_contract:'+name)
    for name, key in (('historical-budget.json', 'historical_budget_sha256'),
                      ('local-readiness.json', 'local_readiness_sha256'),
                      ('model-manifest.json', 'model_manifest_sha256')):
        if sha(transfer/name) != frozen.get(key):
            raise ValueError('formal_freeze_artifact:'+name)
    readiness = read(transfer/'local-readiness.json')
    if (readiness.get('status') != 'local_source_package_checks_passed'
            or readiness.get('source_commit') != source or readiness.get('simulation_evidence') is not False):
        raise ValueError('formal_local_readiness')
    manifest = read(transfer/'model-manifest.json')
    validate_manifest(manifest, root)
    if sha(root/'SOURCE_MANIFEST.json') != frozen.get('source_manifest_sha256'):
        raise ValueError('formal_source_manifest')
    source_manifest = read(root/'SOURCE_MANIFEST.json')['files_sha256']
    required = set(manifest['execution_sha256']) | {
        'workflows/projected_protocol_v38.py', 'workflows/projected_evaluation_v38.py',
        'workflows/projected_prediction_v38.py', 'workflows/projected_models_v38.py',
        'workflows/projected_release_v38.py', 'workflows/collect_projected_formal_v38.py',
        'workflows/validate_projected_formal_v38.py', 'workflows/projected_adapter_v38.py',
        'workflows/projected_budget_v38.py', 'workflows/run_projected_formal_v38.py',
        'workflows/evaluate_projected_formal_v38.py',
        'workflows/projected_archive_v38.py',
        'workflows/audit_projected_v38.py',
    }
    if not required <= set(source_manifest):
        raise ValueError('formal_source_inventory')
    for name, expected_hash in source_manifest.items():
        p = PurePosixPath(name)
        target = (root/name).resolve()
        if (p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name
                or not target.is_relative_to(root.resolve()) or not _sha_string(expected_hash)
                or sha(target) != expected_hash):
            raise ValueError('formal_source_hash:'+name)
    verify_numeric_recovery(transfer, frozen)
    verify_validation_recovery(transfer, frozen)
    verify_resource_amendment(transfer, frozen)
    return frozen, manifest


def verify_accepted_stage(root, transfer, role, source, freeze_sha256):
    """Require a pulled-back semantic audit and match every raw/native artifact.

    This admission verifies the audit's bindings. The independent pullback runner
    must re-run the full semantic validator before producing this certificate.
    """
    root, transfer = Path(root), Path(transfer)
    # Old fixtures do not have a freeze; current real packages always do.
    if (transfer/'freeze.json').is_file():
        frozen=read(transfer/'freeze.json')
        if frozen.get('validation_numeric_recovery_sha256'):
            if source!=frozen.get('source_commit') or freeze_sha256!=sha(transfer/'freeze.json'):
                raise ValueError('formal_prior_stage_analysis_identity')
            source,freeze_sha256=stage_identity(frozen,role,freeze_sha256)
    selected = cases(role)
    ids = {q['run_id'] for q in selected}
    acceptance = read(transfer/(role+'-pullback.json'))
    transfer=stage_directory(transfer,role).parent
    status = read(transfer/role/'stage-status.json')
    if (acceptance.get('status') != 'projected_formal_source_runtime_inventory_pullback_accepted'
            or acceptance.get('role') != role or acceptance.get('source_commit') != source
            or acceptance.get('freeze_sha256') != freeze_sha256
            or set(acceptance.get('trace_sha256', {})) != ids
            or acceptance.get('validator_sha256') != sha(root/'workflows/validate_projected_formal_v38.py')
            or acceptance.get('stage_status_sha256') != sha(transfer/role/'stage-status.json')
            or acceptance.get('archive_sha256') != sha(transfer/(role+'-evidence.tar.gz'))
            or status.get('status') != 'projected_formal_stage_completed_pending_pullback'
            or status.get('role') != role or status.get('source_commit') != source
            or status.get('freeze_sha256') != freeze_sha256 or status.get('rejected') != []
            or len(status.get('accepted', [])) != len(ids) or set(status['accepted']) != ids
            or status.get('trace_sha256') != acceptance['trace_sha256']):
        raise ValueError('formal_prior_stage_admission')
    for q in selected:
        name = q['run_id']
        directory = transfer/role/name
        trace_sha = sha(directory/'trace.json')
        exits = read(directory/'collector-exit.json')
        semantic = read(transfer/role/(name+'.validation.json'))
        if (trace_sha != acceptance['trace_sha256'][name]
                or (transfer/role/(name+'.exit_status')).read_text().strip() != '0'
                or type(exits.get('child_native_exit')) is not int or exits['child_native_exit'] != 0
                or type(exits.get('guarded_collector_exit')) is not int or exits['guarded_collector_exit'] != 0
                or exits.get('trace_sha256') != trace_sha
                or acceptance.get('semantic_sha256', {}).get(name) != sha(transfer/role/(name+'.validation.json'))
                or semantic.get('status') != 'identification_semantics_passed'
                or semantic.get('run_id') != name or semantic.get('role') != role
                or semantic.get('source_commit') != source or semantic.get('training_eligible') is not False
                or semantic.get('physics_ticks') != 2*q['intervals']
                or any(semantic.get(k) != 0 for k in ('contact_ticks', 'impulse_ticks', 'rejected_ticks'))
                or role == 'preflight' and semantic.get('tail', {}).get('eligible_for_excitation') is not True):
            raise ValueError('formal_prior_case_admission:'+name)
    return acceptance


def verify_analysis_audit(transfer, role, source, freeze_sha256):
    transfer = Path(transfer)
    if role not in ('validation', 'test'):
        raise ValueError('formal_analysis_audit_role')
    directory = analysis_directory(transfer, role)
    if (transfer/'freeze.json').is_file():
        frozen = read(transfer/'freeze.json')
        if frozen.get('schema') == RESOURCE_SCHEMA:
            if source != frozen['source_commit'] or freeze_sha256 != sha(transfer/'freeze.json'):
                raise ValueError('formal_resource_analysis_caller')
            source, freeze_sha256 = analysis_identity(frozen, role, freeze_sha256)
    record = read(transfer/(role+'-analysis-audit.json'))
    expected = dict(status='independent_projected_analysis_accepted', role=role,
        source_commit=source, freeze_sha256=freeze_sha256,
        result_sha256=sha(directory/'result.json'), scores_sha256=sha(directory/'scores.json'),
        raw_acceptance_sha256=sha(transfer/(role+'-pullback.json')), rows_checked=1152,
        conditional_replayed=576, full_and_policy_array_metrics=576,
        independent_arithmetic=True, model_fits=0, model_handoff=False,
        evaluation_pass=read(directory/'result.json')['evaluation']['pass'])
    if any(record.get(k) != v or type(record.get(k)) is not type(v) for k, v in expected.items()):
        raise ValueError('formal_analysis_audit_binding')
    return record


def verify_collection_release(root, transfer, source, role):
    # Exact remote roots prevent a fixture/local package from becoming a live run.
    if str(root) != REMOTE_ROOT or str(transfer) != TRANSFER_ROOT or role not in ('preflight', 'validation', 'test'):
        raise ValueError('formal_runtime_root_or_role')
    root, transfer = Path(root), Path(transfer)
    frozen, manifest = verify_bundle(root, transfer, source)
    freeze_sha = sha(transfer/'freeze.json')
    if frozen.get('numeric_recovery_sha256'):
        if role == 'preflight':
            raise ValueError('formal_recovered_preflight_must_not_recollect')
        parent_audit = verify_numeric_recovery(transfer, frozen)
        # Reuse the original eight raw cases with their ORIGINAL source/role
        # identities. The repaired audit receipt is separately frozen and bound.
        checked = verify_accepted_stage(PARENT_ROOT, PARENT_TRANSFER, 'preflight',
            parent_audit['source_commit'], parent_audit['freeze_sha256'])
        if checked != parent_audit:
            raise ValueError('formal_recovered_preflight_binding')
        if frozen.get('validation_numeric_recovery_sha256'):
            if role!='test':
                raise ValueError('formal_recovered_validation_must_not_recollect')
            validation=verify_validation_recovery(transfer,frozen)
            if verify_accepted_stage(root,transfer,'validation',source,freeze_sha)!=validation:
                raise ValueError('formal_recovered_validation_binding')
    elif role in ('validation', 'test'):
        verify_accepted_stage(root, transfer, 'preflight', source, freeze_sha)
    if role == 'test':
        acceptance = verify_accepted_stage(root, transfer, 'validation', source, freeze_sha)
        result_path = analysis_directory(transfer, 'validation')/'result.json'
        scores_path = analysis_directory(transfer, 'validation')/'scores.json'
        validate_validation_result(read(result_path), read(scores_path), manifest, acceptance,
            *analysis_identity(frozen, 'validation', freeze_sha),
            data_identity=stage_identity(frozen,'validation',freeze_sha))
        verify_analysis_audit(transfer, 'validation', source, freeze_sha)
        expected = dict(status='released_prespecified_test_after_validation_GO', source_commit=source,
            freeze_sha256=freeze_sha, validation_result_sha256=sha(result_path),
            validation_scores_sha256=sha(scores_path), validation_acceptance_sha256=sha(transfer/'validation-pullback.json'),
            model_manifest_sha256=sha(transfer/'model-manifest.json'),
            validation_audit_sha256=sha(transfer/'validation-analysis-audit.json'),
            test_cases=[q['run_id'] for q in cases('test')])
        if read(transfer/'test-release.json') != expected:
            raise ValueError('formal_test_release_binding')
    return frozen

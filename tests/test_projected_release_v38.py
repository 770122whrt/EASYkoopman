"""Release rejection paths use synthetic metadata, never real authorization."""
import copy

import pytest

from workflows.projected_protocol_v38 import cases, digest, protocol
from workflows.projected_evaluation_v38 import evaluate, expected_records


def fixture():
    from workflows.projected_release_v38 import predictor_binding
    manifest = {'models': {f+'__'+s: {'sha256': 'a'*64}
                for f in ('linear', 'nonlinear')
                for s in ['pooled'] + ['heldout-'+q['configuration'] for q in cases('preflight')]},
                'execution_sha256': {'synthetic_fixture_only': 'b'*64}}
    acceptance = dict(status='projected_formal_source_runtime_inventory_pullback_accepted',
        role='validation', source_commit='c'*40, freeze_sha256='d'*64,
        trace_sha256={q['run_id']: digest(q) for q in cases('validation')})
    rows = expected_records('validation')
    for r in rows:
        value = .5 if r['family'] == 'nonlinear' else 1.
        r.update(complete_aggregate=True, failed_origins=0, endpoint_rmse=[value]*4, path_rmse=[value]*4,
            trace_sha256=acceptance['trace_sha256'][r['run_id']],
            predictor_binding_sha256=predictor_binding(manifest, r['family'], r['scope'], r['configuration']))
    result = dict(status='completed_projected_formal_evaluation', role='validation',
        source_commit='c'*40, freeze_sha256='d'*64, model_manifest_digest=digest(manifest),
        acceptance_digest=digest(acceptance), scores_digest=digest(rows),
        evaluation=evaluate(rows, 'validation', bootstrap=True), model_fits=0, model_handoff=False)
    return manifest, acceptance, rows, result


def test_old_or_unbound_authorization_cannot_open_new_formal_scope():
    from workflows.projected_release_v38 import validate_authorization
    authorized = dict(schema='projected-formal-v38-new-D23', decision='approved', authorized_by='user',
        approval_reference='TEST FIXTURE ONLY; no real authorization', freeze_sha256='d'*64,
        resource_cap=protocol()['resource_cap'])
    validate_authorization(authorized, 'd'*64)
    for bad in ({}, dict(authorized, decision='pending'), dict(authorized, freeze_sha256='e'*64),
                dict(authorized, schema='old-v25-D23'), dict(authorized, approval_reference='')):
        with pytest.raises(ValueError):
            validate_authorization(bad, 'd'*64)


def test_test_release_recomputes_gate_and_binds_every_data_model_source():
    from workflows.projected_release_v38 import validate_validation_result
    m, a, rows, result = fixture()
    validate_validation_result(result, rows, m, a, 'c'*40, 'd'*64)
    for field, value in [('status', 'running'), ('role', 'test'), ('source_commit', 'e'*40),
                         ('freeze_sha256', 'e'*64), ('model_fits', True), ('evaluation', {'pass': True})]:
        with pytest.raises(ValueError):
            validate_validation_result(dict(result, **{field: value}), rows, m, a, 'c'*40, 'd'*64)
    for field in ('trace_sha256', 'predictor_binding_sha256'):
        bad = copy.deepcopy(rows)
        bad[0][field] = '0'*64
        changed = dict(result, scores_digest=digest(bad))
        with pytest.raises(ValueError):
            validate_validation_result(changed, bad, m, a, 'c'*40, 'd'*64)
    partial = dict(a, trace_sha256=dict(list(a['trace_sha256'].items())[:-1]))
    with pytest.raises(ValueError):
        validate_validation_result(dict(result, acceptance_digest=digest(partial)), rows, m, partial, 'c'*40, 'd'*64)


def test_claimed_go_cannot_override_recomputed_no_go():
    from workflows.projected_release_v38 import validate_validation_result
    m, a, rows, result = fixture()
    for r in rows:
        if r['family'] == 'nonlinear':
            r['endpoint_rmse'] = r['path_rmse'] = [2.]*4
    result['scores_digest'] = digest(rows)
    # Even an honestly updated NO_GO report must not release test.
    result['evaluation'] = evaluate(rows, 'validation', bootstrap=True)
    assert not result['evaluation']['pass']
    with pytest.raises(ValueError, match='validation_not_GO'):
        validate_validation_result(result, rows, m, a, 'c'*40, 'd'*64)


def test_collector_rejects_before_creating_output_or_importing_simulation(tmp_path):
    from workflows.collect_projected_formal_v38 import run_case
    from workflows.feedback_v31 import parameters
    with pytest.raises((ValueError, FileNotFoundError)):
        run_case(cases('test')[0], tmp_path/'output', 'a'*40, parameters())
    assert not (tmp_path/'output').exists()


def test_collector_and_validator_keep_qualified_physics_body_unchanged():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    def function(file, name):
        return next(n for n in ast.parse((root/'workflows'/file).read_text(encoding='utf8')).body
                    if isinstance(n, ast.FunctionDef) and n.name == name)
    old = function('collect_validation_v32.py', 'run_case')
    new = function('collect_projected_formal_v38.py', 'run_case')
    # Admission statements precede the shared policy-parameter assertion.
    def body_after_admission(node):
        index = next(i for i, stmt in enumerate(node.body)
                     if isinstance(stmt, ast.If) and 'feedback_parameters_binding' in ast.unparse(stmt))
        return [ast.dump(n) for n in node.body[index:]]
    assert body_after_admission(old) == body_after_admission(new)
    for name in ('validate_trace', 'validate_hydrodynamics', 'rejected_trace'):
        assert ast.dump(function('validate_identification_v32.py', name)) == ast.dump(
            function('validate_projected_formal_v38.py', name))


def test_snapshot_inspection_does_not_bypass_runtime_authorization(monkeypatch, tmp_path):
    import workflows.projected_release_v38 as module
    called=[]
    monkeypatch.setattr(module, 'verify_snapshot', lambda *args: called.append(1) or ({}, {}))
    (tmp_path/'freeze.json').write_text('{}')
    (tmp_path/'authorization.json').write_text('{"decision":"pending"}')
    with pytest.raises(ValueError,match='new_D23'):
        module.verify_bundle(tmp_path,tmp_path,'a'*40)
    assert not called


def test_recovered_ledger_cannot_use_an_unamended_freeze(tmp_path):
    import json
    from workflows.projected_release_v38 import verify_numeric_recovery
    (tmp_path/'budget.json').write_text(json.dumps({'numeric_recovery': {'schema': 'projected-v38-numeric-recovery'}}))
    with pytest.raises(ValueError, match='formal_numeric_recovery'):
        verify_numeric_recovery(tmp_path, {})


def test_aggregate_roundoff_does_not_change_go_or_case_counts():
    from workflows.projected_release_v38 import require_evaluation_agreement
    good = dict(pass_=True, rows=1152, values=[1., .01])
    require_evaluation_agreement(good, dict(good, values=[1.+1e-13, .01]))
    for bad in (dict(good, pass_=False), dict(good, rows=1152.), dict(good, values=[1.001, .01])):
        with pytest.raises(ValueError): require_evaluation_agreement(bad, good)


def test_repaired_validation_keeps_collection_identity_separate_from_analysis_identity():
    from workflows.projected_release_v38 import stage_identity
    frozen=dict(source_commit='a'*40)
    assert stage_identity(frozen,'validation','b'*64)==('a'*40,'b'*64)
    frozen.update(schema='projected-formal-v38-numeric-repair-before-scoring',
        validation_numeric_recovery_sha256='c'*64,validation_source_commit='d'*40,parent_freeze_sha256='e'*64)
    assert stage_identity(frozen,'validation','b'*64)==('d'*40,'e'*64)
    assert stage_identity(frozen,'test','b'*64)==('a'*40,'b'*64)
    for bad in (dict(frozen,validation_source_commit='bad'),dict(frozen,parent_freeze_sha256='b'*64),
                dict(frozen,schema='projected-formal-v38-before-any-new-data')):
        with pytest.raises(ValueError):stage_identity(bad,'validation','b'*64)


def test_validation_recovery_cannot_self_authorize_without_frozen_receipt(tmp_path):
    import json
    from workflows.projected_release_v38 import verify_validation_recovery
    (tmp_path/'budget.json').write_text(json.dumps({'validation_numeric_recovery':{}}))
    with pytest.raises(ValueError,match='formal_validation_recovery'):
        verify_validation_recovery(tmp_path,{})


def test_inherited_validation_reads_original_directory_without_links_or_copy(tmp_path,monkeypatch):
    import json
    from workflows import projected_release_v38 as module
    current=tmp_path/'current';current.mkdir()
    old=tmp_path/'preserved';old.mkdir()
    frozen=dict(schema='projected-formal-v38-numeric-repair-before-scoring',source_commit='a'*40,
        validation_numeric_recovery_sha256='b'*64,validation_source_commit='c'*40,parent_freeze_sha256='d'*64)
    (current/'freeze.json').write_text(json.dumps(frozen))
    monkeypatch.setattr(module,'VALIDATION_TRANSFER_ROOT',str(old))
    assert module.stage_directory(current,'validation')==old/'validation'
    assert module.stage_directory(current,'test')==current/'test'
    assert not (current/'validation').exists()

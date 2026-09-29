import copy
import json
from pathlib import Path

import pytest

from workflows.projected_protocol_v38 import cases
from workflows.projected_release_v38 import sha


def fixture_files(root, role='preflight'):
    """Synthetic file-admission fixture, not an independently accepted trace."""
    source = root/'source';transfer = root/'transfer'
    (source/'workflows').mkdir(parents=True)
    (source/'workflows/validate_projected_formal_v38.py').write_text('fixture only')
    (transfer/role).mkdir(parents=True)
    dump=lambda path,value:path.write_text(json.dumps(value),encoding='utf8')
    trace_hashes,semantic_hashes={},{}
    for q in cases(role):
        name=q['run_id'];d=transfer/role/name;d.mkdir()
        dump(d/'trace.json',{'fixture_only':True,'request':q})
        trace_hashes[name]=sha(d/'trace.json')
        dump(d/'collector-exit.json',dict(child_native_exit=0,guarded_collector_exit=0,trace_sha256=trace_hashes[name]))
        (transfer/role/(name+'.exit_status')).write_text('0\n')
        p=transfer/role/(name+'.validation.json')
        dump(p,dict(status='identification_semantics_passed',role=role,run_id=name,source_commit='a'*40,
            training_eligible=False,physics_ticks=2*q['intervals'],contact_ticks=0,impulse_ticks=0,rejected_ticks=0,
            tail={'eligible_for_excitation':True}))
        semantic_hashes[name]=sha(p)
    status=dict(status='projected_formal_stage_completed_pending_pullback',role=role,source_commit='a'*40,
        freeze_sha256='b'*64,accepted=list(trace_hashes),rejected=[],trace_sha256=trace_hashes)
    dump(transfer/role/'stage-status.json',status)
    (transfer/(role+'-evidence.tar.gz')).write_bytes(b'fixture archive bytes')
    acceptance=dict(status='projected_formal_source_runtime_inventory_pullback_accepted',role=role,
        source_commit='a'*40,freeze_sha256='b'*64,trace_sha256=trace_hashes,semantic_sha256=semantic_hashes,
        validator_sha256=sha(source/'workflows/validate_projected_formal_v38.py'),
        stage_status_sha256=sha(transfer/role/'stage-status.json'),archive_sha256=sha(transfer/(role+'-evidence.tar.gz')))
    dump(transfer/(role+'-pullback.json'),acceptance)
    return source,transfer,acceptance


def test_complete_files_then_modified_native_trace_or_source_are_rejected(tmp_path):
    from workflows.projected_release_v38 import verify_accepted_stage
    for changed in ('trace','exit','semantic','source','status'):
        source,transfer,acceptance=fixture_files(tmp_path/changed)
        verify_accepted_stage(source,transfer,'preflight','a'*40,'b'*64)
        name=cases('preflight')[0]['run_id']
        p={'trace':transfer/'preflight'/name/'trace.json',
           'exit':transfer/'preflight'/(name+'.exit_status'),
           'semantic':transfer/'preflight'/(name+'.validation.json'),
           'source':source/'workflows/validate_projected_formal_v38.py',
           'status':transfer/'preflight'/'stage-status.json'}[changed]
        p.write_text('1' if changed=='exit' else '{}')
        with pytest.raises((ValueError,KeyError)):
            verify_accepted_stage(source,transfer,'preflight','a'*40,'b'*64)


def test_archive_catalog_and_freeze_identity_do_not_accept_old_or_partial_roles():
    from workflows.projected_archive_v38 import validate_inventory_identity
    from workflows.projected_protocol_v38 import digest,protocol
    good=dict(schema='projected-formal-v38-archive',role='preflight',source_commit='a'*40,
              freeze_sha256='b'*64,protocol_digest=digest(protocol()),cases=cases('preflight'))
    validate_inventory_identity(good,'preflight','a'*40,'b'*64)
    for bad in (dict(good,role='validation'),dict(good,cases=good['cases'][:-1]),
                dict(good,freeze_sha256='c'*64),dict(good,protocol_digest='c'*64)):
        with pytest.raises(ValueError):validate_inventory_identity(bad,'preflight','a'*40,'b'*64)


def test_safe_archiver_refuses_existing_destination_and_pending_without_authorization(tmp_path):
    from workflows.projected_archive_v38 import archive_stage
    with pytest.raises((ValueError,FileNotFoundError)):
        archive_stage(tmp_path/'source',tmp_path/'transfer','preflight')
    assert not (tmp_path/'transfer/preflight-evidence.tar.gz').exists()


def test_pullback_accepts_small_recomputation_differences_and_records_them(tmp_path, monkeypatch):
    """Exercise the real summary comparison; other gates have separate tests.

    These are file fixtures, not Isaac or formal acceptance evidence.
    """
    from types import SimpleNamespace
    from workflows import projected_archive_v38 as archive
    source, transfer, _ = fixture_files(tmp_path)
    (transfer/'inputs').mkdir()
    (transfer/'inputs/freeze.json').write_text('{}')
    (transfer/'inventory.json').write_text(json.dumps({'source_commit': 'a'*40}))
    monkeypatch.setattr(archive, 'verify_raw', lambda *a: None)
    monkeypatch.setattr(archive, 'validate_inventory_identity', lambda *a: None)
    monkeypatch.setattr(archive, 'verify_bundle', lambda *a: None)
    monkeypatch.setattr(archive, '_running_code_matches', lambda *a: None)
    monkeypatch.setattr(archive, 'verify_runtime', lambda *a: {})
    monkeypatch.setattr(archive, 'guarded_exit_code', lambda *a: 0)
    # Keep real hashes for every per-case artifact and stage binding.
    original_sha = archive.sha
    monkeypatch.setattr(archive, 'sha', lambda p: 'b'*64 if Path(p).name == 'freeze.json'
                        else original_sha(source/'workflows/validate_projected_formal_v38.py')
                        if Path(p).name == 'validate_projected_formal_v38.py' else original_sha(p))
    local = {}
    for q in cases('preflight'):
        p = transfer/'preflight'/(q['run_id']+'.validation.json')
        server = json.loads(p.read_text())
        server['maximum_motion'] = {'tilt_rad': 0.03934519317209799}
        server['maximum_control_pwm_speed_wrench_errors'] = [0., 1.043081283569336e-7,
            3.8537464185139925e-5, 7.6038059884098175e-6]
        p.write_text(json.dumps(server))
        local[q['run_id']] = copy.deepcopy(server)
        local[q['run_id']]['maximum_motion']['tilt_rad'] = 0.03934519317209798
        local[q['run_id']]['maximum_control_pwm_speed_wrench_errors'] = [0., 8.940696716308594e-8,
            4.405441819699263e-5, 9.09126563364282e-6]
    monkeypatch.setattr(archive, 'load_episode', lambda path, q, *a:
                        SimpleNamespace(acceptance=local[q['run_id']]))
    result = archive.audit_raw(transfer, 'preflight', 'c'*64)
    assert result['status'].endswith('pullback_accepted')
    assert len(result['semantic_recomputation']) == 8
    for record in result['semantic_recomputation'].values():
        assert record['policy'] == 'semantic-numeric-agreement-v1'
        assert len(record['differences']) == 4
        assert all(d['absolute_difference'] <= d['allowed_difference'] for d in record['differences'])


@pytest.mark.parametrize('change', [
    {'physics_ticks': 513}, {'physics_ticks': 512.0}, {'training_eligible': 0},
    {'source_commit': 'b'*40}, {'status': 'rejected'},
    {'maximum_motion': {'tilt_rad': .04}},
    {'maximum_control_pwm_speed_wrench_errors': [0., 0., 1.5e-4, 0.]},
    {'maximum_control_pwm_speed_wrench_errors': [0., 2e-7, 4e-5, 0.]},
    {'maximum_control_pwm_speed_wrench_errors': [0., 0., 4e-5]},
    {'tail': {'limits': {'tilt_rad': .5000000000000001}}},
    {'new_numeric_field': 0.},
])
def test_semantic_tolerance_keeps_identity_shape_limits_and_large_errors_strict(change):
    from workflows.projected_archive_v38 import compare_semantic_summaries
    good = dict(status='identification_semantics_passed', physics_ticks=512,
        training_eligible=False, source_commit='a'*40,
        maximum_motion={'tilt_rad': .03934519317209799},
        maximum_control_pwm_speed_wrench_errors=[0., 0., 4e-5, 0.],
        tail={'limits': {'tilt_rad': .5}})
    with pytest.raises(ValueError, match='formal_pullback_semantic_recomputation'):
        compare_semantic_summaries(dict(good, **change), good)


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf')])
def test_identical_nonfinite_summaries_cannot_pass(bad):
    from workflows.projected_archive_v38 import compare_semantic_summaries
    for summary in ({'maximum_motion': {'tilt_rad': bad}}, {'unlisted_value': bad}):
        with pytest.raises(ValueError, match='formal_pullback_semantic_recomputation'):
            compare_semantic_summaries(summary, summary)


@pytest.mark.parametrize('bad', [-1e-8, 1.001e-3])
def test_tolerance_never_extends_original_causal_error_limit(bad):
    from workflows.projected_archive_v38 import compare_semantic_summaries
    summary = {'maximum_control_pwm_speed_wrench_errors': [0., 0., bad, 0.]}
    with pytest.raises(ValueError, match='formal_pullback_semantic_recomputation'):
        compare_semantic_summaries(summary, summary)


def test_summary_agreement_is_symmetric_and_unknown_values_remain_exact():
    from workflows.projected_archive_v38 import compare_semantic_summaries
    a = {'maximum_motion': {'tilt_rad': .04}, 'unknown': .04}
    b = {'maximum_motion': {'tilt_rad': .04+1e-12}, 'unknown': .04}
    assert len(compare_semantic_summaries(a, b)['differences']) == 1
    assert len(compare_semantic_summaries(b, a)['differences']) == 1
    b['unknown'] += 1e-12
    with pytest.raises(ValueError, match='formal_pullback_semantic_recomputation'):
        compare_semantic_summaries(a, b)


def test_residual_summary_uses_the_same_bound_as_pointwise_rotor_reconstruction():
    """The infinity norm of a residual is 1-Lipschitz in reconstructed speed.

    A 1e-4 pointwise cross-host allowance cannot consistently require its
    maximum-error summary to agree within 1e-5. Neither is a prediction gate.
    """
    from workflows.projected_archive_v38 import compare_semantic_summaries
    server = {'maximum_control_pwm_speed_wrench_errors': [0., 0., 3.4628240229039875e-5, 0.]}
    local = {'maximum_control_pwm_speed_wrench_errors': [0., 0., 4.630750846246201e-5, 0.]}
    result = compare_semantic_summaries(server, local)
    assert result['differences'][0]['allowed_difference'] == 1e-4
    # The shared bound must remain below the unchanged physical rejection bound.
    too_far = {'maximum_control_pwm_speed_wrench_errors': [0., 0., 2e-4, 0.]}
    with pytest.raises(ValueError, match='formal_pullback_semantic_recomputation'):
        compare_semantic_summaries(server, too_far)


def test_explicit_auditor_revision_allows_only_review_and_operation_files(tmp_path, monkeypatch):
    from workflows import projected_archive_v38 as archive
    old, new = tmp_path/'old', tmp_path/'new'
    for base, text in ((old, 'old'), (new, 'repaired')):
        (base/'workflows').mkdir(parents=True)
        (base/'workflows/projected_archive_v38.py').write_text(text)
        (base/'workflows/validate_projected_formal_v38.py').write_text('unchanged physics')
        files={p.relative_to(base).as_posix():sha(p) for p in base.rglob('*.py')}
        (base/'SOURCE_MANIFEST.json').write_text(json.dumps({'files_sha256':files}))
    monkeypatch.setattr(archive, '__file__', str(new/'workflows/projected_archive_v38.py'))
    revision=dict(schema='projected-v38-auditor-revision', parent_source_commit='a'*40,
        parent_freeze_sha256='b'*64, auditor_source_commit='c'*40,
        parent_source_manifest_sha256=sha(old/'SOURCE_MANIFEST.json'),
        auditor_source_manifest_sha256=sha(new/'SOURCE_MANIFEST.json'))
    with pytest.raises(ValueError): archive._running_code_matches(old)
    archive._running_code_matches(old, revision)
    (new/'workflows/validate_projected_formal_v38.py').write_text('changed physics')
    files=json.loads((new/'SOURCE_MANIFEST.json').read_text())
    files['files_sha256']['workflows/validate_projected_formal_v38.py']=sha(new/'workflows/validate_projected_formal_v38.py')
    (new/'SOURCE_MANIFEST.json').write_text(json.dumps(files))
    revision['auditor_source_manifest_sha256']=sha(new/'SOURCE_MANIFEST.json')
    with pytest.raises(ValueError, match='formal_auditor_revision'):
        archive._running_code_matches(old, revision)

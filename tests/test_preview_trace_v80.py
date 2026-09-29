"""Development fixtures from old traces, never new v80 physics evidence."""
import copy
import gzip
import json
import os
from dataclasses import asdict
from pathlib import Path
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def assets():
    if os.environ.get('EASYUUV_V80_TEST_ASSETS'):
        from workflows.runtime_assets_v56 import AssetLocation, load_assets
        return load_assets(AssetLocation(os.environ['EASYUUV_V80_TEST_ASSETS'],'.','assets/v38/inputs',
            '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    from workflows.diagnose_separation_v79 import prepare
    return prepare(ROOT)[1]


@pytest.fixture(scope='module')
def legacy_traces():
    report = json.loads((ROOT/'docs/evidence/phase9/common-profile-v78-20260924/common-report.json').read_text())
    result = {}
    for kind in ('feedback', 'projected_koopman'):
        row = next(r for r in report['main_rows'] if r['configuration']=='base' and r['controller']==kind)
        result[kind] = json.loads(gzip.decompress((ROOT/row['path'].replace('\\','/')/'trace.json.gz').read_bytes()))
    return result


def converted(legacy_traces, kind='feedback'):
    from workflows.protocol_v80 import case_spec
    from workflows.protocol_v77 import settings
    old_kind = 'feedback' if kind=='feedback' else 'projected_koopman'
    d = copy.deepcopy(legacy_traces[old_kind])
    d['schema'] = 'preview-control-v80'
    d['case'] = case_spec('base', kind, False, 'pitch_pos')
    d['completed_controls'] = len(d['intervals'])
    from koopman.feedback_preview_v79 import audit_observed_pwm
    d['backend_audit']=[]
    for index in range(0,240,4):
        cmd=d['substeps'][index]['command']
        raw=cmd['_last_motor_values_raw'][0];pwm=cmd['telemetry']['motor_pwm_n'][0]
        d['backend_audit'].append(dict(physics_index=index,
            command=copy.deepcopy(cmd['telemetry']['virtual_control_4'][0]),
            pwm_raw=copy.deepcopy(raw),pwm=copy.deepcopy(pwm),**audit_observed_pwm(raw,pwm)))
    d['model'].update(kind=kind, horizon_macro_steps=20,
        weights=asdict(settings('depth4_h20')['weights']),
        pwm_planning_margin=3e-6, pwm_optimizer_margin=4e-6,
        model_identity=dict(kind=kind, symbolic_proxy=None if kind=='feedback' else 'projected_koopman',
                            unique_koopman_representation_claimed=False))
    return d


def mpc_development_fixture(legacy_traces):
    """Add synthetic decision provenance only for exercising validator behavior."""
    d = converted(legacy_traces, 'structured_projected')
    previous_plan = None
    for a in d['solve_audit']:
        i = a['physics_index']
        feedback = next(f['result'] for f in d['feedback_audit'] if f['physics_index']==i)
        previous = d['substeps'][i-1]['command']['telemetry']['virtual_control_4'][0]
        held = np.tile(feedback['command'] if feedback['status']=='ready' else previous, (20, 1))
        plans = {'held':held}
        if previous_plan is not None:
            plans['warm'] = np.vstack([previous_plan[1:], previous_plan[-1]])
        if a['status'] in ('optimized', 'recovered', 'initialization_retained'):
            plans['worker'] = np.array(a['commands'])
            chosen = 'worker'; returned = True
        else:
            chosen = 'warm' if a['status']=='warm_retained' else 'held'; returned = False
            a.update(status='solver_failure_retained', worker_status='no_plan', worker_reason='fixture_failure')
        seed = 'warm' if a['warm_start_used'] else 'held'
        a.update(origin_control=i//2, reference=d['case']['reference'], preview_enabled=False,
            preview=dict(status='disabled',reason='disabled_by_protocol'),
            selection_plans=plans, required_references=list(plans), selected_reference=chosen,
            worker_returned_commands=returned, initialization_source=seed,
            initialization_kind=a.get('initialization_kind', seed))
        previous_plan = np.array(a['commands'])
    return d


def test_nonzero_native_exit_fails_before_other_fields():
    from workflows.validate_preview_v80 import validate
    with pytest.raises(ValueError, match='native_or_status'):
        validate({}, None, 139)


def test_converted_feedback_exercises_full_clock_mechanics_receipt_replay(legacy_traces, assets):
    from workflows.validate_preview_v80 import validate
    result = validate(converted(legacy_traces), assets, 0)
    assert result['physics_steps']==240 and result['actual_pwm_checks']==240
    assert result['decision_audits']==0


@pytest.mark.parametrize('field', ['kind','symbolic_proxy','unique_koopman_representation_claimed'])
def test_model_identity_mismatch_rejected(legacy_traces, assets, field):
    from workflows.validate_preview_v80 import validate
    d = converted(legacy_traces)
    d['model']['model_identity'][field] = 'incorrect'
    with pytest.raises(ValueError, match='model_identity'):
        validate(d, assets, 0)


def test_actual_pwm_gate_cannot_be_replaced_by_cpu_replay_tolerance(legacy_traces, assets):
    from workflows.validate_preview_v80 import validate
    d = converted(legacy_traces)
    v = float(np.float32(.02))-1.99e-6
    d['substeps'][0]['command']['_last_motor_values_raw'][0][0] = v
    d['substeps'][0]['command']['telemetry']['motor_pwm_n'][0][0] = v
    with pytest.raises(ValueError, match='observed_pwm_deadzone_margin'):
        validate(d, assets, 0)


def test_plan_first_action_must_equal_dispatched_command(legacy_traces, assets):
    from workflows.validate_preview_v80 import validate
    d = mpc_development_fixture(legacy_traces)
    d['solve_audit'][0]['commands'][0][0] += .005
    with pytest.raises(ValueError, match='first_plan_action'):
        validate(d, assets, 0)


@pytest.mark.parametrize('name,index', [('held',0),('preview',0),('warm',1)])
def test_missing_causal_reference_rejected_in_full_replay(legacy_traces, assets, monkeypatch, name, index):
    import workflows.validate_preview_v80 as module
    from koopman.feedback_preview_v79 import ExactChecker as LegacyMarginChecker
    # Old v78 plans used 2e-6. This test isolates inventory logic on those old
    # plans; the production 3e-6 checker is separately exercised below.
    monkeypatch.setattr(module, 'ExactChecker', LegacyMarginChecker)
    d = mpc_development_fixture(legacy_traces)
    a = d['solve_audit'][index]
    if name=='preview':
        d['case']['preview_enabled']=True
        a['preview_enabled']=True
        a['preview']['status']='ready'
    else:
        del a['selection_plans'][name]
    with pytest.raises(ValueError, match='reference_inventory'):
        module.validate(d, assets, 0)


def test_old_2e6_plan_is_not_admitted_as_new_3e6_plan(legacy_traces, assets):
    from workflows.validate_preview_v80 import validate
    d = mpc_development_fixture(legacy_traces)
    with pytest.raises(ValueError, match='selected_infeasible'):
        validate(d, assets, 0)


def test_feedback_log_state_is_bound_to_actual_state(legacy_traces, assets):
    from workflows.validate_preview_v80 import validate
    d = converted(legacy_traces)
    d['feedback_audit'][0]['state'][0] += .1
    with pytest.raises(ValueError, match='feedback_state'):
        validate(d, assets, 0)


@pytest.mark.parametrize('mutation,reason', [
    ('digest','history_digest'), ('clock','clock'), ('cleanup','native_cleanup'),
    ('mechanics','context'), ('metric','depth_metric'), ('preview','feedback_preview')])
def test_original_physics_and_new_case_gates_remain_active(legacy_traces, assets, mutation, reason):
    from workflows.validate_preview_v80 import validate
    d=converted(legacy_traces)
    if mutation=='digest':d['substeps'][0]['execution_ack_v55']['receipt']['history_digest']='0'*64
    elif mutation=='clock':d['substeps'][0]['backend_after_physics']['cache_sim_timestamp_s']+=.1
    elif mutation=='cleanup':d['cleanup_completed']['environment']=False
    elif mutation=='mechanics':d['substeps'][0]['command']['telemetry']['mass_kg'][0][0]+=.1
    elif mutation=='metric':d['metrics']['depth_rmse_m']+=.1
    elif mutation=='preview':d['case']['preview_enabled']=True
    with pytest.raises(ValueError, match=reason):
        validate(d, assets, 0)


@pytest.mark.parametrize('mutation,reason', [('delete','backend_audit_indices'),
    ('duplicate','backend_audit_indices'),('command','backend_command'),
    ('pwm','backend_raw_pwm'),('flag','backend_gate_record')])
def test_backend_allocation_is_bound_to_all_four_actual_substeps(legacy_traces, assets, mutation, reason):
    from workflows.validate_preview_v80 import validate
    from koopman.feedback_preview_v79 import audit_observed_pwm
    d=converted(legacy_traces)
    b=d['backend_audit'][0]
    if mutation=='delete':d['backend_audit'].pop()
    elif mutation=='duplicate':d['backend_audit'].append(copy.deepcopy(b))
    elif mutation=='command':b['command'][0]+=.01
    elif mutation=='flag':b['accepted']=False
    elif mutation=='pwm':
        b['pwm_raw'][0]+=.001;b['pwm'][0]+=.001
        b.update(audit_observed_pwm(b['pwm_raw'],b['pwm']))
    with pytest.raises(ValueError, match=reason):
        validate(d, assets, 0)

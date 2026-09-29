"""The regression wrapper must never discard a verified feasible incumbent."""
import importlib
import json
import numpy as np
import pytest


def api():
    return importlib.import_module('workflows.solver_regression_v84')


class Checker:
    horizon = 20

    def check(self, origin, state, commands, previous, reference):
        value = float(np.asarray(commands)[0, 0])
        valid = value >= 0
        return dict(feasible=valid, cost=value if valid else None,
                    reason=None if valid else 'predicted_state_out_of_support',
                    predictions=np.zeros((80, 11)) if valid else None)


def select(candidate=None, status='solver_timeout', incumbent=.3):
    return api().select_verified_plan(Checker(), None, np.zeros(11), np.zeros(4),
        np.zeros(5), {'recorded_physics': np.full((20, 4), incumbent)},
        candidate=candidate, worker_status=status)


def test_timeout_retains_feasible_incumbent():
    result = select()
    assert result['exact_feasible'] and result['selected_source'] == 'recorded_physics'
    assert result['cost'] == pytest.approx(.3)
    assert result['worker_status'] == 'solver_timeout'
    assert result['nlp_return_missed_known_feasible'] is True


def test_infeasible_or_worse_solver_solution_cannot_replace_incumbent():
    for proposed in (-.1, .4):
        result = select(np.full((20, 4), proposed), 'success')
        assert result['selected_source'] == 'recorded_physics'
        assert result['cost'] == pytest.approx(.3)


def test_solver_success_flag_and_reported_cost_are_not_selection_inputs():
    result = select(np.full((20, 4), .1), 'Maximum_Iterations_Exceeded')
    assert result['selected_source'] == 'new_nlp_plan'
    assert result['cost'] == pytest.approx(.1)
    assert result['improvement_over_best_recorded'] == pytest.approx(.2)
    assert not result['global_optimum_claimed']
    assert not result['closed_loop_benefit_claimed']


def test_all_recorded_plans_are_checked_with_each_models_own_cost():
    a = api()
    plans = {'recorded_physics': np.full((20, 4), .3), 'old_learning': np.full((20, 4), .05)}
    r = a.select_verified_plan(Checker(), None, np.zeros(11), np.zeros(4), np.zeros(5), plans,
                              candidate=np.full((20, 4), .1), worker_status='success')
    assert r['selected_source'] == r['best_recorded_source'] == 'old_learning'
    assert r['known_feasible_plan_missed'] is False
    assert r['nlp_return_missed_known_feasible'] is True


@pytest.mark.parametrize('candidate', [np.zeros((1, 4)), np.full((20, 4), np.nan)])
def test_malformed_child_output_cannot_displace_incumbent(candidate):
    result = select(candidate, 'success')
    assert result['selected_source'] == 'recorded_physics'
    assert result['checks']['new_nlp_plan']['reason'] == 'full_plan_invalid'


def test_infeasible_incumbent_does_not_block_valid_new_plan():
    result = select(np.full((20, 4), .1), 'success', incumbent=-.2)
    assert result['exact_feasible']
    assert result['selected_source'] == 'new_nlp_plan'
    assert result['best_recorded_cost'] is None


def test_no_feasible_plan_is_not_success():
    result = select(incumbent=-.2)
    assert result['exact_feasible'] is False
    assert result['commands'] is None and result['cost'] is None


def test_positive_residual_reports_violation_without_unit_aggregation_claim():
    a = api()
    assert a.bound_violation([1, 3], [0, 0], [2, 2]) == 1
    assert a.bound_violation([1, 1], [0, 0], [2, 2]) == 0


def test_budget_reserves_cleanup_and_never_starts_after_deadline():
    a = api()
    assert a.child_timeout(0, 600) == 75
    assert a.child_timeout(570, 600) == 10
    assert a.child_timeout(581, 600) is None


def test_relative_parent_identities_match_absolute_worker_after_json_roundtrip(tmp_path, monkeypatch):
    a = api()
    monkeypatch.chdir(tmp_path)
    file = tmp_path/'models'/'pooled__Rc_0.001.json'
    parent = a.canonical_identity_map({'models/pooled__Rc_0.001.json': 'a'*64})
    assert list(parent) == [str(file.resolve())]
    request = json.loads(json.dumps(dict(expected_identities=parent,
        expected_support_model='b'*64, expected_support_id='c'*64)))
    group = dict(identities={str(file.resolve()): 'a'*64},
                 common_support_model_sha256='b'*64, common_support_id='c'*64)
    a.verify_request_binding(group, request)
    group['common_support_id'] = 'd'*64
    with pytest.raises(ValueError, match='support_id'):
        a.verify_request_binding(group, request)


def test_alias_paths_cannot_hide_conflicting_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match='identity_alias'):
        api().canonical_identity_map({'model.json': 'a'*64, str(tmp_path/'model.json'): 'b'*64})


def test_zero_nlp_outputs_reports_failed_even_when_fallback_is_feasible():
    entries = [dict(child=None, receipt=dict(native_exit=1, group_stopped=True),
                    selection=dict(exact_feasible=True)) for _ in range(6)]
    summary = api().summarize_solver_outcomes(entries)
    assert summary['status'] == 'failed_all_workers_before_nlp'
    assert summary['nlp_attempted'] == 0
    assert summary['worker_failures'] == 6
    assert summary['preserved_feasible_plans'] == 6


def test_success_and_nonconvergence_are_separate_outcomes():
    good = dict(child=dict(solver=dict(success=True), commands=np.zeros((20, 4)).tolist()),
                receipt=dict(native_exit=0, group_stopped=True), selection=dict(exact_feasible=True))
    entries = [good for _ in range(6)]
    assert api().summarize_solver_outcomes(entries)['status'] == 'completed_offline_regression_not_control_benefit'
    bad = dict(good, child=dict(solver=dict(success=False), commands=np.zeros((20, 4)).tolist()))
    assert api().summarize_solver_outcomes([good]*5+[bad])['status'] == 'completed_with_unconverged_nlp'

"""Offline decision-audit contracts; these are not Isaac acceptance tests."""
from types import SimpleNamespace
import numpy as np
import pytest


class Checker:
    horizon = 2
    mask = np.ones(4)
    domain = SimpleNamespace(command_lower=np.full(4, -.95), command_upper=np.full(4, .95))

    def check(self, origin, state, commands, previous, reference):
        a = np.asarray(commands, dtype=np.float32)
        return dict(feasible=True, reason=None, cost=float(np.sum(a.astype(float)**2)),
                    predictions=np.tile(np.asarray(state), (len(a)*4, 1)))

    def deadzone_flat(self, commands):
        return False


def fixture(*, enabled=True, reply='timeout'):
    from koopman.preview_mpc_v79 import PreviewMPC
    checker = Checker()
    class Feedback:
        def decide(self, state, reference, *, previous):
            return dict(status='ready', command=np.full(4, .01))
    class Worker:
        def call(self, request):
            if reply == 'optimized':
                return dict(status='optimized', reason=None, commands=np.zeros((2, 4)))
            if reply == 'baseline_retained':
                return dict(status='baseline_retained', reason=None, commands=request['initial_guess'])
            return dict(status='no_plan', reason='solver_timeout', commands=None)
    solver = PreviewMPC(checker, Worker(), Feedback, preview_enabled=enabled)
    state = np.r_[5.5, 1., np.zeros(9)]
    ref = state[:5]
    origin = SimpleNamespace(origin_control=4)
    prior = dict(origin_control=2, reference=ref.copy(), commands=np.full((2, 4), .02))
    solver._last = dict(origin=2, reference=ref.copy(), commands=prior['commands'].copy())
    feedback = dict(status='ready', command=np.full(4, .03))
    decision = solver.solve(origin=origin, initial_state=state,
        baseline=np.tile(feedback['command'], (2, 1)), previous=np.full(4, .02), reference=ref)
    return dict(checker=checker, origin=origin, state=state, previous=np.full(4, .02),
                reference=ref, feedback_result=feedback, prior_decision=prior,
                decision=decision, feedback_factory=Feedback)


def audit(args):
    from workflows.validate_preview_decision_v79 import audit_decision
    return audit_decision(**args)


def test_timeout_may_retain_causal_preview():
    args = fixture()
    assert args['decision']['selected_reference'] == 'preview'
    assert args['decision']['status'] == 'timeout_retained'
    result = audit(args)
    assert result['accepted'] and result['required_references'] == ['held', 'warm', 'preview']
    assert result['scope'] == 'offline_single_decision'


@pytest.mark.parametrize('name', ['held', 'warm', 'preview'])
def test_missing_required_reference_is_rejected(name):
    args = fixture()
    del args['decision']['selection_plans'][name]
    with pytest.raises(ValueError, match='reference_inventory'):
        audit(args)


@pytest.mark.parametrize('name', ['held', 'warm', 'preview'])
def test_changed_causal_reference_is_rejected(name):
    args = fixture()
    args['decision']['selection_plans'][name] = np.zeros((2, 4))
    with pytest.raises(ValueError, match='causal_' + name):
        audit(args)


def test_short_selected_plan_cannot_use_broadcasting_to_pass():
    args = fixture()
    args['decision']['commands'] = args['decision']['commands'][:1]
    with pytest.raises(ValueError, match='selected_shape'):
        audit(args)


def test_recorded_low_cost_cannot_hide_dominated_selection():
    args = fixture()
    d = args['decision']
    d.update(commands=d['selection_plans']['held'].copy(), selected_reference='held', cost=-100.)
    with pytest.raises(ValueError, match='dominated_selection'):
        audit(args)


def test_forged_status_and_worker_inventory_are_rejected():
    args = fixture()
    args['decision']['status'] = 'optimized'
    with pytest.raises(ValueError, match='selection_status'):
        audit(args)
    args = fixture()
    args['decision']['worker_returned_commands'] = True
    with pytest.raises(ValueError, match='reference_inventory'):
        audit(args)
    args = fixture()
    args['decision']['worker_status'] = 'optimized'
    with pytest.raises(ValueError, match='worker_status'):
        audit(args)


def test_preview_requires_independent_replay_factory():
    args = fixture()
    args['feedback_factory'] = None
    with pytest.raises(ValueError, match='preview_replay_factory'):
        audit(args)


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('reply', ['optimized', 'baseline_retained'])
def test_successful_worker_and_disabled_preview_are_admitted(enabled, reply):
    args = fixture(enabled=enabled, reply=reply)
    result = audit(args)
    assert result['accepted'] and result['preview_replayed'] == enabled
    assert 'worker' in result['required_references']


def test_physical_ramp_provenance_and_retained_worker():
    from koopman.preview_mpc_v79 import PreviewMPC
    class TargetChecker(Checker):
        def check(self, origin, state, commands, previous, reference):
            result = super().check(origin, state, commands, previous, reference)
            result['cost'] = float(np.sum((np.asarray(commands, dtype=np.float32).astype(float)-.03)**2))
            return result
        def deadzone_flat(self, commands):
            return True
    class Worker:
        def call(self, request):
            return dict(status='baseline_retained', reason=None, commands=request['initial_guess'])
    checker = TargetChecker()
    solver = PreviewMPC(checker, Worker(), None, preview_enabled=False)
    state = np.r_[5.5, 1., np.zeros(9)]
    origin = SimpleNamespace(origin_control=2)
    feedback = dict(status='ready', command=np.zeros(4), static_command=np.full(4, .05))
    decision = solver.solve(origin=origin, initial_state=state, baseline=np.zeros((2, 4)),
        previous=np.zeros(4), reference=state[:5], physical_target=feedback['static_command'])
    args = dict(checker=checker, origin=origin, state=state, previous=np.zeros(4),
                reference=state[:5], feedback_result=feedback, prior_decision=None, decision=decision)
    assert decision['status'] == 'initialization_retained'
    assert audit(args)['accepted']
    decision['initialization_source'] = 'preview'
    with pytest.raises(ValueError, match='initialization_source'):
        audit(args)

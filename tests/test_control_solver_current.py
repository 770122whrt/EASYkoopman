"""Consolidated controller behavior against the frozen predecessor implementations."""
import ast
import importlib.util
from pathlib import Path

import numpy as np
import pytest


def current():
    assert importlib.util.find_spec('koopman.control_solver'), 'consolidated controller missing'
    from koopman import control_solver
    return control_solver


@pytest.mark.parametrize('kind', ['physics', 'koopman', 'hybrid'])
def test_three_models_keep_same_predictions_and_exact_admission(kind):
    new = current()
    from koopman import preview_solver_v87 as old
    from koopman.bounded_mpc_v44 import SupportDomain
    from koopman.command_state_v39 import CausalCommandState
    from workflows.disturbance_data_v88 import ROOT, MODEL_PATH, MODEL_SHA256, context
    c = context()
    loaded = new.load_model(ROOT / MODEL_PATH, MODEL_SHA256)
    domain = SupportDomain.diagnostic('base', c, model_id='9' * 64)
    before = old.make_predictor(kind, loaded, c)
    after = new.make_predictor(kind, loaded, c)
    live = CausalCommandState('base', c, episode_id='consolidation', zero_rotor_reset_verified=True)
    command = np.array([0., 0., 0., .03])
    for i in range(16):
        live.record_issued(command, physics_index=i, episode_id='consolidation')
    origin = live.snapshot(configuration='base', context=c, origin_control=8, episode_id='consolidation')
    state = np.array([5.5, 1., 0., 0., 0., 0., 0., 0., 0., 0., 0.])
    reference = state[:5].copy()
    a = old.ExactChecker(domain, before, horizon=4)
    b = new.ExactChecker(domain, after, horizon=4)
    for controls in (np.tile(command, (4, 1)), np.zeros((4, 4)), np.full((4, 4), .9)):
        x = a.check(origin, state, controls, command, reference)
        y = b.check(origin, state, controls, command, reference)
        assert (x['feasible'], x['reason'], x['cost']) == (y['feasible'], y['reason'], y['cost'])
        if x['predictions'] is not None:
            np.testing.assert_array_equal(x['predictions'], y['predictions'])
    assert live.physics_index == 16
    assert new.model_identity(loaded, kind) == old.model_identity(loaded, kind)


def test_current_solver_owns_merged_classes_without_predecessor_inheritance():
    m = current()
    for name in ('ExactChecker', 'ProcessTransport', 'PreviewMPC'):
        cls = getattr(m, name)
        assert cls.__module__ == 'koopman.control_solver'
        assert cls.__bases__ == (object,)
    forbidden = {'koopman.preview_solver_v87', 'koopman.preview_solver_v80',
                 'koopman.preview_mpc_v79', 'koopman.feedback_preview_v79', 'koopman.reliable_mpc_v77'}
    tree = ast.parse(Path(m.__file__).read_text(encoding='utf8'))
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & forbidden


def test_final_worker_constructs_final_mpc():
    m = current()
    import inspect
    source = inspect.getsource(m._Engine.__init__)
    assert 'from koopman.continuous_mpc import ContinuousMPC' in source
    assert 'continuous_mpc_v' not in source


@pytest.mark.parametrize('preview', [False, True])
@pytest.mark.parametrize('reply', ['optimized', 'timeout', 'invalid', 'baseline_retained'])
def test_selection_and_failed_worker_keep_previous_semantics(preview, reply):
    from types import SimpleNamespace
    from koopman.preview_mpc_v79 import PreviewMPC as Historical
    from workflows.validate_preview_decision_v79 import audit_decision
    Current = current().PreviewMPC

    class Checker:
        horizon = 2
        mask = np.ones(4)
        def check(self, origin, state, commands, previous, reference):
            a = np.asarray(commands, dtype=np.float32)
            ok = bool(np.max(abs(a)) < .5)
            return dict(feasible=ok, reason=None if ok else 'support',
                        cost=float(np.sum(a.astype(float)**2)) if ok else None,
                        predictions=np.tile(state, (len(a)*4, 1)) if ok else None)
        def deadzone_flat(self, commands):
            return False
    class Feedback:
        def decide(self, state, reference, *, previous):
            return dict(status='ready', command=np.full(4, .01))
    class Worker:
        def call(self, request):
            if reply == 'timeout':
                return dict(status='no_plan', reason='solver_timeout', commands=None,
                            candidate_commands=None, solver={'return_status': 'Maximum_CpuTime_Exceeded'})
            commands = (np.ones((2, 4)) if reply == 'invalid' else
                        request['initial_guess'] if reply == 'baseline_retained' else np.zeros((2, 4)))
            return dict(status=reply, reason=None, commands=commands,
                        candidate_commands=commands, solver={'return_status': 'Solve_Succeeded'})
    x = np.r_[5.5, 1., np.zeros(9)]
    reference = x[:5]
    origin = SimpleNamespace(origin_control=4)
    args = dict(origin=origin, initial_state=x, previous=np.full(4, .02),
                baseline=np.full((2, 4), .03), reference=reference)
    answers = []
    for cls in (Historical, Current):
        checker = Checker()
        solver = cls(checker, Worker(), Feedback, preview_enabled=preview)
        solver._last = dict(origin=2, reference=reference.copy(), commands=np.full((2, 4), .02))
        answer = solver.solve(**args)
        answers.append(answer)
        if reply != 'invalid':
            audit = audit_decision(checker=checker, origin=origin, state=x,
                previous=args['previous'], reference=reference,
                feedback_result=dict(status='ready', command=np.full(4, .03)),
                prior_decision=dict(origin_control=2, reference=reference.copy(), commands=np.full((2, 4), .02)),
                decision=answer, feedback_factory=Feedback)
            assert audit['accepted']
        else:
            assert answer['reason'] == 'worker_plan_failed_exact_check'
    for key in ('status', 'reason', 'selected_reference', 'required_references', 'selection_audit', 'solver'):
        assert answers[0].get(key) == answers[1].get(key)
    np.testing.assert_array_equal(answers[0]['commands'], answers[1]['commands'])


class EchoEngine:
    """Exercise the actual owned process/pipe lifecycle, without an NLP."""
    def __init__(self, spec):
        pass
    def __call__(self, request):
        import os
        return dict(value=request['value'], pid=os.getpid())


def test_current_transport_owns_and_closes_a_real_child_process():
    import os
    m = current()
    transport = m.ProcessTransport({}, engine_factory=EchoEngine)
    try:
        result = transport.call({'value': 17})
        assert result['value'] == 17 and result['pid'] != os.getpid()
    finally:
        closed = transport.close()
    assert closed['process_stopped'] and closed['io_threads_stopped']

"""30Hz callback sequencing against the archived loop; not Isaac evidence."""
import itertools

import numpy as np
import pytest
import torch

import test_isaac_execution_v55 as legacy
from test_bounded_feedback_v46 import initial
from test_prepared_projected_v40 import context
from test_plan_arbiter_v52 import Clock


@pytest.fixture
def routed_control(monkeypatch):
    """Exercise the process routing and restore it after every test."""
    from easyuuv_nc import control_v24
    from easyuuv_nc.control_v67 import install_control_clock
    for name in ('begin_interval', 'direct_pwm', 'reset_direct'):
        original = getattr(control_v24, name)
        monkeypatch.setattr(control_v24, name, original)
    install_control_clock()
    for name in ('begin_interval', 'direct_pwm', 'reset_direct'):
        monkeypatch.setattr(legacy, name, getattr(control_v24, name))
    return control_v24


class FourStepFixture(legacy.FixtureEnv):
    def __init__(self, configuration='base'):
        super().__init__(configuration)
        self.cfg.decimation = 4
        self.cfg.control_rate_hz_v67 = 30
        self.fail_third_contact = False

    def _physics_step(self, *, render):
        super()._physics_step(render=render)
        if self.fail_third_contact and self.physics_steps == 3:
            self.force = 1.


@pytest.fixture
def bridge30(monkeypatch, routed_control):
    sessions = []

    def create(configuration='base'):
        from koopman.bounded_mpc_v44 import SupportDomain
        from koopman.bounded_feedback_v46 import FeedbackConfig
        from koopman.cached_checks_v53 import CachedTrackingFeedback
        from koopman.execution_ledger_v48 import ResetObservation
        from koopman.rate30_v67 import ExecutionLedger, RuntimeCoordinator
        from workflows.isaac_execution_v67 import IsaacExecutionSession
        from workflows import control_trace_v23

        c = context(configuration)
        x = initial()
        ref = x[:5].copy()
        domain = SupportDomain.diagnostic(configuration, c, 'a' * 64)
        config = FeedbackConfig(slew=.02, timeout_ms=2000)
        policy = CachedTrackingFeedback(domain, c, config=config, allow_diagnostic=True)
        seed = policy.prepare_startup(x, ref)
        assert seed['status'] == 'prepared'
        env = FourStepFixture(configuration)
        reset = ResetObservation('episode', 'reset', 0, x, np.zeros(env._num_thrusters))
        ledger = ExecutionLedger(domain, c, reset, reference=ref, reference_id='ref',
            startup_command=seed['command'], feedback_config=config,
            allow_diagnostic=True, steady=policy.steady)
        runtime = RuntimeCoordinator(ledger, policy, clock=Clock())
        monkeypatch.setattr(control_trace_v23, 'backend_readback', lambda e: e.backend())
        geometry = dict(body_path='/World/body',
            body_local_corners_m=list(itertools.product((-.5, .5), (-.5, .5), (-.25, .25))),
            ground_world_z_m=0., minimum_clearance_m=.1)
        session = IsaacExecutionSession(env, episode_id='episode', reset_id='reset',
            geometry=geometry, contact_getter=env.contact,
            state_getter=lambda e: e.x.copy(), max_substeps=16)
        session.__enter__()
        sessions.append(session)
        env.reset()
        session.reset_observation()
        session.bind(runtime)
        return env, session, runtime

    yield create
    for session in reversed(sessions):
        session.__exit__(RuntimeError, RuntimeError('fixture cleanup'), None)


@pytest.mark.parametrize('configuration', ['base', 'asymmetric', 'uuv4'])
def test_two_macro_intervals_authenticate_eight_ordered_callbacks(bridge30, configuration):
    env, session, runtime = bridge30(configuration)
    for _ in range(2):
        assert legacy.advance(env, session)['status'] == 'completed_interval'
    assert env.physics_steps == env.applies == runtime.ledger.physics_index == 8
    assert runtime.stats['dispatches'] == runtime.stats['confirmed_controls'] == 2
    assert [r['control_index'] for r in session.substeps] == [0] * 4 + [1] * 4
    assert [r['substep_index'] for r in session.substeps] == [0, 1, 2, 3] * 2
    receipts = [r['execution_ack_v55']['receipt'] for r in session.substeps]
    assert [r['physics_index'] for r in receipts] == list(range(1, 9))
    assert [r['interval_complete'] for r in receipts] == [False, False, False, True] * 2
    micro_history = runtime.ledger.acknowledged_commands(0, 4)
    assert micro_history.shape == (4, 4)
    np.testing.assert_array_equal(micro_history[0::2], micro_history[1::2])
    for offset in (0, 4):
        commands = [r['execution_command_v55']['command'] for r in session.substeps[offset:offset+4]]
        for command in commands[1:]:
            np.testing.assert_array_equal(command, commands[0])


def test_third_physics_fault_preserves_three_receipts_before_fourth_apply(bridge30):
    env, session, runtime = bridge30()
    env.fail_third_contact = True
    with pytest.raises((ValueError, RuntimeError)):
        legacy.advance(env, session)
    assert env.physics_steps == env.applies == runtime.ledger.physics_index == 3
    assert runtime.ledger.stopped and runtime.ledger.startup_consumed
    assert runtime.stats['confirmed_controls'] == 0
    assert [r['execution_ack_v55']['receipt']['physics_index']
            for r in session.substeps[:2]] == [1, 2]
    third = session.substeps[2]['execution_ack_v55']
    assert third['actual_history_advanced'] is True
    assert third['status'] == 'stop'
    with pytest.raises((ValueError, RuntimeError)):
        legacy.advance(env, session)
    assert env.physics_steps == env.applies == 3


def test_missing_fourth_receipt_never_completes_or_reconstructs_history(bridge30, monkeypatch):
    env, session, runtime = bridge30()
    finish = session._finish_physics

    def suppress_fourth_receipt():
        if session.pending is not None and session.pending['substep_index'] == 3:
            return
        return finish()

    monkeypatch.setattr(session, '_finish_physics', suppress_fourth_receipt)
    with pytest.raises((ValueError, RuntimeError), match='missing_complete_interval_receipts'):
        legacy.advance(env, session)
    assert env.physics_steps == env.applies == 4
    assert runtime.ledger.physics_index == 3 and runtime.ledger.stopped
    assert runtime.stats['confirmed_controls'] == 0
    assert 'execution_ack_v55' not in session.substeps[3]
    assert session.interval_records[-1]['status'] == 'stopped'


def test_process_route_preserves_unmarked_60hz_environment(routed_control):
    env = legacy.FixtureEnv()
    env.reset()
    env.step(torch.zeros(1, 4))
    assert env.physics_steps == env.applies == 2
    assert env._direct_index_v24 == 2
    assert env._direct_sequence_v24.shape == (1, 2, 4)


def test_duplicate_process_route_installation_is_rejected(routed_control):
    from easyuuv_nc.control_v67 import install_control_clock
    before = {name: getattr(routed_control, name)
              for name in ('begin_interval', 'direct_pwm', 'reset_direct')}
    with pytest.raises(ValueError, match='already_installed'):
        install_control_clock()
    assert all(getattr(routed_control, name) is value for name, value in before.items())

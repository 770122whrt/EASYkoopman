"""Source-control/trace ordering fixtures, explicitly not Isaac physics."""
from types import SimpleNamespace
import itertools
import ast
import hashlib
from pathlib import Path
import numpy as np
import pytest
import torch

from test_bounded_feedback_v46 import initial
from test_prepared_projected_v40 import context
from test_plan_arbiter_v52 import Clock
from koopman.bounded_mpc_v44 import SupportDomain
from koopman.bounded_feedback_v46 import FeedbackConfig
from koopman.execution_ledger_v48 import ResetObservation
from koopman.cached_checks_v53 import CachedTrackingFeedback, CachedExecutionLedger
from koopman.plan_continuity_v54 import RuntimeCoordinator
from workflows.control_seam_v23 import ControlKernel
from easyuuv_nc.control_v24 import begin_interval, direct_pwm, reset_direct


def frozen_physics_loop():
    """Execute the archived server's actual loop ordering, not a guessed loop."""
    from workflows.validate_formal_trace_v25 import DIRECT_RL_SHA
    p = Path(__file__).resolve().parents[1] / 'docs/evidence/phase8_3/server-initialization-repair-20260912/raw/installed/direct_rl_env.py'
    assert hashlib.sha256(p.read_bytes()).hexdigest() == DIRECT_RL_SHA
    cls = next(n for n in ast.parse(p.read_text()).body if isinstance(n, ast.ClassDef) and n.name == 'DirectRLEnv')
    step = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'step')
    loop = next(n for n in step.body if isinstance(n, ast.For))
    wrapper = ast.parse('def physics_loop(self):\n    is_rendering = False').body[0]
    wrapper.body.append(loop)
    ns = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[])), str(p), 'exec'), ns)
    return ns['physics_loop']


class FixtureEnv:
    def __init__(self, configuration='base'):
        self.configuration = configuration
        self.kernel = ControlKernel(configuration)
        self.__dict__.update(vars(self.kernel.env))
        self.cfg.control_input_mode = 'direct_pre_tam_v24'
        self.cfg.decimation = 2
        self.sim = SimpleNamespace(cfg=SimpleNamespace(dt=1/120))
        self.cfg.sim = SimpleNamespace(render_interval=2)
        self.physics_dt = 1/120
        self.sim.step = self._physics_step
        self.scene = SimpleNamespace(write_data_to_sim=lambda: None, update=self._scene_update)
        self.physics_loop = frozen_physics_loop()
        self.thruster_dynamics = self.kernel.actuator
        self._sim_step_counter = 30
        self.stamp = .25
        self._thruster_dynamics_time_s = self.kernel.time
        self.x = np.array([[5.5, 1., 0., 0., 0., 0., 0., 0., 0., 0., 0.]])
        self.xy = np.zeros(2)
        self.token = -1
        self.force = 0.
        self.applies = 0
        self.physics_steps = 0
        self.done = False
        self.mutation = None
        self._last_virtual_control_4 = torch.zeros(1, 4)
        self._last_motor_values_raw = torch.zeros(1, self._num_thrusters)
        self._last_motor_values_clipped = torch.zeros(1, self._num_thrusters)
        self._thrust = torch.zeros(1, 1, 3)
        self._moment = torch.zeros(1, 1, 3)

    def reset(self):
        return self._reset_idx([0])

    def _reset_idx(self, ids):
        reset_direct(self, ids)
        self.thruster_dynamics.state.zero_()
        self._thruster_dynamics_time_s.zero_()
        self.token = -1

    def _pre_physics_step(self, action):
        begin_interval(self, action)

    def _apply_action(self):
        self.applies += 1
        pwm = direct_pwm(self)
        speed = self.kernel.pwm_speed(pwm)
        self._thruster_dynamics_time_s.add_(1/120)
        self.thruster_dynamics.update(speed, self._thruster_dynamics_time_s)
        self.token += 1
        if self.mutation == 'pwm':
            self._last_motor_values_clipped[0, 0] += .01
        if self.mutation == 'command':
            self._last_virtual_control_4[0, 0] += .01

    def _get_dones(self):
        return torch.tensor([self.done]), torch.tensor([False])

    def get_koopman_telemetry_snapshot(self):
        return dict(configuration=self.configuration, step_token=[self.token],
                    control_mask_4=self._control_mask_4,
                    virtual_control_4=self._last_virtual_control_4,
                    motor_pwm_n=self._last_motor_values_clipped,
                    applied_wrench_6=np.zeros((1, 6)))

    def backend(self):
        q = self.x[0, [2, 3, 4, 1]].tolist()
        return dict(transform_actor_world_xyzw=[[*self.xy, self.x[0, 0], *q]],
                    velocity_com_world_6=[self.x[0, 5:].tolist()],
                    mass_kg=[[1.]], gravity_disabled=[[0]],
                    gravity_world_m_s2=[0., 0., 0.],
                    _external_force_b=[[[0., 0., 0.]]],
                    _use_global_wrench_frame=False, has_external_wrench=False,
                    uses_external_wrench_positions=False,
                    cache_sim_timestamp_s=self.stamp)

    def contact(self):
        if self.mutation == 'contact_read' and self.physics_steps:
            raise RuntimeError('fixture_contact_read')
        return dict(body_paths=['/World/body'], normal_force_world_n=[[0., 0., self.force]],
                    physics_dt_s=1/120, sample_timestamp_s=self.stamp - (.1 if self.mutation == 'stale_contact' and self.physics_steps else 0.))

    def step(self, action):
        self._pre_physics_step(action)
        self.physics_loop(self)
        dones = self._get_dones()
        return None, None, dones[0], dones[1], {}

    def _physics_step(self, *, render):
        if self.mutation == 'unknown_execution':
            raise RuntimeError('fixture_unknown_execution')
        self.physics_steps += 1
        if self.mutation == 'skipped_tick':
            self._sim_step_counter += 1
        if self.mutation == 'contact': self.force = 1.
        if self.mutation == 'xy': self.xy[0] = 3.
        if self.mutation == 'state': self.x[0, 8] = 4.

    def _scene_update(self, *, dt):
        if self.mutation != 'stale_timestamp': self.stamp += dt
        if self.mutation == 'reset': self._reset_idx([0])


@pytest.fixture
def bridge(monkeypatch):
    def create(*, observed_reset=True, bind=True, configuration='base'):
        from workflows.isaac_execution_v55 import IsaacExecutionSession
        from workflows import control_trace_v23
        c = context(configuration); x = initial(); ref = x[:5].copy()
        domain = SupportDomain.diagnostic(configuration, c, 'a'*64)
        policy = CachedTrackingFeedback(domain, c, config=FeedbackConfig(timeout_ms=2000), allow_diagnostic=True)
        seed = policy.prepare_startup(x, ref); assert seed['status'] == 'prepared'
        env = FixtureEnv(configuration)
        ledger = CachedExecutionLedger(domain, c, ResetObservation('episode', 'reset', 0, x, np.zeros(env._num_thrusters)),
            reference=ref, reference_id='ref', startup_command=seed['command'], allow_diagnostic=True, steady=policy.steady)
        clock = Clock(); run = RuntimeCoordinator(ledger, policy, clock=clock)
        monkeypatch.setattr(control_trace_v23, 'backend_readback', lambda e: e.backend())
        geometry = dict(body_path='/World/body', body_local_corners_m=list(itertools.product((-.5, .5), (-.5, .5), (-.25, .25))),
                        ground_world_z_m=0., minimum_clearance_m=.1)
        session = IsaacExecutionSession(env, episode_id='episode', reset_id='reset',
            geometry=geometry, contact_getter=env.contact, state_getter=lambda e: e.x.copy(), max_substeps=20)
        session.__enter__()
        if observed_reset:
            env.reset()
        if bind:
            reset = session.reset_observation()
            assert reset.physics_index == 0
            session.bind(run)
        return env, session, run, clock
    return create


def advance(env, session):
    return session.run_interval(env.step, np.array([5.5, 1., 0., 0., 0.]), reference_id='ref')


@pytest.mark.parametrize('configuration', ['base', 'long_body', 'heavy_moderate', 'asymmetric',
                                          'uuv6', 'uuv6_angled', 'uuv4', 'uuv4_angled'])
def test_observed_reset_two_actual_boundary_callbacks_then_next_interval(bridge, configuration):
    env, s, run, _ = bridge(configuration=configuration)
    try:
        assert run.ledger.physics_index == 0
        for _ in range(2):
            result = advance(env, s)
            assert result['status'] == 'completed_interval'
        assert run.ledger.physics_index == 4 and env.physics_steps == 4
        assert run.stats['confirmed_controls'] == 2
        assert [r['execution_ack_v55']['receipt']['physics_index'] for r in s.substeps] == [1, 2, 3, 4]
        assert s.substeps[0]['execution_ack_v55']['actual_history_advanced']
    finally:
        s.__exit__(None, None, None)
    assert '_apply_action' not in env.__dict__


def test_no_observed_reset_cannot_bind_even_if_zero_arrays(bridge):
    env, s, run, _ = bridge(observed_reset=False, bind=False)
    try:
        with pytest.raises((ValueError, RuntimeError), match='reset'):
            s.reset_observation()
    finally:
        s.__exit__(None, None, None)


@pytest.mark.parametrize('bad', ['rotor', 'state', 'clock'])
def test_actual_reset_readback_rejects_nonzero_or_bad_state(bridge, bad):
    env, s, run, _ = bridge(bind=False)
    if bad == 'rotor': env.thruster_dynamics.state[0, 0] = 1.
    if bad == 'state': env.x[0, 5] = 1.
    if bad == 'clock': env._thruster_dynamics_time_s[0] = 1.
    try:
        with pytest.raises((ValueError, RuntimeError), match='reset'):
            s.reset_observation()
    finally:
        s.__exit__(None, None, None)


@pytest.mark.parametrize('bad', ['contact', 'contact_read', 'stale_contact', 'xy', 'state'])
def test_known_first_substep_is_preserved_before_safety_stop(bridge, bad):
    env, s, run, _ = bridge(); env.mutation = bad
    try:
        with pytest.raises((ValueError, RuntimeError)):
            advance(env, s)
        assert env.applies == env.physics_steps == 1
        assert run.ledger.physics_index == 1 and run.ledger.startup_consumed
        assert run.ledger.stopped
        assert s.substeps[0]['execution_ack_v55']['actual_history_advanced']
    finally:
        s.__exit__(RuntimeError, RuntimeError('fixture'), None)


@pytest.mark.parametrize('bad', ['unknown_execution', 'skipped_tick', 'stale_timestamp', 'pwm', 'command'])
def test_uncertain_or_different_execution_stops_without_inventing_receipt(bridge, bad):
    env, s, run, _ = bridge(); env.mutation = bad
    try:
        with pytest.raises((ValueError, RuntimeError)):
            advance(env, s)
        assert env.applies == 1 and run.ledger.physics_index == 0
        assert not run.ledger.startup_consumed and run.ledger.stopped
        with pytest.raises((ValueError, RuntimeError)):
            advance(env, s)
        assert env.applies == 1
    finally:
        s.__exit__(RuntimeError, RuntimeError('fixture'), None)


def test_unexpected_reset_blocked_before_reset_erases_executed_state(bridge):
    env, s, run, _ = bridge(); env.mutation = 'reset'
    try:
        with pytest.raises((ValueError, RuntimeError), match='reset'):
            advance(env, s)
        assert run.ledger.physics_index == 1
        assert s.generations == [1] and env.token == 0
        assert env.applies == 1 and run.ledger.stopped
    finally:
        s.__exit__(RuntimeError, RuntimeError('fixture'), None)


def test_done_flag_stops_after_both_completed_receipts(bridge):
    env, s, run, _ = bridge(); env.done = True
    try:
        with pytest.raises((ValueError, RuntimeError), match='done'):
            advance(env, s)
        assert run.ledger.physics_index == 2 and run.ledger.stopped
    finally:
        s.__exit__(RuntimeError, RuntimeError('fixture'), None)


def test_direct_env_step_cannot_bypass_runtime_dispatch(bridge):
    env, s, run, _ = bridge()
    try:
        with pytest.raises((ValueError, RuntimeError), match='dispatch'):
            env.step(torch.zeros(1, 4))
        assert env.applies == 0 and run.ledger.physics_index == 0
    finally:
        s.__exit__(RuntimeError, RuntimeError('fixture'), None)


@pytest.mark.parametrize('field', ['rotor', 'clock', 'state'])
def test_reset_observation_cannot_be_reused_after_mutation_before_binding(bridge, field):
    env, s, run, _ = bridge(bind=False)
    try:
        s.reset_observation()
        if field == 'rotor': env.thruster_dynamics.state[0, 0] = 1.
        if field == 'clock': env._thruster_dynamics_time_s[0] = 1.
        if field == 'state': env.x[0, 0] += .01
        with pytest.raises((ValueError, RuntimeError), match='reset'):
            s.bind(run)
    finally:
        s.__exit__(None, None, None)


def test_duplicate_pre_dispatch_cannot_issue_a_second_interval(bridge):
    env, s, run, _ = bridge()
    def duplicate(action):
        env._pre_physics_step(action)
        env._pre_physics_step(action)
        return env.step(action)
    try:
        with pytest.raises((ValueError, RuntimeError)):
            s.run_interval(duplicate, initial()[:5], reference_id='ref')
        assert env.applies == 0 and run.ledger.physics_index == 0 and run.ledger.stopped
    finally:
        s.__exit__(RuntimeError, RuntimeError('fixture'), None)

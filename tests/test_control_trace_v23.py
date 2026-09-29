from types import SimpleNamespace

import pytest
import torch

from workflows import control_trace_v23 as trace_module


class Env:
    def __init__(self):
        self.num_envs = 2
        self.cfg = SimpleNamespace(decimation=2)
        self.sim = SimpleNamespace(cfg=SimpleNamespace(dt=.01))
        self.old_actions = torch.zeros(2, 4)
        self._actions = torch.zeros(2, 4)
        self._goal = torch.zeros(2, 4)
        self.x = torch.zeros(2, 11)
        self.token = torch.zeros(2, dtype=torch.long)
        self.u = torch.zeros(2, 4)
        self.thruster_dynamics = SimpleNamespace(state=torch.zeros(2, 3))
        self._thrust = torch.zeros(2, 1, 3)
        self._moment = torch.zeros(2, 1, 3)

    def _pre_physics_step(self, action):
        self._actions = action.clone()

    def _apply_action(self):
        self.u = self._actions + (self._actions - self.old_actions)
        self.old_actions = self._actions.clone()
        self.token += 1

    def _get_dones(self):
        return torch.zeros(2, dtype=torch.bool), torch.zeros(2, dtype=torch.bool)

    def _reset_idx(self, ids):
        self.x[ids] = 0
        self.token[ids] = -1

    def get_koopman_telemetry_snapshot(self):
        return {'virtual_control_4': self.u.clone(), 'step_token': self.token.clone()}

    def step(self):
        self._pre_physics_step(torch.ones(2, 4))
        for _ in range(2):
            self._apply_action()
            self.x[:, 0] += self.u[:, 0]
        return self._get_dones()


def recorder(env, **kwargs):
    return trace_module.ControlTraceSession(env, state_getter=lambda e: e.x.clone(), **kwargs)


def test_two_substeps_record_post_physics_and_do_not_change_commands():
    env, baseline = Env(), Env()
    baseline.step()
    with recorder(env) as trace:
        env.step()
    assert torch.equal(env.x, baseline.x)
    rows = trace.substeps
    assert len(rows) == 2
    assert rows[0]['command']['telemetry']['virtual_control_4'][0][0] == 2
    assert rows[1]['command']['telemetry']['virtual_control_4'][0][0] == 1
    assert rows[0]['state_after_physics_11'][0][0] == 2
    assert rows[1]['state_after_physics_11'][0][0] == 3
    env.x[:] = 99
    assert rows[1]['state_after_physics_11'][0][0] == 3
    assert '_apply_action' not in env.__dict__


def test_reset_generation_is_per_env_and_terminal_is_before_reset():
    env = Env()
    with recorder(env) as trace:
        env.step()
        env._reset_idx([1])
        env.step()
    assert trace.substeps[0]['reset_generation'] == [0, 0]
    assert trace.substeps[2]['reset_generation'] == [0, 1]
    assert trace.events[0]['kind'] == 'dones'
    assert trace.events[1]['kind'] == 'reset'
    assert trace.events[1]['before']['state_11'][1][0] == 3
    assert trace.events[1]['after']['state_11'][1][0] == 0


def test_cap_aborts_before_extra_command_and_restores_methods():
    env = Env()
    with pytest.raises(RuntimeError, match='trace_substep_budget'):
        with recorder(env, max_substeps=1):
            env.step()
    assert env.token.tolist() == [1, 1]
    assert '_apply_action' not in env.__dict__


def test_disabled_does_not_install_hooks_or_take_snapshots():
    env = Env()
    with trace_module.ControlTraceSession(env, enabled=False,
         state_getter=lambda e: pytest.fail('disabled snapshot')) as trace:
        assert '_apply_action' not in env.__dict__
        env.step()
    assert trace.substeps == []


def test_actuator_observer_records_speed_command_once_and_restores_original():
    env = Env()
    calls = []
    def update(command, end_time):
        calls.append(command.clone())
        return command * .5
    env.thruster_dynamics.update = update
    original_apply = env._apply_action
    def apply():
        original_apply()
        env.thruster_dynamics.state = env.thruster_dynamics.update(torch.ones(2, 3), .01)
    env._apply_action = apply
    with recorder(env) as trace:
        env.step()
    assert len(calls) == 2
    assert trace.substeps[0]['actuator_update']['speed_command_n'] == [[1.] * 3] * 2
    assert env.thruster_dynamics.update is update

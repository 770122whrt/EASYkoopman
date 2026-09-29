"""Execute actual environment method bodies without Isaac; local contracts only."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

ENV = Path(__file__).resolve().parents[1] / 'easyuuv_nc/env/easyuuv_env.py'


def real_method(name='_reset_control_history'):
    tree = ast.parse(ENV.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'EasyUUVEnv')
    method = next((n for n in cls.body if isinstance(n, ast.FunctionDef)
                   and n.name == name), None)
    assert method is not None, 'missing reset boundary for controller history'
    scope = {'torch': torch}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(ENV), 'exec'), scope)
    return scope[name]


def runtime(mode):
    return SimpleNamespace(cfg=SimpleNamespace(control_history_reset_mode=mode),
                           old_actions=torch.ones(2, 4), actions_i=torch.full((2, 4), 2.))


def test_episode_local_clears_selected_history_and_legacy_preserves_it():
    reset = real_method()
    for mode in ('legacy', 'episode_local_v1'):
        env = runtime(mode)
        reset(env, torch.tensor([1]))
        assert torch.equal(env.old_actions[0], torch.ones(4))
        assert torch.equal(env.actions_i[0], torch.full((4,), 2.))
        assert torch.equal(env.old_actions[1], torch.full((4,), 1. if mode == 'legacy' else 0.))
        assert torch.equal(env.actions_i[1], torch.full((4,), 2. if mode == 'legacy' else 0.))


def test_typo_fails_without_mutating_history():
    env = runtime('episode_locla')
    with pytest.raises(ValueError, match='control_history_reset_mode'):
        real_method()(env, torch.tensor([1]))
    assert torch.equal(env.old_actions, torch.ones(2, 4))


def test_reset_is_wired_before_parent_reset_and_default_remains_legacy():
    tree = ast.parse(ENV.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'EasyUUVEnv')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_reset_idx')
    text = ast.unparse(method)
    assert 'self._reset_control_history(env_ids)' in text
    assert text.index('self._reset_control_history(env_ids)') < text.index('super()._reset_idx')
    cfg = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'EasyUUVEnvCfg')
    assert "control_history_reset_mode = 'legacy'" in ast.unparse(cfg)


def test_first_pre_step_does_not_reintroduce_previous_episode_reward_history():
    env = runtime('episode_local_v1')
    env._actions = torch.ones(2, 4)
    env._prev_action = torch.zeros(2, 4)
    env._prev_prev_action = torch.zeros(2, 4)
    env._debug = False
    env._tune_gains_enabled = False
    env.device = 'cpu'
    real_method()(env, torch.tensor([1]))
    real_method('_pre_physics_step')(env, torch.zeros(2, 4))
    assert torch.equal(env._prev_action[0], torch.ones(4))
    assert torch.equal(env._prev_action[1], torch.zeros(4))


def test_real_default_s_surface_has_distinct_first_and_second_substep_commands():
    tree = ast.parse(ENV.read_text(encoding='utf-8'))
    cfg_node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'EasyUUVEnvCfg')
    names = {'PID_PWM_value', 'PID_init_args', 'control_method', 's_ratio', 'cascade_control',
             'self_adapt', 'attitude_error_mode', 'action_lim_vec', 'pseudo_error_driven'}
    nodes = [n for n in cfg_node.body if isinstance(n, ast.Assign)
             and isinstance(n.targets[0], ast.Name) and n.targets[0].id in names]
    values = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ENV), 'exec'), values)
    env = SimpleNamespace(cfg=SimpleNamespace(**{n: values[n] for n in names}),
        num_envs=1, _num_thrusters=8, device='cpu', ctrl_mismatch_mode='none',
        _depth_pid_output_scale=1., _depth_integral_gain=0., _depth_deadband_mode='off',
        _depth_invert_compensation=False, _alloc_priority_mode='off', _use_config_alloc=False,
        _action_channel_sign=torch.ones(1, 4), _control_mask_4=torch.ones(1, 4),
        action_lim=torch.tensor(values['action_lim_vec']),
        PID_args=torch.tensor(values['PID_init_args']).reshape(1, 4, 3))
    action = torch.full((1, 4), .1)
    pid = real_method('_pid_control')
    pid(env, action, action, torch.zeros_like(action))
    first = env._last_virtual_control_4.clone()
    pid(env, action, torch.zeros_like(action), torch.zeros_like(action))
    second = env._last_virtual_control_4.clone()
    assert torch.all(first > second)
    expected = torch.tanh(2 * (env.PID_args[:, :, 0] + env.PID_args[:, :, 1]) * action * env.action_lim)
    torch.testing.assert_close(first, expected)
    dynamics = next(n for c in tree.body if isinstance(c, ast.ClassDef) and c.name == 'EasyUUVEnv'
                    for n in c.body if isinstance(n, ast.FunctionDef) and n.name == '_compute_dynamics')
    assert 'action_diff = actions - self.old_actions' in ast.unparse(dynamics)
    assert 'self.old_actions = actions.clone()' in ast.unparse(dynamics)

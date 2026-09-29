"""Current control seam checks on CPU; these do not simulate Isaac physics."""
import ast
import importlib
from pathlib import Path
from types import MethodType

import numpy as np
import pytest
import torch

from workflows.control_seam_v23 import ControlKernel


def current():
    return importlib.import_module('easyuuv_nc.control')


def runtime(configuration='base', *, rate=30, sequence=False):
    kernel = ControlKernel(configuration)
    env = kernel.env
    env.cfg.control_input_mode = ('direct_sequence_replay_v24' if sequence
                                  else 'direct_pre_tam_v24')
    env.cfg.decimation = 4 if rate == 30 else 2
    env.cfg.control_rate_hz_v67 = rate
    return kernel, env


@pytest.mark.parametrize('rate', [30, 60])
@pytest.mark.parametrize('configuration', [
    'base', 'long_body', 'heavy_moderate', 'asymmetric',
    'uuv6', 'uuv6_angled', 'uuv4', 'uuv4_angled',
])
def test_clock_holds_original_allocation_and_enforces_interval(configuration, rate):
    control = current()
    kernel, env = runtime(configuration, rate=rate)
    command = torch.tensor([[.05, -.04, .08, .2]])
    expected = ControlKernel(configuration).command(command, pre_tam=True)
    control.reset_direct(env, [0])
    control.begin_interval(env, command)
    for index in range(env.cfg.decimation):
        if index:
            with pytest.raises(ValueError, match='consume_count_incomplete'):
                control.begin_interval(env, command)
        actual = kernel.command(command)
        np.testing.assert_allclose(actual['pwm'], expected['pwm'], atol=1e-7, rtol=0)
        np.testing.assert_array_equal(actual['virtual_control'], expected['virtual_control'])
    with pytest.raises(ValueError, match='consume_count_exceeded'):
        control.direct_pwm(env)
    control.begin_interval(env, command)
    control.direct_pwm(env)
    control.reset_direct(env, [0])
    assert env._direct_index_v24 == env.cfg.decimation
    assert env._direct_sequence_v24.shape == (1, env.cfg.decimation, 4)
    with pytest.raises(ValueError, match='consume_count_exceeded'):
        control.direct_pwm(env)


def test_two_substep_sequence_order_first_command_and_reset():
    control = current()
    _, env = runtime('uuv6', rate=60, sequence=True)
    commands = torch.tensor([[[.1, .2, .1, 0], [-.1, 0, .2, .1]]])
    control.queue_sequence(env, commands)
    with pytest.raises(ValueError, match='already_pending'):
        control.queue_sequence(env, commands)
    with pytest.raises(ValueError, match='first_command_mismatch'):
        control.begin_interval(env, torch.zeros(1, 4))
    control.begin_interval(env, commands[:, 0])
    for command in commands[0]:
        expected = ControlKernel('uuv6').command(command, pre_tam=True)['pwm']
        np.testing.assert_allclose(control.direct_pwm(env).numpy()[0], expected, atol=1e-7)
    with pytest.raises(ValueError, match='sequence_missing'):
        control.begin_interval(env, commands[:, 0])
    control.queue_sequence(env, commands)
    control.reset_direct(env, [0])
    assert env._direct_pending_v24 is None
    with pytest.raises(ValueError, match='sequence_missing'):
        control.begin_interval(env, commands[:, 0])


def test_four_substep_clock_rejects_sequence_and_wrong_decimation():
    control = current()
    _, env = runtime(sequence=True)
    with pytest.raises(ValueError, match='control_mode_invalid'):
        control.begin_interval(env, torch.zeros(1, 4))
    env.cfg.control_input_mode = 'direct_pre_tam_v24'
    env.cfg.decimation = 2
    with pytest.raises(ValueError, match='decimation_invalid'):
        control.begin_interval(env, torch.zeros(1, 4))


@pytest.mark.parametrize('rate', [30, 60])
@pytest.mark.parametrize('bad', [1.01, float('nan'), float('inf')])
def test_invalid_command_fails_without_starting_interval(rate, bad):
    control = current()
    _, env = runtime(rate=rate)
    control.reset_direct(env, [0])
    with pytest.raises(ValueError, match='command_invalid'):
        control.begin_interval(env, torch.tensor([[bad, 0, 0, 0]]))
    assert env._direct_index_v24 == env.cfg.decimation


@pytest.mark.parametrize('clock', ['fixed_dt', 'float32_accumulated_v1'])
def test_actuator_recurrence_deadzone_and_reset(clock):
    control = current()
    kernel = ControlKernel('uuv6')
    state = control.ActuatorState(6, tau=kernel.tau, dt=kernel.dt, clock=clock)
    for pwm in [np.array([0, .019, .02, -.02, .8, -.8]), np.zeros(6), np.full(6, .1)]:
        np.testing.assert_allclose(state.advance_pwm(pwm), kernel.advance(pwm)['speed'], atol=2e-5)
    snapshot = state.current()
    snapshot[:] = 100
    assert not np.any(state.current() == 100)
    state.reset()
    np.testing.assert_array_equal(state.current(), np.zeros(6))
    assert state.elapsed_time == 0


def test_environment_imports_current_control_without_installing_a_patch():
    control = current()
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / 'easyuuv_nc/env/easyuuv_env.py').read_text(encoding='utf8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'EasyUUVEnv')
    imports = [node.module for node in ast.walk(cls) if isinstance(node, ast.ImportFrom)
               and node.module and node.module.startswith('easyuuv_nc.control')]
    assert imports == ['easyuuv_nc.control'] * 3
    own_tree = ast.parse(Path(control.__file__).read_text(encoding='utf8'))
    assert not any(isinstance(node, ast.ImportFrom) and node.module in {
        'easyuuv_nc.control_v24', 'easyuuv_nc.control_v67'} for node in ast.walk(own_tree))
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                  and node.name == '_pre_physics_step')
    scope = {'torch': torch}
    exec(compile(ast.Module(body=[method], type_ignores=[]), 'actual-pre-physics-step', 'exec'), scope)
    _, env = runtime()
    env._debug = False
    env._tune_gains_enabled = False
    env._actions = torch.zeros(1, 4)
    env._prev_action = torch.zeros(1, 4)
    env._prev_prev_action = torch.zeros(1, 4)
    MethodType(scope['_pre_physics_step'], env)(torch.full((1, 4), .05))
    assert env._direct_sequence_v24.shape == (1, 4, 4)
    for _ in range(4):
        control.direct_pwm(env)

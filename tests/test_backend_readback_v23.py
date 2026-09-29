"""Readback observation contracts; these fixtures are not PhysX evidence."""
from types import SimpleNamespace

import pytest
import torch

from workflows import control_trace_v23 as module
from test_control_trace_v23 import Env, recorder


def test_backend_readback_copies_raw_buffers_and_keeps_frames_explicit():
    values = {'transforms': torch.tensor([[1., 2., 3., 0., 0., 0., 1.]]),
              'velocities': torch.arange(6.).reshape(1, 6),
              'masses': torch.tensor([[30.]]), 'inv_masses': torch.tensor([[1 / 30]]),
              'inertias': torch.eye(3).reshape(1, 9),
              'inv_inertias': torch.eye(3).reshape(1, 9),
              'coms': torch.tensor([[0., 0., 0., 0., 0., 0., 1.]]),
              'disable_gravities': torch.zeros(1, 1)}
    view = SimpleNamespace(**{f'get_{key}': lambda key=key: values[key] for key in values})
    data = SimpleNamespace(root_state_w=torch.zeros(1, 13), _sim_timestamp=.25)
    env = SimpleNamespace(_robot=SimpleNamespace(root_physx_view=view, data=data),
                          sim=SimpleNamespace(cfg=SimpleNamespace(gravity=(0., 0., -9.81))))
    result = module.backend_readback(env)
    assert result['transform_actor_world_xyzw'] == [[1., 2., 3., 0., 0., 0., 1.]]
    assert result['velocity_com_world_6'] == [list(range(6))]
    assert result['cache_state_world_wxyz_13'] == [[0.] * 13]
    values['transforms'][:] = 99
    assert result['transform_actor_world_xyzw'][0][0] == 1


def test_requested_backend_readback_fails_closed_when_unavailable():
    env = Env()
    with pytest.raises(AttributeError):
        recorder(env, backend_readback_enabled=True)._snapshot()


def test_raw_readback_covers_reset_and_completed_physics_without_extra_steps(monkeypatch):
    env = Env()
    monkeypatch.setattr(module, 'backend_readback', lambda e: {'raw_z': e.x[0, 0].item()})
    with recorder(env, backend_readback_enabled=True) as trace:
        env.step()
        env._reset_idx([0])
    assert trace.substeps[0]['backend_after_physics']['raw_z'] == 2
    assert trace.substeps[1]['backend_after_physics']['raw_z'] == 3
    reset = next(e for e in trace.events if e['kind'] == 'reset')
    assert reset['before']['backend']['raw_z'] == 3
    assert reset['after']['backend']['raw_z'] == 0
    assert env.token.tolist() == [-1, 2]


def test_backend_probe_is_opt_in():
    from workflows.trace_control_v23 import parser, request
    assert request(parser().parse_args(['--run-id', 'example']))['backend_readback'] == 'off'
    assert request(parser().parse_args(['--run-id', 'example', '--backend-readback', 'on']))['backend_readback'] == 'on'

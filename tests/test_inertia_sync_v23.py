"""Actual environment methods; local PhysX interface contract, not simulation proof."""
import ast
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest
import torch

from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS, qualification_record

ENV = Path(__file__).resolve().parents[1] / 'easyuuv_nc/env/easyuuv_env.py'


def method(name, *, mechanical_prefix=False):
    tree = ast.parse(ENV.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'EasyUUVEnv')
    node = next((n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name), None)
    assert node is not None, name
    if mechanical_prefix:
        # Run the real config/mass/inertia path, stopping before unrelated COM/TAM setup.
        end = next(i for i, n in enumerate(node.body) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Attribute) and t.attr == 'com_to_cob_offsets' for t in n.targets))
        node.body = node.body[:end]
    scope = {'torch': torch, 'qualification_record': qualification_record}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(ENV), 'exec'), scope)
    return scope[name]


class View:
    def __init__(self, ignore_write=False):
        self.inertias = torch.diag_embed(torch.tensor([[.37, .97, 1.19]] * 2)).reshape(2, 9)
        self.calls = []
        self.ignore_write = ignore_write

    def get_inertias(self):
        return self.inertias.clone()

    def set_inertias(self, values, indices):
        self.calls.append(indices.clone())
        if not self.ignore_write:
            self.inertias[indices] = values[indices]

    def set_masses(self, values, indices):
        pass


def runtime(mode='declared_v1', *, ignore_write=False):
    view = View(ignore_write)
    env = SimpleNamespace(cfg=SimpleNamespace(inertia_sync_mode=mode, mass=22.701,
        embodiment_configs=EMBODIMENT_CONFIGS), num_envs=2, device='cpu',
        inertia_tensors=torch.tensor([[.37, .97, 1.19]] * 2),
        inertia_tensors_mean=torch.tensor([[.8433333]] * 2),
        _robot=SimpleNamespace(root_physx_view=view, _ALL_INDICES=torch.arange(2)))
    if 'def _sync_declared_inertias' in ENV.read_text(encoding='utf-8'):
        env._sync_declared_inertias = MethodType(method('_sync_declared_inertias'), env)
    return env, view


def test_actual_configuration_path_updates_physx_and_hydrodynamic_mean():
    env, view = runtime()
    method('apply_embodiment_config', mechanical_prefix=True)(env, 'uuv6')
    torch.testing.assert_close(view.inertias[:, [0, 4, 8]], env.inertia_tensors)
    torch.testing.assert_close(env.inertia_tensors_mean, env.inertia_tensors.mean(dim=1, keepdim=True))


def test_legacy_configuration_keeps_historical_physics():
    env, view = runtime('legacy')
    before = view.inertias.clone()
    method('apply_embodiment_config', mechanical_prefix=True)(env, 'uuv6')
    assert not view.calls
    torch.testing.assert_close(view.inertias, before)


def test_selective_sync_preserves_other_bodies_and_replaces_selected_diagonal():
    env, view = runtime()
    view.inertias[0, 1] = .01
    before = view.inertias[0].clone()
    env.inertia_tensors[1] = torch.tensor([.5, 1.3, 1.6])
    method('_sync_declared_inertias')(env, torch.tensor([1]))
    torch.testing.assert_close(view.inertias[0], before)
    torch.testing.assert_close(view.inertias[1], torch.diag(env.inertia_tensors[1]).reshape(9))
    assert view.calls[0].tolist() == [1]


@pytest.mark.parametrize('value', [0., -1., float('nan')])
def test_invalid_inertia_rejected_before_backend_write(value):
    env, view = runtime()
    env.inertia_tensors[1, 0] = value
    with pytest.raises(ValueError, match='inertia'):
        method('_sync_declared_inertias')(env, torch.tensor([1]))
    assert not view.calls


def test_silent_backend_failure_is_detected_by_readback():
    env, view = runtime(ignore_write=True)
    env.inertia_tensors[1] *= 1.3
    with pytest.raises(RuntimeError, match='inertia_readback'):
        method('_sync_declared_inertias')(env, torch.tensor([1]))


def test_sync_runs_after_reset_randomization_and_is_opt_in():
    tree = ast.parse(ENV.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'EasyUUVEnv')
    reset = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_reset_domain')
    assert ast.unparse(reset.body[-1]) == 'self._sync_declared_inertias(env_ids)'
    cfg = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'EasyUUVEnvCfg')
    assert "inertia_sync_mode = 'legacy'" in ast.unparse(cfg)

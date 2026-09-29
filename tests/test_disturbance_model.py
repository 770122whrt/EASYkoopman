"""Local contracts only; synthetic arrays are not Isaac performance evidence."""
import importlib
import numpy as np
import pytest
from control_fixtures import context, model
from control_fixtures import state
from koopman import lifted_state as lk
from koopman.physical_predictor import PhysicalPredictor


def api():
    assert importlib.util.find_spec('koopman.disturbance_model'), 'v86 full-latent interface missing'
    return importlib.import_module('koopman.disturbance_model')


def predictor(kind='koopman'):
    m = api(); d = len(lk.feature_names())
    A = np.eye(d); B = np.zeros((d, 12))
    A[4, -2] = .01; A[-2, -1] = .01
    R = np.zeros((10, d)); R[4, -2] = .02
    return m.LiftedPredictor(lk.PreparedLifted(A, B, context()),
        PhysicalPredictor(model(), context(), identified=True), kind=kind, residual=R)


@pytest.mark.parametrize('kind', ['koopman', 'hybrid'])
def test_forecast_has_private_latent_memory_and_never_relifts(monkeypatch, kind):
    m = api(); p = predictor(kind); x = state(); u = np.zeros((1, 6))
    advance = p.start_forecast(x, context())
    def forbidden(*args):
        raise AssertionError('relift inside horizon')
    monkeypatch.setattr(lk, 'lift', forbidden)
    y = advance(x, u, context()); y = advance(y, u, context())
    assert np.isfinite(y).all()
    assert y[0, 5] > 0
    with pytest.raises(ValueError, match='forecast_session_required'):
        p(x, u, context())


def test_repeated_origins_do_not_share_latent_memory():
    p = predictor();x = state();u = np.zeros((1, 6))
    a = p.start_forecast(x, context());b = p.start_forecast(x, context())
    first = a(x, u, context()); a(first, u, context())
    np.testing.assert_array_equal(b(x, u, context()), first)


@pytest.mark.parametrize('kind', ['koopman', 'hybrid'])
def test_symbolic_and_exact_command_rollouts_match(kind):
    pytest.importorskip('casadi')
    from koopman.symbolic_prediction import SymbolicPlant
    from koopman.command_state import CausalCommandState
    p = predictor(kind)
    live = CausalCommandState('base', context(), episode_id='v86', zero_rotor_reset_verified=True)
    origin = live.snapshot(configuration='base', context=context(), origin_control=0, episode_id='v86')
    commands = np.tile([0., .03, 0., .3], (3, 1)); x = state()[0]
    exact = origin.forecast(x, np.repeat(commands, 2, axis=0), p)
    symbolic = SymbolicPlant(p, 'base').forecast(origin, x, commands)
    assert exact['complete']
    np.testing.assert_allclose(exact['predictions'], symbolic['predictions'], atol=2e-7, rtol=1e-6)
    assert live.physics_index == 0


def test_fit_uses_only_explicit_training_rows_and_frozen_physics():
    m = api(); rng = np.random.default_rng(8601); x = state(80)
    x[:,5:] = rng.uniform(-.04,.04,(len(x),6));u = rng.uniform(-.02,.02,(len(x),6))
    physical = PhysicalPredictor(model(), context(), identified=True)
    original = physical.quadratic.copy();y = physical(x, u, context());y[:,5] -= .001*x[:,5]*abs(x[:,5])
    record = m.fit(x, y, u, context(), physical, ridge=.001)
    np.testing.assert_array_equal(original, physical.quadratic)
    assert record['lifted']['training_rows'] == 80
    assert record['audit']['latent_relift_inside_horizon'] is False
    p = m.prepare(record, context(), physical, kind='hybrid')
    assert np.isfinite(p.start_forecast(x[:1],context())(x[:1],u[:1],context())).all()
    record['residual'][0][0] += 1
    with pytest.raises(ValueError,match='hash'):m.prepare(record,context(),physical,kind='hybrid')


def test_hidden_drag_is_additive_and_does_not_mutate_mechanical_context():
    assert importlib.util.find_spec('easyuuv_nc.disturbance'), 'hidden drag hook missing'
    m = importlib.import_module('easyuuv_nc.disturbance')
    import torch
    force = torch.tensor([[-1., 2., -3.]])
    torque = torch.tensor([[.1, -.2, .3]])
    f, t = m.extra_quadratic_drag(force, torque, .2)
    torch.testing.assert_close(f, force*.2);torch.testing.assert_close(t, torque*.2)
    for bad in (-1, float('nan'), 2., True):
        with pytest.raises(ValueError):m.extra_quadratic_drag(force,torque,bad)


def test_real_dynamics_hook_adds_drag_without_mutating_nominal_terms():
    import ast
    from pathlib import Path
    from types import SimpleNamespace
    import torch
    path=Path(__file__).resolve().parents[1]/'easyuuv_nc/env/easyuuv_env.py'
    tree=ast.parse(path.read_text(encoding='utf8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='EasyUUVEnv')
    nodes=next(n.body for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_compute_dynamics')
    start=next(i for i,n in enumerate(nodes) if ast.unparse(n).startswith('forces = density_forces +'))
    end=next(i for i,n in enumerate(nodes) if isinstance(n,ast.If) and ast.unparse(n.test)=='self.boundary_models.any_enabled')
    force=torch.tensor([[-1.,2.,-3.]])
    values={k:force.clone() for k in ('density_forces','density_torques','buoyancy_forces','buoyancy_torques',
                                     'viscosity_forces','viscosity_torques','thruster_forces','thruster_torques')}
    env=SimpleNamespace(cfg=SimpleNamespace(hidden_quadratic_drag_fraction_v86=.2))
    values['self']=env;values['torch']=torch
    exec(compile(ast.Module(body=nodes[start:end],type_ignores=[]),str(path),'exec'),values)
    torch.testing.assert_close(values['forces'],4.2*force)
    torch.testing.assert_close(values['density_forces'],force)
    assert env._disturbance_audit_v86['fraction']==.2

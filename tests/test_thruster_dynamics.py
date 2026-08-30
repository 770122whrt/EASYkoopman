from __future__ import annotations

import importlib.util
import ast
import math
from pathlib import Path
import sys
import types

import pytest
import torch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "easyuuv_nc" / "env" / "thruster_dynamics.py"
ENV_PATH = PROJECT_ROOT / "easyuuv_nc" / "env" / "easyuuv_env.py"


@pytest.fixture
def dynamics_first_order(monkeypatch: pytest.MonkeyPatch):
    """Load the real dynamics module without importing the Isaac Lab environment."""

    compat = types.ModuleType("isaaclab_compat")
    compat.quat_from_euler_xyz = lambda *_args, **_kwargs: None
    monkeypatch.setitem(sys.modules, "isaaclab_compat", compat)

    module_name = "_easyuuv_thruster_dynamics_under_test"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module.DynamicsFirstOrder


def _new_dynamics(dynamics_first_order, *, num_envs=1, thrusters=1, tau=1.0):
    return dynamics_first_order(num_envs, thrusters, tau, torch.device("cpu"))


def _initialize_at_zero(dynamics, command):
    """Exercise the explicit dt=0 contract without creating a time origin."""
    initial = dynamics.update(command, torch.zeros(dynamics.numEnvs))
    torch.testing.assert_close(initial, torch.zeros_like(command))


def test_reset_establishes_zero_previous_end_time(dynamics_first_order):
    dynamics = _new_dynamics(dynamics_first_order, num_envs=2, tau=0.2)

    torch.testing.assert_close(dynamics.prevTime, torch.zeros(2))
    dynamics.update(torch.ones((2, 1)), torch.tensor([0.1, 0.1]))
    dynamics.reset(torch.tensor([1]))

    torch.testing.assert_close(dynamics.prevTime, torch.tensor([0.1, 0.0]))
    torch.testing.assert_close(dynamics.state[1], torch.zeros(1))


def test_first_physics_substep_receives_full_physics_dt(dynamics_first_order):
    tau = 0.1
    physics_dt = 1.0 / 120.0
    dynamics = _new_dynamics(dynamics_first_order, tau=tau)

    state = dynamics.update(torch.ones((1, 1)), torch.tensor([physics_dt]))

    expected = 1.0 - math.exp(-physics_dt / tau)
    torch.testing.assert_close(
        state,
        torch.tensor([[expected]], dtype=torch.float32),
        rtol=8 * torch.finfo(torch.float32).eps,
        atol=8 * torch.finfo(torch.float32).eps,
    )


def test_step_response_is_slower_for_larger_tau(dynamics_first_order):
    fast = _new_dynamics(dynamics_first_order, tau=0.1)
    slow = _new_dynamics(dynamics_first_order, tau=1.0)
    command = torch.ones((1, 1))
    _initialize_at_zero(fast, command)
    _initialize_at_zero(slow, command)

    fast_state = fast.update(command, torch.tensor([0.1]))
    slow_state = slow.update(command, torch.tensor([0.1]))

    assert 0.0 < slow_state.item() < fast_state.item() < 1.0


def test_zero_dt_holds_previous_actuator_state(dynamics_first_order):
    dynamics = _new_dynamics(dynamics_first_order, tau=0.2)
    _initialize_at_zero(dynamics, torch.zeros((1, 1)))
    previous = dynamics.update(torch.ones((1, 1)), torch.tensor([0.1])).clone()

    held = dynamics.update(torch.zeros((1, 1)), torch.tensor([0.1]))

    torch.testing.assert_close(held, previous)


def test_repeated_updates_match_analytic_first_order_response(dynamics_first_order):
    tau = 0.5
    dynamics = _new_dynamics(dynamics_first_order, tau=tau)
    command = torch.ones((1, 1))
    _initialize_at_zero(dynamics, command)

    for timestamp in (0.1, 0.2, 0.3):
        state = dynamics.update(command, torch.tensor([timestamp]))

    expected = 1.0 - math.exp(-0.3 / tau)
    torch.testing.assert_close(state, torch.tensor([[expected]]), rtol=1e-6, atol=1e-6)


def test_two_physics_substeps_use_physics_dt_not_one_repeated_control_time(
    dynamics_first_order,
):
    tau = 0.1
    physics_dt = 1.0 / 120.0
    dynamics = _new_dynamics(dynamics_first_order, tau=tau)
    command = torch.ones((1, 1))
    actuator_time = torch.zeros(1)

    actuator_time += physics_dt
    first = dynamics.update(command, actuator_time).clone()
    actuator_time += physics_dt
    second = dynamics.update(command, actuator_time).clone()

    torch.testing.assert_close(
        first,
        torch.tensor([[1.0 - math.exp(-physics_dt / tau)]]),
        rtol=8 * torch.finfo(torch.float32).eps,
        atol=8 * torch.finfo(torch.float32).eps,
    )
    torch.testing.assert_close(
        second,
        torch.tensor([[1.0 - math.exp(-(2.0 * physics_dt) / tau)]]),
        rtol=8 * torch.finfo(torch.float32).eps,
        atol=8 * torch.finfo(torch.float32).eps,
    )


def test_each_environment_can_use_a_different_tau(dynamics_first_order):
    dynamics = _new_dynamics(dynamics_first_order, num_envs=2, tau=1.0)
    dynamics.set_time_constants(torch.tensor([0, 1]), torch.tensor([0.1, 1.0]))
    command = torch.ones((2, 1))
    _initialize_at_zero(dynamics, command)

    state = dynamics.update(command, torch.tensor([0.1, 0.1]))

    assert state[0, 0] > state[1, 0]
    torch.testing.assert_close(
        state[:, 0],
        torch.tensor([1.0 - math.exp(-1.0), 1.0 - math.exp(-0.1)]),
        rtol=1e-6,
        atol=1e-6,
    )


def test_selected_reset_clears_episode_actuator_memory(dynamics_first_order):
    dynamics = _new_dynamics(dynamics_first_order, num_envs=2, tau=0.2)
    command = torch.ones((2, 1))
    _initialize_at_zero(dynamics, command)
    before_reset = dynamics.update(command, torch.tensor([0.1, 0.1])).clone()

    dynamics.reset(torch.tensor([0]))
    after_reset = dynamics.update(command, torch.tensor([0.1, 0.2]))

    torch.testing.assert_close(
        after_reset[0, 0],
        torch.tensor(1.0 - math.exp(-0.1 / 0.2)),
        rtol=1e-6,
        atol=1e-6,
    )
    assert after_reset[1, 0] > before_reset[1, 0]
    torch.testing.assert_close(
        after_reset[1, 0],
        torch.tensor(1.0 - math.exp(-0.2 / 0.2)),
        rtol=1e-6,
        atol=1e-6,
    )


@pytest.mark.parametrize("tau", [0.0, -0.1, float("nan"), float("inf")])
def test_constructor_rejects_non_positive_or_non_finite_tau(
    dynamics_first_order, tau
):
    with pytest.raises(ValueError, match="finite and strictly positive"):
        _new_dynamics(dynamics_first_order, tau=tau)


def test_set_time_constants_rejects_invalid_tau(dynamics_first_order):
    dynamics = _new_dynamics(dynamics_first_order, num_envs=2, tau=0.1)

    with pytest.raises(ValueError, match="finite and strictly positive"):
        dynamics.set_time_constants([1], [0.0])


def test_update_rejects_backward_time_and_shape_mismatch(dynamics_first_order):
    dynamics = _new_dynamics(dynamics_first_order, num_envs=2, thrusters=2, tau=0.1)
    command = torch.zeros((2, 2))
    _initialize_at_zero(dynamics, command)

    with pytest.raises(ValueError, match="monotonic"):
        dynamics.update(command, torch.tensor([0.1, -0.1]))
    with pytest.raises(ValueError, match="cmd must have shape"):
        dynamics.update(torch.zeros((2, 1)), torch.tensor([0.1, 0.1]))
    with pytest.raises(ValueError, match="t must have shape"):
        dynamics.update(command, torch.tensor([0.1]))


def test_update_preserves_state_dtype_and_rejects_mismatched_dtype(
    dynamics_first_order,
):
    dynamics = _new_dynamics(dynamics_first_order, tau=0.1)

    with pytest.raises(ValueError, match="cmd must use dtype"):
        dynamics.update(torch.ones((1, 1), dtype=torch.float64), torch.tensor([0.0]))

    state = dynamics.update(torch.ones((1, 1)), torch.tensor([0.0]))
    assert state.dtype == torch.float32
    assert state.device == dynamics.device


def test_source_has_no_forced_zero_alpha_path():
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "alpha = torch.zeros_like(alpha)" not in source


def _method_source(path: Path, class_name: str, method_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    return ast.get_source_segment(source, child) or ""
    raise AssertionError(f"{class_name}.{method_name} source not found")


def test_runtime_wires_thruster_lag_to_each_physics_substep():
    init_source = _method_source(ENV_PATH, "EasyUUVEnv", "_init_thruster_dynamics")
    dynamics_source = _method_source(ENV_PATH, "EasyUUVEnv", "_compute_dynamics")
    reset_source = _method_source(ENV_PATH, "EasyUUVEnv", "_reset_idx")

    assert "self._thruster_dynamics_time_s = torch.zeros" in init_source
    assert (
        "end_time_s = self._thruster_dynamics_time_s + float(self.sim.cfg.dt)"
        in dynamics_source
    )
    assert "self.thruster_dynamics.update(motorValues, end_time_s)" in dynamics_source
    assert "self._thruster_dynamics_time_s.copy_(end_time_s)" in dynamics_source
    assert "self.episode_length_buf * self.sim.cfg.dt" not in dynamics_source
    assert "self._thruster_dynamics_time_s[ids] = 0.0" in reset_source

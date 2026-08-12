"""Isaac-free contracts for Phase 7 runtime telemetry and Koopman Bridge v2."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import torch

from easyuuv_nc.embodiments import (
    EMBODIMENT_CONFIGS,
    SUPPORTED_EMBODIMENTS,
    qualification_record,
)
from easyuuv_nc.thrust_allocation import (
    ThrusterLayout,
    allocate,
    build_wrench_matrix,
    control_channels_to_wrench,
    dof_weight_vector,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / "easyuuv_nc" / "env" / "easyuuv_env.py"
ENV_SOURCE = ENV_PATH.read_text(encoding="utf-8")
ENV_TREE = ast.parse(ENV_SOURCE)


def _env_method_source(name: str) -> str:
    for node in ENV_TREE.body:
        if isinstance(node, ast.ClassDef) and node.name == "EasyUUVEnv":
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name == name:
                    return ast.get_source_segment(ENV_SOURCE, member) or ""
    raise AssertionError(f"EasyUUVEnv.{name} source not found")


def _allocation_for(configuration: str, control: torch.Tensor) -> torch.Tensor:
    config = EMBODIMENT_CONFIGS[configuration]
    allocation = config.get("thrust_allocation")
    if allocation is None:
        from easyuuv_nc.thrust_allocation import LEGACY_CONTROL_TO_MOTOR

        return torch.einsum("mc,...c->...m", LEGACY_CONTROL_TO_MOTOR, control)
    layout = ThrusterLayout.from_specs(allocation["specs"])
    wrench = control_channels_to_wrench(
        control * torch.tensor([-1.0, 1.0, -1.0, 1.0])
    )
    return allocate(
        build_wrench_matrix(layout),
        wrench,
        mode=str(allocation["mode"]),
        weight=dof_weight_vector(allocation.get("controllable_dofs")),
    )


@pytest.mark.parametrize("configuration", SUPPORTED_EMBODIMENTS)
def test_control_mask_and_allocation_shape_cover_exact_eight(configuration: str) -> None:
    record = qualification_record(configuration)
    mask = torch.tensor(record["control_mask"], dtype=torch.float32)
    assert mask.shape == (4,)
    assert tuple(mask.int().tolist()) == tuple(record["control_mask"])

    virtual_control = torch.tensor([[0.25, -0.2, 0.4, 0.3]]) * mask
    motor = _allocation_for(configuration, virtual_control)
    assert motor.shape == (1, record["thruster_count"])
    assert record["thruster_count"] in {8, 6, 4}
    assert record["declared_control_rank"] == sum(record["control_mask"])


@pytest.mark.parametrize("configuration", ("uuv4", "uuv4_angled"))
def test_uuv4_nonzero_raw_yaw_is_masked_before_tam(configuration: str) -> None:
    raw_pid_control = torch.tensor([[0.31, -0.23, 0.79, 0.37]])
    mask = torch.tensor(qualification_record(configuration)["control_mask"])
    virtual_control = raw_pid_control * mask

    assert raw_pid_control[0, 2] != 0.0
    assert virtual_control[0, 2].item() == 0.0
    torch.testing.assert_close(
        _allocation_for(configuration, raw_pid_control),
        _allocation_for(configuration, virtual_control),
        rtol=0.0,
        atol=1.0e-6,
    )


def test_runtime_telemetry_captures_raw_action_before_clip_or_overwrite() -> None:
    source = _env_method_source("_pre_physics_step")
    capture = "self._last_raw_action_4 = actions[:, :4].detach().clone()"
    overwrite = "self._actions[:] = actions"
    clip = "self._actions[:] = torch.clip(self._actions, -1, 1).to(self.device)"
    assert capture in source
    assert source.index(capture) < source.index(overwrite) < source.index(clip)


def test_runtime_control_mask_is_catalog_derived_and_feeds_tam() -> None:
    apply_source = _env_method_source("apply_embodiment_config")
    pid_source = _env_method_source("_pid_control")
    assert "qualification_record(embodiment_type)" in apply_source
    assert "self._control_mask_4" in apply_source
    assert "virtual_control = PID_value * self._control_mask_4" in pid_source
    assert "self._last_pid_value = PID_value.detach().clone()" in pid_source
    assert "self._last_virtual_control_4 = virtual_control.detach().clone()" in pid_source
    assert "cmd = virtual_control * self._alloc_channel_sign" in pid_source


def test_runtime_wrench_and_same_call_context_capture_points_are_ordered() -> None:
    source = _env_method_source("_compute_dynamics")
    efficiency = "self._last_thruster_efficiency_n = self.thruster_efficiency_factors.detach().clone()"
    force_sum = "thruster_forces = torch.sum(thruster_forces, dim=-2)"
    torque_sum = "thruster_torques = torch.sum(thruster_torques, dim=-2)"
    wrench = "self._last_applied_wrench_6 = torch.cat((thruster_forces, thruster_torques), dim=-1).detach().clone()"
    fluid_read = "fluid_vel_w = self.get_current_fluid_velocity()"
    fluid_cache = "self._last_fluid_velocity_w = fluid_vel_w.detach().clone()"
    environment_mix = "forces = density_forces + buoyancy_forces + viscosity_forces + thruster_forces"

    for statement in (efficiency, force_sum, torque_sum, wrench, fluid_read, fluid_cache, environment_mix):
        assert statement in source
    assert source.index(efficiency) < source.index(force_sum)
    assert source.index(force_sum) < source.index(wrench)
    assert source.index(torque_sum) < source.index(wrench)
    assert source.index(wrench) < source.index(environment_mix)
    assert source.index(fluid_read) < source.index(fluid_cache) < source.index(environment_mix)


def test_runtime_telemetry_snapshot_is_clone_only_and_tokenized() -> None:
    source = _env_method_source("get_koopman_telemetry_snapshot")
    for field in (
        "raw_action_4",
        "virtual_control_4",
        "motor_pwm_n",
        "applied_wrench_6",
        "fluid_velocity_world_3",
        "thruster_efficiency_n",
        "step_token",
        "valid",
    ):
        assert f'"{field}"' in source
    assert source.count(".detach().clone()") >= 6


def test_runtime_reset_invalidates_telemetry_and_step_token() -> None:
    source = _env_method_source("_reset_idx")
    assert "self._koopman_telemetry_valid[ids] = False" in source
    assert "self._koopman_telemetry_step_token[ids] = -1" in source
    assert "self._last_raw_action_4[ids] = 0.0" in source
    assert "self._last_applied_wrench_6[ids] = 0.0" in source


def test_runtime_token_advances_only_after_complete_telemetry() -> None:
    source = _env_method_source("_compute_dynamics")
    token = "self._koopman_telemetry_step_token += 1"
    valid = "self._koopman_telemetry_valid[:] = True"
    assert token in source and valid in source
    assert source.index("self._last_applied_wrench_6") < source.index(token)
    assert source.index("self._last_fluid_velocity_w") < source.index(token)
    assert source.index("self._last_thruster_efficiency_n") < source.index(token)
    assert source.index(token) < source.index(valid)
